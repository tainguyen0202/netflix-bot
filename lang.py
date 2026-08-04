"""
Language strings — Vietnamese & English (fully synced 1:1)
"""

STRINGS = {
    "vi": {
        # ── Language picker ──
        "lang_prompt": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_vi": "🇻🇳 Tiếng Việt",
        "lang_en": "🇬🇧 English",

        # ── Welcome ──
        "welcome": (
            "🎬 <b>NETFLIX AUTO LOGIN</b>\n"
            "─── 🔸 ───\n\n"
            "👋 Chào <b>{name}</b>!\n\n"
            "🔗 Lấy link đăng nhập Netflix nhanh\n"
            "💻📱📺 Xem được trên mọi thiết bị\n"
            "Chỉ với 1 cú chạm, hệ thống sẽ cấp link đăng nhập thẳng vào Netflix trên mọi thiết bị (Điện thoại, Máy tính, Smart TV) mà không cần nhập mật khẩu.\n\n"
            "💡 <i>Chọn một nút bên dưới để lấy link đăng nhập ngay nhé!</i>"
        ),
        "group_redirect": (
            "👋 Chào {name}\n"
            "Vui lòng nhắn tin riêng với bot để sử dụng đầy đủ tính năng nhé!"
        ),

        # ── Buttons ──
        "btn_loginlink": "🍿 Lấy Link Xem Phim",
        "btn_ref": "👥 Giới thiệu",
        "btn_stats": "📊 Lượt dùng",
        "btn_lang": "🌐 Ngôn ngữ",
        "btn_help": "❓ Trợ giúp & Hướng dẫn",
        "btn_back": "🔙 Quay Lại",
        "btn_join": "📢 Tham Gia Nhóm",
        "btn_check_joined": "🔄 Kiểm Tra Lại",
        "btn_join_group": "📢 Tham Gia {group}",
        "btn_private_chat": "💬 Nhắn tin riêng với bot",
        "donate_btn_vietqr": "🇻🇳 Ngân Hàng VN (VietQR)",
        "donate_btn_binance": "🌐 Binance / Crypto",
        "btn_coffee": "☕️ Ủng hộ Admin",
        "btn_contact_admin": "📩 Liên hệ Admin",
        "admin_btn_import": "🍪 Nhập Cookie",
        "admin_btn_loadcookies": "📂 Quét Cookies",
        "admin_btn_loadproxy": "🔌 Load Proxy",
        "admin_btn_stats": "📊 Stats",

        # ── Join / gate ──
        "join_required": (
            "⚠️ <b>Bạn chưa tham gia đủ các nhóm bắt buộc!</b>\n\n"
            "📢 Các nhóm còn thiếu:\n{missing_list}\n\n"
            "👉 Ấn nút bên dưới để vào nhóm, sau đó ấn <b>🔄 Kiểm Tra Lại</b>."
        ),
        "join_confirmed": "✅ Đã xác nhận! Chào mừng bạn đến với bot.\n\n",

        # ── Login link flow ──
        "no_uses_left": "❌ Bạn đã hết lượt hôm nay.\n⏰ Quay lại sau 00:00 để lấy link mới.",
        "searching": (
            "⏳ Đang chuẩn bị liên kết đăng nhập...\n\n"
            "<i>Vui lòng đợi trong giây lát, hệ thống đang xử lý...</i>"
        ),
        "link_fail": "❌ Rất tiếc, hệ thống chưa thể tạo link ngay lúc này.\n\n💡 Vui lòng thử lại sau vài phút. Nếu vẫn không được, hãy liên hệ Admin để được hỗ trợ!",
        "no_live_cookie": "Hiện tại hệ thống chưa có tài khoản sẵn sàng. Vui lòng thử lại sau vài phút.",
        "old_features_removed": (
            "⚠️ Các chức năng cũ đã được gỡ khỏi bot này.\n\n"
            "Bot hiện chỉ còn:\n"
            "🔗 Nhận Link đăng nhập (máy tính / điện thoại / TV)"
        ),
        "redeem_removed": "⚠️ Redeem code đã được gỡ. Bot hiện chỉ còn /loginlink.",

        # ── Login link message ──
        "link_header": "🎬 <b>NETFLIX LOGIN LINK</b>",
        "link_plan": "Plan: {plan}",
        "link_mail": "Mail: {email}",
        "link_han": "Hạn: {billing}",
        "link_admin": "Liên Hệ: {admin}",
        "link_title": "🔗 <b>Link:</b>",
        "link_devices": (
            " 💻 <a href=\"{pc}\">Xem trên máy tính</a>\n"
            "📱 <a href=\"{phone}\">Xem trên điện thoại</a>\n"
            "📺 <a href=\"{tv}\">Xem trên TV</a>"
        ),
        "link_expire": "⏳ Hết hạn sau: ~1 giờ",
        "link_remaining": "📊 Còn {left}/{limit} lượt hôm nay",
        "link_remaining_inf": "📊 Còn ∞ lượt hôm nay",
        "link_bonus": "🎉 <b>NỔ BONUS! +{bonus} lượt dùng</b> (mốc streak)",

        # ── Session feedback (30 min recheck) ──
        "feedback_checking": "⏳ Đang kiểm tra lại phiên đăng nhập sau 30 phút...",
        "feedback_alive": "✅ Phiên đăng nhập trước đó vẫn còn hoạt động.",
        "feedback_dead": (
            "⚠️ Phiên đăng nhập trước đó không còn hoạt động.\n\n"
            "🔗 Dùng /loginlink hoặc nút Nhận Link để tạo link mới.\n"
            "📺 Mở link Xem trên TV trên trình duyệt TV để đăng nhập."
        ),
        "feedback_error": "⚠️ Tạm thời chưa kiểm tra lại được phiên đăng nhập này. Bạn thử lại sau ít phút.",

        # ── Account report ──
        "acc_header": "🎬 <b>NETFLIX ACCOUNT</b>",
        "acc_plan": "📋 <b>Plan:</b> {plan} ({quality})",
        "acc_region": "🌍 <b>Region:</b> <code>{country}</code> ({currency})",
        "acc_owner": "👤 <b>Owner:</b> {owner}",
        "acc_use_loginlink": "<i>Dùng /loginlink để lấy link đăng nhập</i>",

        # ── Donate ──
        "donate_menu": (
            "☕️ <b>MỜI ADMIN LY CÀ PHÊ DỰ ÁN</b>\n"
            "─── 🔸 ───\n\n"
            "👋 Chào bạn,\n\n"
            "Hệ thống <b>Netflix Auto Login</b> được vận hành hoàn toàn <b>Miễn Phí 100%</b> "
            "nhằm phục vụ cộng đồng xem phim chất lượng cao Premium UHD 4K.\n\n"
            "💡 <b>Lý do cần sự đồng hành từ bạn:</b>\n"
            "Để giữ hệ thống chạy mượt mà 24/7, Admin duy trì chi phí máy chủ VPS tốc độ cao "
            "và hệ thống kết nối riêng hàng tháng.\n\n"
            "🎉 <b>Ủng hộ tùy tâm:</b>\n"
            "Mọi sự đóng góp (dù chỉ là 1 ly cà phê 10k - 20k) đều là nguồn động lực rất lớn "
            "giúp Admin duy trì server lâu dài cho mọi người!\n\n"
            "─── 🔸 ───\n"
            "👇 <i>Chọn phương thức bạn muốn ủng hộ bên dưới nhé:</i>"
        ),
        "donate_vietqr_caption": (
            "💖 <b>CẢM ƠN BẠN ĐÃ ĐỒNG HÀNH VÀ ỦNG HỘ SERVER</b>\n\n"
            "Mã QR dưới đây đã tích hợp sẵn thông tin tài khoản và nội dung chuyển khoản. "
            "Bạn có thể ủng hộ tùy tâm tùy khả năng nhé!\n\n"
            "📌 <b>Thông tin chuyển khoản:</b>\n"
            "• Ngân hàng: <b>ACB BANK</b>\n"
            "• STK: <code>243951569</code> (Chạm để sao chép)\n"
            "• Chủ TK: <b>NGUYEN TAN TAI</b>\n"
            "• Nội dung CK: <code>UNGHONGUOINGHEO</code>\n\n"
            "💡 <b>Cách quét nhanh:</b> Lưu ảnh QR này về máy ➔ Mở App Ngân hàng ➔ "
            "Chọn \"Quét mã QR\" từ thư viện ảnh."
        ),
        "donate_binance_caption": (
            "💖 <b>THANK YOU FOR SUPPORTING THE SERVER!</b>\n\n"
            "Scan the QR to send crypto, or send directly to:\n\n"
            "📌 <b>Binance Pay ID:</b>\n<code>{pay_id}</code>\n\n"
            "📌 <b>USDT (BEP20) Wallet:</b>\n<code>{wallet}</code>\n\n"
            "💡 <b>Quick guide:</b> Copy the address ➔ Open your exchange/wallet app ➔ "
            "Send USDT on <b>BEP20</b> network only.\n\n"
            "❤️ Every contribution keeps the server free for everyone!"
        ),
        "qr_send_error": "❌ Lỗi gửi ảnh QR. Thử lại sau.",

        # ── Help ──
        "help": (
            "📢 HƯỚNG DẪN KHẮC PHỤC LỖI LOGIN NETFLIX\n\n"
            "1️⃣ Trước khi đăng nhập:\n"
            "✅ Android:\n"
            "• Xóa cache ứng dụng Netflix.\n"
            "• Mở link bằng trình duyệt mặc định của máy.\n\n"
            "✅ iPhone/iPad:\n"
            "• Mở link bằng Safari hoặc Chrome.\n\n"
            "⚠️ Không sử dụng chế độ Ẩn danh (Incognito) hoặc Riêng tư (Private).\n"
            "⚠️ Nếu đang dùng DNS/VPN tùy chỉnh, hãy tắt trước khi đăng nhập.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "2️⃣ Nếu không tự đăng nhập khi đã qua app netflix:\n"
            "1. Nhấn Open App.\n"
            "2. Khi Netflix mở ra nhưng chưa đăng nhập:\n"
            "   • Quay lại trình duyệt.\n"
            "   • Tiếp tục nhấn Open App.\n"
            "3. Lặp lại 2–3 lần.\n"
            "4. Đổi link mới.\n"
            "5. Nếu vẫn không được hãy xoá app tải lại và đổi link khác.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "3️⃣ Nếu xuất hiện lỗi đăng nhập khác:\n"
            "Mở trình duyệt và truy cập:\n"
            "https://www.netflix.com/unsupported\n"
            "Sau đó tải lại hoặc truy cập 2–3 lần rồi thử đăng nhập lại.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "4️⃣ Nếu vẫn không vào được:\n"
            "✅ Chuyển sang trình duyệt chính của máy (Safari/Chrome).\n"
            "✅ Bật chế độ Trang web cho máy tính (Desktop Site) (IPAD ONLY).\n"
            "✅ Đăng nhập và sử dụng Netflix trên trình duyệt web.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "5️⃣ Khuyến nghị:\n"
            "🔹 Cập nhật iOS/Android lên phiên bản mới nhất.\n"
            "🔹 Xóa cache và cookies của trình duyệt.\n"
            "🔹 Đổi sang mạng Wi-Fi hoặc 4G/5G khác.\n"
            "🔹 Nếu đã thử tất cả các cách trên nhưng vẫn lỗi, vui lòng liên hệ Admin để kiểm tra và hỗ trợ."
        ),

        # ── Stats ──
        "stats": (
            "📊 <b>Trạng thái của bạn</b>\n"
            "────────────────────────\n\n"
            "👤 User: <b>{name}</b>\n"
            "📅 Hôm nay: {today}\n"
            "🎟️ Đã nhận: {used}/{limit}\n"
            "✅ Còn lại: {remaining} lượt\n"
            "⏰ Reset sau: {reset}\n\n"
            "🔥 Chuỗi ngày: {streak} ngày liên tục (bonus: +{streak_bonus})\n"
            "────────────────────────\n"
            "🔗 Muốn thêm lượt? Giới thiệu bạn bè!\n"
            "• Mỗi 1 ref = +1 lượt/ngày (tối đa +{max_ref})\n"
            "• Ref hiện tại: {ref_count} (bonus: +{ref_bonus})\n"
        ),

        # ── Referral ──
        "ref_info": (
            "👥 <b>CHƯƠNG TRÌNH GIỚI THIỆU NHẬN LƯỢT DÙNG</b> 👥\n"
            "─── 🔸 ───\n"
            "Chia sẻ link giới thiệu của bạn cho bạn bè để nhận thêm lượt dùng bot miễn phí hàng ngày!\n\n"
            "🎁 <b>Các mốc thưởng bổ sung:</b>\n"
            "• Giới thiệu 1 người ➔ +1 lượt/ngày (Tổng 4 lượt)\n"
            "• Giới thiệu 3 người ➔ +2 lượt/ngày (Tổng 5 lượt)\n"
            "• Giới thiệu 7 người ➔ +3 lượt/ngày (Tổng 6 lượt)\n"
            "• Giới thiệu 15 người ➔ +4 lượt/ngày (Tổng 7 lượt)\n"
            "• Giới thiệu 30 người ➔ +5 lượt/ngày (Tổng 8 lượt)\n\n"
            "📊 <b>Thống kê của bạn:</b>\n"
            "• Đã giới thiệu thành công: <b>{ref_count}</b> người.\n"
            "• Lượt dùng hàng ngày hiện tại: <b>{total_limit}</b> lượt/ngày.\n\n"
            "🔗 <b>Link giới thiệu của bạn:</b>\n"
            "<code>{ref_link}</code>\n"
            "─── 🔸 ───\n"
            "<i>(Bấm vào link ở trên để tự động copy)</i>"
        ),
        "ref_new": "🎉 {name} đã giới thiệu bạn! Chào mừng!",
        "ref_got": "🔔 Bạn được +1 lượt/ngày! ({ref_count}/{max_ref}) nhờ giới thiệu {name}.",

        # ── Admin ──
        "not_admin": "⛔ Bạn không phải Admin.",
        "admin_denied": "⛔ Không có quyền.",
        "admin_stats": (
            "📊 <b>THỐNG KÊ BOT</b>\n"
            "─── 🔸 ───\n"
            "👥 Tổng users: {users}\n"
            "🟢 User dùng hôm nay: {users_today}\n"
            "🎁 Lượt hôm nay: {gets_today}\n"
            "📦 Tổng lượt từ trước: {gets_total}\n"
            "🔗 Tổng ref: {refs_total}\n"
            "🍪 Cookie: {cookies_remaining}/{cookies_total} (💀 {cookies_dead} | ⚰️ {cookies_perm})\n"
            "⚡ Link buffer: {buffer_validated}/{buffer_total} validated\n"
            "🌐 Proxy sống: {proxies_live} (file: {proxies_file})\n"
            "🗑️ Proxy dead đã xóa: {proxies_removed}\n"
            "🎟️ Gift code active: {codes} (còn {code_uses} lượt)"
        ),
        "admin_import_prompt": (
            "📎 Gửi <b>text</b> hoặc file <b>.txt/.zip/.json</b> chứa cookie.\n"
            "Chỉ cần <code>NetflixId</code>, có thể kèm <code>SecureNetflixId</code>."
        ),
        "cookie_report": (
            "📥 KẾT QUẢ NẠP COOKIE POOL\n"
            "─── 🔸 ───\n"
            "🔍 Cookie phát hiện trong file: {total_parsed}\n"
            "🧹 Cookie quá hạn/cũ (Bỏ qua): {expired}\n"
            "♻️ Cookie trùng lặp (Bỏ qua): {duplicate}\n"
            "✅ Cookie hợp lệ thêm vào Pool: {added}\n"
            "📊 Tổng Cookie Pool hiện tại: {pool}"
        ),
        "folder_report": (
            "📥 KẾT QUẢ QUÉT FOLDER\n"
            "─── 🔸 ───\n"
            "📂 Thư mục: {folder}\n"
            "📁 File quét: {files}\n"
            "✅ Cookie thêm vào Pool: {added}\n"
            "🗑️ File xóa (trùng/đã xử lý): {deleted}\n"
            "📊 Tổng Cookie Pool: {pool}"
        ),
        "folder_empty": "⚠️ Không tìm thấy file cookie nào trong thư mục:\n📂 {folder}\n\nGửi file .txt/.json/.zip vào đây rồi bấm lại.",
        "proxy_report": (
            "🔌 KẾT QUẢ NẠP PROXY\n"
            "─── 🔸 ───\n"
            "📂 Thư mục: {folder}\n"
            "📁 File quét: {files}\n"
            "✅ Proxy thêm vào file: {added}\n"
            "🗑️ File xóa (trùng/đã xử lý): {deleted}\n"
            "📊 Tổng proxy trong PROXY_URLS.txt: {total}"
        ),
        "proxy_empty": "⚠️ Không tìm thấy dòng proxy hợp lệ nào trong thư mục:\n📂 {folder}",
        "cookie_report_empty": "\n⚠️ Không tìm thấy dữ liệu hợp lệ",
        "cookie_zip_limited": "⚠️ Chỉ xử lý 500 file đầu trong ZIP\n\n",
        "cookie_file_not_received": "⚠️ Không nhận được file.",
        "cookie_file_too_big": "❌ File quá lớn (max 20MB).",
        "cookie_file_download_error": "❌ Lỗi tải file: {error}",
        "cookie_file_json_error": "❌ Lỗi đọc JSON: {error}",
        "cookie_file_zip_error": "❌ Lỗi đọc ZIP: {error}",
        "cookie_file_bad_type": "❌ Chỉ nhận file .txt, .zip hoặc .json.",
        "cookie_file_process_error": "❌ Lỗi xử lý file: {error}",
        "addluot_usage": "Cách dùng:\n/addluot <số_lượt>\n/addluot <user_id> <số_lượt>",
        "addluot_bad_format": "Sai định dạng. Ví dụ: /addluot 123456789 5",
        "addluot_positive": "Số lượt phải > 0",
        "addluot_done": "✅ Đã cộng {amount} lượt cho user <code>{target_id}</code>\nLượt hiện tại: <b>{new_total}</b>",
        "addcode_usage": "Cách dùng:\n/addcode <CODE> <SỐ_LƯỢT> [SỐ_NGƯỜI_DÙNG]\nVí dụ: /addcode ANHYEUEM 5 1",
        "addcode_bad_uses": "Số lượt không hợp lệ.",
        "addcode_bad_claims": "Số người dùng code không hợp lệ.",
        "addcode_fail": "❌ {err}",
        "addcode_done": (
            "✅ Tạo gift code thành công\n"
            "Code: <code>{code}</code>\n"
            "Số lượt cộng: <b>{uses}</b>\n"
            "Số lượt nhập code: <b>{claims}</b>"
        ),
        "msg_usage": (
            "📢 <b>Cách dùng:</b>\n"
            "<code>/msg nội dung tin nhắn</code>\n\n"
            "<b>Ví dụ:</b>\n"
            "<code>/msg Bot cập nhật phiên bản mới!</code>"
        ),
        "no_users": "⚠️ Chưa có user nào trong hệ thống.",
        "msg_sending": "📢 Đang gửi tin nhắn tới {count} users...",
        "msg_done": "✅ Đã gửi xong!\n📨 Thành công: {sent}/{total}\n❌ Thất bại: {failed}",
        "broadcast_header": (
            "📢 <b>THÔNG BÁO TỪ ADMIN</b>\n"
            "─── 🔸 ───\n\n"
            "{content}\n\n"
            "─── 🔸 ───"
        ),
    },

    "en": {
        # ── Language picker ──
        "lang_prompt": "🌐 Chọn ngôn ngữ / Choose language:",
        "lang_vi": "🇻🇳 Tiếng Việt",
        "lang_en": "🇬🇧 English",

        # ── Welcome ──
        "welcome": (
            "🎬 <b>NETFLIX AUTO LOGIN</b>\n"
            "─── 🔸 ───\n\n"
            "👋 Hello <b>{name}</b>!\n\n"
            "🔗 Get a Netflix login link quickly\n"
            "💻📱📺 Works on every device\n"
            "One tap — the system gives you a login link straight into Netflix on any device (Phone, Computer, Smart TV) without a password.\n\n"
            "💡 <i>Choose an option below to get your login link now!</i>"
        ),
        "group_redirect": (
            "👋 Hello {name}!\n"
            "Please message the bot privately to use all the features!"
        ),

        # ── Buttons ──
        "btn_loginlink": "🍿 Get Watch Link",
        "btn_ref": "👥 Referral",
        "btn_stats": "📊 My Status",
        "btn_lang": "🌐 Language",
        "btn_help": "❓ Help & Guide",
        "btn_back": "🔙 Back",
        "btn_join": "📢 Join Group",
        "btn_check_joined": "🔄 Check Again",
        "btn_join_group": "📢 Join {group}",
        "btn_private_chat": "💬 Message the bot privately",
        "donate_btn_vietqr": "🇻🇳 Vietnam Bank (VietQR)",
        "donate_btn_binance": "🌐 Binance / Crypto",
        "btn_coffee": "☕️ Support Admin",
        "btn_contact_admin": "📩 Contact Admin",
        "admin_btn_import": "🍪 Import Cookies",
        "admin_btn_loadcookies": "📂 Scan Cookies",
        "admin_btn_loadproxy": "🔌 Load Proxy",
        "admin_btn_stats": "📊 Stats",

        # ── Join / gate ──
        "join_required": (
            "⚠️ <b>You have not joined all required groups!</b>\n\n"
            "📢 Missing groups:\n{missing_list}\n\n"
            "👉 Press the buttons below to join, then press <b>🔄 Check Again</b>."
        ),
        "join_confirmed": "✅ Verified! Welcome to the bot.\n\n",

        # ── Login link flow ──
        "no_uses_left": "❌ You have run out of uses today.\n⏰ Come back after 00:00 to get a new link.",
        "searching": (
            "⏳ Preparing your login link...\n\n"
            "<i>Please wait a moment, our system is processing...</i>"
        ),
        "link_fail": "❌ Sorry, the system could not create a link right now.\n\n💡 Please try again in a few minutes. If it still fails, contact Admin for support!",
        "no_live_cookie": "No accounts are available right now. Please try again in a few minutes.",
        "old_features_removed": (
            "⚠️ Old features have been removed from this bot.\n\n"
            "This bot now only has:\n"
            "🔗 Get Login Link (computer / phone / TV)"
        ),
        "redeem_removed": "⚠️ Redeem code was removed. This bot now only has /loginlink.",

        # ── Login link message ──
        "link_header": "🎬 <b>NETFLIX LOGIN LINK</b>",
        "link_plan": "Plan: {plan}",
        "link_mail": "Mail: {email}",
        "link_han": "Billing: {billing}",
        "link_admin": "Contact: {admin}",
        "link_title": "🔗 <b>Link:</b>",
        "link_devices": (
            " 💻 <a href=\"{pc}\">Watch on computer</a>\n"
            "📱 <a href=\"{phone}\">Watch on phone</a>\n"
            "📺 <a href=\"{tv}\">Watch on TV</a>"
        ),
        "link_expire": "⏳ Expires in: ~1 hour",
        "link_remaining": "📊 {left}/{limit} uses left today",
        "link_remaining_inf": "📊 ∞ uses left today",
        "link_bonus": "🎉 <b>BONUS! +{bonus} uses</b> (streak milestone)",

        # ── Session feedback (30 min recheck) ──
        "feedback_checking": "⏳ Re-checking your login session after 30 minutes...",
        "feedback_alive": "✅ Your previous login session is still active.",
        "feedback_dead": (
            "⚠️ Your previous login session is no longer active.\n\n"
            "🔗 Use /loginlink or the Get Link button to create a new link.\n"
            "📺 Open the TV link on your TV browser to sign in."
        ),
        "feedback_error": "⚠️ Could not re-check this session right now. Try again in a few minutes.",

        # ── Account report ──
        "acc_header": "🎬 <b>NETFLIX ACCOUNT</b>",
        "acc_plan": "📋 <b>Plan:</b> {plan} ({quality})",
        "acc_region": "🌍 <b>Region:</b> <code>{country}</code> ({currency})",
        "acc_owner": "👤 <b>Owner:</b> {owner}",
        "acc_use_loginlink": "<i>Use /loginlink to get your login link</i>",

        # ── Donate ──
        "donate_menu": (
            "☕️ <b>BUY ADMIN A COFFEE</b>\n"
            "─── 🔸 ───\n\n"
            "👋 Hello,\n\n"
            "This <b>Netflix Auto Login</b> system is maintained <b>100% Free</b> for the community "
            "to enjoy Premium UHD 4K movies.\n\n"
            "💡 <b>Why we need your support:</b>\n"
            "To keep the system running smoothly 24/7, we cover monthly costs for high-speed VPS "
            "servers and dedicated proxy systems.\n\n"
            "🎉 <b>Optional Donation:</b>\n"
            "Every contribution (even a small coffee) gives us huge motivation to keep this server "
            "alive for everyone!\n\n"
            "─── 🔸 ───\n"
            "👇 <i>Choose your preferred donation method below:</i>"
        ),
        "donate_vietqr_caption": (
            "💖 <b>THANK YOU FOR SUPPORTING THE SERVER!</b>\n\n"
            "The QR below already includes the bank account and transfer details. "
            "Donate any amount you like!\n\n"
            "📌 <b>Bank transfer info:</b>\n"
            "• Bank: <b>ACB BANK</b>\n"
            "• Account No: <code>243951569</code> (Tap to copy)\n"
            "• Account Name: <b>NGUYEN TAN TAI</b>\n"
            "• Reference: <code>UNGHONGUOINGHEO</code>\n\n"
            "💡 <b>Quick scan:</b> Save this QR ➔ Open your banking app ➔ "
            "Choose \"Scan QR\" from the gallery."
        ),
        "donate_binance_caption": (
            "💖 <b>THANK YOU FOR SUPPORTING THE SERVER!</b>\n\n"
            "Scan the QR to send crypto, or send directly to:\n\n"
            "📌 <b>Binance Pay ID:</b>\n<code>{pay_id}</code>\n\n"
            "📌 <b>USDT (BEP20) Wallet:</b>\n<code>{wallet}</code>\n\n"
            "💡 <b>Quick guide:</b> Copy the address ➔ Open your exchange/wallet app ➔ "
            "Send USDT on <b>BEP20</b> network only.\n\n"
            "❤️ Every contribution keeps the server free for everyone!"
        ),
        "qr_send_error": "❌ Failed to send QR image. Try again later.",

        # ── Help ──
        "help": (
            "📢 NETFLIX LOGIN FIX GUIDE\n\n"
            "1️⃣ Before logging in:\n"
            "✅ Android:\n"
            "• Clear the Netflix app cache.\n"
            "• Open the link in your device's default browser.\n\n"
            "✅ iPhone/iPad:\n"
            "• Open the link with Safari or Chrome.\n\n"
            "⚠️ Do not use Incognito / Private mode.\n"
            "⚠️ If you use a custom DNS/VPN, turn it off before logging in.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "2️⃣ If it does not auto-login when the Netflix app opens:\n"
            "1. Tap Open App.\n"
            "2. If Netflix opens but you are not logged in:\n"
            "   • Go back to the browser.\n"
            "   • Tap Open App again.\n"
            "3. Repeat 2–3 times.\n"
            "4. Get a new link.\n"
            "5. Still not working? Uninstall the app, reinstall it, and get another link.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "3️⃣ If another login error appears:\n"
            "Open your browser and go to:\n"
            "https://www.netflix.com/unsupported\n"
            "Then reload or visit it 2–3 times and try logging in again.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "4️⃣ If you still cannot get in:\n"
            "✅ Switch to your device's main browser (Safari/Chrome).\n"
            "✅ Enable Desktop Site mode (IPAD ONLY).\n"
            "✅ Log in and use Netflix in the web browser.\n\n"
            "⸻⸻⸻⸻⸻\n\n"
            "5️⃣ Recommendations:\n"
            "🔹 Update iOS/Android to the latest version.\n"
            "🔹 Clear browser cache and cookies.\n"
            "🔹 Switch to another Wi-Fi or 4G/5G network.\n"
            "🔹 If you tried everything and it still fails, contact the Admin for help."
        ),

        # ── Stats ──
        "stats": (
            "📊 <b>Your Status</b>\n"
            "────────────────────────\n\n"
            "👤 User: <b>{name}</b>\n"
            "📅 Today: {today}\n"
            "🎟️ Used: {used}/{limit}\n"
            "✅ Remaining: {remaining} uses\n"
            "⏰ Resets in: {reset}\n\n"
            "🔥 Streak: {streak} days (bonus: +{streak_bonus})\n"
            "────────────────────────\n"
            "🔗 Want more uses? Refer friends!\n"
            "• Each ref = +1 use/day (max +{max_ref})\n"
            "• Current refs: {ref_count} (bonus: +{ref_bonus})\n"
        ),

        # ── Referral ──
        "ref_info": (
            "👥 <b>REFERRAL PROGRAM — GET FREE USES</b> 👥\n"
            "─── 🔸 ───\n"
            "Share your referral link with friends to get more free bot uses every day!\n\n"
            "🎁 <b>Bonus milestones:</b>\n"
            "• Refer 1 person ➔ +1 use/day (Total 4 uses)\n"
            "• Refer 3 people ➔ +2 use/day (Total 5 uses)\n"
            "• Refer 7 people ➔ +3 use/day (Total 6 uses)\n"
            "• Refer 15 people ➔ +4 use/day (Total 7 uses)\n"
            "• Refer 30 people ➔ +5 use/day (Total 8 uses)\n\n"
            "📊 <b>Your stats:</b>\n"
            "• Successfully referred: <b>{ref_count}</b> people.\n"
            "• Current daily uses: <b>{total_limit}</b> uses/day.\n\n"
            "🔗 <b>Your referral link:</b>\n"
            "<code>{ref_link}</code>\n"
            "─── 🔸 ───\n"
            "<i>(Tap the link above to copy it)</i>"
        ),
        "ref_new": "🎉 {name} referred you! Welcome!",
        "ref_got": "🔔 You got +1 use/day! ({ref_count}/{max_ref}) thanks to {name}.",

        # ── Admin ──
        "not_admin": "⛔ You are not an Admin.",
        "admin_denied": "⛔ No permission.",
        "admin_stats": (
            "📊 <b>BOT STATS</b>\n"
            "─── 🔸 ───\n"
            "👥 Total users: {users}\n"
            "🟢 Users active today: {users_today}\n"
            "🎁 Uses today: {gets_today}\n"
            "📦 Total uses all-time: {gets_total}\n"
            "🔗 Total refs: {refs_total}\n"
            "🍪 Cookies: {cookies_remaining}/{cookies_total} (💀 {cookies_dead} | ⚰️ {cookies_perm})\n"
            "⚡ Link buffer: {buffer_validated}/{buffer_total} validated\n"
            "🌐 Live proxies: {proxies_live} (file: {proxies_file})\n"
            "🗑️ Dead proxies removed: {proxies_removed}\n"
            "🎟️ Active gift codes: {codes} ({code_uses} uses left)"
        ),
        "admin_import_prompt": (
            "📎 Send <b>text</b> or a <b>.txt/.zip/.json</b> file containing cookies.\n"
            "Only <code>NetflixId</code> is required; <code>SecureNetflixId</code> is optional."
        ),
        "cookie_report": (
            "📥 COOKIE POOL IMPORT RESULT\n"
            "─── 🔸 ───\n"
            "🔍 Lines scanned: {total_parsed}\n"
            "🧹 Expired/old cookies (skipped): {expired}\n"
            "♻️ Duplicate cookies (skipped): {duplicate}\n"
            "✅ Valid cookies added to Pool: {added}\n"
            "📊 Current Cookie Pool: {pool}"
        ),
        "cookie_report_empty": "\n⚠️ No valid data found",
        "cookie_zip_limited": "⚠️ Only first 500 files in ZIP processed\n\n",
        "folder_report": (
            "📥 FOLDER SCAN RESULT\n"
            "─── 🔸 ───\n"
            "📂 Folder: {folder}\n"
            "📁 Files scanned: {files}\n"
            "✅ Cookies added to Pool: {added}\n"
            "🗑️ Files deleted (duplicate/processed): {deleted}\n"
            "📊 Total Cookie Pool: {pool}"
        ),
        "folder_empty": "⚠️ No cookie files found in folder:\n📂 {folder}\n\nPut .txt/.json/.zip files there and try again.",
        "proxy_report": (
            "🔌 PROXY LOAD RESULT\n"
            "─── 🔸 ───\n"
            "📂 Folder: {folder}\n"
            "📁 Files scanned: {files}\n"
            "✅ Proxies added to file: {added}\n"
            "🗑️ Files deleted (duplicate/processed): {deleted}\n"
            "📊 Total proxies in PROXY_URLS.txt: {total}"
        ),
        "proxy_empty": "⚠️ No valid proxy lines found in folder:\n📂 {folder}",
        "cookie_file_not_received": "⚠️ File not received.",
        "cookie_file_too_big": "❌ File too large (max 20MB).",
        "cookie_file_download_error": "❌ Download error: {error}",
        "cookie_file_json_error": "❌ JSON parse error: {error}",
        "cookie_file_zip_error": "❌ ZIP parse error: {error}",
        "cookie_file_bad_type": "❌ Only .txt, .zip or .json files are accepted.",
        "cookie_file_process_error": "❌ File processing error: {error}",
        "addluot_usage": "Usage:\n/addluot <amount>\n/addluot <user_id> <amount>",
        "addluot_bad_format": "Invalid format. Example: /addluot 123456789 5",
        "addluot_positive": "Amount must be > 0",
        "addluot_done": "✅ Added {amount} uses for user <code>{target_id}</code>\nCurrent uses: <b>{new_total}</b>",
        "addcode_usage": "Usage:\n/addcode <CODE> <USES> [MAX_CLAIMS]\nExample: /addcode ANHYEUEM 5 1",
        "addcode_bad_uses": "Invalid uses amount.",
        "addcode_bad_claims": "Invalid max claims.",
        "addcode_fail": "❌ {err}",
        "addcode_done": (
            "✅ Gift code created\n"
            "Code: <code>{code}</code>\n"
            "Uses added: <b>{uses}</b>\n"
            "Max claims: <b>{claims}</b>"
        ),
        "msg_usage": (
            "📢 <b>Usage:</b>\n"
            "<code>/msg message content</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/msg Bot updated to a new version!</code>"
        ),
        "no_users": "⚠️ No users in the system yet.",
        "msg_sending": "📢 Sending message to {count} users...",
        "msg_done": "✅ Done!\n📨 Success: {sent}/{total}\n❌ Failed: {failed}",
        "broadcast_header": (
            "📢 <b>ANNOUNCEMENT FROM ADMIN</b>\n"
            "─── 🔸 ───\n\n"
            "{content}\n\n"
            "─── 🔸 ───"
        ),
    },
}


def t(key, lang="vi", **kwargs):
    """Get translated string."""
    s = STRINGS.get(lang, STRINGS["vi"]).get(key, STRINGS["vi"].get(key, key))
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError):
            return s
    return s
