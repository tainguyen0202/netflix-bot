"""
Storage -- cookie pool, users, plans, referrals, and payment orders.
"""

import os
import json
import random
import re
import secrets
import threading
import logging
import time
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from config import (
    COOKIE_FILE,
    USER_FILE,
    GIFT_CODE_FILE,
    ORDER_FILE,
    PLAN_PRICE_FILE,
    REF_FREE_PER_REF,
    REF_DAILY_CAP,
    BASE_DIR,
    ADMIN_IDS,
    SHRINKME_GATE_TTL,
    PLAN_DURATION_DAYS,
    PLAN_BASIC_DAILY,
    PLAN_PRO_DAILY,
    PLAN_BASIC_PRICE_VND,
    PLAN_PRO_PRICE_VND,
    PLAN_BASIC_PRICE_USDT,
    PLAN_PRO_PRICE_USDT,
    SEPAY_ORDER_TTL_MINUTES,
    BINANCE_ORDER_TTL_MINUTES,
    SHRINKME_API_KEY,
)

logger = logging.getLogger("NetflixBot")

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh") if ZoneInfo else timezone(timedelta(hours=7))
UTC_TZ = timezone.utc

_lock = threading.RLock()

# ── Single cookie pool ──
_cookies = []
_dead_set = set()
_dead_times = {}
_permanent_dead_set = set()
_inflight_set = set()

_users = {}
_gift_codes = {}
_orders = {}
_plan_prices = {}

# ── Link buffer (RAM, TTL 30 min, chỉ chứa link đã validate) ──
_link_buffer = []  # list[dict] {"link", "payload", "created", "validated"}
LINK_BUFFER_TTL = 30 * 60
LINK_BUFFER_MAX = 20

# ── Known-good / blocked cookie learning ──
_nftoken_good = {}    # idx -> last_success_ts
_nftoken_blocked = {}  # idx -> blocked_until_ts

# ── Shrinkme gate tokens (RAM, TTL SHRINKME_GATE_TTL, single-use, bind user_id) ──
_shrinkme_pending = {}  # token -> {"user_id": int, "created": float}

# ── Save debounce: gom nhiều thay đổi thành 1 lần ghi user.json ──
_save_dirty = False
_save_timer = None
SAVE_DEBOUNCE_SECONDS = 3

COOKIE_RETRY_WAIT = 3600
COOKIE_PERMANENT_DEAD_AFTER = 86400


def _ensure_user_shape(user, user_id):
    """Backfill missing keys for old records."""
    changed = False
    defaults = {
        "user_id": user_id,
        "username": None,
        "first_name": None,
        "lang": None,
        "referrer_id": None,
        "referrals": [],
        "ref_daily": {},
        "last_active": None,
        "total_links_success": 0,
        "total_gated_success": 0,
        "total_ref_nogate_success": 0,
        "total_basic_success": 0,
        "total_pro_success": 0,
        "total_manual_bonus_success": 0,
        "gated_success_daily": {},
        "ref_nogate_success_daily": {},
        "basic_success_daily": {},
        "pro_success_daily": {},
        "manual_bonus_success_daily": {},
        "first_get": None,
        "plan_name": None,
        "plan_started_at": None,
        "plan_expires_at": None,
        "plan_daily_used": {},
        "ref_nogate_used_daily": {},
        "manual_nogate_daily": {},
        "manual_nogate_used_daily": {},
    }
    for key, value in defaults.items():
        if key not in user:
            user[key] = value
            changed = True
    legacy_keys = (
        "checkin_streak",
        "checkin_last",
        "checkin_daily",
        "daily_uses",
        "streak",
        "uses_left",
        "extra_uses",
        "l4m_free_used_today",
        "shrinkme_free_used_today",
        "total_gets",
    )
    for key in legacy_keys:
        if key in user:
            user.pop(key, None)
            changed = True
    return changed


# ════════════════════════════════════════════════════════════════════
#  Cookie Pool
# ════════════════════════════════════════════════════════════════════

def _load_cookie_file(path):
    """Load cookies from a file, return list of lines."""
    if not os.path.exists(path):
        logger.warning(f"Cookie file '{path}' not found!")
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or len(line) < 10:
                continue
            lines.append(line)
    return lines


def _save_cookie_file(path, cookies, dead_set, permanent_dead_set):
    """Rewrite cookie file -- only remove permanently dead cookies."""
    alive = [c for i, c in enumerate(cookies) if i not in permanent_dead_set]
    try:
        with open(path, "w", encoding="utf-8") as f:
            for c in alive:
                f.write(c + "\n")
        logger.info(f"Saved {len(alive)} cookies to {os.path.basename(path)} (removed {len(permanent_dead_set)} permanent dead)")
    except Exception as e:
        logger.warning(f"Failed to save cookies to {path}: {e}")


def _remap_learning_indexes(old_cookies, new_cookies):
    """Remap nftoken learning dicts after cookie list changes."""
    if not old_cookies:
        return
    new_cookie_map = {cookie: i for i, cookie in enumerate(new_cookies)}
    global _nftoken_good, _nftoken_blocked
    _nftoken_good = {
        new_cookie_map[old_cookies[idx]]: ts
        for idx, ts in _nftoken_good.items()
        if 0 <= idx < len(old_cookies) and old_cookies[idx] in new_cookie_map
    }
    _nftoken_blocked = {
        new_cookie_map[old_cookies[idx]]: until
        for idx, until in _nftoken_blocked.items()
        if 0 <= idx < len(old_cookies) and old_cookies[idx] in new_cookie_map
    }


def _extract_netflix_id(cookie_line: str) -> str:
    """Rút NetflixId từ dòng cookie (pool chuẩn 'NetflixId=...; ...')."""
    m = re.search(r"(?:^|[;\s])netflixid\s*=\s*[\"']?([^\s;\"'\n]+)[\"']?", cookie_line or "", re.IGNORECASE)
    if not m:
        return ""
    v = m.group(1).strip()
    if v.endswith(";"):
        v = v[:-1].rstrip()
    return v


