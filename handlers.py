"""
Telegram handlers for the simplified Netflix login bot.
"""

import asyncio
import io
import os
import time
import logging
import json
import re
import zipfile
from html import escape
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import Forbidden, BadRequest, RetryAfter
from telegram.ext import ContextTypes, ApplicationHandlerStop
from telegram.constants import ParseMode

from config import (
    ADMIN_IDS, GROUP_USERNAME, GROUP_USERNAMES, REF_FREE_PER_REF, REF_DAILY_CAP,
    BOT_USERNAME, CURRENCY_MAP, BASE_DIR, COOKIE_FILE,
    BANK_BIN, BANK_ACCOUNT, BANK_HOLDER, BINANCE_PAY_ID, USDT_BEP20_ADDRESS,
    COOKIE_UPLOAD_WINDOW, ZIP_FILE_LIMIT,
    ADMIN_TAG,
    SHRINKME_API_KEY,
    PLAN_DURATION_DAYS,
    MANUAL_BONUS_COMMAND,
)
from lang import t
from shrinkme import shorten as shrinkme_shorten
from storage import (
    load_cookies,
    get_random_index, mark_dead, mark_permanent_dead, release_index, delete_cookie,
    get_cookie_line, get_cookie_stats,
    get_user, set_user_lang, get_user_lang, get_total_users, delete_user,
    update_user_profile,
    record_use,
    get_ref_free_left, get_ref_today, add_referral,
    get_uses_left, consume_use, add_uses, get_next_refill_time,
    create_gift_code, redeem_gift_code, get_user_daily_limit,
    get_today_uses,
    get_all_user_ids,
    pop_link_buffer, push_link_buffer, get_link_buffer_stats,
    get_buffer_source_indices,
    mark_nftoken_good, mark_nftoken_blocked, get_bot_stats,
    add_cookies, _extract_netflix_id,
    create_shrinkme_token, pop_shrinkme_token,
    get_plan_snapshot, consume_plan_nogate, get_manual_nogate_left,
    consume_manual_nogate, create_order, get_order, set_binance_transaction,
    approve_order, reject_order, list_orders, add_manual_nogate_bonus,
    attach_order_message, expire_stale_orders, find_user_pending_order, cancel_order,
    cleanup_orders, now_vn, _parse_iso_dt, grant_plan, remove_plan, user_exists,
    get_active_plan_counts,
    get_plan_price_vnd, get_plan_price_usdt, get_plan_quota, set_plan_price,
)

logger = logging.getLogger("NetflixBot")
_executor = ThreadPoolExecutor(max_workers=4)
_active_sessions = {}
_feedback_jobs = {}
_pending_join = {}  # user_id -> (chat_id, message_id) — message prompt join đang hiển thị
_get_inflight_users = set()
_inflight_lock = None  # lazy-init asyncio.Lock
_next_use_source = {}
_pending_ref_global = {}  # ref deep-link click trong group → (referrer_id, ts) → credit khi user /start ở DM
_PENDING_REF_TTL = 24 * 3600  # dọn entry cũ sau 24h nếu user chưa bao giờ /start ở DM
FEEDBACK_DELAY_SECONDS = 30 * 60


def _capture_user_profile(user):
    if not user:
        return
    update_user_profile(
        user.id,
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
    )


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
        plan = get_plan_snapshot(user_id)
        lines.append(
            t(
                "link_remaining",
                lang,
                left=int((plan or {}).get("daily_left") or 0),
                limit=int((plan or {}).get("daily_quota") or 0),
            )
        )

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
        [InlineKeyboardButton(t("btn_buy_plan", lang), callback_data="plan_menu")],
        [InlineKeyboardButton(t("btn_stats", lang), callback_data="stats_input"),
         InlineKeyboardButton(t("btn_ref", lang), callback_data="ref_input")],
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


def plan_menu_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("plan_basic_btn", lang), callback_data="buy_plan_basic")],
        [InlineKeyboardButton(t("plan_pro_btn", lang), callback_data="buy_plan_pro")],
        [InlineKeyboardButton(t("btn_back", lang), callback_data="back")],
    ])


def plan_payment_keyboard(lang, plan_name):
    if plan_name == "basic":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(t("plan_basic_sepay_btn", lang), callback_data="buy_basic_sepay")],
            [InlineKeyboardButton(t("plan_basic_binance_btn", lang), callback_data="buy_basic_binance")],
            [InlineKeyboardButton(t("btn_back", lang), callback_data="plan_back")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("plan_pro_sepay_btn", lang), callback_data="buy_pro_sepay")],
        [InlineKeyboardButton(t("plan_pro_binance_btn", lang), callback_data="buy_pro_binance")],
        [InlineKeyboardButton(t("btn_back", lang), callback_data="plan_back")],
    ])


def binance_admin_keyboard(order_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt", callback_data=f"admin_binance_approve:{order_id}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"admin_binance_reject:{order_id}"),
        ],
    ])


def _build_plan_menu_text(lang: str) -> str:
    return t(
        "plan_menu",
        lang,
        basic_vnd=_fmt_vnd(get_plan_price_vnd("basic")),
        basic_usdt=get_plan_price_usdt("basic"),
        basic_daily=get_plan_quota("basic"),
        pro_vnd=_fmt_vnd(get_plan_price_vnd("pro")),
        pro_usdt=get_plan_price_usdt("pro"),
        pro_daily=get_plan_quota("pro"),
        days=PLAN_DURATION_DAYS,
    )


def _build_plan_payment_text(lang: str, plan_name: str) -> str:
    if plan_name == "basic":
        plan_label = f"{_fmt_vnd(get_plan_price_vnd('basic'))} VND / {get_plan_price_usdt('basic')} USDT"
        plan_daily = get_plan_quota("basic")
    else:
        plan_label = f"{_fmt_vnd(get_plan_price_vnd('pro'))} VND / {get_plan_price_usdt('pro')} USDT"
        plan_daily = get_plan_quota("pro")
    return t(
        "plan_payment_step",
        lang,
        plan=plan_name.upper(),
        price=plan_label,
        daily=plan_daily,
        days=PLAN_DURATION_DAYS,
    )


