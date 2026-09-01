# AGENT.md — Netflix Login Bot

> Đọc file này TRƯỚC khi sửa code. Repo là git repo (origin GitHub). KHÔNG có test
> framework — kiểm tra bằng py_compile + test ad-hoc python3.

## Project / System Objective
Bot Telegram tiếng Việt/Anh: người dùng nhận link đăng nhập Netflix từ pool cookie
(không bao giờ thấy cookie thô). Mô hình access:
- Free: không giới hạn lượt/ngày, luôn phải qua gate (xác thực link).
- Ref: mỗi ref thành công = +3 lượt KHÔNG cần vượt gate trong ngày, reset 00:00.
- Plan Basic (10k/30 ngày, 10 no-gate/ngày) & Pro (20k/30 ngày, 20 no-gate/ngày).
- Thanh toán: SePay tự động (webhook), Binance/USDT bán tự động (admin duyệt inline).
Admin quản lý pool cookie/proxy + đơn hàng qua panel nút.

## Current Status
- Bot chạy bằng systemd (file template `deploy/netflixbot.service`, env `deploy/env.example`).
  Deploy: copy service → /etc/systemd/system, tạo /root/bot_netflix/.env.bot, `systemctl daemon-reload`,
  `systemctl enable --now netflixbot`; log `journalctl -u netflixbot -f`.
- Webhook SePay chạy song song với Telegram polling tại `0.0.0.0:8080/sepay-webhook`.
- Secret KHÔNG commit: đọc từ `local_config.py` (bị .gitignore chặn) hoặc env `.env.bot`.
- Menu command: user `start/loginlink/ref/stats/help`; admin thêm `admin/addluot/addcookie/loadcookies/loadproxy/addproxy/msg/delusers`.

