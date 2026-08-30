#!/usr/bin/env python3
"""
Netflix Login Bot — Entry point
"""

import sys
import logging

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from telegram import (
    Update, BotCommand,
    BotCommandScopeDefault, BotCommandScopeChat,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatMemberHandler,
    TypeHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, ADMIN_IDS
from storage import load_cookies, load_users, load_gift_codes, load_orders
from proxies import start_proxy_scanner
from sepay_webhook import start_sepay_webhook_server
from handlers import (
    cmd_start, cmd_addluot,
    cmd_loginlink, cmd_msg, cmd_admin,
    cmd_ref, cmd_stats, cmd_addcookie, cmd_loadcookies, cmd_loadproxy, cmd_help, buffer_refill_job,
    cmd_addproxy, handle_document_upload,
    cmd_delusers,
    handle_text_input, handle_cookie_file_upload, button_handler, cmd_chat_member, error_handler,
    group_silence, expire_orders_job,
)

# ── Logging ──
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NetflixBot")


USER_COMMANDS = [
    BotCommand("start", "Bắt đầu / Start"),
    BotCommand("loginlink", "Lấy link đăng nhập / Get login link"),
    BotCommand("ref", "Link giới thiệu / Referral link"),
    BotCommand("stats", "Lượt dùng / My status"),
    BotCommand("help", "Hướng dẫn khắc phục lỗi / Troubleshooting"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("admin", "Panel admin"),
    BotCommand("addluot", "Cộng bonus no-gate hôm nay"),
    BotCommand("addcookie", "Nạp cookie pool"),
    BotCommand("loadcookies", "Quét thư mục Cookies"),
    BotCommand("loadproxy", "Nạp proxy từ thư mục Proxy"),
    BotCommand("addproxy", "Nạp proxy qua chat"),
    BotCommand("msg", "Gửi tin nhắn tới mọi user"),
    BotCommand("delusers", "Xóa user chặn bot"),
]


async def _setup_commands(app):
    try:
        bot = app.bot
        # Xóa các scope cũ (bot phiên bản trước để lại lệnh /topup, /tv, /addsub...)
        # Scope AllChatAdministrators ưu tiên hơn Default → bắt buộc phải dọn
        for scope in (
            BotCommandScopeAllChatAdministrators(),
            BotCommandScopeAllPrivateChats(),
            BotCommandScopeAllGroupChats(),
        ):
            try:
                await bot.set_my_commands([], scope=scope)
            except Exception as e:
                logger.warning(f"Clear scope {type(scope).__name__} failed: {e}")

        # Set lại menu mặc định + admin (scope Chat cũ sẽ tự hết hạn theo scope mới)
        await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
        await bot.set_my_commands(
            USER_COMMANDS,
            scope=BotCommandScopeAllPrivateChats(),
        )
        for admin_id in ADMIN_IDS:
            await bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        logger.info("✅ Command menu set (default + %d admin scopes, old scopes cleared).", len(ADMIN_IDS))
    except Exception as e:
        logger.error("Failed to set commands menu: %s", e)


def main():
    print()
    print("─── 🔸 ───")
    print("  🎬 Netflix Login Bot")
    print("  💡 Nhấn Ctrl+C để dừng")
    print("─── 🔸 ───")
    print()

    # Load data
    total = load_cookies()
    load_users()
    load_gift_codes()
    load_orders()
    logger.info(f"✅ Ready! {total} cookies loaded.")

    # Khởi động proxy scanner nền
    start_proxy_scanner()

    # Build app
    request = HTTPXRequest(
        connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0,
        pool_timeout=30.0, connection_pool_size=40,
    )
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)
        .post_init(_setup_commands)
        .build()
    )
    start_sepay_webhook_server(app.bot)

    # Register handlers
    # Gatekeeper group=-1: im lặng hoàn toàn trong nhóm/kênh — chỉ cho qua
    # update tư cách thành viên (chat_member...) để auto-mở khi user join đủ nhóm.
    app.add_handler(TypeHandler(Update, group_silence), group=-1)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("addluot", cmd_addluot))
    app.add_handler(CommandHandler("loginlink", cmd_loginlink))
    app.add_handler(CommandHandler("msg", cmd_msg))
    app.add_handler(CommandHandler("delusers", cmd_delusers))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("ref", cmd_ref))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("addcookie", cmd_addcookie))
    app.add_handler(CommandHandler("loadcookies", cmd_loadcookies))
    app.add_handler(CommandHandler("loadproxy", cmd_loadproxy))
    app.add_handler(CommandHandler("addproxy", cmd_addproxy))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(
        filters.Document.ALL & filters.ChatType.PRIVATE,
        handle_document_upload,
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatMemberHandler(cmd_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(error_handler)

    # Buffer refill job: mỗi 60s tự gen + validate link nạp sẵn (chỉ khi buffer dưới ngưỡng)
    app.job_queue.run_repeating(buffer_refill_job, interval=60, first=30)
    app.job_queue.run_repeating(expire_orders_job, interval=60, first=60)

    logger.info("🚀 Bot is running!")
    # ALL_TYPES để nhận cả update chat_member (mặc định Telegram loại trừ loại này)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