def _fmt_time(iso_str):
    try:
        dt = _parse_iso_dt(iso_str)
        if not dt:
            return iso_str
        return dt.strftime("%H:%M - %d/%m/%Y")
    except Exception:
        return iso_str


def _fmt_vnd(amount):
    try:
        return f"{int(amount):,}".replace(",", ".")
    except Exception:
        return str(amount)


def _fmt_plan_name(plan_name: str) -> str:
    return str(plan_name or "").upper()


def _fmt_admin_user(user_id: int, fallback_user=None) -> str:
    info = get_user(user_id)
    username = (info.get("username") or "").strip().lstrip("@")
    first_name = (info.get("first_name") or "").strip()
    if fallback_user:
        username = username or (getattr(fallback_user, "username", None) or "").strip().lstrip("@")
        first_name = first_name or (getattr(fallback_user, "first_name", None) or "").strip()

    extra = []
    if username:
        extra.append(f"@{escape(username)}")
    if first_name:
        extra.append(escape(first_name))
    suffix = f" ({' | '.join(extra)})" if extra else ""
    return f"<code>{user_id}</code>{suffix}"


def _fmt_status_text(status: str, lang: str) -> str:
    status = str(status or "").lower()
    mapping = {
        "pending": f"⏳ {t('order_pending', lang)}",
        "paid": f"💰 {t('order_paid', lang)}",
        "approved": f"✅ {t('order_approved', lang)}",
        "rejected": f"❌ {t('order_rejected', lang)}",
        "expired": f"⌛ {t('order_expired', lang)}",
        "cancelled": f"🚫 {t('order_cancelled', lang)}",
    }
    return mapping.get(status, status.upper())


def _build_stats_text(lang: str, user_id: int, display_name: str) -> str:
    plan = get_plan_snapshot(user_id)
    plan_name = _fmt_plan_name((plan or {}).get("plan_name") or "free") if plan else "FREE"
    expires_at = plan.get("expires_at") if plan else None
    plan_left = int((plan or {}).get("daily_left") or 0)
    return t(
        "stats",
        lang,
        name=display_name,
        today=now_vn().strftime("%d/%m/%Y"),
        plan_name=plan_name,
        plan_left=plan_left,
        plan_quota=int((plan or {}).get("daily_quota") or 0),
        plan_expires=_fmt_time(expires_at) if expires_at else "-",
        ref_today=get_ref_today(user_id),
        ref_free_left=get_ref_free_left(user_id),
        reset=get_next_refill_time(user_id).strftime("%H:%M"),
    )


def _build_binance_admin_text(order: dict, user) -> str:
    return t(
        "admin_binance_pending",
        "vi",
        status=_fmt_status_text(order.get("status") or "pending", "vi"),
        plan=_fmt_plan_name(order.get("plan")),
        amount=f"{escape(str(order.get('amount_usdt') or '0'))} USDT",
        provider="BINANCE",
        order_id=order.get("order_id") or "-",
        user_display=_fmt_admin_user(user.id, fallback_user=user),
        order_code=order.get("order_code") or "-",
        created_at=_fmt_time(order.get("created_at")) if order.get("created_at") else "-",
        expires_at=_fmt_time(order.get("expires_at")) if order.get("expires_at") else "-",
        tx=order.get("transaction_note") or "-",
    )


def _build_order_status_text(order: dict, lang: str) -> str:
    if not order:
        return t("generic_error", lang)
    plan_name = _fmt_plan_name(order.get("plan"))
    provider = t("payment_bank", lang) if order.get("provider") == "sepay" else t("payment_usdt", lang)
    amount = f"{_fmt_vnd(order.get('amount_vnd'))} VND" if order.get("provider") == "sepay" else f"{order.get('amount_usdt')} USDT"
    return t(
        "order_status",
        lang,
        status=_fmt_status_text(order.get("status"), lang),
        plan=plan_name,
        provider=provider,
        amount=amount,
        order_code=order.get("order_code") or "-",
        expires_at=_fmt_time(order.get("expires_at")) if order.get("expires_at") else "-",
        tx=order.get("transaction_note") or "-",
    )


def _build_admin_order_detail(order: dict, lang: str) -> str:
    if not order:
        return t("generic_error", lang)
    amount = f"{_fmt_vnd(order.get('amount_vnd'))} VND" if order.get("provider") == "sepay" else f"{order.get('amount_usdt')} USDT"
    return t(
        "admin_order_detail",
        lang,
        status=_fmt_status_text(order.get("status"), lang),
        order_id=order.get("order_id") or "-",
        user_display=_fmt_admin_user(int(order.get("user_id") or 0)),
        provider=str(order.get("provider") or "").upper(),
        plan=_fmt_plan_name(order.get("plan")),
        amount=amount,
        order_code=order.get("order_code") or "-",
        created_at=_fmt_time(order.get("created_at")) if order.get("created_at") else "-",
        expires_at=_fmt_time(order.get("expires_at")) if order.get("expires_at") else "-",
        paid_at=_fmt_time(order.get("paid_at")) if order.get("paid_at") else "-",
        approved_at=_fmt_time(order.get("approved_at")) if order.get("approved_at") else "-",
        tx=order.get("transaction_id") or order.get("transaction_note") or "-",
    )


def _admin_user_keyboard(user_id: int, lang: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("admin_btn_grant_basic", lang), callback_data=f"admin_user_grant_basic:{user_id}"),
            InlineKeyboardButton(t("admin_btn_grant_pro", lang), callback_data=f"admin_user_grant_pro:{user_id}"),
        ],
        [
            InlineKeyboardButton(t("admin_btn_remove_plan", lang), callback_data=f"admin_user_remove_plan:{user_id}"),
            InlineKeyboardButton(t("admin_btn_add_bonus", lang), callback_data=f"admin_user_bonus:{user_id}"),
        ],
        [
            InlineKeyboardButton(t("btn_back", lang), callback_data="admin_back"),
        ],
    ])