def add_cookies(cookie_lines, website_name="Netflix", status="unknown"):
    """Thêm cookie mới vào pool an toàn (dedup theo NetflixId, giữ lock).

    - Dedup so với _cookies trong RAM (nguồn sự thật duy nhất).
    - Ghi file append TRƯỚC, thành công mới cập nhật _cookies (chống lệch RAM/file).
    - KHÔNG gọi load_cookies() → giữ nguyên _dead_set/_inflight_set/_dead_times.
    - Với website_name != "Netflix" (cookie đa nền tảng), dedup theo toàn bộ dòng
      cookie (không có NetflixId) để tránh bỏ sót.
    Returns {"added": N, "duplicate": N}.
    """
    with _lock:
        is_netflix = (website_name or "Netflix").lower() == "netflix"
        existing_ids = set()
        for c in _cookies:
            if is_netflix:
                cid = _extract_netflix_id(c)
            else:
                cid = c.strip()
            if cid:
                existing_ids.add(cid)
        to_add: list[str] = []
        added = 0
        duplicate = 0
        for c in cookie_lines:
            # Sanitize: strip newlines và control chars (chống injection nhiều dòng)
            c = "".join(ch for ch in (c or "") if ch >= " " or ch == "\t")
            c = c.strip()
            if not c:
                continue
            cid = _extract_netflix_id(c) if is_netflix else c.strip()
            if not cid:
                continue
            if cid in existing_ids:
                duplicate += 1
                continue
            existing_ids.add(cid)
            to_add.append(c)
            added += 1

        if to_add:
            try:
                with open(COOKIE_FILE, "a", encoding="utf-8") as f:
                    for c in to_add:
                        f.write(c + "\n")
            except Exception as e:
                logger.error(f"Cookie merge write error (pool unchanged): {e}")
                return {"added": 0, "duplicate": duplicate + added}
            old_cookies = list(_cookies)
            _cookies.extend(to_add)
            _remap_learning_indexes(old_cookies, _cookies)
            logger.info(f"Added {added} new cookies to pool (duplicates: {duplicate})")
            # Queue Supabase upsert for the new cookies (offline-safe, non-blocking).
            # status="unknown" = chưa được check thật; website_name phân biệt nền tảng.
            try:
                from supabase_sync import enqueue_cookie_sync
                for c in to_add:
                    enqueue_cookie_sync("upsert", c, status=status, website_name=website_name)
            except Exception:
                pass
        return {"added": added, "duplicate": duplicate}


def load_cookies():
    """Load cookies from single cookie file. Returns total count."""
    global _cookies, _dead_set, _permanent_dead_set
    global _inflight_set, _dead_times
    lines = _load_cookie_file(COOKIE_FILE)
    with _lock:
        old_cookies = list(_cookies)
        _cookies = lines
        _dead_set = set()
        _permanent_dead_set = set()
        _inflight_set = set()
        _dead_times = {}
        _remap_learning_indexes(old_cookies, lines)
    logger.info(f"Loaded {len(lines)} cookies")

    # Auto cleanup permanent dead cookies
    import threading as _threading
    _threading.Timer(5.0, _cleanup_permanent_dead_cookies).start()

    return len(lines)


def save_cookies():
    _save_cookie_file(COOKIE_FILE, _cookies, _dead_set, _permanent_dead_set)


def _cleanup_permanent_dead_cookies():
    """Clean up permanent dead cookies from file."""
    global _permanent_dead_set
    if _permanent_dead_set:
        logger.info(f"Cleaning up {len(_permanent_dead_set)} permanent dead cookies")
        save_cookies()
        _permanent_dead_set.clear()


def get_random_index(user_id=None, exclude=None):
    """Get random alive cookie index. `exclude` = set các index không được chọn."""
    now = time.time()
    exclude = exclude or set()
    with _lock:
        # Auto cleanup: promote temporary dead → permanent dead after 24h
        retry_list = []
        for idx in list(_dead_set):
            dead_time = _dead_times.get(idx, now)
            if now - dead_time >= COOKIE_RETRY_WAIT:
                if now - dead_time >= COOKIE_PERMANENT_DEAD_AFTER:
                    _permanent_dead_set.add(idx)
                    _dead_set.discard(idx)
                    _dead_times.pop(idx, None)
                else:
                    retry_list.append(idx)

        all_alive = [i for i in range(len(_cookies))
                     if i not in _inflight_set
                     and i not in _permanent_dead_set
                     and i not in exclude
                     and (i not in _dead_set or i in retry_list)]

        # Exclude accounts đang bị cách ly (token bị chặn tạm thời)
        blocked_now = {i for i, until in _nftoken_blocked.items() if until > now}
        all_alive = [i for i in all_alive if i not in blocked_now]

        fresh = [i for i in all_alive if i not in _dead_set]
        retry = [i for i in retry_list]

        priority = fresh if fresh else (retry if retry else [])

        # Weighted 70/30: 70% ưu tiên account từng gen token thành công (tỷ lệ OK cao),
        # 30% rơi vào toàn pool → cookie chưa thử vẫn được dùng dần, tận dụng hết pool
        # (không như ưu tiên tuyệt đối cũ khiến pool lớn chỉ xoay vòng cụm nhỏ).
        good_list = [i for i in priority if _nftoken_good.get(i, 0) > now - 3600]
        if len(good_list) >= 2 and random.random() < 0.7:
            priority = good_list

        if not priority:
            return None

        idx = random.choice(priority)
        _inflight_set.add(idx)
        if idx in _dead_set and idx in retry_list:
            _dead_set.discard(idx)
            _dead_times.pop(idx, None)
        return idx


def mark_dead(index, user_id=None, vip=None):
    """Mark cookie as temporarily dead."""
    with _lock:
        _inflight_set.discard(index)
        if index not in _permanent_dead_set:
            _dead_set.add(index)
            _dead_times[index] = time.time()
            if 0 <= index < len(_cookies):
                try:
                    from supabase_sync import enqueue_cookie_sync
                    enqueue_cookie_sync("upsert", _cookies[index], status="dead")
                except Exception:
                    pass


def mark_permanent_dead(index, user_id=None, vip=None):
    """Mark cookie as permanently dead."""
    logger.info(f"Marking cookie #{index + 1} as permanent dead")
    with _lock:
        _inflight_set.discard(index)
        _dead_set.discard(index)
        _dead_times.pop(index, None)
        _permanent_dead_set.add(index)
        if 0 <= index < len(_cookies):
            try:
                from supabase_sync import enqueue_cookie_sync
                enqueue_cookie_sync("upsert", _cookies[index], status="dead")
            except Exception:
                pass


def release_index(index, user_id=None, vip=None):
    """Release an in-flight cookie index."""
    with _lock:
        _inflight_set.discard(index)


def delete_cookie(index, user_id=None, vip=None):
    """Xóa cookie khỏi pool + file ngay lập tức (lazy delete khi phát hiện DEAD)."""
    with _lock:
        if not (0 <= index < len(_cookies)):
            return False
        old_cookies = list(_cookies)
        raw = _cookies.pop(index)
        _dead_set.discard(index)
        _permanent_dead_set.discard(index)
        _inflight_set.discard(index)
        _dead_times.pop(index, None)
        # Remap các index theo dõi token learning
        _remap_learning_indexes(old_cookies, _cookies)
        _save_cookie_file(COOKIE_FILE, _cookies, _dead_set, _permanent_dead_set)
        logger.info(f"Deleted dead cookie #{index + 1}")
        try:
            from supabase_sync import enqueue_cookie_sync
            enqueue_cookie_sync("delete", raw)
        except Exception:
            pass
        return True


