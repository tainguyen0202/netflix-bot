# Netflix Login Link Bot

Bot Telegram tạo link đăng nhập Netflix tự động từ pool cookie — người dùng nhận link
hợp lệ 30 phút mà không bao giờ thấy cookie thô. Hỗ trợ tiếng Việt / English.

## Tính năng

- 🔗 Link đăng nhập 3 thiết bị (đổi token qua iOS Argo API, path `/login?nftoken=`)
- ⚡ Buffer link tự nạp + validate mỗi 150s, chống lặp account cho từng user
- 🍪 Nhập cookie đa định dạng: plain, Netscape tab, JSON Cookie-Editor (`.txt/.json/.zip`)
- 📂 `/loadcookies` — quét thư mục `Cookies/` đệ quy, tự xóa file trùng/đã xử lý
- 🔌 `/loadproxy` — quét thư mục `Proxy/`, dedup vào `PROXY_URLS.txt`
- 📎 `/addproxy` — nạp proxy qua chat (gửi file `.txt/.json/.zip` cho bot, dedup tự động)
- 💀 Tự xóa cookie dead (xác nhận từ API) + proxy dead (3 lần fail liên tiếp)
- 👥 Giới hạn 3 lượt/ngày + bonus giới thiệu, gate bắt buộc tham gia nhóm

## Yêu cầu

- Python 3.10+
- `pip install -r requirements.txt`

## Cấu hình

Sửa `config.py` trước khi chạy:

| Biến | Ý nghĩa |
|---|---|
| `BOT_TOKEN` | Token bot từ @BotFather (bắt buộc) |
| `ADMIN_IDS` | Danh sách user_id admin |
| `DAILY_LIMIT` | Lượt dùng mỗi ngày (mặc định 3) |
| `GROUP_USERNAMES` | Các nhóm bắt buộc phải tham gia |
| `ADMIN_TAG` | Tag hiển thị "Liên Hệ: Admin" |

## Cách chạy

```bash
pip install -r requirements.txt
python3 main.py
```

## Lệnh

**User**: `/start` · `/loginlink` · `/ref` · `/help`

**Admin**: `/admin` (panel nút) · `/loadcookies` · `/loadproxy` · `/addproxy` · `/addcookie` · `/addluot` · `/addcode` · `/msg`

## Cấu trúc

```
main.py      — khởi động bot, đăng ký lệnh, menu command
handlers.py  — commands/callback, parse cookie, quét thư mục
checker.py   — check cookie, generate/validate NFToken (iOS Argo)
storage.py   — pool cookie, user.json, giftcodes.json, link buffer
proxies.py   — proxy pool, scanner nền, tự xóa dead
lang.py      — chuỗi i18n (vi/en)
config.py    — cấu hình
```

## Lưu ý

- Dữ liệu thật (`cookie.txt`, `PROXY_URLS.txt`, `user.json`, `giftcodes.json`, `bot.log`)
  nằm trong `.gitignore` — không push lên GitHub
- `AGENT.md` = hướng dẫn cho agent sửa code · `WORK_PROGRESS.md` = tiến độ & quyết định
