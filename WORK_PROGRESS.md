# WORK_PROGRESS.md — Netflix Login Bot

## Project Name
Netflix Login Link Bot (@autologinnetflix_bot) — /root/bot-telegram/bot_netflix/bot_netflix/

## Start Date
Chưa xác minh chính xác — log sớm nhất 2026-07-31 (bot.log), thư mục tạo 2026-07-31 06:31.

## Goal
Cấp link đăng nhập Netflix tự động từ pool cookie. Mô hình access:
- Free: không giới hạn lượt, luôn phải qua gate (xác thực link).
- Ref: +3 no-gate/ngày cho mỗi ref thành công, reset 00:00.
- Plan Basic/Pro: 10/20 no-gate/ngày trong 30 ngày.
- Thanh toán: SePay tự động (webhook) và Binance/USDT bán tự động (admin duyệt inline).

## Baseline (2026-08-01 đầu phiên)
- Pool 368 cookie unique; bug lặp cookie #53 (33 lần) khi cấp link
- Cookie chỉ nhập được định dạng plain; upload 1 file/lần; quét folder thủ công
- Lệnh /reload (chỉ reload pool) + /loadfolder; proxy dead không bao giờ bị xóa khỏi file

## Design Decisions (đã chốt với user)
- 2026-08-30: Bỏ DAILY_LIMIT/check-in/gift code/donate; thay bằng free gated unlimited + ref + plan.
- 2026-08-30: Menu mới 4 hàng (🍿 Lấy Link / 👑 Mua Gói / 📊 + 👥 / 🌐 + ❓).
- 2026-08-30: SePay tự động (webhook + API Key), không cần nút "đã chuyển khoản".
- 2026-08-30: Binance chọn gói trước, admin chỉ bấm 1 nút Duyệt/Từ chối.
- 2026-08-30: Link4m chính → Layma backup → cả 2 lỗi → báo bảo trì, KHÔNG bypass trực tiếp.
- 2026-08-30: Order TTL 15 phút (sepay) / 30 phút (binance); auto-expire + edit message.
- 2026-08-30: UI user sạch: không dòng gạch ngang, không lộ backend/provider, xưng "Ngân hàng VN" / "Thanh toán USDT".
- 2026-08-30: Admin không cần tiếng Anh mới (giữ EN cũ fallback, không phát triển thêm).
- 2026-08-30: `addluot` đổi nghĩa thành "cộng no-gate bonus hôm nay", không hiện ở stats user.
- 2026-08-01: Đổi token qua iOS Argo API; path `/login?nftoken=`; 3 thiết bị chung URL
- 2026-08-01: Rule expired cookie 60 → **90 ngày** (giữ lọc dt 2022-2025)
- 2026-08-01: Format link message theo mockup (header/link/expire/uses/Liên Hệ Admin);
  admin thấy "∞ lượt", client thấy số lượt thật
- 2026-08-01: Upload nhiều file trong window **20s** (COOKIE_UPLOAD_WINDOW)
- 2026-08-01: `/loadfolder` → `/loadcookies` (đổi hẳn, không alias); **xóa /reload**;
  thêm `/loadproxy`; đưa cả 2 vào menu admin + panel nút (thay nút Reload)
- 2026-08-01: Proxy dead tự xóa khỏi PROXY_URLS.txt sau **3 lần fail liên tiếp**
  (scanner nền; chỉ scan-fail tính, runtime mark_bad chỉ cooldown)
- 2026-08-01: Nút donate lên menu chính (hàng 3, callback `donate`): "☕️ Mời Admin ly cà phê"
  / "☕️ Buy Admin a coffee"; donate_menu viết lại văn phong mượt (free 100%, ủng hộ tùy tâm);
  **xóa hẳn /notify** (cmd_notify, keys notify_text/notify_sending/notify_done, qr_caption);
  menu chính 4 hàng (help xuống hàng 4)
- 2026-08-01: Chuẩn hóa văn phong tin nhắn khách hàng: bỏ từ kỹ thuật khỏi tin hiển thị
  (searching/link_fail bỏ error raw, xóa blocked_token, no_live_cookie thân thiện, stats 🍪→🎟️);
  log lỗi chi tiết giữ ở logger (admin xem journalctl)