def _build_admin_user_card(user_id: int, lang: str) -> str:
    user = get_user(user_id)
    plan = get_plan_snapshot(user_id)
    plan_name = (plan.get("plan_name") or "free").upper() if plan else "FREE"
    return t(
        "admin_user_view",
        lang,
        user_id=user_id,
        plan_name=plan_name,
        plan_expires=_fmt_time(plan.get("expires_at")) if plan and plan.get("expires_at") else "-",
        plan_quota=plan.get("daily_quota") if plan else 0,
        plan_left=plan.get("daily_left") if plan else 0,
    )


def _build_bank_qr_url(order):
    from urllib.parse import quote
    return (
        f"https://img.vietqr.io/image/{BANK_BIN}-{BANK_ACCOUNT}-compact2.png"
        f"?amount={int(order.get('amount_vnd', 0) or 0)}"
        f"&addInfo={quote(str(order.get('order_code') or ''))}"
        f"&accountName={quote(BANK_HOLDER)}"
    )


def _order_resolved_text(order: dict, lang: str) -> str:
    """Text hiển thị khi đơn SePay đã kết thúc (kích hoạt / huỷ / hết hạn)."""
    status = str(order.get("status") or "").lower()
    plan_name = str(order.get("plan") or "").upper()
    if status == "approved":
        return t("plan_approved", lang, plan=plan_name)
    if status == "cancelled":
        return t("plan_cancelled", lang)
    return t("order_expired_text", lang)


async def _replace_user_order_message(context, order: dict, lang: str):
    """Xoá ảnh QR cũ + gửi text trạng thái kết thúc (không nút)."""
    chat_id = order.get("user_chat_id")
    message_id = order.get("user_message_id")
    if chat_id and message_id:
        try:
            await context.bot.delete_message(int(chat_id), int(message_id))
        except Exception:
            pass
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=_order_resolved_text(order, lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def _edit_order_message(context: ContextTypes.DEFAULT_TYPE, order: dict, lang: str, *, reply_markup=None):
    if not order:
        return
    if order.get("provider") == "sepay" and order.get("status") in ("approved", "cancelled", "expired"):
        await _replace_user_order_message(context, order, lang)
        return
    chat_id = order.get("user_chat_id")
    message_id = order.get("user_message_id")
    if chat_id and message_id:
        await _safe_edit_message(
            context,
            int(chat_id),
            int(message_id),
            text=_build_order_status_text(order, lang),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )


async def _send_or_refresh_payment_message(message, order: dict, lang: str, caption: str):
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_cancel_order", lang), callback_data=f"cancel_order:{order['order_id']}")],
    ])
    if order.get("user_chat_id") and order.get("user_message_id"):
        try:
            await message.get_bot().edit_message_text(
                chat_id=int(order["user_chat_id"]),
                message_id=int(order["user_message_id"]),
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            return order
        except Exception:
            pass
    sent = await message.reply_text(caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=reply_markup)
    attach_order_message(order["order_id"], user_chat_id=sent.chat_id, user_message_id=sent.message_id)
    return get_order(order["order_id"])


async def _send_sepay_payment_message(message, order: dict, lang: str, caption: str):
    """Gửi 1 ảnh QR động + caption + nút Huỷ đơn (message này sẽ bị xoá khi kết thúc)."""
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_cancel_order", lang), callback_data=f"cancel_order:{order['order_id']}")],
    ])
    sent = await message.reply_photo(
        photo=_build_bank_qr_url(order),
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )
    attach_order_message(
        order["order_id"],
        user_chat_id=sent.chat_id,
        user_message_id=sent.message_id,
    )
    return get_order(order["order_id"])


async def expire_orders_job(context: ContextTypes.DEFAULT_TYPE):
    expired = expire_stale_orders()
    for order in expired:
        user_lang = get_user_lang(order["user_id"]) or "vi"
        await _edit_order_message(context, order, user_lang)
        admin_chat_id = order.get("admin_chat_id")
        admin_message_id = order.get("admin_message_id")
        if admin_chat_id and admin_message_id:
            await _safe_edit_message(
                context,
                int(admin_chat_id),
                int(admin_message_id),
                text=t("admin_order_expired", "vi", order_id=order.get("order_id")),
                parse_mode=ParseMode.HTML,
            )

    # Dọn đơn đã kết thúc (cancelled/expired) quá 15 phút
    cleaned = cleanup_orders()
    for order in cleaned:
        logger.info("[Cleanup] Removed order %s (status=%s)", order.get("order_id"), order.get("status"))
        # Xoá message chat nếu còn
        for field in ("user_chat_id", "admin_chat_id"):
            chat_id = order.get(field)
            msg_id = order.get("user_message_id" if field == "user_chat_id" else "admin_message_id")
            if chat_id and msg_id:
                try:
                    await context.bot.delete_message(int(chat_id), int(msg_id))
                except Exception:
                    pass


# ═══════════════════════════════════════════════════════════════════
#  Admin UI
# ═══════════════════════════════════════════════════════════════════

ADMIN_CALLBACKS = {
    "admin_import_cookie",
    "admin_loadcookies",
    "admin_loadproxy",
    "admin_addproxy",
    "admin_stats",
    "admin_orders_binance",
    "admin_orders_all",
    "admin_plan_overview",
    "admin_orders_view",
    "admin_user_search",
    "admin_resources",
}


_FILTER_STATUS = {
    "pending": {"pending"},
    "done": {"approved", "paid"},
    "closed": {"cancelled", "expired", "rejected"},
    "all": None,
}


def admin_keyboard(lang="vi"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("admin_btn_user_search", lang), callback_data="admin_user_search"),
            InlineKeyboardButton(t("admin_btn_plans", lang), callback_data="admin_plan_overview"),
        ],
        [
            InlineKeyboardButton(t("admin_btn_orders", lang), callback_data="admin_orders_all"),
            InlineKeyboardButton(t("admin_btn_stats", lang), callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton(t("admin_btn_resources", lang), callback_data="admin_resources"),
        ],
    ])