def delete_cookie_by_raw(raw_line, user_id=None, vip=None):
    """Xóa cookie theo raw_line khỏi pool + file (dùng khi check_pool/API phát hiện DEAD)."""
    if not raw_line:
        return False
    with _lock:
        for i, line in enumerate(_cookies):
            if line == raw_line:
                break
        else:
            return False
    return delete_cookie(i, user_id=user_id, vip=vip)


def get_cookie_line(index, user_id=None, vip=None):
    """Get raw cookie line by index."""
    with _lock:
        if 0 <= index < len(_cookies):
            return _cookies[index]
    return None


def get_all_cookies():
    """Return a copy of the full cookie pool (for Supabase sync)."""
    with _lock:
        return list(_cookies)


def get_cookie_stats(user_id=None, vip=None):
    """Return cookie stats."""
    with _lock:
        total = len(_cookies)
        temp_dead = len(_dead_set)
        perm_dead = len(_permanent_dead_set)
        remaining = total - temp_dead - perm_dead
    return {"total": total, "dead": temp_dead, "permanent_dead": perm_dead, "remaining": remaining}


def push_link_buffer(link, payload, validated=True):
    """Push 1 link đã tạo vào buffer RAM (TTL 30 phút, giữ tối đa LINK_BUFFER_MAX)."""
    now = time.time()
    with _lock:
        _link_buffer[:] = [e for e in _link_buffer if now - e["created"] < LINK_BUFFER_TTL]
        _link_buffer.append({
            "link": link,
            "payload": payload or {},
            "created": now,
            "validated": bool(validated),
        })
        if len(_link_buffer) > LINK_BUFFER_MAX:
            del _link_buffer[: len(_link_buffer) - LINK_BUFFER_MAX]


def pop_link_buffer():
    """Pop link cũ nhất còn hạn (FIFO). Returns dict or None."""
    with _lock:
        now = time.time()
        while _link_buffer and now - _link_buffer[0]["created"] >= LINK_BUFFER_TTL:
            _link_buffer.pop(0)
        if not _link_buffer:
            return None
        return _link_buffer.pop(0)


def get_link_buffer_stats():
    """Return {"total", "validated"} của buffer."""
    with _lock:
        now = time.time()
        while _link_buffer and now - _link_buffer[0]["created"] >= LINK_BUFFER_TTL:
            _link_buffer.pop(0)
        return {
            "total": len(_link_buffer),
            "validated": sum(1 for e in _link_buffer if e.get("validated")),
        }


def get_buffer_source_indices():
    """Set các source_index (cookie) đang có link trong buffer — chống lặp cookie."""
    with _lock:
        return {
            e.get("payload", {}).get("source_index")
            for e in _link_buffer
            if e.get("payload", {}).get("source_index") is not None
        }


def _purge_expired_shrinkme_locked(now):
    """Dọn token gate hết hạn (PHẢI giữ _lock)."""
    expired = [tk for tk, v in _shrinkme_pending.items() if now - v["created"] >= SHRINKME_GATE_TTL]
    for tk in expired:
        del _shrinkme_pending[tk]


def create_shrinkme_token(user_id):
    """Tạo token gate shrinkme cho user. Mỗi user chỉ giữ 1 token (token mới thay token cũ)."""
    with _lock:
        now = time.time()
        _purge_expired_shrinkme_locked(now)
        for tk in [tk for tk, v in _shrinkme_pending.items() if v["user_id"] == user_id]:
            del _shrinkme_pending[tk]
        token = secrets.token_hex(16)
        _shrinkme_pending[token] = {"user_id": user_id, "created": now}
        return token


def pop_shrinkme_token(token, user_id):
    """
    Xác thực + tiêu thụ token gate (single-use).
    Returns True chỉ khi: tồn tại + đúng user + còn hạn.
    """
    if not token:
        return False
    with _lock:
        now = time.time()
        _purge_expired_shrinkme_locked(now)
        info = _shrinkme_pending.pop(token, None)
        if not info or info["user_id"] != user_id:
            return False
        return now - info["created"] < SHRINKME_GATE_TTL


def mark_nftoken_good(index):
    """Ghi nhận cookie gen token thành công."""
    with _lock:
        _nftoken_good[index] = time.time()
        _nftoken_blocked.pop(index, None)


def mark_nftoken_blocked(index, cooldown=3600):
    """Cách ly cookie bị chặn tạo token (access denied / token invalid)."""
    with _lock:
        _nftoken_blocked[index] = time.time() + cooldown
        _nftoken_good.pop(index, None)


def get_bot_stats():
    """Tổng hợp thống kê toàn bot theo mô hình free gated / ref / plan / orders."""
    with _lock:
        today = now_vn().strftime("%Y-%m-%d")
        month = today[:7]
        users_total = len(_users)
        users_today = 0
        users_7d = 0
        users_30d = 0
        gets_today = 0
        gets_total = 0
        gated_today = 0
        ref_today_success = 0
        basic_today = 0
        pro_today = 0
        manual_today = 0
        refs_total = 0
        refs_today = 0
        active_basic = 0
        active_pro = 0
        revenue_today_vnd = 0
        revenue_month_vnd = 0
        revenue_total_vnd = 0
        orders_pending = 0
        orders_paid = 0
        orders_approved = 0
        orders_rejected = 0
        orders_expired = 0
        orders_cancelled = 0
        sepay_paid = 0
        binance_paid = 0

        today_dt = now_vn().date()
        for u in _users.values():
            last_active = u.get("last_active")
            try:
                active_dt = datetime.fromisoformat(last_active).date() if last_active else None
            except Exception:
                active_dt = None
            if active_dt == today_dt:
                users_today += 1
            if active_dt and (today_dt - active_dt).days <= 6:
                users_7d += 1
            if active_dt and (today_dt - active_dt).days <= 29:
                users_30d += 1
            gets_total += int(u.get("total_links_success", 0) or 0)
            user_gated_today = int((u.get("gated_success_daily") or {}).get(today, 0) or 0)
            user_ref_today_success = int((u.get("ref_nogate_success_daily") or {}).get(today, 0) or 0)
            user_basic_today = int((u.get("basic_success_daily") or {}).get(today, 0) or 0)
            user_pro_today = int((u.get("pro_success_daily") or {}).get(today, 0) or 0)
            user_manual_today = int((u.get("manual_bonus_success_daily") or {}).get(today, 0) or 0)
            gated_today += user_gated_today
            ref_today_success += user_ref_today_success
            basic_today += user_basic_today
            pro_today += user_pro_today
            manual_today += user_manual_today
            gets_today += user_gated_today + user_ref_today_success + user_basic_today + user_pro_today + user_manual_today
            refs_total += len(u.get("referrals") or [])
            rd = u.get("ref_daily") or {}
            refs_today += int(rd.get(today, 0) or 0)

            expires = _parse_iso_dt(u.get("plan_expires_at"))
            plan_name = (u.get("plan_name") or "").lower()
            if expires and expires > now_vn():
                if plan_name == "basic":
                    active_basic += 1
                elif plan_name == "pro":
                    active_pro += 1

        for order in _orders.values():
            status = order.get("status") or "pending"
            provider = order.get("provider") or ""
            amount_vnd = int(order.get("amount_vnd", 0) or 0)
            paid_at = order.get("paid_at") or order.get("approved_at") or ""
            if status == "pending":
                orders_pending += 1
            elif status == "paid":
                orders_paid += 1
            elif status == "approved":
                orders_approved += 1
            elif status == "rejected":
                orders_rejected += 1
            elif status == "expired":
                orders_expired += 1
            elif status == "cancelled":
                orders_cancelled += 1

            if status in ("paid", "approved"):
                if provider == "sepay":
                    sepay_paid += 1
                elif provider == "binance":
                    binance_paid += 1
                revenue_total_vnd += amount_vnd
                if isinstance(paid_at, str) and paid_at.startswith(today):
                    revenue_today_vnd += amount_vnd
                if isinstance(paid_at, str) and paid_at.startswith(month):
                    revenue_month_vnd += amount_vnd

        buffer_stats = get_link_buffer_stats()
    cookie = get_cookie_stats()
    return {
        "users": users_total,
        "users_today": users_today,
        "users_7d": users_7d,
        "users_30d": users_30d,
        "gets_today": gets_today,
        "gets_total": gets_total,
        "gated_today": gated_today,
        "ref_success_today": ref_today_success,
        "basic_today": basic_today,
        "pro_today": pro_today,
        "manual_today": manual_today,
        "refs_total": refs_total,
        "refs_today": refs_today,
        "active_basic": active_basic,
        "active_pro": active_pro,
        "revenue_today_vnd": revenue_today_vnd,
        "revenue_month_vnd": revenue_month_vnd,
        "revenue_total_vnd": revenue_total_vnd,
        "orders_pending": orders_pending,
        "orders_paid": orders_paid,
        "orders_approved": orders_approved,
        "orders_rejected": orders_rejected,
        "orders_expired": orders_expired,
        "orders_cancelled": orders_cancelled,
        "sepay_paid": sepay_paid,
        "binance_paid": binance_paid,
        "cookies_remaining": cookie["remaining"],
        "cookies_total": cookie["total"],
        "cookies_dead": cookie["dead"],
        "cookies_perm": cookie["permanent_dead"],
        "buffer_total": buffer_stats["total"],
        "buffer_validated": buffer_stats["validated"],
        "codes": 0,
        "code_uses": 0,
    }


