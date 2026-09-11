#!/usr/bin/env python3
"""Gửi thông báo broadcast cho tất cả user (bot cũ + Supabase telegram_id)."""

import asyncio
import json
import os
import re
import sys

import httpx

# Đọc .env.bot trước khi import config
_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(_dir, ".env.bot")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                os.environ.setdefault(key, val)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
USER_FILE = os.path.join(_dir, "user.json")

if not BOT_TOKEN:
    print("❌ Thiếu BOT_TOKEN")
    sys.exit(1)


def get_old_bot_users():
    """Đọc user từ user.json của bot cũ."""
    if not os.path.exists(USER_FILE):
        return set()
    try:
        with open(USER_FILE, encoding="utf-8") as f:
            users = json.load(f)
        return {int(uid) for uid in users.keys() if str(uid).lstrip("-").isdigit()}
    except Exception as e:
        print(f"⚠️ Lỗi đọc user.json: {e}")
        return set()


def get_supabase_users():
    """Đọc user có telegram_id từ Supabase."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return set()
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles?select=telegram_id&telegram_id=not.is.null",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json()
        return {int(row["telegram_id"]) for row in rows if row.get("telegram_id")}
    except Exception as e:
        print(f"⚠️ Lỗi đọc Supabase: {e}")
        return set()


async def send_broadcast(message: str):
    old_users = get_old_bot_users()
    sb_users = get_supabase_users()
    all_uids = sorted(old_users | sb_users)
    print(f"📡 Bot cũ: {len(old_users)} user | Supabase: {len(sb_users)} user | Tổng: {len(all_uids)}")

    if not all_uids:
        print("⚠️ Không có user nào để gửi.")
        return

    sent = 0
    blocked = 0
    failed = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for uid in all_uids:
            try:
                r = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": uid,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
                data = r.json()
                if data.get("ok"):
                    sent += 1
                else:
                    code = data.get("error_code")
                    if code in (403, 400):
                        blocked += 1
                    else:
                        failed += 1
                        print(f"  ⚠️ {uid}: {data.get('description')}")
            except Exception as e:
                failed += 1
                print(f"  ⚠️ {uid}: {e}")
            await asyncio.sleep(0.05)

    print(f"✅ Gửi xong: {sent} thành công | {blocked} bị chặn | {failed} lỗi")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cú pháp: python3 broadcast_msg.py '<nội dung thông báo>'")
        sys.exit(1)
    message = sys.argv[1]
    asyncio.run(send_broadcast(message))