def resources_keyboard(lang="vi"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("admin_btn_import", lang), callback_data="admin_import_cookie"),
            InlineKeyboardButton(t("admin_btn_loadcookies", lang), callback_data="admin_loadcookies"),
        ],
        [
            InlineKeyboardButton(t("admin_btn_addproxy", lang), callback_data="admin_addproxy"),
            InlineKeyboardButton(t("admin_btn_loadproxy", lang), callback_data="admin_loadproxy"),
        ],
        [
            InlineKeyboardButton(t("btn_back", lang), callback_data="admin_back"),
        ],
    ])


def _admin_stats_text(lang="vi"):
    bs = get_bot_stats()
    from proxies import get_proxy_stats
    ps = get_proxy_stats()
    return t(
        "admin_stats",
        lang,
        users=bs['users'], users_today=bs['users_today'],
        users_7d=bs['users_7d'], users_30d=bs['users_30d'],
        gets_today=bs['gets_today'], gets_total=bs['gets_total'],
        active_basic=bs['active_basic'], active_pro=bs['active_pro'],
        revenue_today_vnd=bs['revenue_today_vnd'], revenue_month_vnd=bs['revenue_month_vnd'], revenue_total_vnd=bs['revenue_total_vnd'],
        orders_pending=bs['orders_pending'], orders_approved=bs['orders_approved'],
        orders_rejected=bs['orders_rejected'], orders_expired=bs['orders_expired'],
        sepay_paid=bs['sepay_paid'], binance_paid=bs['binance_paid'],
        cookies_remaining=bs['cookies_remaining'], cookies_total=bs['cookies_total'], cookies_dead=bs['cookies_dead'],
        buffer_validated=bs['buffer_validated'], buffer_total=bs['buffer_total'],
        proxies_live=ps['live'],
    )


def _admin_list_orders(orders, lang, title_key):
    """Trả về (text, inline_keyboard) cho danh sách đơn admin."""
    lines = [t(title_key, lang)]
    buttons = []
    for order in orders:
        plan = _fmt_plan_name(order.get("plan"))
        amount = f"{order.get('amount_usdt')}U" if order.get("provider") == "binance" else f"{int(order.get('amount_vnd') or 0) // 1000}k"
        status_icon = {
            "pending": "⏳", "paid": "💰", "approved": "✅",
            "rejected": "❌", "expired": "⌛", "cancelled": "🚫",
        }.get(str(order.get("status") or "").lower(), "•")
        user_display = _fmt_admin_user(int(order.get("user_id") or 0))
        order_id_short = str(order.get("order_id") or "-")[:8]
        lines.append(
            f"{status_icon} <code>#{order_id_short}</code> · {user_display} · {plan} · {amount}"
        )
        buttons.append([InlineKeyboardButton(str(order.get("order_id")), callback_data=f"admin_order_detail:{order.get('order_id')}")])
    buttons.append([
        InlineKeyboardButton(t("admin_btn_filter_all", lang), callback_data="admin_orders_view:all"),
        InlineKeyboardButton(t("admin_btn_filter_pending", lang), callback_data="admin_orders_view:pending"),
    ])
    buttons.append([
        InlineKeyboardButton(t("admin_btn_filter_done", lang), callback_data="admin_orders_view:done"),
    ])
    buttons.append([InlineKeyboardButton(t("btn_back", lang), callback_data="admin_back")])
    return "\n\n".join(lines), InlineKeyboardMarkup(buttons)


def _admin_order_detail_keyboard(order, lang):
    buttons = []
    status = str(order.get("status") or "").lower()
    provider = str(order.get("provider") or "").lower()
    order_id = order.get("order_id")

    if status == "pending" and provider == "binance":
        buttons.append([
            InlineKeyboardButton("✅ Duyệt", callback_data=f"admin_binance_approve:{order_id}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"admin_binance_reject:{order_id}"),
        ])

    buttons.append([InlineKeyboardButton(t("btn_back", lang), callback_data="admin_orders_all")])
    return InlineKeyboardMarkup(buttons)


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
        except Exception as e:
            # Lỗi kỹ thuật (rate limit / network / quyền API) KHÔNG chặn oan user
            logger.warning(f"[GroupCheck] Failed to check @{g} for user {user_id}: {type(e).__name__}")
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
                       bonus_per_ref=REF_FREE_PER_REF, name=ref_name),
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
#  Im lặng hoàn toàn trong group/channel — bot chỉ nhận sự kiện join
# ═══════════════════════════════════════════════════════════════════

def _capture_group_ref(user, msg) -> None:
    """Bắt deep-link /start ref_<id> gõ trong nhóm (im lặng) → credit khi user /start ở DM."""
    if not user or not msg or not msg.text:
        return
    parts = msg.text.split()
    if len(parts) >= 2 and parts[0].strip().lower().startswith("/start"):
        arg = parts[1].strip().lower()
        if arg.startswith("ref_") and arg[4:].isdigit():
            _pending_ref_global[user.id] = (int(arg[4:]), time.time())
            _cleanup_stale_pending_refs()


_MEMBER_UPDATE_KEYS = ("chat_member", "my_chat_member", "chat_join_request")


