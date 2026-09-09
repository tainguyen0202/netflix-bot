"""
Supabase sync layer for the Netflix bot.

Bot stays the source of truth (cookie.txt / user.json / orders.json /
plan_prices.json). This module pushes changes to Supabase so the web app
can read the same data, and periodically checks cookies to fill real
country / plan / email / status fields.

Design (Approach A):
  - In-memory FIFO queue for cookie changes (add / delete / dead).
  - sync_job: batch upsert cookies + users + orders + plan prices.
  - check_pool_job: walk the pool slowly, call check_cookie, update real
    country / plan / email / status into Supabase.
  - Offline-safe: if Supabase is down we keep the queue in RAM and retry
    on the next job tick. We never block the bot hot path.
"""

import asyncio
import datetime
import json
import logging
import re
import threading
import time

logger = logging.getLogger("NetflixBot")

try:
    from supabase import create_client, Client
except Exception:  # pragma: no cover
    create_client = None
    Client = None

from config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
    ADMIN_API_KEY,
)

# ── Client ──
_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not create_client or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    with _client_lock:
        if _client is None:
            try:
                _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            except Exception as e:
                logger.warning("Supabase client init failed: %s", e)
                _client = None
    return _client


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY and create_client)


def grant_plan_to_supabase(identifier, plan_name):
    """Cấp gói thẳng lên Supabase profile theo id hoặc email (không đụng user.json bot).

    Dùng cho admin web cấp gói cho user web (Supabase UID / email). Trả về profile dict
    đã cập nhật hoặc None nếu không tìm thấy / lỗi.
    """
    client = _get_client()
    if client is None:
        return None
    plan_name = (plan_name or "").lower()
    if plan_name not in ("basic", "pro"):
        return None
    identifier = str(identifier or "").strip()
    if not identifier:
        return None

    try:
        # Tìm profile theo id hoặc email.
        if "@" in identifier:
            rows = client.table("profiles").select("*").eq("email", identifier).limit(1).execute()
        else:
            rows = client.table("profiles").select("*").eq("id", identifier).limit(1).execute()
        data = rows.data or []
        if not data:
            return None
        profile = data[0]

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = (now + datetime.timedelta(days=30)).isoformat()
        quota = 20 if plan_name == "pro" else 10
        updated = {
            "plan": plan_name,
            "quota_limit": quota,
            "plan_expires_at": expires,
            "plan_started_at": profile.get("plan_started_at") or now.isoformat(),
            "updated_at": now.isoformat(),
        }
        res = (
            client.table("profiles")
            .update(updated)
            .eq("id", profile["id"])
            .execute()
        )
        return (res.data or [None])[0]
    except Exception as e:
        logger.warning("Supabase grant_plan_to_supabase failed: %s", e)
        return None


# ── Web orders (đơn hàng tạo từ web, chờ SePay xác nhận) ──

def _gen_order_code():
    import secrets
    return f"NF{secrets.token_hex(3).upper()}"