# ════════════════════════════════════════════════════════════════════
#  User Data
# ════════════════════════════════════════════════════════════════════

def load_users():
    """Load user data from user.json."""
    global _users
    if not os.path.exists(USER_FILE):
        _users = {}
        logger.info("No user.json found, starting fresh.")
        return
    try:
        with open(USER_FILE, "r", encoding="utf-8") as f:
            _users = json.load(f)

        changed = False
        with _lock:
            for uid, user in _users.items():
                try:
                    parsed_uid = int(uid)
                except (TypeError, ValueError):
                    parsed_uid = user.get("user_id") or 0
                if _ensure_user_shape(user, parsed_uid):
                    changed = True

        if changed:
            save_users()

        logger.info(f"Loaded {len(_users)} users")
    except Exception as e:
        logger.warning(f"Failed to load users: {e}")
        _users = {}


def save_users():
    """Save user data to user.json ngay lập tức (startup / shutdown)."""
    _do_save_users()


def _schedule_save():
    """Gom nhiều thay đổi thành 1 lần ghi sau SAVE_DEBOUNCE_SECONDS."""
    global _save_dirty, _save_timer
    _save_dirty = True
    if _save_timer is not None:
        return
    _save_timer = threading.Timer(SAVE_DEBOUNCE_SECONDS, _flush_save)
    _save_timer.daemon = True
    _save_timer.start()


def _flush_save():
    global _save_timer
    _save_timer = None
    if _save_dirty:
        _do_save_users()


def _do_save_users():
    global _save_dirty
    _save_dirty = False
    try:
        cutoff = (now_vn() - timedelta(days=90)).strftime("%Y-%m-%d")
        with _lock:
            for u in _users.values():
                for field in (
                    "ref_daily",
                    "plan_daily_used",
                    "ref_nogate_used_daily",
                    "manual_nogate_daily",
                    "manual_nogate_used_daily",
                ):
                    data = u.get(field) or {}
                    for d in [d for d in data if d < cutoff]:
                        data.pop(d, None)
            snapshot = json.dumps(_users, indent=2, ensure_ascii=False)
        tmp_file = USER_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(snapshot)
        os.replace(tmp_file, USER_FILE)
    except Exception as e:
        logger.warning(f"Failed to save users: {e}")


def get_user(user_id):
    """Get or create user data."""
    uid = str(user_id)
    with _lock:
        if uid not in _users:
            _users[uid] = {
                "user_id": user_id,
                "username": None,
                "first_name": None,
                "lang": None,
                "referrer_id": None,
                "referrals": [],
                "ref_daily": {},
                "last_active": None,
                "total_links_success": 0,
                "total_gated_success": 0,
                "total_ref_nogate_success": 0,
                "total_basic_success": 0,
                "total_pro_success": 0,
                "total_manual_bonus_success": 0,
                "gated_success_daily": {},
                "ref_nogate_success_daily": {},
                "basic_success_daily": {},
                "pro_success_daily": {},
                "manual_bonus_success_daily": {},
                "first_get": None,
                "plan_name": None,
                "plan_started_at": None,
                "plan_expires_at": None,
                "plan_daily_used": {},
                "ref_nogate_used_daily": {},
                "manual_nogate_daily": {},
                "manual_nogate_used_daily": {},
            }
        else:
            _ensure_user_shape(_users[uid], user_id)
        return _users[uid]


def set_user_lang(user_id, lang):
    uid = str(user_id)
    with _lock:
        user = get_user(user_id)
        user["lang"] = lang
    _schedule_save()


def update_user_profile(user_id, username=None, first_name=None):
    changed = False
    with _lock:
        user = get_user(user_id)
        if username is not None and user.get("username") != username:
            user["username"] = username
            changed = True
        if first_name is not None and user.get("first_name") != first_name:
            user["first_name"] = first_name
            changed = True
    if changed:
        _schedule_save()


def get_user_lang(user_id):
    uid = str(user_id)
    with _lock:
        user = _users.get(uid)
        if user:
            return user.get("lang")
    return None


def get_total_users():
    with _lock:
        return len(_users)


def user_exists(user_id):
    with _lock:
        return str(user_id) in _users


def delete_user(user_id):
    """Delete user from user.json. Returns True if deleted."""
    uid = str(user_id)
    with _lock:
        if uid in _users:
            del _users[uid]
            _schedule_save()
            logger.info(f"Deleted user {uid} from user.json")
            return True
        return False