async def group_silence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gatekeeper chạy TRƯỚC mọi handler (group=-1):
    - Group/supergroup/channel: chỉ cho qua update tư cách thành viên
      (chat_member/my_chat_member/chat_join_request phục vụ auto-mở).
      Mọi message/callback khác trong nhóm → chặn im lặng.
    - Private và update không gắn chat → đi tiếp như bình thường."""
    if any(getattr(update, k, None) for k in _MEMBER_UPDATE_KEYS):
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    if chat.type in ("group", "supergroup", "channel"):
        _capture_group_ref(update.effective_user, update.effective_message)
        raise ApplicationHandlerStop  # im lặng hoàn toàn


# ═══════════════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    _capture_user_profile(user)

    # Deep link referral: /start ref_<id> — parse EARLY before lang check
    if context.args:
        arg = context.args[0].strip().lower()
        if arg.startswith("ref_") and arg[4:].isdigit():
            referrer_id = int(arg[4:])
            if referrer_id != user.id:
                context.user_data["pending_ref"] = referrer_id
        elif arg.startswith("shrinkme_"):
            # Gate shrinkme: user quay lại từ link rút gọn → giữ token để xử lý sau khi pass gate nhóm
            context.user_data["pending_shrinkme"] = arg[len("shrinkme_"):]

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

    # Gate shrinkme: xác thực token → cấp link Netflix (thay message welcome)
    if await _process_shrinkme_pending(update, context, lang):
        return

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
    _capture_user_profile(user)
    lang = get_user_lang(user.id) or "vi"
    # Chặn callback từ group/channel — bot chỉ hoạt động trong inbox riêng (im lặng)
    chat = query.message.chat if query.message else None
    if chat and chat.type != "private":
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
    # Allow: language selection, back button, help + admin callbacks
    if data not in ("lang_vi", "lang_en", "change_lang", "back", "help_input") and not data.startswith("admin_") and not data.startswith("cancel_order:") and data not in ADMIN_CALLBACKS:
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

    if data == "plan_menu":
        await query.edit_message_text(
            _build_plan_menu_text(lang),
            parse_mode=ParseMode.HTML,
            reply_markup=plan_menu_keyboard(lang),
            disable_web_page_preview=True,
        )
        return

    if data in ("buy_plan_basic", "buy_plan_pro"):
        plan_name = "basic" if data == "buy_plan_basic" else "pro"
        context.user_data["pending_plan"] = plan_name
        await query.edit_message_text(
            _build_plan_payment_text(lang, plan_name),
            parse_mode=ParseMode.HTML,
            reply_markup=plan_payment_keyboard(lang, plan_name),
            disable_web_page_preview=True,
        )
        return

    if data == "plan_back":
        context.user_data["pending_plan"] = None
        await query.edit_message_text(
            _build_plan_menu_text(lang),
            parse_mode=ParseMode.HTML,
            reply_markup=plan_menu_keyboard(lang),
            disable_web_page_preview=True,
        )
        return

    if data.startswith("cancel_order:"):
        order_id = data.split(":", 1)[1]
        order = cancel_order(order_id, user_id=user.id)
        if order:
            await _edit_order_message(context, order, lang)
            # Cập nhật tin nhắn chờ duyệt trên admin nếu có
            admin_chat_id = order.get("admin_chat_id")
            admin_message_id = order.get("admin_message_id")
            if admin_chat_id and admin_message_id:
                await _safe_edit_message(
                    context,
                    int(admin_chat_id),
                    int(admin_message_id),
                    text=t("admin_order_cancelled", "vi", order_id=order_id),
                    parse_mode=ParseMode.HTML,
                )
        else:
            await query.answer(t("binance_tx_invalid", lang), show_alert=True)
        return

    if data in ("buy_basic_sepay", "buy_pro_sepay"):
        plan_name = "basic" if "basic" in data else "pro"
        order = create_order(user.id, "sepay", plan_name)
        if not order:
            await query.answer(t("generic_error", lang), show_alert=True)
            return
        caption = t(
            "sepay_payment",
            lang,
            plan=plan_name.upper(),
            amount_vnd=_fmt_vnd(order["amount_vnd"]),
            bank_bin=BANK_BIN,
            bank_account=BANK_ACCOUNT,
            bank_holder=BANK_HOLDER,
            order_code=order["order_code"],
            days=PLAN_DURATION_DAYS,
            daily=get_plan_quota(plan_name),
        )
        await _send_sepay_payment_message(query.message, order, lang, caption)
        return

    if data in ("buy_basic_binance", "buy_pro_binance"):
        plan_name = "basic" if "basic" in data else "pro"
        order = create_order(user.id, "binance", plan_name)
        if not order:
            await query.answer(t("generic_error", lang), show_alert=True)
            return
        context.user_data["await_binance_order_id"] = order["order_id"]
        caption = t(
            "binance_payment",
            lang,
            plan=plan_name.upper(),
            amount_usdt=order["amount_usdt"],
            pay_id=BINANCE_PAY_ID,
            wallet=USDT_BEP20_ADDRESS,
            order_code=order["order_code"],
            payment_name=t("payment_usdt", lang),
        )
        await _send_or_refresh_payment_message(query.message, order, lang, caption)
        return

    # -- Admin callbacks (bypass group gate above) --
    if data in ADMIN_CALLBACKS:
        if user.id not in ADMIN_IDS:
            await query.answer(t("admin_denied", lang), show_alert=True)
            return
        if data == "admin_user_search":
            context.user_data["await_admin_user_search"] = True
            await query.edit_message_text(
                t("admin_user_search_prompt", lang),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(lang),
            )
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
            await query.edit_message_text(
                _admin_stats_text(lang),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(lang),
            )
            return
        if data == "admin_orders_all":
            orders = list_orders(limit=10)
            text, kb = _admin_list_orders(orders, lang, "admin_orders_all_text")
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        if data == "admin_resources":
            await query.edit_message_text(
                "🔧 <b>Quản lý tài nguyên</b>\n\nChọn thao tác:",
                parse_mode=ParseMode.HTML,
                reply_markup=resources_keyboard(lang),
            )
            return
        if data == "admin_plan_overview":
            active = get_active_plan_counts()
            await query.edit_message_text(
                t("admin_plan_overview_text", lang, basic=active.get("basic", 0), pro=active.get("pro", 0)),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard(lang),
            )
            return

    if data.startswith("admin_binance_"):
        if user.id not in ADMIN_IDS:
            await query.answer(t("admin_denied", lang), show_alert=True)
            return
        action, _, order_id = data.partition(":")
        order = None
        if action == "admin_binance_approve":
            order = approve_order(order_id, admin_id=user.id)
            if order:
                await query.edit_message_text(
                    _build_admin_order_detail(order, "vi"),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_admin_order_detail_keyboard(order, lang),
                )
                try:
                    await _edit_order_message(context, order, get_user_lang(order["user_id"]) or "vi")
                    await context.bot.send_message(chat_id=order["user_id"], text=t("plan_approved", get_user_lang(order["user_id"]) or "vi", plan=str(order.get("plan") or "").upper()), parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            return
        if action == "admin_binance_reject":
            order = reject_order(order_id, admin_id=user.id, reason="Rejected by admin")
            if order:
                await query.edit_message_text(
                    _build_admin_order_detail(order, "vi"),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_admin_order_detail_keyboard(order, lang),
                )
                try:
                    await _edit_order_message(context, order, get_user_lang(order["user_id"]) or "vi")
                    await context.bot.send_message(chat_id=order["user_id"], text=t("plan_rejected", get_user_lang(order["user_id"]) or "vi"), parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            return

    if data.startswith("admin_order_detail:"):
        if user.id not in ADMIN_IDS:
            await query.answer(t("admin_denied", lang), show_alert=True)
            return
        order_id = data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await query.answer(t("generic_error", lang), show_alert=True)
            return
        await query.edit_message_text(
            _build_admin_order_detail(order, "vi"),
            parse_mode=ParseMode.HTML,
            reply_markup=_admin_order_detail_keyboard(order, lang),
        )
        return

    if data.startswith("admin_orders_view:"):
        if user.id not in ADMIN_IDS:
            await query.answer(t("admin_denied", lang), show_alert=True)
            return
        _filter = data.split(":", 1)[1]
        statuses = _FILTER_STATUS.get(_filter)
        orders = list_orders(status=statuses, limit=10)
        text, kb = _admin_list_orders(orders, lang, "admin_orders_all_text")
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("admin_user_"):
        if user.id not in ADMIN_IDS:
            await query.answer(t("admin_denied", lang), show_alert=True)
            return
        action_parts = data.split(":", 1)
        if len(action_parts) != 2:
            await query.answer(t("generic_error", lang), show_alert=True)
            return
        action, target = action_parts
        try:
            target_id = int(target)
        except (TypeError, ValueError):
            await query.answer(t("admin_user_not_found", lang), show_alert=True)
            return

        if action == "admin_user_view":
            await query.edit_message_text(
                _build_admin_user_card(target_id, "vi"),
                parse_mode=ParseMode.HTML,
                reply_markup=_admin_user_keyboard(target_id, "vi"),
            )
            return

        if action == "admin_user_grant_basic":
            ok = grant_plan(target_id, "basic", approved_by=user.id, source="manual")
            await query.answer(t("admin_user_grant_done", "vi", plan="BASIC") if ok else t("admin_user_not_found", "vi"), show_alert=True)
            if ok:
                await query.edit_message_text(
                    _build_admin_user_card(target_id, "vi"),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_admin_user_keyboard(target_id, "vi"),
                )
            return

        if action == "admin_user_grant_pro":
            ok = grant_plan(target_id, "pro", approved_by=user.id, source="manual")
            await query.answer(t("admin_user_grant_done", "vi", plan="PRO") if ok else t("admin_user_not_found", "vi"), show_alert=True)
            if ok:
                await query.edit_message_text(
                    _build_admin_user_card(target_id, "vi"),
                    parse_mode=ParseMode.HTML,
                    reply_markup=_admin_user_keyboard(target_id, "vi"),
                )
            return

        if action == "admin_user_remove_plan":
            remove_plan(target_id)
            await query.answer(t("admin_user_remove_done", "vi"), show_alert=True)
            await query.edit_message_text(
                _build_admin_user_card(target_id, "vi"),
                parse_mode=ParseMode.HTML,
                reply_markup=_admin_user_keyboard(target_id, "vi"),
            )
            return

        if action == "admin_user_bonus":
            context.user_data["await_admin_bonus_user"] = target_id
            await query.edit_message_text(
                t("admin_user_bonus_prompt", "vi", user_id=target_id),
                parse_mode=ParseMode.HTML,
                reply_markup=admin_keyboard("vi"),
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
        # Gate shrinkme pending: user mới vừa chọn ngôn ngữ từ deep link → cấp link luôn
        if await _process_shrinkme_pending(update, context, chosen):
            return
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
        ref_free_left = get_ref_free_left(user.id)
        await query.edit_message_text(
            t("ref_info", lang,
              ref_link=ref_link,
              ref_today=ref_today, ref_free_left=ref_free_left,
              max_ref=REF_DAILY_CAP,
              bonus_per_ref=REF_FREE_PER_REF,
              max_bonus=REF_DAILY_CAP * REF_FREE_PER_REF),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=back_keyboard(lang),
        )
        return

    if data == "stats_input":
        name = user.first_name or user.username or str(user.id)
        await query.edit_message_text(
            _build_stats_text(lang, user.id, name),
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

        # Gate shrinkme: giống cmd_loginlink — admin/key rỗng bỏ qua; API lỗi → luồng trực tiếp
        if await _try_send_shrinkme_gate(query.edit_message_text, user, lang):
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
                source = _next_use_source.pop(user.id, "gated")
                if consume_use(user.id, 1):
                    use_res = record_use(user.id, username=user.username, first_name=user.first_name, source=source)
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

    if data == "admin_back":
        await query.edit_message_text(
            _admin_stats_text(lang),
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(lang),
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
    await msg.reply_text(
        _admin_stats_text(lang),
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

    new_total = add_manual_nogate_bonus(target_id, amount)
    await msg.reply_text(
        t("addluot_done", lang, amount=amount, target_id=target_id, new_total=new_total),
        parse_mode=ParseMode.HTML,
    )


async def cmd_setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    if not context.args:
        lines = []
        for plan in ("basic", "pro"):
            vnd = get_plan_price_vnd(plan)
            usdt = get_plan_price_usdt(plan)
            quota = get_plan_quota(plan)
            lines.append(
                f"• {plan.upper()}: <b>{_fmt_vnd(vnd)} VND</b> / <b>{usdt} USDT</b>"
                f" — <b>{quota}</b> link/ngày"
            )
        await msg.reply_text(
            t("setprice_current", lang, basic=lines[0], pro=lines[1]),
            parse_mode=ParseMode.HTML,
        )
        return

    if len(context.args) not in (3, 4):
        await msg.reply_text(t("setprice_usage", lang))
        return

    plan_name = context.args[0].lower()
    if plan_name not in ("basic", "pro"):
        await msg.reply_text(t("setprice_invalid_plan", lang))
        return

    quota = context.args[3] if len(context.args) == 4 else None
    ok, err = set_plan_price(plan_name, context.args[1], context.args[2], quota)
    if not ok:
        key = {
            "invalid_vnd": "setprice_invalid_vnd",
            "invalid_usdt": "setprice_invalid_usdt",
            "invalid_quota": "setprice_invalid_quota",
        }.get(err, "setprice_bad_format")
        await msg.reply_text(t(key, lang))
        return

    vnd = get_plan_price_vnd(plan_name)
    usdt = get_plan_price_usdt(plan_name)
    quota = get_plan_quota(plan_name)
    await msg.reply_text(
        t(
            "setprice_done", lang,
            plan=plan_name.upper(),
            vnd=_fmt_vnd(vnd),
            usdt=usdt,
            quota=quota,
        ),
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

    await msg.reply_text(t("gift_removed", lang), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
#  /loginlink command -- Generate login link from active session
# ═══════════════════════════════════════════════════════════════════

async def _deliver_login_link(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Gen + gửi link Netflix cho user (dùng chung cho /loginlink trực tiếp và gate shrinkme).
    Caller phải tự check lượt trước khi gọi. Returns True nếu gửi link thành công."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return False

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
        source = _next_use_source.pop(user.id, "gated")
        if consume_use(user.id, 1):
            use_res = record_use(user.id, username=user.username, first_name=user.first_name, source=source)
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
        return True

    logger.warning(f"[_deliver_login_link] Login link failed for user {user.id}: {error}")
    await searching_msg.edit_text(
        t("link_fail", lang),
        parse_mode=ParseMode.HTML,
        reply_markup=result_keyboard(lang),
    )
    return False


async def _try_send_shrinkme_gate(send_fn, user, lang: str) -> bool:
    """
    Thử gửi message gate shrinkme qua send_fn (msg.reply_text hoặc query.edit_message_text).
    Admin / key rỗng / còn lượt miễn phí hôm nay / API lỗi → False (caller chạy luồng trực tiếp như cũ).
    True = đã gửi gate, caller dừng.
    """
    if user.id in ADMIN_IDS or not SHRINKME_API_KEY:
        _next_use_source[user.id] = "gated"
        return False

    plan_source = consume_plan_nogate(user.id)
    if plan_source:
        _next_use_source[user.id] = plan_source
        logger.info(f"[Plan] No-gate plan use for user {user.id} via {plan_source}")
        return False

    # REF free: lượt không cần vượt gate từ giới thiệu (hôm nay, reset 00:00)
    if get_ref_free_left(user.id) > 0:
        consume_shrinkme_free(user.id)
        _next_use_source[user.id] = "ref"
        logger.info(f"[Link4m] Ref-free pass used for user {user.id} (left {get_ref_free_left(user.id)}) — direct link")
        return False

    if get_manual_nogate_left(user.id) > 0 and consume_manual_nogate(user.id):
        _next_use_source[user.id] = "manual"
        logger.info(f"[ManualBonus] No-gate manual bonus used for user {user.id}")
        return False

    token = create_shrinkme_token(user.id)
    deep_link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=shrinkme_{token}"
    loop = asyncio.get_event_loop()
    short = await loop.run_in_executor(_executor, shrinkme_shorten, deep_link)
    if not short:
        logger.warning("[Gate] shrinkme failed — maintenance mode")
        await send_fn(
            t("gate_maintenance", lang),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return True

    logger.info(f"[Gate] Shrinkme gate link sent to user {user.id}")
    _next_use_source[user.id] = "gated"
    await send_fn(
        t("shrinkme_gate_msg", lang, url=short),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return True


async def _process_shrinkme_pending(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Xử lý pending gate shrinkme (nếu có) trong luồng /start hoặc chọn ngôn ngữ.
    Returns True nếu đã xử lý (caller dừng, không hiện welcome)."""
    user = update.effective_user
    token = context.user_data.pop("pending_shrinkme", None)
    if token is None or not user:
        return False

    if pop_shrinkme_token(token, user.id):
        logger.info(f"[Gate] Gate completed via /start shrinkme_ — user {user.id} token OK")
        await _deliver_login_link(update, context, lang)
    else:
        logger.warning(f"[Gate] /start shrinkme_ REJECTED for user {user.id} (expired/used/mismatch)")
        msg = update.effective_message
        text = t("shrinkme_invalid", lang)
        keyboard = main_keyboard(lang, user.id)
        if msg:
            await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
    return True


