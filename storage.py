"""
Storage -- Single Cookie pool, User data, Referral tracking
All data persisted to user.json
No VIP system -- everyone shares the same pool with 5 uses/day
"""

import os
import json
import random
import re
import threading
import logging
import time
from datetime import datetime, timedelta

from config import (
    COOKIE_FILE, USER_FILE, GIFT_CODE_FILE, DAILY_LIMIT, MAX_REF_BONUS, BASE_DIR,
    ADMIN_IDS,
)

logger = logging.getLogger("NetflixBot")

_lock = threading.RLock()

# ── Single cookie pool ──
_cookies = []
_dead_set = set()
_dead_times = {}
_permanent_dead_set = set()
_inflight_set = set()
_account_usage = {}
_user_account_usage = {}

_users = {}
_gift_codes = {}

# ── Link buffer (RAM, TTL 30 min, chỉ chứa link đã validate) ──
_link_buffer = []  # list[dict] {"link", "payload", "created", "validated"}
LINK_BUFFER_TTL = 30 * 60
LINK_BUFFER_MAX = 10

# ── Known-good / blocked cookie learning ──
_nftoken_good = {}    # idx -> last_success_ts
_nftoken_blocked = {}  # idx -> blocked_until_ts

FREE_REFILL_INTERVAL = timedelta(hours=24)
COOKIE_RETRY_WAIT = 3600
COOKIE_PERMANENT_DEAD_AFTER = 86400
USER_ACCOUNT_COOLDOWN = 604800


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _ensure_user_shape(user, user_id):
    """Backfill missing keys for old records."""
    changed = False
    today = datetime.now().strftime("%Y-%m-%d")
    defaults = {
        "user_id": user_id,
        "username": None,
        "first_name": None,
        "lang": None,
        "referrer_id": None,
        "referrals": [],
        "daily_uses": {},
        "streak": 0,
        "last_active": None,
        "total_gets": 0,
        "first_get": None,
        "uses_left": DAILY_LIMIT,
        "last_free_refill_at": datetime.now().isoformat(),
    }
    for key, value in defaults.items():
        if key not in user:
            user[key] = value
            changed = True
    if user.get("uses_left") is None:
        used_today = 0
        try:
            used_today = int((user.get("daily_uses") or {}).get(today, 0))
        except (TypeError, ValueError):
            used_today = 0
        user["uses_left"] = max(0, DAILY_LIMIT - used_today)
        changed = True
    if not user.get("last_free_refill_at"):
        user["last_free_refill_at"] = datetime.now().isoformat()
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


def _remap_user_account_usage(old_cookies, new_cookies, user_account_usage):
    """Remap user account usage indices after cookie list changes."""
    if not old_cookies or not user_account_usage:
        return
    new_cookie_map = {cookie: i for i, cookie in enumerate(new_cookies)}
    for uid in list(user_account_usage.keys()):
        new_history = []
        for old_idx, used_time in user_account_usage[uid]:
            if 0 <= old_idx < len(old_cookies):
                old_cookie = old_cookies[old_idx]
                new_idx = new_cookie_map.get(old_cookie)
                if new_idx is not None:
                    new_history.append((new_idx, used_time))
        user_account_usage[uid] = new_history


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
        _remap_user_account_usage(old_cookies, lines, _user_account_usage)
    logger.info(f"Loaded {len(lines)} cookies")

    # Auto cleanup permanent dead cookies
    import threading as _threading
    _threading.Timer(5.0, _cleanup_permanent_dead_cookies).start()

    return len(lines)


def save_cookies():
    _save_cookie_file(COOKIE_FILE, _cookies, _dead_set, _permanent_dead_set)


# Alias for backward compatibility
def save_cookies_for(user_id=None, vip=None):
    """Save cookies (single pool, ignores vip param)."""
    save_cookies()


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

        # Only exclude accounts that THIS user previously got
        excluded_for_user = set()
        if user_id:
            user_history = _user_account_usage.get(user_id, [])
            for cookie_idx, used_time in user_history:
                excluded_for_user.add(cookie_idx)

        fresh = [i for i in all_alive if i not in _dead_set and i not in excluded_for_user]
        retry = [i for i in retry_list if i not in excluded_for_user]

        priority = fresh if fresh else (retry if retry else [])

        # Ưu tiên account từng gen token thành công (tỷ lệ thành công cao hơn).
        # CHỈ khi có >= 2 cookie good — nếu chỉ 1 cookie tốt mà ưu tiên tuyệt đối
        # thì pool 128 cookie chỉ quay vòng 1 cookie (bug lặp link 2026-07-31).
        good_list = [i for i in priority if _nftoken_good.get(i, 0) > now - 3600]
        if len(good_list) >= 2:
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
            for uid in list(_user_account_usage.keys()):
                history = _user_account_usage[uid]
                if history and history[-1][0] == index:
                    history.pop()


