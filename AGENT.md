# AGENT.md — Netflix Login Bot

> Đọc file này TRƯỚC khi sửa code. Repo này KHÔNG phải git repo, KHÔNG có test
> framework — kiểm tra bằng py_compile + test ad-hoc python3 -c.

## Project / System Objective
Bot Telegram tiếng Việt/Anh: người dùng nhận link đăng nhập Netflix từ pool cookie
(không bao giờ thấy cookie thô), link hợp lệ 30 phút, mỗi user 3 lượt/ngày (+ bonus
giới thiệu tối đa 5). Admin quản lý pool cookie/proxy qua lệnh + panel nút.

## Current Status (2026-08-01)
- Active: bot chạy bằng `systemd-run --unit=netflixbot` (transient, KHÔNG có file
  /etc/systemd/system/netflixbot.service). Restart: `systemctl stop netflixbot` → rồi
  `systemd-run --unit=netflixbot --working-directory=/root/telegram-bot/bot_netflix/bot_netflix python3 -u main.py`
- Pool cookie: 2209 (cookie.txt); proxy file: 11073 dòng; proxy sống thay đổi theo vòng quét
- Menu command đã set: user 4 lệnh, admin 10 lệnh (gồm loadcookies, loadproxy; /reload và /loadfolder đã bị xóa hẳn)

