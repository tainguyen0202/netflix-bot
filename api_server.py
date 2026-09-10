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
import hmac
import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

from config import ADMIN_API_KEY, SEPAY_WEBHOOK_HOST, SEPAY_WEBHOOK_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY

logger = logging.getLogger("NetflixBot")

_server = None
_bot = None
_rate = {}  # ip -> [timestamps]
_RATE_LIMIT = 60  # requests per minute per IP (raised for bulk admin import)
_RATE_WINDOW = 60
_RATE_LIMITS = {
    # path_prefix -> (limit, window_seconds)
    "/api/order/create": (5, 15 * 60),       # chống spam tạo đơn (5 lần/15 phút)
    "/api/order/status": (30, 60),           # poll trạng thái đơn
    "/api/admin": (20, 60),                  # admin API chặt hơn
    "/api/check-cookie": (60, 60),
    "/api/batch-check": (60, 60),
    "/api/combo-check": (60, 60),
    "/api/sepay/process": (120, 60),         # webhook SePay có thể gọi nhiều
}
_MAX_BATCH_CHECK = 100  # giới hạn số cookie/lần check (tránh quá tải bot + chặn IP)
_MAX_BODY_SIZE = 1_000_000  # 1MB — từ chối payload quá lớn
_MAX_COOKIE_LEN = 5000      # độ dài tối đa 1 dòng cookie
_MAX_IMPORT_COOKIES = 5000  # số cookie tối đa/lần import
_MAX_COMBO_CHECK = 100      # số combo tối đa/lần check


def _secure_compare(a, b):
    """So sánh chuỗi constant-time (chống timing attack)."""
    try:
        return hmac.compare_digest(str(a or ""), str(b or ""))
    except Exception:
        return False