def mark_permanent_dead(index, user_id=None, vip=None):
    """Mark cookie as permanently dead."""
    logger.info(f"Marking cookie #{index + 1} as permanent dead")
    with _lock:
        _inflight_set.discard(index)
        _dead_set.discard(index)
        _dead_times.pop(index, None)
        _permanent_dead_set.add(index)


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
        global _nftoken_good, _nftoken_blocked
        _nftoken_good = {
            (i if i < index else i - 1): ts
            for i, ts in _nftoken_good.items() if i != index
        }
        _nftoken_blocked = {
            (i if i < index else i - 1): ts
            for i, ts in _nftoken_blocked.items() if i != index
        }
        _remap_user_account_usage(old_cookies, _cookies, _user_account_usage)
        _save_cookie_file(COOKIE_FILE, _cookies, _dead_set, _permanent_dead_set)
        logger.info(f"Deleted dead cookie #{index + 1}")
        return True


def get_cookie_line(index, user_id=None, vip=None):
    """Get raw cookie line by index."""
    with _lock:
        if 0 <= index < len(_cookies):
            return _cookies[index]
    return None


def get_cookie_stats(user_id=None, vip=None):
    """Return cookie stats."""
    with _lock:
        total = len(_cookies)
        temp_dead = len(_dead_set)
        perm_dead = len(_permanent_dead_set)
        remaining = total - temp_dead - perm_dead
    return {"total": total, "dead": temp_dead, "permanent_dead": perm_dead, "remaining": remaining}


def get_user_used_accounts(user_id):
    """Return set of cookie indexes this user already received."""
    if not user_id:
        return set()
    with _lock:
        history = _user_account_usage.get(user_id, [])
        return {idx for idx, _ts in history}


def get_total_cookie_stats():
    """Return cookie stats (same as get_cookie_stats for single pool)."""
    return get_cookie_stats()


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
    """Tổng hợp thống kê toàn bot (users, lượt, cookie, buffer, gift code)."""
    with _lock:
        today = datetime.now().strftime("%Y-%m-%d")
        users_total = len(_users)
        users_today = 0
        gets_today = 0
        gets_total = 0
        refs_total = 0
        for u in _users.values():
            du = u.get("daily_uses") or {}
            d = int(du.get(today, 0) or 0)
            if d > 0:
                users_today += 1
            gets_today += d
            gets_total += int(u.get("total_gets", 0) or 0)
            refs_total += len(u.get("referrals") or [])
        codes = sum(1 for c in _gift_codes.values() if c.get("active"))
        code_uses = sum(int(c.get("uses", 0) or 0) for c in _gift_codes.values() if c.get("active"))
        buffer_stats = get_link_buffer_stats()
    cookie = get_cookie_stats()
    return {
        "users": users_total,
        "users_today": users_today,
        "gets_today": gets_today,
        "gets_total": gets_total,
        "refs_total": refs_total,
        "cookies_remaining": cookie["remaining"],
        "cookies_total": cookie["total"],
        "cookies_dead": cookie["dead"],
        "cookies_perm": cookie["permanent_dead"],
        "buffer_total": buffer_stats["total"],
        "buffer_validated": buffer_stats["validated"],
        "codes": codes,
        "code_uses": code_uses,
    }


def record_account_usage(index, user_id=None, vip=None):
    """Record when an account was given to a user."""
    with _lock:
        _account_usage[index] = time.time()
        if user_id:
            if user_id not in _user_account_usage:
                _user_account_usage[user_id] = []
            _user_account_usage[user_id].append((index, time.time()))


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
    """Save user data to user.json."""
    try:
        with open(USER_FILE, "w", encoding="utf-8") as f:
            json.dump(_users, f, indent=2, ensure_ascii=False)
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
                "daily_uses": {},
                "streak": 0,
                "last_active": None,
                "total_gets": 0,
                "first_get": None,
                "uses_left": DAILY_LIMIT,
                "last_free_refill_at": datetime.now().isoformat(),
            }
        else:
            _ensure_user_shape(_users[uid], user_id)
        return _users[uid]


def set_user_lang(user_id, lang):
    uid = str(user_id)
    with _lock:
        user = get_user(user_id)
        user["lang"] = lang
        save_users()


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


def delete_user(user_id):
    """Delete user from user.json. Returns True if deleted."""
    uid = str(user_id)
    with _lock:
        if uid in _users:
            del _users[uid]
            save_users()
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
            "created_at": datetime.now().isoformat(),
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

        save_users()
        save_gift_codes()
        return True, "OK", added, current + added


# ════════════════════════════════════════════════════════════════════
#  Daily Limits & Referral
# ════════════════════════════════════════════════════════════════════

def get_user_daily_limit(user_id):
    """Get user's daily limit = DAILY_LIMIT + min(ref_count, MAX_REF_BONUS)."""
    base = DAILY_LIMIT
    user = get_user(user_id)
    ref_bonus = min(len(user.get("referrals", [])), MAX_REF_BONUS)
    return base + ref_bonus


def get_user_daily_limit_val(user_id):
    """Return the daily limit for a user."""
    return get_user_daily_limit(user_id)


