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
    COOKIE_FILE, USER_FILE, GIFT_CODE_FILE, DAILY_LIMIT, REF_BONUS_PER_REF, REF_DAILY_CAP, BASE_DIR,
CHECKIN_DAILY_BONUS, CHECKIN_MILESTONE_DAYS, CHECKIN_MILESTONE_BONUS,
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

_users = {}
_gift_codes = {}

# ── Link buffer (RAM, TTL 30 min, chỉ chứa link đã validate) ──
_link_buffer = []  # list[dict] {"link", "payload", "created", "validated"}
LINK_BUFFER_TTL = 30 * 60
LINK_BUFFER_MAX = 20

# ── Known-good / blocked cookie learning ──
_nftoken_good = {}    # idx -> last_success_ts
_nftoken_blocked = {}  # idx -> blocked_until_ts

# ── Save debounce: gom nhiều thay đổi thành 1 lần ghi user.json ──
_save_dirty = False
_save_timer = None
SAVE_DEBOUNCE_SECONDS = 3

COOKIE_RETRY_WAIT = 3600
COOKIE_PERMANENT_DEAD_AFTER = 86400


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
        "ref_daily": {},
        "checkin_streak": 0,
        "checkin_last": None,
        "checkin_daily": {},
        "daily_uses": {},
        "streak": 0,
        "last_active": None,
        "total_gets": 0,
        "first_get": None,
        "uses_left": DAILY_LIMIT,
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
        _remap_learning_indexes(old_cookies, _cookies)
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
        refs_today = 0
        checkins_today = 0
        for u in _users.values():
            du = u.get("daily_uses") or {}
            d = int(du.get(today, 0) or 0)
            if d > 0:
                users_today += 1
            gets_today += d
            gets_total += int(u.get("total_gets", 0) or 0)
            refs_total += len(u.get("referrals") or [])
            rd = u.get("ref_daily") or {}
            refs_today += int(rd.get(today, 0) or 0)
            cd = u.get("checkin_daily") or {}
            if int(cd.get(today, 0) or 0) > 0:
                checkins_today += 1
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
        "refs_today": refs_today,
        "checkins_today": checkins_today,
        "cookies_remaining": cookie["remaining"],
        "cookies_total": cookie["total"],
        "cookies_dead": cookie["dead"],
        "cookies_perm": cookie["permanent_dead"],
        "buffer_total": buffer_stats["total"],
        "buffer_validated": buffer_stats["validated"],
        "codes": codes,
        "code_uses": code_uses,
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
        # Prune daily_uses cũ > 90 ngày → user.json không phình theo thời gian
        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        with _lock:
            for u in _users.values():
                du = u.get("daily_uses") or {}
                for d in [d for d in du if d < cutoff]:
                    du.pop(d, None)
                rd = u.get("ref_daily") or {}
                for d in [d for d in rd if d < cutoff]:
                    rd.pop(d, None)
                cd = u.get("checkin_daily") or {}
                for d in [d for d in cd if d < cutoff]:
                    cd.pop(d, None)
            snapshot = json.dumps(_users, indent=2, ensure_ascii=False)
        with open(USER_FILE, "w", encoding="utf-8") as f:
            f.write(snapshot)
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
                "checkin_streak": 0,
                "checkin_last": None,
                "checkin_daily": {},
                "daily_uses": {},
                "streak": 0,
                "last_active": None,
                "total_gets": 0,
                "first_get": None,
                "uses_left": DAILY_LIMIT,
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

        _schedule_save()
        save_gift_codes()
        return True, "OK", added, current + added


# ════════════════════════════════════════════════════════════════════
#  Daily Limits & Referral
# ════════════════════════════════════════════════════════════════════

def get_user_daily_limit(user_id):
    """Daily limit = DAILY_LIMIT + ref bonus hôm nay + check-in bonus hôm nay (đều reset 00:00)."""
    return DAILY_LIMIT + get_ref_bonus(user_id) + get_checkin_bonus(user_id)


def get_today_uses(user_id):
    user = get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    return user.get("daily_uses", {}).get(today, 0)


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
    _schedule_save()
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

        # (Streak cũ đã bỏ — chuỗi điểm danh giờ gắn với do_checkin, tách khỏi việc lấy link)

        user["total_gets"] = user.get("total_gets", 0) + 1
        if not user.get("first_get"):
            user["first_get"] = now.isoformat()

    _schedule_save()
    return {"bonus": 0, "streak": 0, "streak_grew": False}


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
        if int(referrer_id) == nuid:
            return False

        referrer["referrals"].append(nuid)
        new_user["referrer_id"] = int(referrer_id)

        # Đếm ref hôm nay (cộng dồn không giới hạn, bonus chỉ tính tối đa REF_DAILY_CAP)
        if "ref_daily" not in referrer:
            referrer["ref_daily"] = {}
        today = datetime.now().strftime("%Y-%m-%d")
        referrer["ref_daily"][today] = int(referrer["ref_daily"].get(today, 0) or 0) + 1

        _schedule_save()
        return True


def get_ref_count(user_id):
    user = get_user(user_id)
    return len(user.get("referrals", []))


def get_ref_today(user_id):
    """Số ref thành công HÔM NAY (key theo ngày, tự reset khi sang ngày mới)."""
    user = get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    return int((user.get("ref_daily") or {}).get(today, 0) or 0)


def get_ref_bonus(user_id):
    """Bonus lượt dùng hôm nay từ ref = min(ref_today, REF_DAILY_CAP) * REF_BONUS_PER_REF."""
    return min(get_ref_today(user_id), REF_DAILY_CAP) * REF_BONUS_PER_REF


# ════════════════════════════════════════════════════════════════════
#  Điểm danh (check-in) hàng ngày
# ════════════════════════════════════════════════════════════════════

def get_checkin_bonus(user_id):
    """Bonus lượt dùng hôm nay từ điểm danh (chỉ áp dụng trong ngày, reset 00:00)."""
    user = get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    return int((user.get("checkin_daily") or {}).get(today, 0) or 0)


def get_checkin_streak(user_id):
    """Chuỗi ngày điểm danh liên tiếp (còn sống nếu hôm qua/hôm nay đã điểm danh)."""
    user = get_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last = user.get("checkin_last")
    if last == today or last == yesterday:
        return int(user.get("checkin_streak", 0) or 0)
    return 0


def do_checkin(user_id):
    """Điểm danh 1 lần/ngày → +CHECKIN_DAILY_BONUS lượt hôm nay; đủ mốc 7 ngày liên tiếp
    thưởng thêm CHECKIN_MILESTONE_BONUS lượt hôm đó. Trả dict; ok=False nếu đã điểm danh hôm nay."""
    with _lock:
        user = get_user(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        if user.get("checkin_last") == today:
            return {"ok": False, "streak": int(user.get("checkin_streak", 0) or 0)}

        if user.get("checkin_last") == yesterday:
            streak = int(user.get("checkin_streak", 0) or 0) + 1
        else:
            streak = 1

        user["checkin_streak"] = streak
        user["checkin_last"] = today

        bonus = CHECKIN_DAILY_BONUS
        milestone = False
        if streak > 0 and streak % CHECKIN_MILESTONE_DAYS == 0:
            bonus += CHECKIN_MILESTONE_BONUS
            milestone = True

        if "checkin_daily" not in user:
            user["checkin_daily"] = {}
        user["checkin_daily"][today] = bonus

        _schedule_save()
        return {"ok": True, "streak": streak, "bonus": bonus, "milestone": milestone}
