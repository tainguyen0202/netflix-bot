"""
HTTP API server for the web app.

Exposes the bot's real Netflix logic (check cookie, generate NFToken,
3-device login links) plus admin operations, so the web app can call it
through a Vercel serverless proxy (avoids mixed-content + hides the bot IP).

Endpoints:
  POST /api/check-cookie   {cookie} -> {status, country, plan, email, links, expires}
  POST /api/batch-check    {cookies: []} -> {results: []}
  POST /api/combo-check    {combos: []} -> {results: []}
  Admin (Authorization: Bearer <ADMIN_API_KEY>):
    GET  /api/admin/stats
    GET  /api/admin/users
    POST /api/admin/user/{id}/grant|remove|bonus
    GET  /api/admin/orders
    POST /api/admin/order/{id}/approve|reject
    GET  /api/admin/plan
    POST /api/admin/plan
    POST /api/admin/cookies/import
"""

import asyncio
import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from config import ADMIN_API_KEY, SEPAY_WEBHOOK_HOST

logger = logging.getLogger("NetflixBot")

_server = None
_rate = {}  # ip -> [timestamps]
_RATE_LIMIT = 60  # requests per minute per IP (raised for bulk admin import)
_RATE_WINDOW = 60


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _json_response(handler, status, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.end_headers()
    handler.wfile.write(raw)


def _rate_limited(ip):
    now = time.time()
    with threading.Lock():
        ts = _rate.get(ip, [])
        ts = [t for t in ts if now - t < _RATE_WINDOW]
        if len(ts) >= _RATE_LIMIT:
            _rate[ip] = ts
            return True
        ts.append(now)
        _rate[ip] = ts
    return False


def _parse_cookie_parts(raw_line):
    parts = {}
    for m in re.finditer(
        r"(?:^|[;\s])(netflixid|securenetflixid|nfvdid)\s*=\s*[\"']?([^\s;\"'\n]+)[\"']?",
        raw_line or "",
        re.IGNORECASE,
    ):
        name = m.group(1).lower()
        value = m.group(2).strip().rstrip(";")
        if name == "netflixid":
            parts["NetflixId"] = value
        elif name == "securenetflixid":
            parts["SecureNetflixId"] = value
        elif name == "nfvdid":
            parts["nfvdid"] = value
    return parts


def _build_device_links(token):
    """Build 3-device login links from an NFToken (same as bot)."""
    if not token:
        return {}
    if "+" in token or "/" in token:
        try:
            token = quote(token, safe="")
        except Exception:
            pass
    return {
        "pc": f"https://netflix.com/?nftoken={token}",
        "phone": f"https://netflix.com/unsupported?nftoken={token}",
        "tv": f"https://netflix.com/tv2?nftoken={token}",
        "login": f"https://www.netflix.com/login?nftoken={token}",
    }


def _check_and_link(cookie_line):
    """Check a cookie and generate a real NFToken + 3-device links."""
    from checker import check_cookie, generate_nftoken
    from supabase_sync import enqueue_cookie_sync

    parts = _parse_cookie_parts(cookie_line)
    if not parts.get("NetflixId"):
        return {"status": "ERROR", "error": "Missing NetflixId"}

    info = check_cookie(parts["NetflixId"], parts.get("SecureNetflixId"))
    status = info.get("status")

    # Cookie DEAD → xóa khỏi pool + file ngay (giữ pool gọn dần).
    if status == "DEAD":
        try:
            from storage import delete_cookie_by_raw
            if delete_cookie_by_raw(cookie_line):
                logger.info("[API] deleted dead cookie")
        except Exception as e:
            logger.warning("[API] delete dead cookie failed: %s", e)

    # Upsert the real check result to Supabase (on-demand sync) so the web
    # map reflects accurate status/country/plan as users use the tools.
    try:
        fields = {
            "status": "green" if status == "LIVE" else ("dead" if status == "DEAD" else "unknown"),
            "website_name": "Netflix",
            "last_checked_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        }
        country = info.get("country")
        if country and len(country) == 2:
            fields["country_code"] = country.upper()
        if info.get("plan"):
            fields["plan_name"] = str(info["plan"])
        if info.get("email"):
            fields["email"] = str(info["email"])
        enqueue_cookie_sync("upsert", cookie_line, **fields)
    except Exception:
        pass

    result = {
        "status": status,
        "country": info.get("country"),
        "plan": info.get("plan"),
        "email": info.get("email"),
        "membershipStatus": info.get("membershipStatus"),
    }

    if status == "LIVE":
        token, err = generate_nftoken(parts)
        if token:
            result["token"] = token
            result["links"] = _build_device_links(token)
            result["expires"] = "60 phút"
        else:
            result["tokenError"] = err
    return result


def _admin_authorized(handler):
    auth = handler.headers.get("Authorization", "")
    if not ADMIN_API_KEY:
        return False
    return auth == f"Bearer {ADMIN_API_KEY}"


def _handle_admin(handler, method, path, body):
    from storage import (
        get_bot_stats,
        get_all_user_ids,
        get_user,
        grant_plan,
        remove_plan,
        add_manual_nogate_bonus,
        list_orders,
        approve_order,
        reject_order,
        get_plan_price_vnd,
        get_plan_price_usdt,
        get_plan_quota,
        set_plan_price,
        add_cookies,
    )

    if not _admin_authorized(handler):
        _json_response(handler, 401, {"success": False, "error": "Unauthorized"})
        return

    # Stats
    if method == "GET" and path == "/api/admin/stats":
        _json_response(handler, 200, {"success": True, "stats": get_bot_stats()})
        return

    # Users
    if method == "GET" and path == "/api/admin/users":
        users = []
        for uid in get_all_user_ids():
            u = get_user(uid)
            users.append({
                "id": str(uid),
                "username": u.get("username"),
                "first_name": u.get("first_name"),
                "plan": u.get("plan_name") or "free",
                "plan_expires_at": u.get("plan_expires_at"),
                "total_links_success": u.get("total_links_success", 0),
                "lang": u.get("lang"),
            })
        _json_response(handler, 200, {"success": True, "users": users})
        return

    # Cấp gói thẳng lên Supabase profile (user web theo id/email, không đụng user.json bot).
    if method == "POST" and path == "/api/admin/user/grant":
        from supabase_sync import grant_plan_to_supabase

        identifier = (body or {}).get("user_id") or (body or {}).get("email")
        plan = (body or {}).get("plan", "basic")
        profile = grant_plan_to_supabase(identifier, plan)
        if profile:
            _json_response(handler, 200, {"success": True, "profile": profile})
        else:
            _json_response(handler, 404, {"success": False, "error": "User not found or grant failed"})
        return

    m = re.match(r"^/api/admin/user/(\d+)/(grant|remove|bonus)$", path)
    if method == "POST" and m:
        uid = int(m.group(1))
        action = m.group(2)
        data = body or {}
        if action == "grant":
            plan = data.get("plan", "basic")
            grant_plan(uid, plan, approved_by=0, source="manual")
            _json_response(handler, 200, {"success": True})
        elif action == "remove":
            remove_plan(uid)
            _json_response(handler, 200, {"success": True})
        elif action == "bonus":
            amount = int(data.get("amount", 0) or 0)
            add_manual_nogate_bonus(uid, amount)
            _json_response(handler, 200, {"success": True})
        return

    # Orders
    if method == "GET" and path == "/api/admin/orders":
        orders = list_orders(limit=200)
        _json_response(handler, 200, {"success": True, "orders": orders})
        return

    m = re.match(r"^/api/admin/order/([^/]+)/(approve|reject)$", path)
    if method == "POST" and m:
        order_id = m.group(1)
        action = m.group(2)
        if action == "approve":
            approve_order(order_id, admin_id=0)
        else:
            reject_order(order_id, admin_id=0, reason="Rejected via web")
        _json_response(handler, 200, {"success": True})
        return

    # Plan prices
    if method == "GET" and path == "/api/admin/plan":
        _json_response(handler, 200, {
            "success": True,
            "plan": {
                "basic": {
                    "price_vnd": get_plan_price_vnd("basic"),
                    "price_usdt": get_plan_price_usdt("basic"),
                    "quota": get_plan_quota("basic"),
                },
                "pro": {
                    "price_vnd": get_plan_price_vnd("pro"),
                    "price_usdt": get_plan_price_usdt("pro"),
                    "quota": get_plan_quota("pro"),
                },
            },
        })
        return

    if method == "POST" and path == "/api/admin/plan":
        data = body or {}
        plan = data.get("plan")
        if plan in ("basic", "pro"):
            set_plan_price(
                plan,
                data.get("price_vnd"),
                data.get("price_usdt"),
                data.get("quota"),
            )
            _json_response(handler, 200, {"success": True})
        else:
            _json_response(handler, 400, {"success": False, "error": "Invalid plan"})
        return

    # Cookie import
    if method == "POST" and path == "/api/admin/cookies/import":
        data = body or {}
        lines = data.get("cookies") or []
        if isinstance(lines, str):
            lines = [l for l in lines.splitlines() if l.strip()]
        website_name = (data.get("website_name") or "Netflix").strip() or "Netflix"
        status = (data.get("status") or "unknown").strip() or "unknown"
        res = add_cookies(lines, website_name=website_name, status=status)
        _json_response(handler, 200, {"success": True, "result": res})
        return

    _json_response(handler, 404, {"success": False, "error": "Not found"})


def _handle_tools(handler, method, path, body):
    if method == "POST" and path == "/api/check-cookie":
        cookie = (body or {}).get("cookie", "")
        result = _check_and_link(cookie)
        _json_response(handler, 200, {"success": True, "result": result})
        return

    if method == "POST" and path == "/api/batch-check":
        cookies = (body or {}).get("cookies") or []
        results = [_check_and_link(c) for c in cookies]
        _json_response(handler, 200, {"success": True, "results": results})
        return

    if method == "POST" and path == "/api/combo-check":
        combos = (body or {}).get("combos") or []
        results = []
        for combo in combos:
            # format: user:pass:cookie  or  user:pass|cookie
            parts = combo.split(":", 2)
            if len(parts) == 3:
                user, pw, cookie = parts
            else:
                user, pw, cookie = combo.split("|", 2) if "|" in combo else (combo, "", "")
            res = _check_and_link(cookie)
            res["user"] = user
            results.append(res)
        _json_response(handler, 200, {"success": True, "results": results})
        return

    _json_response(handler, 404, {"success": False, "error": "Not found"})


def start_api_server():
    global _server
    if _server is not None:
        return _server

    class ApiHandler(BaseHTTPRequestHandler):
        def _handle(self):
            ip = self.client_address[0]
            if _rate_limited(ip):
                _json_response(self, 429, {"success": False, "error": "Rate limited"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length or 0)
            body = {}
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    body = {}
            path = self.path.split("?")[0]
            if path.startswith("/api/admin"):
                _handle_admin(self, self.command, path, body)
            elif path.startswith("/api/"):
                _handle_tools(self, self.command, path, body)
            else:
                _json_response(self, 404, {"success": False, "error": "Not found"})

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def log_message(self, fmt, *args):
            logger.info("[API] " + fmt, *args)

    _server = ReusableThreadingHTTPServer((SEPAY_WEBHOOK_HOST, 8081), ApiHandler)
    thread = threading.Thread(target=_server.serve_forever, daemon=True, name="api-server")
    thread.start()
    logger.info("[API] Listening at http://%s:8081", SEPAY_WEBHOOK_HOST)
    return _server