def get_today_uses(user_id):
    user = get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    return user.get("daily_uses", {}).get(today, 0)


def can_use_today(user_id):
    limit = get_user_daily_limit(user_id)
    used = get_today_uses(user_id)
    base_left = max(0, limit - used)
    
    user = get_user(user_id)
    extra_uses = int(user.get("extra_uses", 0))
    
    remaining = base_left + extra_uses
    return remaining > 0, used, limit, ""


def get_uses_left(user_id):
    """Returns total remaining uses: base remaining + extra_uses. Admin = vô hạn."""
    if user_id in ADMIN_IDS:
        return 10 ** 9
    limit = get_user_daily_limit(user_id)
    used = get_today_uses(user_id)
    base_left = max(0, limit - used)
    
    user = get_user(user_id)
    extra_uses = int(user.get("extra_uses", 0))
    return base_left + extra_uses


def get_next_refill_time(user_id):
    """Returns midnight tonight (next reset)."""
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow


def add_uses(user_id, amount):
    """Add extra one-time uses to a user."""
    with _lock:
        user = get_user(user_id)
        current = int(user.get("extra_uses", 0))
        user["extra_uses"] = current + amount
        save_users()
    return get_uses_left(user_id)


def consume_use(user_id, amount=1):
    """Check if user can use. Actual counting is done via record_use. Admin = vô hạn."""
    if user_id in ADMIN_IDS:
        return True
    remaining = get_uses_left(user_id)
    return remaining >= amount


def record_use(user_id, username=None, first_name=None):
    uid = str(user_id)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    with _lock:
        user = get_user(user_id)
        if username:
            user["username"] = username
        if first_name:
            user["first_name"] = first_name

        limit = get_user_daily_limit(user_id)

        if "daily_uses" not in user:
            user["daily_uses"] = {}
            
        used_today = user["daily_uses"].get(today, 0)
        
        # If base uses exhausted, deduct from extra_uses
        if used_today >= limit:
            extra_uses = int(user.get("extra_uses", 0))
            if extra_uses > 0:
                user["extra_uses"] = extra_uses - 1
                
        user["daily_uses"][today] = used_today + 1

        # Streak chỉ tăng 1 lần/ngày — lần dùng đầu tiên trong ngày mới tính bonus mốc
        streak_grew = False
        if user.get("last_active") == yesterday:
            user["streak"] = user.get("streak", 0) + 1
            streak_grew = True
        elif user.get("last_active") != today:
            user["streak"] = 1
            streak_grew = True
        user["last_active"] = today

        # Bonus theo cột mốc: chỉ nổ khi streak vừa tăng (mỗi mốc 1 lần)
        bonus = 0
        streak = user.get("streak", 0)
        if streak_grew and streak > 0:
            if streak % 7 == 0:
                bonus = 3
            elif streak % 3 == 0:
                bonus = 1
            if bonus > 0:
                user["extra_uses"] = int(user.get("extra_uses", 0)) + bonus

        user["total_gets"] = user.get("total_gets", 0) + 1
        if not user.get("first_get"):
            user["first_get"] = now.isoformat()

        save_users()

    return {"bonus": bonus, "streak": streak, "streak_grew": streak_grew}


def get_streak(user_id):
    user = get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last = user.get("last_active")
    if last == today or last == yesterday:
        return user.get("streak", 0)
    return 0


# ════════════════════════════════════════════════════════════════════
#  Referral System
# ════════════════════════════════════════════════════════════════════

def add_referral(referrer_id, new_user_id):
    with _lock:
        referrer = get_user(referrer_id)
        if "referrals" not in referrer:
            referrer["referrals"] = []

        nuid = int(new_user_id)
        new_user = get_user(new_user_id)

        existing_referrer = new_user.get("referrer_id")
        if existing_referrer and int(existing_referrer) != int(referrer_id):
            return False
        if existing_referrer and int(existing_referrer) == int(referrer_id):
            return False

        if nuid in referrer["referrals"]:
            return False
        if len(referrer["referrals"]) >= MAX_REF_BONUS:
            return False
        if int(referrer_id) == nuid:
            return False

        referrer["referrals"].append(nuid)
        new_user["referrer_id"] = int(referrer_id)

        save_users()
        return True


def get_ref_count(user_id):
    user = get_user(user_id)
    return len(user.get("referrals", []))


def get_ref_bonus(user_id):
    return min(get_ref_count(user_id), MAX_REF_BONUS)


# ════════════════════════════════════════════════════════════════════
#  Backward compatibility stubs (VIP removed)
# ════════════════════════════════════════════════════════════════════

def is_vip(user_id):
    """VIP is removed. Always returns False."""
    return False

def load_vip():
    """No-op. VIP system removed."""
    pass

def add_vip(*args, **kwargs):
    return False, 0

def remove_vip(user_id):
    return False

def get_vip_list():
    return []

def get_vip_info(user_id):
    return None

def get_vip_remaining_days(user_id):
    return 0