## Background
- Phiên bản trước bug: bot gửi đi gửi lại cùng 1 cookie (cookie #53, 33 lần).
- Đã sửa bằng: ưu tiên list `good_list` (cookie vừa validate OK), chống trùng account
  theo user (`get_user_used_accounts`), chống trùng trong 1 job (`exclude`/`used_this_run`),
  đổi token qua iOS Argo API path `/login?nftoken=<quote(token, safe='')>`.

## Current Architecture
```
handlers.py   — mọi command/callback/parse cookie (~1938 dòng)
checker.py    — HTTP tới Netflix: check_cookie (account page), generate/validate NFToken (iOS Argo)
storage.py    — pool cookie RAM + user.json + giftcodes.json + link buffer
proxies.py    — proxy pool: quét nền (batch 200 / 600s), auto-xóa dead sau MAX_FAIL=3
lang.py       — 2 dict STRINGS vi/en; t(key, lang, **kwargs)
config.py     — token bot, ADMIN_IDS=[1208795685], DAILY_LIMIT=3, MAX_REF_BONUS=5,
                COOKIE_UPLOAD_WINDOW=20, đường dẫn file
main.py       — ApplicationBuilder, đăng ký handler, _setup_commands, buffer_refill_job (150s)
```

## Runtime / Request Flow
1. User `/loginlink` → `cmd_loginlink` → `_find_and_generate_login_link`:
   - check lượt ngày (DAILY_LIMIT + ref bonus) + group gate (3 nhóm bắt buộc)
   - pop từ `_link_buffer` (RAM, TTL 30ph, max 10, chỉ link đã validate) → ưu tiên `good_list`
   - không có buffer → gen on-demand: `check_cookie` (URL /account) → OK → `generate_nftoken`
     → validate → tạo link (3 thiết bị chung 1 URL) → push buffer
   - skip cookie trong lịch sử user (`get_user_used_accounts`) + `used_this_run`
   - `check_cookie` trả DEAD/FORMER_MEMBER → `delete_cookie` (xóa khỏi pool + ghi đè cookie.txt NGAY)
   - 403/429/5xx → ERROR (KHÔNG đánh DEAD)
2. `buffer_refill_job` chạy mỗi 150s (first=30), tự gen+validate khi buffer trống.
3. Nhập cookie: `/addcookie` hoặc nút panel → gửi file .txt/.json/.zip (window 20s cho nhiều file)
   → `parse_netflix_data` → `_process_cookie_lines` (dedup NetflixId) → append + `load_cookies()`.
4. `/loadcookies` / `/loadproxy` (admin, panel nút hoặc lệnh): scan folder đệ quy qua
   `asyncio.to_thread` (KHÔNG block event loop), dedup vs pool/file, xóa file không đóng góp
   + thư mục rỗng.

## Data Model / Storage
- `cookie.txt`: 1 dòng = 1 cookie chuẩn `NetflixId=...; SecureNetflixId=...; nfvdid=...`
- `user.json`: {user_id: {lang, ref_count, ref_bonus, used_today, session_id, last_used_ts}}
- `giftcodes.json`: gift code dùng để gia hạn lượt
- RAM: `_cookies[]`, `_dead_set`/`_dead_times` (retry 1h), `_permanent_dead_set` (xóa sau 24h),
  `_inflight_set`, `_user_account_usage` (index cookie theo user, remap khi pool đổi),
  `_link_buffer`, `_nftoken_good`/`_nftoken_blocked`
- PROXY_URLS.txt: `ip:port` mỗi dòng; `_live` (max 30), `_bad_until` (cooldown 300s),
  `_fail_count` (xóa file sau 3 fail liên tiếp), `_dead_removed` (stats)

## Key Technical Decisions
- NFToken: iOS Argo `https://ios.prod.ftl.netflix.com/iosui/user/15.48` (hardcode trong
  checker.py ~804). Config cũ `NFTOKEN_API_URL` android13/graphql ĐÃ BỊ XÓA (dead code).
- Path login đúng: `/login?nftoken=<token>`; 3 thiết bị dùng chung 1 URL (`_build_device_links`).
- Rule expired khi parse: `dt=` quá 90 ngày hoặc thuộc 2022-2025 → bỏ (max_age_ms=90 ngày,
  ĐỔI 60→90 theo yêu cầu user 2026-08-01).
- Netscape/json: `_json_to_netscape` sắp xếp NetflixId TRƯỚC SecureNetflixId/nfvdid
  (lỗi cũ: sid đứng trước nid → rớt + bỏ qua lọc expired).
- Link message: header `🎬 NETFLIX LOGIN LINK`, separator `─── 🔸 ───` (KHÔNG dùng `━━━`),
  admin thấy `📊 Còn ∞ lượt hôm nay`, client thấy số lượt cụ thể; cuối message `Liên Hệ: <a href="https://t.me/lucasnguyen0202">Admin</a>`.
- `/reload`, `/loadfolder` đã xóa hẳn (2026-08-01); thay bằng `/loadcookies` + `/loadproxy`.

## Rules bắt buộc khi sửa code (ĐỌC MỖI LẦN FIX BUG)

### 0. Quy trình fix bug (bắt buộc, đúng thứ tự)
1. **Xác định + tái hiện lỗi**: đọc log (`journalctl -u netflixbot --no-pager -n 50 | grep -v getUpdates`,
   hoặc bot.log cũ) / chạy lại hàm gây lỗi — trước khi đụng code
2. **Grep trước, đoán sau**: tìm hàm/hằng liên quan qua grep (vd `grep -n "def cmd_... " handlers.py`)
3. **Sửa nhỏ nhất**, theo đúng pattern hiện có (không refactor lan rộng)
4. **`python3 -m py_compile`** tất cả file đổi (main.py handlers.py checker.py storage.py proxies.py lang.py config.py)
5. **Test ad-hoc** bằng `python3 -c "import sys; sys.path.insert(0,'.'); ..."` (repo KHÔNG có pytest)
6. Nếu đụng cookie.txt / PROXY_URLS.txt: **stop bot trước** (`systemctl stop netflixbot`),
   test trên file giả/tmp, dọn data test, rồi restart
7. **Restart** bằng systemd-run (lệnh ở Current Status) + theo dõi journalctl 1-2 phút
   (buffer_refill_job, proxy scan, không Traceback)
8. **Báo user**: file:line đã sửa + kết quả verify (không nói "xong" khi chưa chạy verify)

### 1. Lệnh mới → cập nhật menu button
Thêm `BotCommand` vào `USER_COMMANDS` hoặc `ADMIN_COMMANDS` (main.py ~47-62) + `CommandHandler`.
Menu chỉ có hiệu lực SAU RESTART (`_setup_commands` chạy lúc khởi động). Test bằng log
`✅ Command menu set`.

### 2. Nút panel admin mới
Thêm callback vào `ADMIN_CALLBACKS` (handlers.py:176) + nhánh xử lý trong `button_handler`
+ key `admin_btn_*` trong lang.py (vi+en).

### 3. Mọi text hiển thị cho user → đi qua `t()` trong lang.py
Thêm đủ CẢ vi lẫn en (`t()` fallback về vi khi thiếu). KHÔNG hardcode text trong handlers.

### 4. Dùng đúng cấu trúc message
Separator `─── 🔸 ───` (cấm `━━━`), header/blank line/Plan/Mail/Hạn/Link theo
`_build_loginlink_message` (handlers.py:95).

### 5. Sau mọi thay đổi
`python3 -m py_compile` (danh sách ở rule 0.4) + grep tìm tham chiếu cũ trước khi xóa.

### 6. KHÔNG đổi ngẫu nhiên
Rule expired cookie (90 ngày + 2022-2025) và `DAILY_LIMIT=3` (docstring storage.py cũ ghi
"5 uses/day" — LẤY config làm chuẩn).

### 7. Cookie dead
Chỉ xóa khi `check_cookie` xác nhận DEAD/FORMER_MEMBER; 403/429/5xx là ERROR → retry,
không xóa (tránh xóa oan khi bị throttle).

### 8. File pool
Append an toàn = `_process_cookie_lines`/`_scan_cookie_folder` (tự dedup + load_cookies).
Sửa tay cookie.txt rất dễ hỏng format — không khuyến khích.

### 9. Proxy
Chỉ hỗ trợ `ip:port` (không auth `user:pass@`, không IPv6 — `_normalize_proxy` loại chúng).
Xóa dead: 3 fail liên tiếp qua scan (scan-fail mới tính; `mark_bad` runtime chỉ cooldown 300s).

### 10. Thread safety
Mọi truy cập dict pool trong `proxies.py`/`storage.py` phải trong `_lock` (threading.RLock).
Scan đồng bộ trong handler async → `asyncio.to_thread` (đã có — giữ pattern này khi thêm lệnh quét).

### 11. Restart bot
`systemctl stop netflixbot` trước khi start lại (transient unit). KHÔNG dùng `nohup ... &`
từ shell session (bị kill theo shell). Lệnh start ở Current Status.

### 12. Khác
Không commit (không phải git repo). Không log BOT_TOKEN (config.py:8) hoặc giá trị
cookie/NFToken đầy đủ vào log.

### 13. Upload nhiều file
`COOKIE_UPLOAD_WINDOW=20` — nếu sửa handler upload, giữ cơ chế window + gia hạn cuối mỗi file.

## Constraints / Risks
- Token i18n: admin chỉ dùng tiếng Việt (bản en giữ cho fallback).
- Folder scan tự XÓA file trùng/đã xử lý — không phục hồi được; chạy thử trên dữ liệu giả trước.
- `concurrent_updates(True)` + `getUpdates` polling; scan dài phải nằm trong thread.
- Netflix có thể throttle IP (403/429) — check_cookie đã guard, không được bỏ guard.

## Testing Notes
- Không có framework/test runner. Cách test thực tế (đã dùng):
  - `python3 -m py_compile <files>` — syntax
  - `python3 -c "import sys; sys.path.insert(0,'.'); from handlers import ..."` — test hàm
    (vd parse_netflix_data, _json_to_netscape, _normalize_proxy, _scan_*_folder, proxies fail-count)
  - chạy scan folder khi `systemctl stop netflixbot` (tránh xung đột file), rồi restart
  - theo dõi `journalctl -u netflixbot --no-pager -n 30 | grep -v getUpdates`

## Deployment Notes
- Không có .service file — bot = transient systemd-run (lệnh ở Current Status).
- Bot.log nằm trong thư mục repo (hiện stdout đã đi vào journald từ bản chạy systemd-run).
- cookie.txt / PROXY_URLS.txt / user.json / giftcodes.json: dữ liệu thật, backup trước khi test ghi đè.

## Non-Goals
- Không phải hệ thống "bán account": không VIP tier, không thêm sub/plan (đã bỏ), single pool.
- Không hỗ trợ proxy có auth; không hỗ trợ IPv6.
- Không có webhook (polling).

## Open Questions
- `_schedule_feedback_prompt` (feedback sau khi dùng link): chưa xác minh luồng đầy đủ khi
  làm việc với 3 thiết bị dùng chung URL.
- Thời điểm chính xác tạo bot (log sớm nhất 2026-07-31): chưa xác minh.
- `9remote.service` (/etc/systemd/system) — service remote dùng chung máy, không liên quan bot.