def _is_valid_email(email):
    """Validate email đơn giản (không cần regex phức tạp)."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if len(email) > 254 or "@" not in email:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and " " not in email


def _clean_cookie_line(line):
    """Làm sạch 1 dòng cookie: strip, bỏ control chars, giới hạn độ dài."""
    if not isinstance(line, str):
        return ""
    line = line.strip()
    # Bỏ control characters (chống newline injection vào file)
    line = "".join(ch for ch in line if ch >= " " or ch == "\t")
    if len(line) > _MAX_COOKIE_LEN:
        return ""
    return line


def _verify_supabase_user(handler):
    """Verify Supabase JWT từ header Authorization. Trả về (user_id, email) hoặc (None, None)."""
    import urllib.request
    import urllib.error

    auth = handler.headers.get("Authorization", "")
    m = re.match(r"^Bearer\s+(.+)$", auth or "", re.IGNORECASE)
    if not m or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None, None
    jwt = m.group(1).strip()
    if not jwt:
        return None, None
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {jwt}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
        uid = str(data.get("id") or "").strip()
        email = str(data.get("email") or "").strip()
        if not uid:
            return None, None
        return uid, email
    except Exception as e:
        logger.warning("[API] verify_supabase_user failed: %s", e)
        return None, None


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


def _rate_limited(ip, path=""):
    limit, window = _RATE_LIMIT, _RATE_WINDOW
    bucket = "default"
    for prefix, (l, w) in _RATE_LIMITS.items():
        if path.startswith(prefix):
            limit, window = l, w
            bucket = prefix
            break
    now = time.time()
    with threading.Lock():
        key = f"{ip}|{bucket}"
        ts = _rate.get(key, [])
        ts = [t for t in ts if now - t < window]
        if len(ts) >= limit:
            _rate[key] = ts
            return True
        ts.append(now)
        _rate[key] = ts
    return False


def _parse_cookie_parts(raw_line):
    """Parse cookie string bằng cùng parser checker.py (hỗ trợ raw value, pipe, JSON)."""
    from checker import parse_cookie_line
    netflix_id, secure_id, extras = parse_cookie_line(raw_line or "")
    parts = {}
    if netflix_id:
        parts["NetflixId"] = netflix_id
    if secure_id:
        parts["SecureNetflixId"] = secure_id
    if extras:
        parts.update(extras)
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
    elif status == "LIVE":
        # Cookie LIVE mới (dán từ checker) → âm thầm thêm vào pool chung
        # (cookie.txt bot + Supabase) để bot + web dùng chung 1 pool.
        try:
            from storage import add_cookies, _extract_netflix_id, _cookies
            cid = _extract_netflix_id(cookie_line)
            exists = any(_extract_netflix_id(c) == cid for c in _cookies)
            if cid and not exists:
                add_cookies([cookie_line], website_name="Netflix", status="green")
                logger.info("[API] added live cookie to shared pool")
        except Exception as e:
            logger.warning("[API] add live cookie to pool failed: %s", e)

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
    return _secure_compare(auth, f"Bearer {ADMIN_API_KEY}")


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
        from storage import get_plan_quota, get_plan_daily_used
        users = []
        for uid in get_all_user_ids():
            u = get_user(uid)
            plan_name = u.get("plan_name") or "free"
            daily_used = get_plan_daily_used(uid)
            users.append({
                "id": str(uid),
                "username": u.get("username"),
                "first_name": u.get("first_name"),
                "email": u.get("email") or f"{u.get('username') or uid}@telegram.bot",
                "full_name": u.get("first_name") or u.get("username") or f"User {uid}",
                "plan": plan_name,
                "quota_limit": get_plan_quota(plan_name),
                "links_used_today": daily_used,
                "plan_expires_at": u.get("plan_expires_at"),
                "total_links_success": u.get("total_links_success", 0),
                "status": "active",
                "lang": u.get("lang"),
            })
        _json_response(handler, 200, {"success": True, "users": users})
        return

    # Cấp gói thẳng lên Supabase profile (user web theo id/email, không đụng user.json bot).
    if method == "POST" and path == "/api/admin/user/grant":
        from supabase_sync import grant_plan_to_supabase

        identifier = str((body or {}).get("user_id") or (body or {}).get("email") or "").strip()
        plan = str((body or {}).get("plan", "basic") or "").strip().lower()
        if not identifier or len(identifier) > 200:
            _json_response(handler, 400, {"success": False, "error": "Invalid user_id or email"})
            return
        if plan not in ("basic", "pro"):
            _json_response(handler, 400, {"success": False, "error": "Invalid plan"})
            return
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
            plan = str(data.get("plan", "basic") or "").strip().lower()
            if plan not in ("basic", "pro"):
                _json_response(handler, 400, {"success": False, "error": "Invalid plan"})
                return
            grant_plan(uid, plan, approved_by=0, source="manual")
            _json_response(handler, 200, {"success": True})
        elif action == "remove":
            remove_plan(uid)
            _json_response(handler, 200, {"success": True})
        elif action == "bonus":
            try:
                amount = int(data.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0
            if amount < 0 or amount > 1_000_000:
                _json_response(handler, 400, {"success": False, "error": "Invalid amount"})
                return
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
        plan = str(data.get("plan") or "").strip().lower()
        if plan in ("basic", "pro"):
            try:
                price_vnd = int(data.get("price_vnd") or 0)
                quota = int(data.get("quota") or 0)
            except (TypeError, ValueError):
                _json_response(handler, 400, {"success": False, "error": "Invalid price or quota"})
                return
            if price_vnd < 0 or quota < 0 or quota > 1000:
                _json_response(handler, 400, {"success": False, "error": "Invalid price or quota"})
                return
            set_plan_price(
                plan,
                price_vnd,
                data.get("price_usdt"),
                quota,
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
        if not isinstance(lines, list):
            _json_response(handler, 400, {"success": False, "error": "cookies must be an array"})
            return
        lines = [_clean_cookie_line(l) for l in lines]
        lines = [l for l in lines if l]
        if len(lines) > _MAX_IMPORT_COOKIES:
            lines = lines[:_MAX_IMPORT_COOKIES]
        website_name = str((data.get("website_name") or "Netflix")).strip()[:50] or "Netflix"
        status = str((data.get("status") or "unknown")).strip()[:20] or "unknown"
        res = add_cookies(lines, website_name=website_name, status=status)
        _json_response(handler, 200, {"success": True, "result": res})
        return

    _json_response(handler, 404, {"success": False, "error": "Not found"})


def self_path_query(handler):
    """Trả về phần query string của request path."""
    return handler.path.split("?", 1)[1] if "?" in handler.path else ""


def _handle_tools(handler, method, path, body):
    # SePay webhook (forward từ Vercel) - xác thực bằng API key SePay.
    if method == "POST" and path == "/api/sepay/process":
        from sepay_webhook import process_sepay_payload

        auth = handler.headers.get("Authorization", "")
        if not _secure_compare(auth, f"Apikey {SEPAY_WEBHOOK_API_KEY}"):
            _json_response(handler, 401, {"success": False})
            return
        status, resp = process_sepay_payload(body or {}, _bot)
        _json_response(handler, status, resp)
        return

    # Tạo đơn hàng web (chờ SePay xác nhận) - yêu cầu Supabase JWT.
    # Danh tính lấy từ JWT đã verify, không tin user_id trong body.
    if method == "POST" and path == "/api/order/create":
        from supabase_sync import create_web_order

        verified_uid, verified_email = _verify_supabase_user(handler)
        if not verified_uid:
            _json_response(handler, 401, {"success": False, "error": "Unauthorized"})
            return
        user_id = verified_uid
        email = verified_email
        plan = str((body or {}).get("plan", "basic") or "").strip().lower()
        if email and not _is_valid_email(email):
            _json_response(handler, 400, {"success": False, "error": "Invalid email"})
            return
        if plan not in ("basic", "pro"):
            _json_response(handler, 400, {"success": False, "error": "Invalid plan"})
            return
        order = create_web_order(user_id, email, plan)
        if order:
            _json_response(handler, 200, {
                "success": True,
                "order": {
                    "order_code": order.get("order_code"),
                    "plan": order.get("plan"),
                    "amount_vnd": order.get("amount_vnd"),
                    "status": order.get("status"),
                    "expires_at": order.get("expires_at"),
                },
            })
        else:
            _json_response(handler, 400, {"success": False, "error": "Không thể tạo đơn hàng"})
        return

    # Kiểm tra trạng thái đơn hàng web - public.
    if method == "GET" and path == "/api/order/status":
        from urllib.parse import parse_qs
        from supabase_sync import get_web_order_status

        qs = parse_qs(self_path_query(handler))
        order_code = (qs.get("order_code") or [""])[0]
        if not order_code or len(order_code) > 50:
            _json_response(handler, 400, {"success": False, "error": "Invalid order_code"})
            return
        order = get_web_order_status(order_code)
        if order:
            _json_response(handler, 200, {
                "success": True,
                "order": {
                    "order_code": order.get("order_code"),
                    "plan": order.get("plan"),
                    "amount_vnd": order.get("amount_vnd"),
                    "status": order.get("status"),
                    "transaction_id": order.get("transaction_id"),
                    "approved_at": order.get("approved_at"),
                },
            })
        else:
            _json_response(handler, 404, {"success": False, "error": "Không tìm thấy đơn hàng"})
        return

    if method == "POST" and path == "/api/check-cookie":
        cookie = _clean_cookie_line((body or {}).get("cookie", ""))
        if not cookie:
            _json_response(handler, 400, {"success": False, "error": "Missing or invalid cookie"})
            return
        result = _check_and_link(cookie)
        _json_response(handler, 200, {"success": True, "result": result})
        return

    if method == "POST" and path == "/api/batch-check":
        cookies = (body or {}).get("cookies") or []
        if not isinstance(cookies, list):
            _json_response(handler, 400, {"success": False, "error": "cookies must be an array"})
            return
        cookies = [_clean_cookie_line(c) for c in cookies]
        cookies = [c for c in cookies if c]
        if len(cookies) > _MAX_BATCH_CHECK:
            cookies = cookies[:_MAX_BATCH_CHECK]
        results = [_check_and_link(c) for c in cookies]
        _json_response(handler, 200, {"success": True, "results": results})
        return

    if method == "POST" and path == "/api/combo-check":
        combos = (body or {}).get("combos") or []
        if not isinstance(combos, list):
            _json_response(handler, 400, {"success": False, "error": "combos must be an array"})
            return
        if len(combos) > _MAX_COMBO_CHECK:
            combos = combos[:_MAX_COMBO_CHECK]
        results = []
        for combo in combos:
            if not isinstance(combo, str) or len(combo) > _MAX_COOKIE_LEN:
                continue
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


def start_api_server(bot=None):
    global _server, _bot
    if _server is not None:
        return _server
    _bot = bot

    class ApiHandler(BaseHTTPRequestHandler):
        def _handle(self):
            ip = self.client_address[0]
            path = self.path.split("?")[0]
            if _rate_limited(ip, path):
                _json_response(self, 429, {"success": False, "error": "Rate limited"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            # Từ chối payload quá lớn (chống DoS qua body khổng lồ)
            if length > _MAX_BODY_SIZE:
                _json_response(self, 413, {"success": False, "error": "Payload too large"})
                return
            raw = self.rfile.read(length or 0)
            body = {}
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    _json_response(self, 400, {"success": False, "error": "Invalid JSON body"})
                    return
                if not isinstance(body, dict):
                    _json_response(self, 400, {"success": False, "error": "Body must be a JSON object"})
                    return
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