- 2026-08-02: Lệnh trong group/channel → chuyển hướng inbox riêng (`cmd_group_redirect`,
  đăng ký trước CommandHandlers bằng `filters.COMMAND & filters.ChatType.GROUPS`); bot trong
  nhóm chỉ để check join; ref deep-link click trong nhóm lưu `_pending_ref_global` (credit khi
  user /start ở DM); button_handler chặn callback không private. Group reply: "👋 Chào bạn,
  vui lòng nhắn tin riêng..." + nút URL "💬 Nhắn tin riêng với bot" (KHÔNG tự gửi menu vào DM)

## Task Checklist (2026-08-01 — tất cả hoàn thành)
- [x] Fix lặp cookie: ưu tiên good_list, exclude theo user + trong job
- [x] Parser Netscape tab (#HttpOnly_, ≥7 cột) + JSON Cookie-Editor (`_json_to_netscape`, sort nid trước)
- [x] parse_netflix_data trả cookie_count; report "🔍 Cookie phát hiện trong file"
- [x] Format link message mới + separator `─── 🔸 ───` (toàn repo)
- [x] Upload nhiều file (window 20s)
- [x] `/loadcookies`: scan đệ quy txt/json/zip, dedup, tự xóa file thừa + dirs rỗng,
      thông báo folder_empty, chạy qua asyncio.to_thread
- [x] `/loadproxy`: thư mục Proxy/, normalize ip:port, dedup vs PROXY_URLS.txt, xóa file thừa
- [x] Xóa /reload + /loadfolder + block NFTOKEN API cũ trong config.py
- [x] Menu commands admin (loadcookies/loadproxy) + 2 nút panel (loadcookies/loadproxy)
- [x] Proxy dead: _fail_count + MAX_FAIL=3 + ghi đè file lọc dead + stats "Proxy dead đã xóa"
- [x] Scan folder thật: 7384 file → 939 cookie mới; lần 2 dọn 939 file xử lý → folder sạch
- [x] Restart bot qua systemd-run; verify menu + buffer + proxy scanner (29 live)
- [x] Tạo AGENT.md + WORK_PROGRESS.md (2026-08-01)

## Progress Log
- **2026-08-30** — Thay đổi mô hình access & thanh toán hoàn chỉnh:
  - Bỏ donate/checkin/gift/daily-limit khỏi flow chính.
  - Menu mới theo layout user chốt.
  - `storage.py`: thêm order model, TTL, chống trùng pending, `expire_stale_orders`, `least_expired` cleanup.
  - `handlers.py`: UI mua gói Basic/Pro, Binance submit + admin duyệt inline, gate giữ nguyên + layma backup.
  - `sepay_webhook.py`: HTTP server 8080, idempotent, tự cấp gói, báo late payment.
  - `layma.py`: shortener backup.
  - `config.py`: plan/order/payment config, secret đọc từ env/local_config.
  - `main.py`: schedule expire_orders_job, start webhook server.
  - `lang.py`: dọn separator, ẩn backend, update stats/ref/plan text.
  - `AGENT.md` + `WORK_PROGRESS.md`: cập nhật mô hình mới.
  - `deploy/netflixbot.service` + `deploy/env.example`: service chuẩn.
  - Order TTL + edit message lifecycle đã có, chặn cấp nhầm khi expired.
  - Admin có thêm view: tất cả đơn, chi tiết đơn, gói active.
  - Command cũ (`/checkin`, `/addcode`) không còn đăng ký trong bot.
  - Git push lên `main` (commit `98a9827`).
- **2026-08-30** — Hoàn thiện UX thanh toán:
  - Luồng mua gói tách 2 bước: Chọn gói → Chọn cổng thanh toán.
  - QR ngân hàng SePay giờ là QR động theo đơn (`amount` + `addInfo=order_code` + `accountName`),
    quét ra đúng số tiền + đúng nội dung chuyển khoản.
  - Sau thanh toán/huỷ/hết hạn: xoá ảnh QR và gửi text xác nhận đơn thuần (không nút).
  - USDT giữ QR segno tĩnh (giống donate cũ) + text.
  - Thêm nút "❌ Huỷ đơn": bấm → đơn `cancelled`, xoá QR; bấm mua lại tạo đơn mới.
  - Toàn bộ text vi có dấu đầy đủ; EN cung cấp đầy đủ cho khách hàng; admin chỉ vi.
  - Restart qua systemd, webhook 200, không traceback.
- **2026-08-31** — Chuẩn hoá giờ Việt Nam ở tầng code:
  - Phát hiện VPS chạy `UTC`, khiến hạn gói/user stats/order timestamps lệch đúng 7 giờ so với giờ VN.
  - `storage.py`: thêm `VN_TZ` + `now_vn()`; chốt chính sách đúng là parse datetime cũ naive như giờ VN,
    không phải UTC.
  - Toàn bộ reset theo ngày (`_today_str`, `_next_midnight`, ref/quota/order TTL, plan expiry, stats hôm nay)
    chạy theo giờ Việt Nam, không phụ thuộc timezone hệ điều hành của VPS.
  - `handlers.py`: hiển thị hạn gói và các mốc order/admin detail theo giờ Việt Nam.
  - Quyết định chốt: về sau đổi VPS vẫn giữ giờ Việt Nam bằng code, KHÔNG chỉnh timezone toàn server.
- **2026-09-01** — Sửa timezone hạn gói SePay + metadata admin:
  - `storage.py`: sửa `_parse_iso_dt()` để legacy naive datetime được hiểu là giờ Việt Nam; thêm cơ chế
    tự dựng lại `plan_expires_at` từ lịch sử order `approved` khi phát hiện dữ liệu cũ đã bị lệch `+7h`.
  - Xác minh case thật user `1922883506`: hạn gói được diễn giải lại từ `05:45 - 29/11/2026` thành
    `22:45 - 28/11/2026` theo giờ VN.
  - `sepay_webhook.py`: thông báo `SEPAY CAP GOI THANH CONG` giờ có user format
    `<code>id</code> (@username | first_name)` + `Han goi`; thông báo `GIAO DICH DEN MUON` cũng thêm
    username/name cho admin dễ nhận diện.
  - Chuẩn hoá hiển thị thời gian trong luồng SePay về format `HH:MM - DD/MM/YYYY` thay vì raw ISO.
  - `storage.py` + `handlers.py`: thêm `update_user_profile()` và capture profile sớm từ `/start`,
    callback, text input để user mua gói trước khi lấy link vẫn có `username` trong các thông báo admin.
  - Verify: `python3 -m py_compile storage.py sepay_webhook.py handlers.py` PASS; smoke parse plan PASS.
- **2026-08-31** — Giao diện + dọn dữ liệu:
  - `cleanup_orders()`: tự xoá đơn `cancelled`/`expired` khi `approved_at` quá 15 phút
    (`CLEANUP_FINISHED_AFTER_MINUTES`), gắn vào `expire_orders_job`, xoá msg chat còn sót.
  - Giữ nguyên `pending/paid/approved/rejected`; đơn đã kết thúc bị dọn sạch sau 15 phút.
  - Admin order list gộp vào 1 helper `_admin_list_orders`, thêm nút lọc trạng thái
    (Tất cả / Đang chờ / Hoàn tất / Huỷ-Hết hạn).
  - Sửa bug `admin_binance_reject` nằm sai vị trí (unreachable) → nút Từ chối hoạt động lại.
  - Lần chạy thử tự dọn 13 đơn cancelled/expired lịch sử cũ (>15 phút) khỏi `orders.json`.
  - Verify: py_compile PASS + smoke cleanup PASS + bot restart systemd OK, push commit `c93d476`.
- **2026-08-31** — Nâng cấp admin:
  - Bộ lọc đơn nhóm đúng nghĩa: `done = approved+paid`, `closed = cancelled+expired+rejected`
    (`_FILTER_STATUS`); `list_orders(status=...)` nhận str hoặc list/tuple/set.
  - Thêm nút `❌ Huỷ đơn` cho đơn Binance/USDT (trước đây chỉ có ở SePay).
  - Màn `🔍 Tìm user`: nhập user_id → card thông tin + nút Cấp Basic/Pro, Thu hồi gói, Bonus.
    Dùng `user_exists()` (tránh tạo user rỗng khi tra cứu); cấp manual qua `grant_plan(source="manual")`
    KHÔNG tạo doanh thu.
  - Gộp stats admin vào `_admin_stats_text()` (bớt duplicate `cmd_admin` + callback `admin_stats`).
  - `admin_plan_overview` đếm user active từ `get_active_plan_counts()` → khớp với `admin_stats`.
  - Verify: py_compile PASS + smoke (filter, user card, active counts) PASS.
- **2026-08-16** (chính sách xoá cookie an toàn): link hết hạn 1h KHÔNG xoá cookie (không code theo
  dõi — trước đây chỉ do check_cookie báo DEAD mới xoá). Phát hiện `mark_dead`/`mark_permanent_dead`
  từng là dead code — mọi DEAD đều `delete_cookie` (xoá vĩnh viễn, không retry) → kho giảm nhanh do
  false-positive (proxy trả trang login/shell với cookie còn sống). Sửa: thêm `direct=True` cho
  `check_cookie` (chỉ gọi IP VPS, không proxy) + helper `_cookie_dead_policy`: DEAD rõ ràng (membership
  FORMER/NON/NEVER/ANONYMOUS) → xoá ngay; DEAD mơ hồ → xác minh lại qua VPS, VPS=LIVE/ERROR →
  `mark_dead` (temp, retry sau 1h, auto promote 24h), VPS=DEAD → xoá. Áp dụng 3 nơi: gen link,
  fill buffer, recheck 30p. Log "temp-dead (ambiguous, VPS=...)". Test policy 4 case PASS.
- **2026-08-16** (thêm lệnh /checkin): gõ `/checkin` trong **nhóm** → điểm danh ngay, reply hiện
  cho cả nhóm thấy; gõ trong **DM** → giữ gate nhóm (thiếu nhóm → nhắc join). Tách helper
  `_checkin_result_text` dùng chung cho nút "📅 Điểm danh" + lệnh. Thêm vào menu lệnh riêng tư
  ("Điểm danh nhận lượt / Daily check-in"). Đăng ký handler TRƯỚC cmd_group_redirect để không bị
  chặn. Thông báo đổi cách tích lượt gửi qua `/msg` (không thêm code). Test logic + py_compile PASS.
- **2026-08-16** (phiên điểm danh + menu mới): bỏ streak cũ (tự tăng khi lấy link) → **Điểm danh**:
  nút "📅 Điểm danh" bấm 1 lần/ngày = **+1 lượt HÔM NAY** (CHECKIN_DAILY_BONUS), đủ **7 ngày liên
  tiếp** thưởng thêm **+5 lượt hôm đó** (CHECKIN_MILESTONE), reset 00:00; bỏ lỡ 1 ngày → chuỗi về 0.
  `get_user_daily_limit = 3 + ref_hôm_nay + checkin_hôm_nay`. `record_use` bỏ streak/bonus mốc cũ
  (streak tách hẳn khỏi việc lấy link). Data thêm `checkin_streak`/`checkin_last`/`checkin_daily{}`.
  **Bỏ "Ref cả đời" khỏi hiển thị user** (ref_info/stats) — chỉ còn ref hôm nay; `referrals[]` giữ
  cho chống trùng + admin. **Menu mới 2 nút/hàng** theo mockup user (H1 Lấy Link; H2 Điểm danh|Giới
  thiệu; H3 Lượt dùng|Ủng hộ; H4 Ngôn ngữ|Trợ giúp) — rút gọn nút help/coffee. Admin stats thêm
  "Điểm danh hôm nay". Test ad-hoc check-in 9 case PASS + py_compile PASS + bot restart OK.
- **2026-08-16** (phiên ref bonus theo ngày): mỗi ref thành công = **+3 lượt dùng HÔM NAY**
  (REF_BONUS_PER_REF=3), cộng dồn trong ngày tối đa **10 ref/ngày** (+30 lượt, REF_DAILY_CAP=10),
  reset về 3 lượt mỗi 00:00. Bỏ bonus ref vĩnh viễn + cap cả đời 5 (MAX_REF_BONUS) — migration
  reset hết, `referrals[]` giữ hiển thị ref cả đời. Data model thêm `ref_daily: {ngày: count}`.
  Fix 4 bug: (1) chọn ngôn ngữ credit ref khi CHƯA đủ nhóm → giờ check nhóm trước;
  (2) join đủ nhóm qua `cmd_chat_member` không credit ref → giờ credit qua `_credit_pending_ref`;
  (3) `ref_input` hiển thị total_limit double-count ref_bonus → dùng `get_user_daily_limit` thống nhất;
  (4) `_pending_ref_global` không bao giờ dọn → lưu (referrer_id, ts) + cleanup 24h.
  admin_stats thêm "Ref hôm nay". Test ad-hoc storage 9 case PASS + py_compile PASS + bot restart OK.
- **2026-08-05** (phiên mới): thêm `/addproxy` — admin nạp proxy qua chat (txt/json/zip,
  window 20s, cap 20MB, dedup vs PROXY_URLS.txt qua add_proxy_lines, report
  proxy_chat_report); nút "📎 Nạp Proxy" trong panel admin; dispatcher
  handle_document_upload chuyển file proxy/cookie theo state; menu admin 9→10 lệnh;
  nhắc nhở file_upload_no_state khi admin gửi file chưa kích hoạt state (vẫn không nhận);
  donate_binance: QR tự sinh từ USDT_BEP20_ADDRESS qua segno (xóa BINANCE_FILE_ID — file_id sai từ commit đầu, log lỗi "Wrong file identifier");
  ZIP_FILE_LIMIT 500→5000 (config.py) dùng chung cookie + proxy, chuỗi cookie_zip_limited hiển thị {limit}
- **2026-07-31**: Dựng bot nền (theo log đầu tiên). Chưa xác minh chi tiết.
- **2026-08-01** (phiên chính):
  - Fix bug lặp cookie #53 → buffer đa dạng (46/122/94, 94/46/21); 3 test ad-hoc pass
  - Thêm hỗ trợ định dạng B (Netscape tab), D (Cookie-Editor), E (checker khác, bị lọc 90 ngày)
  - Scan cookie folder lần đầu: 990 cookie mới; phát hiện 2 thư mục con bị bỏ sót
    (NETFLIXCOOKIES 569 txt DEADFLIX, netflix cookie By KEn 6807 json)
  - Mở rộng scan đệ quy + nhánh json; sửa lỗi thứ tự sid/nid (dt=2022 lọt khi sid đứng trước)
  - Scan lần 2: +939 cookie (7384 file quét, 6445 xóa), pool 1358 → **2209**
  - Đổi /loadfolder→/loadcookies, thêm /loadproxy, xóa /reload, menu + panel nút mới
  - Proxy dead tự xóa sau 3 fail (test fail-count pass, reset-on-pass pass)

## Tests Run (2026-08-01)
- `python3 -m py_compile main.py handlers.py checker.py storage.py proxies.py lang.py config.py` → PASS
- Fix lặp cookie: 3 unit test ad-hoc (history exclusion, no-repeat-in-job, buffer skip) → PASS
- `parse_netflix_data` mẫu A–E: A/C/D vào pool, E bị lọc 90 ngày → PASS
- `_json_to_netscape` 300 file KEn: 184 cookie hợp lệ, 116 expired lọc đúng → PASS
- `_scan_cookie_folder` thật: 7384 files, +939 added, 6445 deleted (1.9s) → PASS; lần 2: 939 xóa, +0
- `_normalize_proxy`: loại auth/IPv6/thiếu port, giữ ip:port → PASS
- `_scan_proxy_folder` mẫu: +5 added, dedup đúng → PASS
- proxies fail-count: 3 vòng fail → xóa khỏi file; pass → reset; fail 1 → giữ → PASS
- `add_proxy_lines`: dedup vs file, cập nhật file_total → PASS (data test đã dọn)

## Tests Run (2026-08-16) — cookie import hardening + silent recheck
- 20 test ad-hoc PASS (`/tmp/opencode/test_fixes.py`):
  - `storage.add_cookies`: thêm mới đúng, KHÔNG wipe `_dead_set`/`_dead_times`/`_inflight_set`
  - Dedup theo RAM; ghi file fail → `_cookies` không đổi, trả 0
  - 4 luồng × 50 cookie → file + RAM không trùng lặp, RAM == file
  - B5: Netscape expiry float (`1750000000.0`) / scientific (`1.75e9`) hết hạn → bị lọc; tương lai giữ
  - B7: `SecureNetflixId` trước `NetflixId` → group chờ hợp sid đúng; group mồ côi (chỉ sid) bỏ an toàn
  - `skipped` đếm đúng dòng thiếu nid; `cookie_report`/`folder_report` hiển thị dòng skipped

## Deploy / Release Notes
- Bot restart bằng systemd-run transient (lệnh trong AGENT.md Current Status)
- Menu command set OK trong log: `✅ Command menu set (default + 1 admin scopes...)`
- Không có bản release/version chính thức; deploy = restart process

## Known Issues
- Nếu VPS chưa cài systemd service, bot vẫn chạy tạm bằng nohup — cần chuyển sang service file.
- Cổng 8080 chưa có HTTPS; nếu SePay yêu cầu HTTPS thì cần Nginx reverse proxy.
- `admin_stats` có thể chưa thống kê `expired` orders trong template (đã thêm vào `get_bot_stats`).
- `giftcode.json` vẫn còn file nhưng không dùng trong runtime — có thể xóa sau.

## Next Steps
- Deploy service systemd + env file để restart ổn định.
- Backup định kỳ cookie.txt/user.json/orders.json.
- (Tùy chọn) Thêm HTTPS cho webhook SePay (Nginx + Let's Encrypt).
- (Tùy chọn) Xác minh luồng feedback sau khi dùng link (`_schedule_feedback_prompt`).

## Changelog
- **2026-08-17** — Fix mất/gãy cookie khi import (kiểm thử trên 6 pack thật, 1395 cookie):
  - **BUG NGHIÊM TRỌNG `_clean()`**: `rstrip(".;, ")` cắt dấu `.` cuối token → cookie bị lưu
    vào pool với giá trị sai (dùng là fail). 554-zip 230/554, Hits 128/217, X219 55/219, marcoscerini
    1/1. Fix: chỉ strip whitespace + 1 dấu `;` cuối, **GIỮ dấu `.`** (padding base64url).
  - **BUG group chờ expiry**: nfvdid đứng trước NetflixId → cookie dùng expiry của **nfvdid**
    (sớm hơn) để xét hết hạn → cookie hợp lệ bị loại nhầm. Fix: khi hợp nid vào group chờ, dùng
    expiry của dòng NetflixId. (X219: 8 cookie hợp lệ trước đây bị vứt → giờ giữ.)
  - Comment-skip: dòng `#` (trừ `#HttpOnly_`) không tính skipped. Hits: skipped 651 → 0.
  - Lọc skipped chỉ đếm dòng "cookie thật" (`key=value`): ULPfile info / HIT header / login link
    không phồng số. 554-zip: 6094 → 0; X231: 920 → 0.
  - B6: Netscape 6-cột (`NetflixId=value` gộp) + guard fall-through nhánh raw khi cột name không
    phải cookie Netflix nhưng dòng chứa netflixid=.
  - Quoted value: regex 4 chỗ hỗ trợ `NetflixId="..."`.
  - Đổi label: `⏭️ Dòng không phải cookie Netflix (Bỏ qua)` (vi/en × cookie_report/folder_report).
  - Verify: 6 pack thật → 0 lost, 0 skipped, giá trị giữ nguyên đuôi `.`; 11 synthetic test mới +
    20 test cũ PASS; py_compile OK.
  - **Lưu ý deploy**: pool cookie.txt được rebuild từ 6 pack (1076 unique, giá trị đầy đủ).
    Standalone import không gọi `load_cookies()` trước `save_cookies()` → file ghi đè; cookie cũ
    ngoài 6 pack (nếu có) không được giữ. Không có backup (cookie.txt không tracked git).
- **2026-08-16** — Cookie import hardening + silent recheck:
  - `storage.add_cookies()` (giữ `_lock`, dedup theo RAM, ghi file trước → cập nhật `_cookies`, KHÔNG gọi `load_cookies()` để giữ `_dead_set`/`_inflight_set`/`_dead_times`) → hết race double-use cookie khi nhiều admin upload/scan cùng lúc, hết mất temp-dead khi import
  - `_process_cookie_lines`/`_scan_cookie_folder` dùng `add_cookies`; `_extract_netflix_id` chuyển về storage
  - `parse_netflix_data`: đếm `skipped` (dòng thiếu NetflixId), report có dòng ⏭️
  - B5: Netscape expiry hỗ trợ float/scientific → lọc đúng cookie quá hạn
  - B7: Netscape `SecureNetflixId`/`nfvdid` đứng trước `NetflixId` → vẫn gom được (trước đây mất sid)
  - Recheck 30 phút im lặng: bỏ tin "⏳ Đang kiểm tra..." + "✅ vẫn hoạt động"; chỉ nhắn khi phiên DEAD/ERROR; vẫn recheck + xóa cookie chết qua `_cookie_dead_policy`
