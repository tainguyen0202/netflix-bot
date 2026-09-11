#!/usr/bin/env python3
"""Pull cookies from Supabase `cookies` table → cookie.txt (bot pool)."""

import os
import sys

# Đọc .env.bot trước khi import config
_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(_dir, ".env.bot")
if os.path.isfile(env_path):
    import re
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

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
COOKIE_FILE = os.path.join(_dir, "cookie.txt")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_KEY trong .env.bot")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

print("📡 Đang kéo cookies từ Supabase...")

# Paginate — Supabase trả tối đa 1000 row/lần
all_rows = []
page_size = 1000
offset = 0
while True:
    res = (
        client.table("cookies")
        .select("raw_line, status")
        .neq("status", "dead")          # bỏ dead
        .range(offset, offset + page_size - 1)
        .execute()
    )
    rows = res.data or []
    all_rows.extend(rows)
    if len(rows) < page_size:
        break
    offset += page_size

if not all_rows:
    print("⚠️  Không có cookie nào trên Supabase (hoặc tất cả đều dead).")
    sys.exit(0)

# Ghi ra cookie.txt — mỗi dòng = raw_line
lines = []
for r in all_rows:
    raw = (r.get("raw_line") or "").strip()
    if raw:
        lines.append(raw)

# Dedup giữ thứ tự
seen = set()
unique = []
for ln in lines:
    if ln not in seen:
        seen.add(ln)
        unique.append(ln)

with open(COOKIE_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(unique) + "\n")

print(f"✅ Đã ghi {len(unique)} cookies vào {COOKIE_FILE}")