def get_all_user_ids():
    """Return list of all user IDs (as int)."""
    with _lock:
        result = []
        for uid in _users:
            try:
                result.append(int(uid))
            except (ValueError, TypeError):
                pass
        return result


# ════════════════════════════════════════════════════════════════════
#  Gift Code
# ════════════════════════════════════════════════════════════════════

def _normalize_gift_code(code):
    raw = str(code or "").strip().upper()
    return re.sub(r"\s+", "", raw)


def load_gift_codes():
    global _gift_codes
    if not os.path.exists(GIFT_CODE_FILE):
        _gift_codes = {}
        return
    try:
        with open(GIFT_CODE_FILE, "r", encoding="utf-8") as f:
            _gift_codes = json.load(f)
    except Exception:
        _gift_codes = {}


def save_gift_codes():
    try:
        with open(GIFT_CODE_FILE, "w", encoding="utf-8") as f:
            json.dump(_gift_codes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save gift codes: {e}")


def _parse_iso_dt(value):
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # Backward-compatible: older records were stored as VN-local naive datetimes.
            dt = dt.replace(tzinfo=VN_TZ)
        return dt.astimezone(VN_TZ)
    except Exception:
        return None


def now_vn():
    return datetime.now(VN_TZ)


def _rebuild_plan_window_from_orders(user_id):
    approvals = []
    with _lock:
        orders = list(_orders.values())

    for order in orders:
        if int(order.get("user_id") or 0) != int(user_id):
            continue
        if order.get("status") != "approved":
            continue
        plan_name = (order.get("plan") or "").lower()
        if plan_name not in ("basic", "pro"):
            continue

        approved_at = (
            _parse_iso_dt(order.get("approved_at"))
            or _parse_iso_dt(order.get("paid_at"))
            or _parse_iso_dt(order.get("created_at"))
        )
        if approved_at:
            approvals.append((approved_at, plan_name))

    if not approvals:
        return None

    approvals.sort(key=lambda item: item[0])
    plan_started_at = approvals[0][0]
    plan_name = approvals[-1][1]
    expires_at = None
    for approved_at, current_plan_name in approvals:
        start = expires_at if expires_at and expires_at > approved_at else approved_at
        expires_at = start + timedelta(days=PLAN_DURATION_DAYS)
        plan_name = current_plan_name

    return {
        "plan_name": plan_name,
        "plan_started_at": plan_started_at,
        "plan_expires_at": expires_at,
    }


def _get_effective_plan_window(user_id, user=None):
    user = user or get_user(user_id)
    plan_name = (user.get("plan_name") or "").lower()
    expires_at = _parse_iso_dt(user.get("plan_expires_at"))

    rebuilt = _rebuild_plan_window_from_orders(user_id)
    if rebuilt and rebuilt.get("plan_name") == plan_name:
        rebuilt_exp = rebuilt.get("plan_expires_at")
        if rebuilt_exp and (
            not expires_at or abs((rebuilt_exp - expires_at).total_seconds()) >= 60
        ):
            with _lock:
                user["plan_started_at"] = rebuilt["plan_started_at"].isoformat()
                user["plan_expires_at"] = rebuilt_exp.isoformat()
            _schedule_save()
            expires_at = rebuilt_exp

    return plan_name, expires_at


def _today_str():
    return now_vn().strftime("%Y-%m-%d")


def _next_midnight():
    now = now_vn()
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json_file(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_orders():
    global _orders
    with _lock:
        loaded = _load_json_file(ORDER_FILE, {})
        _orders = loaded if isinstance(loaded, dict) else {}


def save_orders():
    with _lock:
        _save_json_file(ORDER_FILE, _orders)


def _plan_quota(plan_name):
    plan_name = (plan_name or "").lower()
    if plan_name == "basic":
        return PLAN_BASIC_DAILY
    if plan_name == "pro":
        return PLAN_PRO_DAILY
    return 0


def load_plan_prices():
    global _plan_prices
    with _lock:
        loaded = _load_json_file(PLAN_PRICE_FILE, {})
        _plan_prices = loaded if isinstance(loaded, dict) else {}


def save_plan_prices():
    with _lock:
        _save_json_file(PLAN_PRICE_FILE, _plan_prices)


def get_plan_price_vnd(plan_name):
    plan_name = (plan_name or "").lower()
    with _lock:
        val = _plan_prices.get(plan_name, {}).get("vnd")
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    return _plan_price_vnd(plan_name)


def get_plan_price_usdt(plan_name):
    plan_name = (plan_name or "").lower()
    with _lock:
        val = _plan_prices.get(plan_name, {}).get("usdt")
    if val is not None:
        return str(val)
    return _plan_price_usdt(plan_name)


def get_plan_quota(plan_name):
    plan_name = (plan_name or "").lower()
    with _lock:
        val = _plan_prices.get(plan_name, {}).get("quota")
    if val is not None:
        try:
            return int(val)
        except (TypeError, ValueError):
            pass
    return _plan_quota(plan_name)


def set_plan_price(plan_name, vnd, usdt, quota=None):
    """Cập nhật giá/quota gói runtime (persist qua restart). Trả (ok, msg)."""
    plan_name = (plan_name or "").lower()
    if plan_name not in ("basic", "pro"):
        return False, "invalid_plan"
    try:
        vnd = int(vnd)
    except (TypeError, ValueError):
        return False, "invalid_vnd"
    if vnd <= 0:
        return False, "invalid_vnd"
    try:
        usdt = float(usdt)
    except (TypeError, ValueError):
        return False, "invalid_usdt"
    if usdt <= 0:
        return False, "invalid_usdt"
    usdt_str = str(int(usdt)) if usdt == int(usdt) else str(usdt)
    if quota is not None:
        try:
            quota = int(quota)
        except (TypeError, ValueError):
            return False, "invalid_quota"
        if quota <= 0:
            return False, "invalid_quota"
    with _lock:
        entry = dict(_plan_prices.get(plan_name) or {})
        entry["vnd"] = vnd
        entry["usdt"] = usdt_str
        if quota is not None:
            entry["quota"] = quota
        _plan_prices[plan_name] = entry
        save_plan_prices()
    return True, None


def _plan_price_vnd(plan_name):
    plan_name = (plan_name or "").lower()
    if plan_name == "basic":
        return PLAN_BASIC_PRICE_VND
    if plan_name == "pro":
        return PLAN_PRO_PRICE_VND
    return 0


def _plan_price_usdt(plan_name):
    plan_name = (plan_name or "").lower()
    if plan_name == "basic":
        return PLAN_BASIC_PRICE_USDT
    if plan_name == "pro":
        return PLAN_PRO_PRICE_USDT
    return "0"


def _order_ttl_minutes(provider):
    provider = (provider or "").lower()
    if provider == "sepay":
        return SEPAY_ORDER_TTL_MINUTES
    if provider == "binance":
        return BINANCE_ORDER_TTL_MINUTES
    return 15


def create_gift_code(code, uses, created_by=None, max_claims=1):
    ncode = _normalize_gift_code(code)
    if not ncode:
        return False, "Code khong hop le.", None
    try:
        uses = int(uses)
    except (TypeError, ValueError):
        return False, "So luot khong hop le.", None
    try:
        max_claims = int(max_claims)
    except (TypeError, ValueError):
        max_claims = 1
    if uses <= 0:
        return False, "So luot phai > 0.", None
    if max_claims <= 0:
        return False, "So luot nhap code phai > 0.", None

    with _lock:
        _gift_codes[ncode] = {
            "code": ncode,
            "uses": uses,
            "remaining_claims": max_claims,
            "claimed_by": [],
            "created_by": int(created_by) if created_by else None,
            "created_at": now_vn().isoformat(),
            "active": True,
        }
        save_gift_codes()
    return True, "OK", ncode


def redeem_gift_code(user_id, code):
    ncode = _normalize_gift_code(code)
    if not ncode:
        return False, "Code khong hop le.", 0, get_uses_left(user_id)

    with _lock:
        gift = _gift_codes.get(ncode)
        if not gift:
            return False, "Code khong ton tai.", 0, get_uses_left(user_id)

        if not gift.get("active", True):
            return False, "Code da bi khoa.", 0, get_uses_left(user_id)

        try:
            remaining_claims = int(gift.get("remaining_claims", 0))
        except (TypeError, ValueError):
            remaining_claims = 0
        if remaining_claims <= 0:
            return False, "Code da het luot su dung.", 0, get_uses_left(user_id)

        claimed_by = gift.get("claimed_by") or []
        if int(user_id) in claimed_by:
            return False, "Ban da dung code nay roi.", 0, get_uses_left(user_id)

        try:
            added = int(gift.get("uses", 0))
        except (TypeError, ValueError):
            added = 0
        if added <= 0:
            return False, "Code khong hop le.", 0, get_uses_left(user_id)

        current = get_uses_left(user_id)
        add_uses(user_id, added)

        claimed_by.append(int(user_id))
        gift["claimed_by"] = claimed_by
        gift["remaining_claims"] = remaining_claims - 1

        _schedule_save()
        save_gift_codes()
        return True, "OK", added, current + added


# ════════════════════════════════════════════════════════════════════
#  Access Model / Referral / Plans / Orders
# ════════════════════════════════════════════════════════════════════

def get_user_daily_limit(user_id):
    """Hạn mức link/ngày của user = quota gói đang active (0 nếu free)."""
    return get_plan_daily_quota(user_id)


def get_today_uses(user_id):
    user = get_user(user_id)
    today = _today_str()
    return int((user.get("gated_success_daily") or {}).get(today, 0) or 0)


def get_uses_left(user_id):
    """Tổng lượt no-gate còn lại: quota gói + ref bonus + manual bonus.
    Admin = vô hạn. Khi gate shrinkme bật, user luôn còn ít nhất 1 lượt (vượt gate)."""
    if user_id in ADMIN_IDS:
        return 10 ** 9
    left = get_plan_daily_left(user_id) + get_ref_free_left(user_id) + get_manual_nogate_left(user_id)
    if SHRINKME_API_KEY:
        return max(left, 1)
    return left


def get_next_refill_time(user_id):
    return _next_midnight()


def add_uses(user_id, amount):
    return add_manual_nogate_bonus(user_id, amount)


def consume_use(user_id, amount=1):
    """Kiểm tra user còn đủ lượt không. Đếm lượt thực tế qua record_use + gate consume.
    Admin = luôn cho phép."""
    if user_id in ADMIN_IDS:
        return True
    return get_uses_left(user_id) >= amount


def _bump_daily_counter(user, field, amount=1):
    today = _today_str()
    daily = user.get(field) or {}
    daily[today] = int(daily.get(today, 0) or 0) + amount
    user[field] = daily


def _record_success_fields(user, source: str):
    source = (source or "gated").lower()
    user["total_links_success"] = int(user.get("total_links_success", 0) or 0) + 1
    if source == "gated":
        user["total_gated_success"] = int(user.get("total_gated_success", 0) or 0) + 1
        _bump_daily_counter(user, "gated_success_daily")
    elif source == "ref":
        user["total_ref_nogate_success"] = int(user.get("total_ref_nogate_success", 0) or 0) + 1
        _bump_daily_counter(user, "ref_nogate_success_daily")
    elif source == "basic":
        user["total_basic_success"] = int(user.get("total_basic_success", 0) or 0) + 1
        _bump_daily_counter(user, "basic_success_daily")
    elif source == "pro":
        user["total_pro_success"] = int(user.get("total_pro_success", 0) or 0) + 1
        _bump_daily_counter(user, "pro_success_daily")
    elif source == "manual":
        user["total_manual_bonus_success"] = int(user.get("total_manual_bonus_success", 0) or 0) + 1
        _bump_daily_counter(user, "manual_bonus_success_daily")


def record_use(user_id, username=None, first_name=None, source="gated"):
    now = now_vn()
    with _lock:
        user = get_user(user_id)
        if username:
            user["username"] = username
        if first_name:
            user["first_name"] = first_name
        user["last_active"] = now.isoformat()
        if not user.get("first_get"):
            user["first_get"] = now.isoformat()
        _record_success_fields(user, source)
    _schedule_save()
    return {"bonus": 0, "streak": 0, "streak_grew": False, "source": source}


def add_referral(referrer_id, new_user_id):
    with _lock:
        referrer = get_user(referrer_id)
        nuid = int(new_user_id)
        new_user = get_user(new_user_id)

        if _is_in_referral_chain(referrer_id, nuid):
            return False
        existing_referrer = new_user.get("referrer_id")
        if existing_referrer and int(existing_referrer) != int(referrer_id):
            return False
        if existing_referrer and int(existing_referrer) == int(referrer_id):
            return False
        if nuid in (referrer.get("referrals") or []):
            return False
        if int(referrer_id) == nuid:
            return False

        referrer.setdefault("referrals", []).append(nuid)
        new_user["referrer_id"] = int(referrer_id)
        today = _today_str()
        ref_daily = referrer.get("ref_daily") or {}
        ref_daily[today] = int(ref_daily.get(today, 0) or 0) + 1
        referrer["ref_daily"] = ref_daily
    _schedule_save()
    return True


def _is_in_referral_chain(referrer_id, new_user_id):
    """Kiểm tra new_user_id có nằm trong chuỗi referrer của referrer_id không (chống ref vòng)."""
    current = int(referrer_id)
    seen = set()
    while current and current not in seen:
        seen.add(current)
        if current == int(new_user_id):
            return True
        current = get_user(current).get("referrer_id")
    return False


def get_ref_count(user_id):
    return len(get_user(user_id).get("referrals", []))


def get_ref_today(user_id):
    user = get_user(user_id)
    return int((user.get("ref_daily") or {}).get(_today_str(), 0) or 0)


def get_ref_free_quota(user_id):
    return min(get_ref_today(user_id), REF_DAILY_CAP) * REF_FREE_PER_REF


def get_ref_free_left(user_id):
    user = get_user(user_id)
    today = _today_str()
    used = int((user.get("ref_nogate_used_daily") or {}).get(today, 0) or 0)
    return max(0, get_ref_free_quota(user_id) - used)


def consume_shrinkme_free(user_id):
    with _lock:
        user = get_user(user_id)
        today = _today_str()
        used_daily = user.get("ref_nogate_used_daily") or {}
        used = int(used_daily.get(today, 0) or 0)
        quota = get_ref_free_quota(user_id)
        if used >= quota:
            return False
        used_daily[today] = used + 1
        user["ref_nogate_used_daily"] = used_daily
    _schedule_save()
    return True


def get_plan(user_id):
    user = get_user(user_id)
    plan_name, expires_at = _get_effective_plan_window(user_id, user)
    if not plan_name or not expires_at or expires_at <= now_vn():
        return None, None
    return plan_name, expires_at


def is_plan_active(user_id):
    plan_name, expires_at = get_plan(user_id)
    return bool(plan_name and expires_at)


def get_plan_daily_quota(user_id):
    plan_name, _ = get_plan(user_id)
    return get_plan_quota(plan_name)


def get_plan_daily_used(user_id):
    user = get_user(user_id)
    today = _today_str()
    return int((user.get("plan_daily_used") or {}).get(today, 0) or 0)


def get_plan_daily_left(user_id):
    quota = get_plan_daily_quota(user_id)
    if quota <= 0:
        return 0
    return max(0, quota - get_plan_daily_used(user_id))


def consume_plan_nogate(user_id):
    with _lock:
        user = get_user(user_id)
        plan_name, expires_at = get_plan(user_id)
        if not plan_name or not expires_at:
            return None
        quota = get_plan_quota(plan_name)
        today = _today_str()
        plan_daily_used = user.get("plan_daily_used") or {}
        used = int(plan_daily_used.get(today, 0) or 0)
        if used >= quota:
            return None
        plan_daily_used[today] = used + 1
        user["plan_daily_used"] = plan_daily_used
    _schedule_save()
    return plan_name


def add_manual_nogate_bonus(user_id, amount):
    amount = int(amount or 0)
    if amount <= 0:
        return get_manual_nogate_left(user_id)
    with _lock:
        user = get_user(user_id)
        today = _today_str()
        daily = user.get("manual_nogate_daily") or {}
        daily[today] = int(daily.get(today, 0) or 0) + amount
        user["manual_nogate_daily"] = daily
    _schedule_save()
    return get_manual_nogate_left(user_id)


def get_manual_nogate_left(user_id):
    user = get_user(user_id)
    today = _today_str()
    granted = int((user.get("manual_nogate_daily") or {}).get(today, 0) or 0)
    used = int((user.get("manual_nogate_used_daily") or {}).get(today, 0) or 0)
    return max(0, granted - used)


def consume_manual_nogate(user_id):
    with _lock:
        user = get_user(user_id)
        today = _today_str()
        granted = int((user.get("manual_nogate_daily") or {}).get(today, 0) or 0)
        used_daily = user.get("manual_nogate_used_daily") or {}
        used = int(used_daily.get(today, 0) or 0)
        if used >= granted:
            return False
        used_daily[today] = used + 1
        user["manual_nogate_used_daily"] = used_daily
    _schedule_save()
    return True


def grant_plan(user_id, plan_name, approved_by=None, source=None, order_id=None):
    plan_name = (plan_name or "").lower()
    if plan_name not in ("basic", "pro"):
        return False
    now = now_vn()
    with _lock:
        user = get_user(user_id)
        current_exp = _parse_iso_dt(user.get("plan_expires_at"))
        start = current_exp if current_exp and current_exp > now else now
        user["plan_name"] = plan_name
        user["plan_started_at"] = user.get("plan_started_at") or now.isoformat()
        user["plan_expires_at"] = (start + timedelta(days=PLAN_DURATION_DAYS)).isoformat()
        user["last_active"] = now.isoformat()
        if order_id and order_id in _orders:
            order = _orders[order_id]
            order["status"] = "approved"
            order["approved_at"] = now.isoformat()
            order["approved_by"] = int(approved_by) if approved_by else None
            if source:
                order["approved_source"] = source
            save_orders()
    _schedule_save()
    return True


def remove_plan(user_id):
    with _lock:
        user = get_user(user_id)
        user["plan_name"] = None
        user["plan_started_at"] = None
        user["plan_expires_at"] = None
        user["plan_daily_used"] = {}
    _schedule_save()


def get_plan_snapshot(user_id):
    user = get_user(user_id)
    plan_name, expires_at = get_plan(user_id)
    return {
        "plan_name": plan_name,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "daily_quota": get_plan_quota(plan_name),
        "daily_used": get_plan_daily_used(user_id),
        "daily_left": get_plan_daily_left(user_id),
    }


def create_order(user_id, provider, plan_name):
    provider = (provider or "").lower()
    plan_name = (plan_name or "").lower()
    if provider not in ("sepay", "binance") or plan_name not in ("basic", "pro"):
        return None
    expire_stale_orders()
    existing = find_user_pending_order(user_id, provider=provider, plan_name=plan_name)
    if existing:
        return existing
    now = now_vn()
    prefix = "NF"
    order_id = secrets.token_hex(8)
    order_code = f"{prefix}{secrets.token_hex(3).upper()}"
    amount_vnd = get_plan_price_vnd(plan_name)
    amount_usdt = get_plan_price_usdt(plan_name)
    expires_at = (now + timedelta(minutes=_order_ttl_minutes(provider))).isoformat()
    order = {
        "order_id": order_id,
        "user_id": int(user_id),
        "provider": provider,
        "plan": plan_name,
        "amount_vnd": amount_vnd,
        "amount_usdt": amount_usdt,
        "currency": "VND" if provider == "sepay" else "USDT",
        "order_code": order_code,
        "status": "pending",
        "transaction_id": None,
        "transaction_note": None,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "paid_at": None,
        "approved_at": None,
        "approved_by": None,
        "user_chat_id": None,
        "user_message_id": None,
        "admin_chat_id": None,
        "admin_message_id": None,
    }
    with _lock:
        _orders[order_id] = order
        save_orders()
    return order


def get_order(order_id):
    expire_stale_orders()
    with _lock:
        order = _orders.get(order_id)
        return dict(order) if isinstance(order, dict) else None


def _normalize_order_code(code):
    return str(code or "").strip().upper().replace("-", "")


def find_pending_order_by_code(order_code, provider="sepay"):
    expire_stale_orders()
    normalized = _normalize_order_code(order_code)
    with _lock:
        for order in _orders.values():
            if (order.get("provider") == provider and order.get("status") == "pending"
                    and _normalize_order_code(order.get("order_code")) == normalized):
                return dict(order)
    return None


def find_order_by_code(order_code, provider=None):
    normalized = _normalize_order_code(order_code)
    if not normalized:
        return None
    with _lock:
        for order in _orders.values():
            if provider and order.get("provider") != provider:
                continue
            if _normalize_order_code(order.get("order_code")) == normalized:
                return dict(order)
    return None


def mark_order_paid(order_id, transaction_id=None, transaction_note=None):
    now = now_vn().isoformat()
    with _lock:
        order = _orders.get(order_id)
        if not order or order.get("status") not in ("pending", "paid"):
            return None
        if order.get("status") == "expired":
            return None
        if transaction_id:
            order["transaction_id"] = str(transaction_id)
        if transaction_note:
            order["transaction_note"] = transaction_note
        order["status"] = "paid"
        order["paid_at"] = now
        save_orders()
        return dict(order)


def approve_order(order_id, admin_id=None):
    expire_stale_orders()
    with _lock:
        order = _orders.get(order_id)
        if not order or order.get("status") not in ("pending", "paid"):
            return None
        plan_name = order.get("plan")
        user_id = int(order.get("user_id"))
    if not grant_plan(user_id, plan_name, approved_by=admin_id, source="manual", order_id=order_id):
        return None
    return get_order(order_id)


def reject_order(order_id, admin_id=None, reason=None):
    expire_stale_orders()
    with _lock:
        order = _orders.get(order_id)
        if not order or order.get("status") in ("approved", "rejected", "expired"):
            return None
        order["status"] = "rejected"
        order["approved_at"] = now_vn().isoformat()
        order["approved_by"] = int(admin_id) if admin_id else None
        if reason:
            order["transaction_note"] = reason
        save_orders()
        return dict(order)


def cancel_order(order_id, user_id=None):
    expire_stale_orders()
    with _lock:
        order = _orders.get(order_id)
        if not order or order.get("status") != "pending":
            return None
        if user_id is not None and int(order.get("user_id") or 0) != int(user_id):
            return None
        order["status"] = "cancelled"
        order["approved_at"] = now_vn().isoformat()
        order["approved_by"] = int(user_id) if user_id else None
        save_orders()
        return dict(order)


def list_orders(status=None, provider=None, limit=50):
    expire_stale_orders()
    with _lock:
        items = list(_orders.values())
    if isinstance(status, str):
        statuses = {status}
    elif isinstance(status, (list, tuple, set)):
        statuses = set(status)
    else:
        statuses = None
    if statuses:
        items = [o for o in items if (o.get("status") or "pending") in statuses]
    if provider:
        items = [o for o in items if o.get("provider") == provider]
    items.sort(key=lambda o: o.get("created_at") or "", reverse=True)
    return items[:limit]


def find_processed_transaction(transaction_id):
    tid = str(transaction_id or "").strip()
    if not tid:
        return None
    with _lock:
        for order in _orders.values():
            if str(order.get("transaction_id") or "") == tid and order.get("status") in ("paid", "approved"):
                return dict(order)
    return None


def set_binance_transaction(order_id, tx_value):
    expire_stale_orders()
    tx_value = str(tx_value or "").strip()
    if not tx_value:
        return None
    with _lock:
        order = _orders.get(order_id)
        if not order or order.get("provider") != "binance" or order.get("status") != "pending":
            return None
        order["transaction_note"] = tx_value
        save_orders()
        return dict(order)


def find_user_pending_order(user_id, provider=None, plan_name=None):
    user_id = int(user_id)
    provider = (provider or "").lower() if provider else None
    plan_name = (plan_name or "").lower() if plan_name else None
    expire_stale_orders()
    with _lock:
        for order in _orders.values():
            if int(order.get("user_id") or 0) != user_id:
                continue
            if order.get("status") != "pending":
                continue
            if provider and order.get("provider") != provider:
                continue
            if plan_name and order.get("plan") != plan_name:
                continue
            return dict(order)
    return None


def attach_order_message(order_id, *, user_chat_id=None, user_message_id=None, admin_chat_id=None, admin_message_id=None):
    with _lock:
        order = _orders.get(order_id)
        if not order:
            return None
        if user_chat_id is not None:
            order["user_chat_id"] = int(user_chat_id)
        if user_message_id is not None:
            order["user_message_id"] = int(user_message_id)
        if admin_chat_id is not None:
            order["admin_chat_id"] = int(admin_chat_id)
        if admin_message_id is not None:
            order["admin_message_id"] = int(admin_message_id)
        save_orders()
        return dict(order)


def expire_stale_orders():
    now = now_vn()
    expired = []
    with _lock:
        changed = False
        for order in _orders.values():
            if order.get("status") != "pending":
                continue
            expires_at = _parse_iso_dt(order.get("expires_at"))
            if not expires_at:
                # Fallback: đơn cũ thiếu expires_at → tính từ created_at + TTL
                created_at = _parse_iso_dt(order.get("created_at"))
                if created_at:
                    ttl = _order_ttl_minutes(order.get("provider"))
                    expires_at = created_at + timedelta(minutes=ttl)
            if expires_at and expires_at <= now:
                order["status"] = "expired"
                order["approved_at"] = now.isoformat()
                expired.append(dict(order))
                changed = True
        if changed:
            save_orders()
    return expired


CLEANUP_FINISHED_AFTER_MINUTES = 1


def cleanup_orders():
    """Xoá các đơn đã kết thúc (cancelled/expired) sau CLEANUP_FINISHED_AFTER_MINUTES
    để giữ orders.json sạch, nhưng vẫn đủ thời gian báo 'giao dịch đến muộn'."""
    now = now_vn()
    removed = []
    with _lock:
        stale_ids = []
        for oid, order in _orders.items():
            status = order.get("status")
            if status not in ("cancelled", "expired", "rejected"):
                continue
            ended_at = _parse_iso_dt(order.get("approved_at"))
            if not ended_at:
                ended_at = _parse_iso_dt(order.get("created_at"))
            if ended_at and (now - ended_at) >= timedelta(minutes=CLEANUP_FINISHED_AFTER_MINUTES):
                stale_ids.append(oid)
        for oid in stale_ids:
            order = _orders.pop(oid, None)
            if order:
                removed.append(dict(order))
        if stale_ids:
            save_orders()
    return removed


def get_active_plan_counts():
    stats = {"basic": 0, "pro": 0}
    now = now_vn()
    with _lock:
        for user in _users.values():
            plan_name = (user.get("plan_name") or "").lower()
            expires = _parse_iso_dt(user.get("plan_expires_at"))
            if plan_name in stats and expires and expires > now:
                stats[plan_name] += 1
    return stats


def get_checkin_bonus(user_id):
    return 0


def get_checkin_streak(user_id):
    return 0


def do_checkin(user_id):
    return {"ok": False, "streak": 0, "bonus": 0, "milestone": False}