async def cmd_loginlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    lang = get_user_lang(user.id) or "vi"

    # Check remaining uses
    uses_left_val = get_uses_left(user.id)
    if uses_left_val <= 0:
        await msg.reply_text(
            t("no_uses_left", lang),
            parse_mode=ParseMode.HTML,
        )
        return

    # Gate shrinkme: admin bỏ qua; key rỗng tắt gate; API lỗi → fallback luồng cũ.
    if await _try_send_shrinkme_gate(msg.reply_text, user, lang):
        return

    await _deliver_login_link(update, context, lang)



# ═══════════════════════════════════════════════════════════════════
async def cmd_removeplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return
    if not context.args:
        await msg.reply_text(t("admin_removeplan_usage", lang))
        return
    try:
        target_id = int(context.args[0])
    except (TypeError, ValueError):
        await msg.reply_text(t("admin_removeplan_usage", lang))
        return
    if not user_exists(target_id):
        await msg.reply_text(t("admin_removeplan_not_found", lang))
        return
    remove_plan(target_id)
    await msg.reply_text(
        t("admin_removeplan_done", lang, user_id=target_id),
        parse_mode=ParseMode.HTML,
    )


#  Text input handler
# ═══════════════════════════════════════════════════════════════════

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return
    _capture_user_profile(update.effective_user)

    if bool(context.user_data.get("await_admin_user_search")):
        context.user_data["await_admin_user_search"] = False
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            return
        lang = get_user_lang(user.id) or "vi"
        try:
            target_id = int(msg.text.strip())
        except (TypeError, ValueError):
            await msg.reply_text(t("admin_user_not_found", lang), parse_mode=ParseMode.HTML)
            return
        if not user_exists(target_id):
            await msg.reply_text(t("admin_user_not_found", lang), parse_mode=ParseMode.HTML)
            return
        await msg.reply_text(
            _build_admin_user_card(target_id, "vi"),
            parse_mode=ParseMode.HTML,
            reply_markup=_admin_user_keyboard(target_id, "vi"),
        )
        return

    bonus_user_id = context.user_data.get("await_admin_bonus_user")
    if bonus_user_id is not None:
        context.user_data["await_admin_bonus_user"] = None
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            return
        lang = get_user_lang(user.id) or "vi"
        try:
            amount = int(msg.text.strip())
        except (TypeError, ValueError):
            await msg.reply_text(t("admin_user_bonus_bad", lang), parse_mode=ParseMode.HTML)
            return
        if amount <= 0:
            await msg.reply_text(t("admin_user_bonus_bad", lang), parse_mode=ParseMode.HTML)
            return
        left = add_manual_nogate_bonus(bonus_user_id, amount)
        await msg.reply_text(
            t("admin_user_bonus_done", "vi", user_id=bonus_user_id, amount=amount, left=left),
            parse_mode=ParseMode.HTML,
        )
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

    pending_binance_order_id = context.user_data.get("await_binance_order_id")
    if pending_binance_order_id:
        context.user_data["await_binance_order_id"] = None
        user = update.effective_user
        if not user:
            return
        lang = get_user_lang(user.id) or "vi"
        order = set_binance_transaction(pending_binance_order_id, msg.text.strip())
        if not order:
            await msg.reply_text(t("binance_tx_invalid", lang), parse_mode=ParseMode.HTML)
            return
        await _edit_order_message(context, order, lang)
        try:
            admin_msg = await context.bot.send_message(
                chat_id=ADMIN_IDS[0],
                text=_build_binance_admin_text(order, user),
                parse_mode=ParseMode.HTML,
                reply_markup=binance_admin_keyboard(order["order_id"]),
            )
            attach_order_message(order["order_id"], admin_chat_id=admin_msg.chat_id, admin_message_id=admin_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to notify admin for binance order {pending_binance_order_id}: {e}")
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
    ref_free_left = get_ref_free_left(user.id)

    await msg.reply_text(
        t("ref_info", lang,
          ref_link=ref_link,
          ref_today=ref_today, ref_free_left=ref_free_left,
          max_ref=REF_DAILY_CAP,
          bonus_per_ref=REF_FREE_PER_REF,
          max_bonus=REF_DAILY_CAP * REF_FREE_PER_REF),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard(lang),
    )


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    await msg.reply_text(t("checkin_removed", lang), parse_mode=ParseMode.HTML)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    name = user.first_name or user.username or str(user.id)
    await msg.reply_text(
        _build_stats_text(lang, user.id, name),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard(lang),
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

    text = msg.text or ""
    parts = text.split(maxsplit=1)
    content = parts[1].strip() if len(parts) > 1 else ""

    if not content:
        await msg.reply_text(
            t("msg_usage", lang),
            parse_mode=ParseMode.HTML,
        )
        return
    all_uids = get_all_user_ids()
    if not all_uids:
        await msg.reply_text(t("no_users", lang))
        return

    await msg.reply_text(
        t("msg_sending", lang, count=len(all_uids)),
    )

    sent = 0
    blocked = 0
    retryable_failed = 0
    for uid in all_uids:
        try:
            await _send_with_retry(
                context.bot.send_message,
                chat_id=uid,
                text=content,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent += 1
        except Forbidden:
            blocked += 1
        except Exception:
            retryable_failed += 1
        # Tránh bị rate limit bởi Telegram
        await asyncio.sleep(0.05)

    await msg.reply_text(
        t("msg_done", lang, sent=sent, total=len(all_uids), blocked=blocked,
          retryable=retryable_failed),
        parse_mode=ParseMode.HTML,
    )


def _should_delete_blocked(exc: Exception) -> bool:
    """True nếu lỗi là do user chặn bot / tài khoản bị deactivated / chat not found (xóa được)."""
    text = str(exc).lower()
    return any(k in text for k in (
        "bot was blocked by the user",
        "user is deactivated",
        "chat not found",
        "chat_id is empty",
        "bot was kicked from the chat",
    ))


async def _send_with_retry(send_coro_factory, **kwargs):
    """Gọi send_*, nếu bị RetryAfter → chờ retry_after giây rồi gửi lại 1 lần."""
    try:
        return await send_coro_factory(**kwargs)
    except RetryAfter as e:
        await asyncio.sleep(max(0, (e.retry_after or 1)))
        return await send_coro_factory(**kwargs)


async def cmd_delusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: quét tất cả user, xóa user chặn bot / bị deactivated (dùng sendChatAction typing — nhẹ)."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    lang = get_user_lang(user.id) or "vi"
    if user.id not in ADMIN_IDS:
        await msg.reply_text(t("not_admin", lang))
        return

    all_uids = get_all_user_ids()
    if not all_uids:
        await msg.reply_text(t("no_users", lang))
        return

    await msg.reply_text(t("delusers_run", lang, count=len(all_uids)))

    removed = 0
    kept = 0
    for uid in all_uids:
        if uid in ADMIN_IDS:
            kept += 1
            continue
        try:
            await _send_with_retry(context.bot.send_chat_action, chat_id=uid, action="typing")
            kept += 1
        except RetryAfter as e:
            await asyncio.sleep(max(0, (e.retry_after or 1)))
            kept += 1
        except Exception as e:
            if _should_delete_blocked(e):
                delete_user(uid)
                removed += 1
            else:
                kept += 1
        await asyncio.sleep(0.05)

    await msg.reply_text(
        t("delusers_done", lang, removed=removed, kept=kept, total=len(all_uids)),
        parse_mode=ParseMode.HTML,
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