def create_web_order(user_id, email, plan_name):
    """Tạo đơn hàng pending trên Supabase cho user web (Google OAuth).

    Upsert profile nếu chưa có, rồi tạo order với order_code NFxxxxxx.
    Trả về dict order hoặc None nếu lỗi.
    """
    client = _get_client()
    if client is None:
        return None
    plan_name = (plan_name or "").lower()
    if plan_name not in ("basic", "pro"):
        return None
    user_id = str(user_id or "").strip()
    if not user_id:
        return None

    try:
        # Upsert profile (đảm bảo FK orders.user_id hợp lệ).
        now = datetime.datetime.now(datetime.timezone.utc)
        profile_payload = {
            "id": user_id,
            "email": (email or "").strip() or None,
            "plan": "free",
            "quota_limit": 0,
            "links_used_today": 0,
            "last_reset_date": now.strftime("%Y-%m-%d"),
            "updated_at": now.isoformat(),
        }
        client.table("profiles").upsert(profile_payload, on_conflict="id").execute()

        # Tìm đơn pending còn hạn của user + plan này (tránh spam tạo đơn).
        pending = (
            client.table("orders")
            .select("*")
            .eq("user_id", user_id)
            .eq("plan", plan_name)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = pending.data or []
        if rows:
            existing = rows[0]
            expires = existing.get("expires_at")
            if expires and datetime.datetime.fromisoformat(str(expires).replace("Z", "+00:00")) > now:
                return existing

        price_vnd = 10000 if plan_name == "basic" else 20000
        order_id = f"ord_{user_id[:8]}_{int(now.timestamp())}"
        order_code = _gen_order_code()
        expires_at = (now + datetime.timedelta(minutes=30)).isoformat()
        order_payload = {
            "id": order_id,
            "user_id": user_id,
            "provider": "sepay",
            "plan": plan_name,
            "amount_vnd": price_vnd,
            "amount_usdt": None,
            "order_code": order_code,
            "status": "pending",
            "transaction_id": None,
            "note": None,
            "created_at": now.isoformat(),
            "expires_at": expires_at,
            "paid_at": None,
            "approved_at": None,
            "rejected_at": None,
        }
        res = client.table("orders").upsert(order_payload, on_conflict="id").execute()
        return (res.data or [order_payload])[0]
    except Exception as e:
        logger.warning("Supabase create_web_order failed: %s", e)
        return None


def get_web_order_status(order_code):
    """Đọc trạng thái đơn hàng web theo order_code (NFxxxxxx)."""
    client = _get_client()
    if client is None:
        return None
    order_code = str(order_code or "").strip().upper()
    if not order_code:
        return None
    try:
        res = (
            client.table("orders")
            .select("*")
            .eq("order_code", order_code)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("Supabase get_web_order_status failed: %s", e)
        return None


def grant_web_order(order_code, transaction_id=None, transaction_note=None):
    """Cấp gói cho user web khi SePay xác nhận thanh toán.

    Tìm order theo order_code, nếu pending/paid thì cấp gói lên profile
    Supabase và cập nhật order thành approved. Trả về dict order hoặc None.
    """
    client = _get_client()
    if client is None:
        return None
    order_code = str(order_code or "").strip().upper()
    if not order_code:
        return None
    try:
        res = (
            client.table("orders")
            .select("*")
            .eq("order_code", order_code)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        order = rows[0]
        if order.get("status") not in ("pending", "paid"):
            return order

        plan_name = order.get("plan")
        user_id = order.get("user_id")
        now = datetime.datetime.now(datetime.timezone.utc)

        # Cấp gói lên profile.
        profile_res = (
            client.table("profiles")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        profile_rows = profile_res.data or []
        if not profile_rows:
            return None
        profile = profile_rows[0]
        current_exp = profile.get("plan_expires_at")
        start = now
        if current_exp:
            try:
                exp_dt = datetime.datetime.fromisoformat(str(current_exp).replace("Z", "+00:00"))
                if exp_dt > now:
                    start = exp_dt
            except Exception:
                pass
        expires = (start + datetime.timedelta(days=30)).isoformat()
        quota = 20 if plan_name == "pro" else 10
        client.table("profiles").update({
            "plan": plan_name,
            "quota_limit": quota,
            "plan_expires_at": expires,
            "plan_started_at": profile.get("plan_started_at") or now.isoformat(),
            "updated_at": now.isoformat(),
        }).eq("id", user_id).execute()

        # Cập nhật order thành approved.
        update = {
            "status": "approved",
            "paid_at": order.get("paid_at") or now.isoformat(),
            "approved_at": now.isoformat(),
        }
        if transaction_id:
            update["transaction_id"] = str(transaction_id)
        if transaction_note:
            update["note"] = str(transaction_note)
        client.table("orders").update(update).eq("id", order["id"]).execute()

        order.update(update)
        return order
    except Exception as e:
        logger.warning("Supabase grant_web_order failed: %s", e)
        return None


# ── Cookie change queue ──
_cookie_queue = []
_cookie_queue_lock = threading.Lock()


def enqueue_cookie_sync(action, raw_line, **fields):
    """Queue a cookie change. Never blocks / never raises."""
    global _cookie_queue
    if not raw_line:
        return
    item = {"action": action, "raw_line": raw_line}
    item.update(fields)
    with _cookie_queue_lock:
        _cookie_queue.append(item)
        if len(_cookie_queue) > 5000:
            _cookie_queue = _cookie_queue[-5000:]


def _drain_cookie_queue():
    with _cookie_queue_lock:
        items = list(_cookie_queue)
        _cookie_queue.clear()
    return items


# ── Cookie parsing helpers ──
def _extract_cookie_parts(raw_line):
    """Split a raw cookie line into NetflixId / SecureNetflixId / nfvdid."""
    parts = {}
    for m in re.finditer(r"(?:^|[;\s])(netflixid|securenetflixid|nfvdid)\s*=\s*[\"']?([^\s;\"'\n]+)[\"']?", raw_line or "", re.IGNORECASE):
        name = m.group(1).lower()
        value = m.group(2).strip().rstrip(";")
        if name == "netflixid":
            parts["netflix_id"] = value
        elif name == "securenetflixid":
            parts["secure_id"] = value
        elif name == "nfvdid":
            parts["nfvdid"] = value
    return parts


def _status_to_supabase(status):
    """Map check_cookie status to Supabase cookies.status."""
    if status == "LIVE":
        return "green"
    if status == "DEAD":
        return "dead"
    return "unknown"  # ERROR -> unknown, retry later


# ── Rải cookie chưa xác định quốc gia vào các nước ──

# Các nước phổ biến để rải cookie chưa có country_code (rải đều, không ưu tiên).
_RANDOM_COUNTRIES = [
    "VN", "US", "JP", "KR", "IN", "BR", "TR", "PH", "ID", "MX",
    "TH", "MY", "SG", "DE", "FR", "GB", "ES", "IT", "PL", "AR",
    "CL", "CO", "PE", "EG", "SA", "AE", "AU", "CA", "NL", "SE",
]


def assign_random_country_codes(limit=100):
    """Gán country_code ngẫu nhiên cho cookie chưa xác định (country_code='').

    Mục đích: rải cookie UN vào các nước để web hiển thị và mọi người click
    gen link. Khi check thật (check_pool_job / API check-cookie) sẽ cập nhật
    country_code thật hoặc xóa nếu DEAD.
    """
    client = _get_client()
    if client is None:
        return 0
    try:
        res = (
            client.table("cookies")
            .select("id")
            .eq("country_code", "")
            .limit(limit)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return 0
        import random
        import time
        count = 0
        for r in rows:
            client.table("cookies").update(
                {"country_code": random.choice(_RANDOM_COUNTRIES)}
            ).eq("id", r["id"]).execute()
            count += 1
            time.sleep(0.05)  # tránh quá tải / Gateway Timeout
        return count
    except Exception as e:
        logger.warning("Supabase assign_random_country_codes failed: %s", e)
        return 0


# ── Sync jobs ──
async def sync_job(context=None):
    """Push cookie queue + users + orders + plan prices to Supabase."""
    if not is_configured():
        return
    client = _get_client()
    if client is None:
        return

    # 1. Cookie queue (add / delete / dead)
    items = _drain_cookie_queue()
    if items:
        try:
            rows = []
            for it in items:
                if it["action"] == "delete":
                    # delete by raw_line
                    try:
                        client.table("cookies").delete().eq("raw_line", it["raw_line"]).execute()
                    except Exception as e:
                        logger.warning("Supabase cookie delete failed: %s", e)
                    continue
                row = {
                    "raw_line": it["raw_line"],
                    "status": it.get("status", "unknown"),
                    "country_code": it.get("country_code") or "",
                }
                if it.get("website_name"):
                    row["website_name"] = it["website_name"]
                if it.get("plan_name"):
                    row["plan_name"] = it["plan_name"]
                if it.get("email"):
                    row["email"] = it["email"]
                rows.append(row)
            if rows:
                client.table("cookies").upsert(rows, on_conflict="raw_line").execute()
        except Exception as e:
            logger.warning("Supabase cookie sync failed: %s", e)
            # Re-queue on failure (offline-safe)
            with _cookie_queue_lock:
                _cookie_queue = items + _cookie_queue

    # 2. Users -> profiles
    try:
        _sync_users(client)
    except Exception as e:
        logger.warning("Supabase users sync failed: %s", e)

    # 3. Orders
    try:
        _sync_orders(client)
    except Exception as e:
        logger.warning("Supabase orders sync failed: %s", e)

    # 4. Plan prices
    try:
        _sync_plan_prices(client)
    except Exception as e:
        logger.warning("Supabase plan sync failed: %s", e)


def _sync_users(client):
    from storage import get_all_user_ids, get_user

    ids = get_all_user_ids()
    if not ids:
        return
    rows = []
    for uid in ids:
        u = get_user(uid)
        rows.append({
            "id": str(uid),
            "telegram_id": int(uid),
            "email": u.get("email"),
            "full_name": u.get("first_name"),
            "username": u.get("username"),
            "plan": u.get("plan_name") or "free",
            "quota_limit": 0,
            "links_used_today": 0,
            "last_reset_date": None,
            "plan_expires_at": u.get("plan_expires_at"),
            "plan_started_at": u.get("plan_started_at"),
            "ref_code": None,
            "referred_by": str(u["referrer_id"]) if u.get("referrer_id") else None,
            "referrals": json.dumps(u.get("referrals") or []),
            "total_links_success": int(u.get("total_links_success", 0) or 0),
            "lang": u.get("lang"),
            "status": "active",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        })
    # upsert in batches of 100
    for i in range(0, len(rows), 100):
        client.table("profiles").upsert(rows[i:i + 100], on_conflict="id").execute()


def _sync_orders(client):
    from storage import list_orders

    orders = list_orders(limit=500)
    if not orders:
        return
    rows = []
    for o in orders:
        rows.append({
            "id": o["order_id"],
            "user_id": str(o["user_id"]),
            "provider": o.get("provider"),
            "plan": o.get("plan"),
            "amount_vnd": o.get("amount_vnd"),
            "amount_usdt": o.get("amount_usdt"),
            "order_code": o.get("order_code"),
            "status": o.get("status"),
            "transaction_id": o.get("transaction_id"),
            "note": o.get("transaction_note"),
            "created_at": o.get("created_at"),
            "expires_at": o.get("expires_at"),
            "paid_at": o.get("paid_at"),
            "approved_at": o.get("approved_at"),
            "rejected_at": None,
        })
    for i in range(0, len(rows), 100):
        client.table("orders").upsert(rows[i:i + 100], on_conflict="id").execute()


def _sync_plan_prices(client):
    from storage import get_plan_price_vnd, get_plan_price_usdt, get_plan_quota

    rows = []
    for plan in ("basic", "pro"):
        rows.append({
            "plan_name": plan,
            "price_vnd": get_plan_price_vnd(plan),
            "price_usdt": get_plan_price_usdt(plan),
            "quota_limit": get_plan_quota(plan),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        })
    client.table("plan_prices").upsert(rows, on_conflict="plan_name").execute()


async def check_pool_job(context=None):
    """Walk the cookie pool, check cookies concurrently, update real fields.

    - Processes a small batch per tick with light concurrency.
    - Rate-limit guard: small delay between batches.
    - Emergency break: stop entirely after repeated 429/403 to avoid IP ban.
    """
    from config import PAUSE_BUFFER

    if PAUSE_BUFFER:
        return

    if not is_configured():
        return
    client = _get_client()
    if client is None:
        return

    # Rải cookie chưa xác định quốc gia vào các nước (để web hiển thị + mọi người click).
    try:
        assign_random_country_codes(limit=100)
    except Exception as e:
        logger.warning("assign_random_country_codes failed: %s", e)

    from storage import get_all_cookies
    from checker import check_cookie

    cookies = get_all_cookies()
    if not cookies:
        return

    # Process a small batch per tick with light concurrency.
    batch_size = 40
    concurrency = 10
    start = int(getattr(check_pool_job, "_offset", 0))
    batch = cookies[start:start + batch_size]
    if not batch:
        check_pool_job._offset = 0
        return
    check_pool_job._offset = start + batch_size

    # Emergency break state (persisted on the function object)
    throttle_count = int(getattr(check_pool_job, "_throttle", 0))

    async def _check_one(raw):
        nonlocal throttle_count
        parts = _extract_cookie_parts(raw)
        if not parts.get("netflix_id"):
            return None
        try:
            info = await asyncio.to_thread(
                check_cookie,
                parts["netflix_id"],
                parts.get("secure_id"),
            )
        except Exception as e:
            logger.warning("check_pool check failed: %s", e)
            return None

        status = info.get("status")
        # Track throttling for emergency break
        if status == "ERROR" and ("429" in str(info.get("error", "")) or "403" in str(info.get("error", ""))):
            throttle_count += 1
            if throttle_count >= 3:
                logger.warning("check_pool EMERGENCY BREAK: 3 consecutive 429/403. Stopping to avoid IP ban.")
                check_pool_job._throttle = throttle_count
                raise _EmergencyBreak()
        else:
            throttle_count = 0

        # Xóa cookie DEAD khỏi pool + file ngay (giữ pool gọn dần).
        if status == "DEAD":
            try:
                from storage import delete_cookie_by_raw
                if delete_cookie_by_raw(raw):
                    logger.info("check_pool deleted dead cookie")
            except Exception as e:
                logger.warning("check_pool delete dead failed: %s", e)
            return None

        row = {
            "raw_line": raw,
            "status": _status_to_supabase(status),
            "country_code": "",
            "last_checked_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        }
        country = info.get("country")
        if country and len(country) == 2:
            row["country_code"] = country.upper()
        if info.get("plan"):
            row["plan_name"] = str(info["plan"])
        if info.get("email"):
            row["email"] = info["email"]
        return row

    class _EmergencyBreak(Exception):
        pass

    rows = []
    try:
        # Run in small concurrent chunks
        for i in range(0, len(batch), concurrency):
            chunk = batch[i:i + concurrency]
            results = await asyncio.gather(*[_check_one(raw) for raw in chunk])
            rows.extend([r for r in results if r])
    except _EmergencyBreak:
        # Stop processing; keep offset so we resume after the throttle window
        check_pool_job._offset = max(0, start - batch_size)
        return

    check_pool_job._throttle = throttle_count

    if rows:
        try:
            client.table("cookies").upsert(rows, on_conflict="raw_line").execute()
        except Exception as e:
            logger.warning("Supabase check_pool upsert failed: %s", e)