## Background
- Phiên bản trước bug: bot gửi đi gửi lại cùng 1 cookie (cookie #53, 33 lần).
- Đã sửa bằng: ưu tiên list `good_list` (cookie vừa validate OK), chống trùng account
  theo user (`get_user_used_accounts`), chống trùng trong 1 job (`exclude`/`used_this_run`),
  đổi token qua iOS Argo API path `/login?nftoken=<quote(token, safe='')>`.

## Current Architecture
```
handlers.py      — mọi command/callback/parse cookie + UI mua gói + admin order/plan
checker.py       — HTTP tới Netflix: check_cookie (account), generate/validate NFToken
storage.py       — cookie pool + user.json + orders.json + plan/ref/manual quota + order lifecycle
link4m.py        — rút gọn deep link qua link4m.co (flat: lỗi → None)
layma.py         — shortener backup (dùng khi link4m lỗi)
sepay_webhook.py — HTTP server nhận webhook SePay, idempotent, tự cấp gói
proxies.py       — proxy pool: quét nền, auto-xóa dead sau MAX_FAIL=3
lang.py          — 2 dict STRINGS vi/en; t(key, lang, **kwargs)
config.py        — token bot, ADMIN_IDS, plan/order TTL, payment; secret đọc từ env/local_config
main.py          — ApplicationBuilder, handler, buffer_refill_job, expire_orders_job
```

## Runtime / Request Flow
1. User `/loginlink` / nút Get Link → `_try_send_l4m_gate`:
   - admin → thẳng; nếu còn quota plan (basic/pro) → dùng plan, không vượt gate;
   - kế đến ref no-gate quota; kế đến manual (chỉ admin core, KHÔNG hiện ở UI user);
   - nếu hết → tạo token gate (RAM TTL 30ph, single-use) → deep link `t.me/<bot>?start=l4m_<token>`
     rút gọn qua link4m, lỗi → layma backup, cả 2 lỗi → báo "đang bảo trì" (KHÔNG bypass trực tiếp).
2. Vượt xong → `/start l4m_<token>` → `_process_l4m_pending` → `_deliver_login_link` (record source).
3. Mua gói: `Mua Gói` → 2 bước (chọn gói → chọn cổng `Ngân hàng VN` / `Thanh toán USDT`).
   - SePay: tạo order pending, gửi 1 ảnh QR VietQR động (`amount` + `addInfo=order_code`); khi approved/
     expired/cancelled thì xoá ảnh và gửi text mới.
   - USDT: tạo order, user gửi mã giao dịch → admin được tin nhắn + nút Duyệt/Từ chối → `edit` lại.
4. `expire_orders_job` chạy mỗi 60s: đơn pending quá TTL → expired + `edit` message; giao dịch đến muộn
   KHÔNG tự cấp gói, chỉ báo admin; sau đó `cleanup_orders()` xoá đơn cancelled/expired quá 15 phút
   (tính từ `approved_at`) và xoá msg chat còn sót để giữ dữ liệu sạch.

## Data Model / Storage
- `cookie.txt`: 1 dòng = 1 cookie chuẩn `NetflixId=...; SecureNetflixId=...; nfvdid=...`
- `user.json`: {user_id: {lang, last_active, plan_name, plan_started_at, plan_expires_at,
   plan_daily_used, ref_daily, ref_nogate_used_daily, manual_nogate_daily,
   manual_nogate_used_daily, referrals[], total_links_success, các *success_daily}>{}
  - `get_plan_snapshot` = plan hiện tại + quota/used/left; hết gói tự về free gated.
- `orders.json`: {order_id: {user_id, provider(sepay|binance), plan, amount_vnd/usdt,
   order_code, status(pending|paid|approved|rejected|expired), transaction_id/note,
   created_at, expires_at, paid_at, approved_at, user_chat_id/user_message_id,
   admin_chat_id/admin_message_id}}
  - TTL: sepay 15 phút, binance 30 phút (`expire_stale_orders`).
  - Idempotent: webhook theo SePay `id` chống cấp 2 lần; order expired KHÔNG auto-cấp.
  - `cleanup_orders()`: xoá đơn `cancelled`/`expired` khi `approved_at` cũ hơn 15 phút
    (`CLEANUP_FINISHED_AFTER_MINUTES`). Giữ nguyên pending/paid/approved/rejected.
  - Tất cả timestamp/quy tắc reset/ngày đều chạy theo **giờ Việt Nam ở tầng code**, KHÔNG phụ thuộc timezone VPS.
    Legacy naive datetime trong file json được hiểu là **giờ VN cũ** khi parse; nếu `plan_expires_at`
    đã từng bị lệch do parse sai, `get_plan()` sẽ tự dựng lại hạn gói từ lịch sử order `approved`.
- `giftcodes.json`: còn file nhưng KHÔNG dùng trong flow (gift code đã gỡ khỏi runtime).
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
- Link message: header `🎬 NETFLIX LOGIN LINK`, KHÔNG còn separator gạch ngang (spacing bằng dòng trống).
- **UI user KHÔNG lộ backend**: dùng `Ngân hàng VN` / `Thanh toán USDT` thay cho SePay/Binance;
  không hiện tên link4m/layma/webhook; không hiện `manual addluot` ở stats user.
- Message order dùng `edit` (KHÔNG delete) để chat gọn, ít lỗi.
- Timezone policy: dùng `storage.now_vn()` / `ZoneInfo("Asia/Ho_Chi_Minh")` (fallback UTC+7),
  KHÔNG dùng `datetime.now()` trực tiếp cho logic user-facing/order/quota.

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
Thêm callback vào `ADMIN_CALLBACKS` (handlers.py) + nhánh `button_handler` + key `admin_btn_*`.
Text admin chỉ cần tiếng Việt (EN admin giữ làm fallback, KHÔNG cần phát triển tiếp).
- Admin `🔍 Tìm user`: nhập user_id → card thông tin + nút Cấp Basic/Pro, Thu hồi gói, Bonus.
  Dùng `user_exists()` (KHÔNG dùng `get_user()` để tránh tạo user rỗng khi tra cứu).
  Cấp gói thủ công dùng `grant_plan(source="manual")` → KHÔNG tạo doanh thu.
- `admin_plan_overview` đếm user active từ `get_active_plan_counts()` (đồng bộ với `admin_stats`).
- Bộ lọc đơn nhóm: `done = approved+paid`, `closed = cancelled+expired+rejected` (`_FILTER_STATUS`).
- `list_orders(status=...)` nhận str hoặc list/tuple/set nhiều status.

### 3. Mọi text hiển thị cho user → đi qua `t()` trong lang.py
Thêm đủ vi + en cho user (fallback về vi khi thiếu). KHÔNG hardcode text trong handlers.
Text user phải: dễ hiểu, hướng dịch vụ, không lộ tên backend/provider.

### 3.1. Timezone bắt buộc
- Mọi logic ngày/giờ trong bot phải dùng helper giờ Việt Nam (`now_vn()`, `_today_str()`, `_next_midnight()`).
- KHÔNG dùng `datetime.now()` trực tiếp cho quota/ref/reset/ngày, order timestamps, plan expiry.
- Khi parse datetime cũ không có timezone: coi là **giờ Việt Nam**, không coi là `UTC`.

### 3.2. Metadata user cho admin/payment
- Lưu `username`/`first_name` sớm từ `/start`, callback và text input qua `update_user_profile()` để admin
  không bị thiếu danh tính user nếu người mua chưa từng lấy link.
- Thông báo admin SePay phải hiện user theo format `<code>user_id</code> (@username | first_name)`.
- Thông báo `SEPAY CAP GOI THANH CONG` phải kèm `Han goi` theo giờ Việt Nam.

### 4. Cấu trúc message
KHÔNG dùng dòng gạch ngang (`───`, `━━━`, `────`); cách đoạn bằng dòng trống để thân thiện
mobile. Theo `_build_loginlink_message` (handlers.py).

### 5. Sau mọi thay đổi
`python3 -m py_compile` (danh sách ở rule 0.4) + grep tìm tham chiếu cũ trước khi xóa.

### 6. KHÔNG đổi ngẫu nhiên
Rule expired cookie (90 ngày + 2022-2025). Mô hình access: free gated unlimited; ref +3 no-gate/ngày
reset 00:00; plan Basic/Pro 30 ngày. KHÔNG khôi phục DAILY_LIMIT/check-in/gift vào flow chính.

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
`systemctl restart netflixbot` (service `deploy/netflixbot.service`). KHÔNG dùng `nohup ... &`
từ shell (dễ đụng cổng webhook 8080 + bị kill theo shell).

### 12. Khác
Commit code, KHÔNG commit secret hay dữ liệu runtime: `local_config.py`, `orders.json`,
`user.json`, `cookie.txt`, `.env.bot`, `.venv/` đều bị .gitignore chặn.
Không log BOT_TOKEN / secret / toàn bộ cookie hoặc NFToken vào log.

### 13. Upload nhiều file
`COOKIE_UPLOAD_WINDOW=20` — nếu sửa handler upload, giữ cơ chế window + gia hạn cuối mỗi file.

## Constraints / Risks
- Token i18n: admin chỉ dùng tiếng Việt (bản en giữ cho fallback).
- Webhook SePay phải idempotent: cùng transaction id KHÔNG cấp 2 lần; đơn expired KHÔNG auto-cấp.
- `0.0.0.0:8080` = cổng webhook; tránh restart trùng cổng (dùng systemd restart, không nohup xen kẽ).
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
- Deploy = systemd service (template `deploy/netflixbot.service`) + env `deploy/env.example`
  → `/root/bot_netflix/.env.bot`. Restart: `systemctl restart netflixbot`; log: `journalctl -u netflixbot -f`.
- cookie.txt / PROXY_URLS.txt / user.json / orders.json: dữ liệu thật, backup trước khi test ghi đè.

## Non-Goals
- Không phải hệ thống "bán account": single pool; chỉ có plan Basic/Pro (no-gate quota), không có sub/tier khác.
- Không hỗ trợ proxy có auth; không hỗ trợ IPv6.
- Không dùng Telegram webhook mode; vẫn polling, webhook chỉ dành cho SePay thanh toán.

## Open Questions
- `_schedule_feedback_prompt` (feedback sau khi dùng link): chưa xác minh luồng đầy đủ khi
  làm việc với 3 thiết bị dùng chung URL.
- Thời điểm chính xác tạo bot (log sớm nhất 2026-07-31): chưa xác minh.
- `9remote.service` (/etc/systemd/system) — service remote dùng chung máy, không liên quan bot.
