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
            "\n"
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
        "btn_loginlink": "🍿 Lấy Link Xem Phim 🍿",
        "btn_buy_plan": "👑 Mua Gói 👑",
        "btn_ref": "👥 Giới thiệu",
        "btn_stats": "📊 Lượt dùng",
        "btn_lang": "🌐 Ngôn ngữ",
        "btn_help": "❓ Trợ giúp",
        "btn_back": "🔙 Quay Lại",
        "btn_join": "📢 Tham Gia Nhóm",
        "btn_check_joined": "🔄 Kiểm Tra Lại",
        "btn_join_group": "📢 Tham Gia {group}",
        "btn_private_chat": "💬 Nhắn tin riêng với bot",
        "btn_contact_admin": "📩 Liên hệ Admin",
        "admin_btn_import": "🍪 Nhập Cookie",
        "admin_btn_loadcookies": "📂 Quét Cookies",
        "admin_btn_loadproxy": "🔌 Load Proxy",
        "admin_btn_addproxy": "📎 Nạp Proxy",
        "admin_btn_stats": "📊 Stats",
        "admin_btn_orders": "📦 Đơn hàng",
        "admin_btn_resources": "🔧 Tài nguyên",
        "admin_btn_plans": "👑 Gói active",
        "admin_btn_user_search": "🔍 Tìm user",
        "admin_user_search_prompt": "Nhập <b>User ID</b> để tra cứu:",
        "admin_user_not_found": "❌ Không tìm thấy user này.",
        "admin_user_bonus_bad": "❌ Số lượng không hợp lệ.",
        "admin_user_view": (
            "👤 <b>USER</b> <code>{user_id}</code>\n"
            "👑 Gói: <b>{plan_name}</b>\n"
            "📅 Hạn: {plan_expires}\n"
            "🎟️ Còn: {plan_left}/{plan_quota}"
        ),
        "admin_user_grant_done": "✅ Đã cấp gói <b>{plan}</b> cho user.",
        "admin_user_remove_done": "✅ Đã thu hồi gói.",
        "admin_removeplan_usage": "Cú pháp: /removeplan <user_id>",
        "admin_removeplan_done": "✅ Đã hủy gói của user <code>{user_id}</code>.",
        "admin_removeplan_not_found": "❌ Không tìm thấy user này.",
        "admin_user_bonus_prompt": "Nhập số lượt bonus cho user <code>{user_id}</code>:",
        "admin_user_bonus_done": "✅ Đã cộng <b>{amount}</b> lượt bonus cho user <code>{user_id}</code>.\nCòn lại hôm nay: <b>{left}</b>.",
        "admin_btn_grant_basic": "👑 Cấp Basic",
        "admin_btn_grant_pro": "👑 Cấp Pro",
        "admin_btn_remove_plan": "↩️ Thu hồi gói",
        "admin_btn_add_bonus": "➕ Bonus",
        "admin_btn_filter_all": "Tất cả",
        "admin_btn_filter_pending": "⏳ Đang chờ",
        "admin_btn_filter_done": "✅ Hoàn tất",
        "admin_btn_filter_closed": "🚫 Huỷ/Hết hạn",

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

        # ── Link4m gate ──
        "shrinkme_gate_msg": (
            "🔐 <b>XÁC THỰC ĐỂ NHẬN LINK NETFLIX</b>\n"
            "\n"
            "💡 <i>Tài khoản free luôn cần vượt link. Nếu bạn có ref thưởng hoặc gói đang hoạt động, bot sẽ tự bỏ qua bước này.</i>\n\n"
            "1️⃣ Copy link dưới đây và mở bằng trình duyệt ngoài (Chrome/Safari):\n"
            "🔗 <code>{url}</code>\n\n"
            "2️⃣ Đợi ~15-30s, hoàn tất các bước trên trang theo hướng dẫn\n"
            "3️⃣ Hệ thống đưa bạn quay lại bot → nhận ngay link Netflix\n\n"
            "💡 <i>Lỡ đóng trang? Copy lại link trên.\n"
            "Chưa nhận được link Netflix? Gõ /loginlink để lấy link mới.</i>"
        ),
        "shrinkme_invalid": (
            "⌛ Liên kết xác thực đã hết hạn hoặc đã được sử dụng.\n\n"
            "👉 Vui lòng gõ /loginlink để lấy liên kết mới nhé!"
        ),
        "gate_maintenance": "⚠️ Hệ thống vượt link đang bảo trì. Vui lòng thử lại sau ít phút.",
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
        "link_remaining": "📊 Gói hôm nay còn {left}/{limit} lượt không cần vượt",
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

        "plan_menu": (
            "👑 <b>MUA GÓI KHÔNG CẦN VƯỢT LINK</b>\n"
            "\n"
            "• Gói Basic: {basic_vnd} VND / {basic_usdt} USDT\n"
            "  {basic_daily} link/ngày trong {days} ngày\n\n"
            "• Gói Pro: {pro_vnd} VND / {pro_usdt} USDT\n"
            "  {pro_daily} link/ngày trong {days} ngày\n\n"
            "Chọn gói bạn muốn mua."
        ),
        "plan_basic_btn": "⭐️ Gói Basic",
        "plan_pro_btn": "👑 Gói Pro",
        "plan_payment_step": (
            "💳 <b>CHỌN CỔNG THANH TOÁN</b>\n"
            "\n"
            "Gói: <b>{plan}</b>\n"
            "Giá: <b>{price}</b>\n"
            "• Thời hạn: {days} ngày ({daily} link/ngày)\n\n"
            "Chọn cổng thanh toán bên dưới."
        ),
        "pay_sepay": "Basic • Ngân hàng VN",
        "pay_binance": "Basic • Thanh toán USDT",
        "pay_sepay_pro": "Pro • Ngân hàng VN",
        "pay_binance_pro": "Pro • Thanh toán USDT",
        "plan_basic_sepay_btn": "🏦 Ngân hàng Việt Nam",
        "plan_basic_binance_btn": "💵 Cổng USDT (Crypto)",
        "plan_pro_sepay_btn": "🏦 Ngân hàng Việt Nam",
        "plan_pro_binance_btn": "💵 Cổng USDT (Crypto)",
        "payment_bank": "Ngân hàng VN",
        "payment_usdt": "Thanh toán USDT",
        "sepay_payment": (
            "🏦 <b>THANH TOÁN GÓI {plan}</b>\n\n"
            "• Giá: <b>{amount_vnd} VND</b>\n"
            "• Thời hạn: <b>{days} ngày</b> ({daily} link/ngày)\n\n"
            "📋 Thông tin chuyển khoản:\n"
            "• Ngân hàng: <b>{bank_bin}</b>\n"
            "• Số TK: <code>{bank_account}</code>\n"
            "• Tên: <code>{bank_holder}</code>\n"
            "• Nội dung: <code>{order_code}</code>\n\n"
            "⚡ Hệ thống sẽ tự động kích hoạt sau khi nhận được tiền."
        ),
        "binance_payment": (
            "🌐 <b>THANH TOÁN USDT</b>\n\n"
            "• Gói: <b>{plan}</b>\n"
            "• Số tiền: <b>{amount_usdt} USDT</b>\n\n"
            "📌 Chọn 1 trong 2 hình thức chuyển:\n\n"
            "1. Binance Pay ID:\n<code>{pay_id}</code>\n\n"
            "2. Ví BEP20 (BSC):\n<code>{wallet}</code>\n\n"
            "• Mã đơn: <code>{order_code}</code>\n\n"
            "⚠️ Sau khi chuyển xong, vui lòng gửi Mã giao dịch (TxID / Order ID) vào chat để admin duyệt."
        ),
        "binance_tx_received": "✅ Đã nhận mã giao dịch USDT. Admin sẽ kiểm tra và duyệt sớm nhất có thể.",
        "binance_tx_invalid": "❌ Không tìm thấy đơn thanh toán USDT đang chờ. Hãy bấm Mua Gói để tạo đơn mới.",
        "plan_approved": "✅ Gói <b>{plan}</b> đã được kích hoạt thành công cho tài khoản của bạn.",
        "plan_rejected": "❌ Yêu cầu thanh toán của bạn đã bị từ chối. Hãy kiểm tra lại giao dịch và tạo đơn mới.",
        "plan_cancelled": "❌ Đơn của bạn đã được huỷ. Nếu muốn mua lại, hãy bấm 👑 Mua Gói.",
        "order_status": (
            "🧾 <b>TRẠNG THÁI ĐƠN</b>\n\n"
            "• Trạng thái: <b>{status}</b>\n"
            "• Gói: <b>{plan}</b>\n"
            "• Cổng: <b>{provider}</b>\n"
            "• Số tiền: <b>{amount}</b>\n\n"
            "📌 Thông tin đơn:\n"
            "• Mã TT: <code>{order_code}</code>\n"
            "• Hết hạn: {expires_at} (giờ VN)\n"
            "• Mã giao dịch: <code>{tx}</code>"
        ),
        "order_pending": "Chờ thanh toán",
        "order_paid": "Đã nhận thanh toán",
        "order_approved": "Đã kích hoạt gói",
        "order_rejected": "Bị từ chối",
        "order_expired": "Đã hết hạn",
        "order_cancelled": "Đã huỷ",
        "btn_cancel_order": "❌ Huỷ đơn",
        "order_expired_text": "⏰ Đơn của bạn đã hết hạn. Nếu vẫn muốn mua, vui lòng tạo đơn mới.",
        "gift_removed": "⚠️ Gift code đã được gỡ khỏi bot này.",
        "checkin_removed": "⚠️ Điểm danh đã được gỡ khỏi bot này.",
        "generic_error": "❌ Có lỗi xảy ra. Vui lòng thử lại sau.",

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
            "\n"
            "2️⃣ Nếu không tự đăng nhập khi đã qua app netflix:\n"
            "1. Nhấn Open App.\n"
            "2. Khi Netflix mở ra nhưng chưa đăng nhập:\n"
            "   • Quay lại trình duyệt.\n"
            "   • Tiếp tục nhấn Open App.\n"
            "3. Lặp lại 2–3 lần.\n"
            "4. Đổi link mới.\n"
            "5. Nếu vẫn không được hãy xoá app tải lại và đổi link khác.\n\n"
            "\n"
            "3️⃣ Nếu xuất hiện lỗi đăng nhập khác:\n"
            "Mở trình duyệt và truy cập:\n"
            "https://www.netflix.com/unsupported\n"
            "Sau đó tải lại hoặc truy cập 2–3 lần rồi thử đăng nhập lại.\n\n"
            "\n"
            "4️⃣ Nếu vẫn không vào được:\n"
            "✅ Chuyển sang trình duyệt chính của máy (Safari/Chrome).\n"
            "✅ Bật chế độ Trang web cho máy tính (Desktop Site) (IPAD ONLY).\n"
            "✅ Đăng nhập và sử dụng Netflix trên trình duyệt web.\n\n"
            "\n"
            "5️⃣ Khuyến nghị:\n"
            "🔹 Cập nhật iOS/Android lên phiên bản mới nhất.\n"
            "🔹 Xóa cache và cookies của trình duyệt.\n"
            "🔹 Đổi sang mạng Wi-Fi hoặc 4G/5G khác.\n"
            "🔹 Nếu đã thử tất cả các cách trên nhưng vẫn lỗi, vui lòng liên hệ Admin để kiểm tra và hỗ trợ."
        ),

        # ── Stats ──
        "stats": (
            "📊 <b>Trạng thái của bạn</b>\n"
            "\n"
            "👤 Người dùng: <b>{name}</b>\n"
            "📅 Hôm nay: {today}\n"
            "👑 Gói hiện tại: <b>{plan_name}</b>\n"
            "🎟️ Gói hôm nay còn: <b>{plan_left}/{plan_quota}</b> lượt không cần vượt\n"
            "🎁 Ref hôm nay: <b>{ref_today}</b> người, còn <b>{ref_free_left}</b> lượt không cần vượt\n"
            "⏰ Reset quota ngày lúc: {reset} (giờ VN)\n"
            "📆 Hạn gói: <b>{plan_expires}</b> (giờ VN)\n"
            "\n"
            "💡 Free user được lấy link không giới hạn, nhưng luôn phải vượt link."
        ),

        # ── Referral ──
        "ref_info": (
            "👥 <b>CHƯƠNG TRÌNH GIỚI THIỆU NHẬN LƯỢT DÙNG</b> 👥\n"
            "\n"
            "Chia sẻ link giới thiệu của bạn cho bạn bè!\n"
            "Khi bạn bè bấm link, mở bot và <b>tham gia đầy đủ các nhóm</b> — bạn được thưởng ngay!\n\n"
            "🎁 <b>Cách tính thưởng:</b>\n"
            "• Mỗi 1 ref thành công = <b>+{bonus_per_ref} lượt KHÔNG cần vượt xác thực</b>\n"
            "• Cộng dồn trong ngày, tối đa <b>{max_ref} ref/ngày</b> (+{max_bonus} lượt free)\n"
            "• Reset lúc 00:00 mỗi ngày\n\n"
            "📊 <b>Thống kê của bạn:</b>\n"
            "• Ref hôm nay: <b>{ref_today}</b> (còn <b>{ref_free_left}</b> lượt không cần vượt)\n"
            "🔗 <b>Link giới thiệu của bạn:</b>\n"
            "<code>{ref_link}</code>\n\n"
            "<i>(Bấm vào link ở trên để tự động copy)</i>"
        ),
        "ref_new": "🎉 {name} đã giới thiệu bạn! Chào mừng!",
        "ref_got": "🔔 Bạn được <b>+{bonus_per_ref} lượt KHÔNG cần vượt xác thực hôm nay</b>! ({ref_today}/{max_ref} ref hôm nay) nhờ giới thiệu {name}.",

        # ── Check-in ──
        "checkin_done": (
            "🎉 <b>ĐIỂM DANH THÀNH CÔNG!</b>\n"
            "\n"
            "📅 Ngày điểm danh liên tiếp: <b>{streak}</b>\n"
            "🎁 Nhận: <b>+{bonus} lượt dùng hôm nay</b>\n"
            "{milestone_text}"
            "⏰ Reset về 00:00 hôm sau.\n\n"
            "💡 Đủ <b>{milestone_days} ngày liên tiếp</b> sẽ được thưởng thêm!"
        ),
        "checkin_milestone": "🎊 <b>NỔ MỐC {milestone_days} NGÀY! +{milestone_bonus} lượt thưởng!</b>\n",
        "checkin_already": "⏰ Bạn đã điểm danh hôm nay rồi!\n🔥 Chuỗi hiện tại: <b>{streak} ngày</b>\n\n📅 Quay lại sau 00:00 để điểm danh tiếp nhé.",

        # ── Admin ──
        "not_admin": "⛔ Bạn không phải Admin.",
        "admin_denied": "⛔ Không có quyền.",
        "admin_stats": (
            "📊 <b>THỐNG KÊ BOT</b>\n"
            "\n"
            "👥 <b>NGƯỜI DÙNG</b>\n"
            "Tổng: {users} · Hôm nay: {users_today}\n"
            "7 ngày: {users_7d} · 30 ngày: {users_30d}\n"
            "\n"
            "⚡ <b>LƯỢT TẢI</b>\n"
            "Hôm nay: {gets_today} · Tổng: {gets_total}\n"
            "\n"
            "👑 <b>GÓI</b>: Basic {active_basic} · Pro {active_pro}\n"
            "\n"
            "💰 <b>DOANH THU</b>\n"
            "Hôm nay: {revenue_today_vnd} VND\n"
            "Tháng: {revenue_month_vnd} VND\n"
            "Tổng: {revenue_total_vnd} VND\n"
            "\n"
            "📦 <b>ĐƠN HÀNG</b>\n"
            "SePay: {sepay_paid} · Binance: {binance_paid}\n"
            "Chờ: {orders_pending} · Duyệt: {orders_approved}\n"
            "Từ chối: {orders_rejected} · HH: {orders_expired}\n"
            "\n"
            "🍪 <b>TÀI NGUYÊN</b>\n"
            "Cookie: {cookies_remaining}/{cookies_total} (💀 {cookies_dead})\n"
            "Buffer: {buffer_validated}/{buffer_total}\n"
            "Proxy: {proxies_live} sống"
        ),
        "admin_orders": "<b>BINANCE CHỜ DUYỆT</b>",
        "admin_orders_all_text": "<b>TẤT CẢ ĐƠN GẦN ĐÂY</b>",
        "admin_order_row": "• <code>{order_id}</code> | {user_display} | {plan} | {amount} | {status} | Mã GD: <code>{tx}</code>",
        "admin_order_row_full": "• <code>{order_id}</code> | {user_display} | {provider} | {plan} | {status}",
        "admin_binance_pending": (
            "🧾 <b>CHI TIẾT ĐƠN HÀNG</b>\n\n"
            "• Trạng thái: <b>{status}</b>\n"
            "• Gói: <b>{plan}</b>\n"
            "• Cổng: <b>{provider}</b>\n"
            "• Số tiền: <b>{amount}</b>\n\n"
            "📌 Thông tin chi tiết:\n"
            "• Mã đơn: <code>{order_id}</code>\n"
            "• Người dùng: {user_display}\n"
            "• Mã TT: <code>{order_code}</code>\n"
            "• Tạo lúc: {created_at}\n"
            "• Hết hạn: {expires_at}\n"
            "• Mã giao dịch: <code>{tx}</code>"
        ),
        "admin_order_detail": (
            "🧾 <b>CHI TIẾT ĐƠN HÀNG</b>\n\n"
            "• Trạng thái: <b>{status}</b>\n"
            "• Gói: <b>{plan}</b>\n"
            "• Cổng: <b>{provider}</b>\n"
            "• Số tiền: <b>{amount}</b>\n\n"
            "📌 Thông tin chi tiết:\n"
            "• Mã đơn: <code>{order_id}</code>\n"
            "• Người dùng: {user_display}\n"
            "• Mã TT: <code>{order_code}</code>\n"
            "• Tạo lúc: {created_at}\n"
            "• Hết hạn: {expires_at}\n"
            "• Đã nhận tiền: {paid_at}\n"
            "• Duyệt lúc: {approved_at}\n"
            "• Mã giao dịch: <code>{tx}</code>"
        ),
        "admin_order_expired": "⏰ Đơn <code>{order_id}</code> đã hết hạn.",
        "admin_order_cancelled": "🚫 Đơn <code>{order_id}</code> đã bị user huỷ.",
        "admin_plan_overview_text": "<b>GÓI ĐANG HOẠT ĐỘNG</b>\n\n• Gói BASIC: <b>{basic}</b>\n• Gói PRO: <b>{pro}</b>",
        "admin_binance_approved": "✅ Đã duyệt đơn Binance <code>{order_id}</code>.",
        "admin_binance_rejected": "❌ Đã từ chối đơn Binance <code>{order_id}</code>.",
        "admin_import_prompt": (
            "📎 Gửi <b>text</b> hoặc file <b>.txt/.zip/.json</b> chứa cookie.\n"
            "Chỉ cần <code>NetflixId</code>, có thể kèm <code>SecureNetflixId</code>."
        ),
        "admin_proxy_prompt": (
            "📎 Gửi <b>text</b> hoặc file <b>.txt/.zip/.json</b> chứa proxy.\n"
            "Mỗi dòng một proxy dạng <code>ip:port</code>."
        ),
        "file_upload_no_state": (
            "ℹ️ File chưa được nhận.\n\n"
            "Bấm <b>📎 Nạp Proxy</b> hoặc lệnh <code>/addproxy</code> để mở cửa sổ "
            "nhận file (20 giây), sau đó gửi lại file.\n"
            "🍪 Nạp cookie: bấm <b>🍪 Nhập Cookie</b> hoặc <code>/addcookie</code>."
        ),
        "cookie_report": (
            "📥 KẾT QUẢ NẠP COOKIE POOL\n"
            "\n"
            "🔍 Cookie phát hiện trong file: {total_parsed}\n"
            "🧹 Cookie quá hạn/cũ (Bỏ qua): {expired}\n"
            "♻️ Cookie trùng lặp (Bỏ qua): {duplicate}\n"
            "⏭️ Dòng không phải cookie Netflix (Bỏ qua): {skipped}\n"
            "✅ Cookie hợp lệ thêm vào Pool: {added}\n"
            "📊 Tổng Cookie Pool hiện tại: {pool}"
        ),
        "folder_report": (
            "📥 KẾT QUẢ QUÉT FOLDER\n"
            "\n"
            "📂 Thư mục: {folder}\n"
            "📁 File quét: {files}\n"
            "✅ Cookie thêm vào Pool: {added}\n"
            "⏭️ Dòng không phải cookie Netflix (Bỏ qua): {skipped}\n"
            "🗑️ File xóa (trùng/đã xử lý): {deleted}\n"
            "📊 Tổng Cookie Pool: {pool}"
        ),
        "folder_empty": "⚠️ Không tìm thấy file cookie nào trong thư mục:\n📂 {folder}\n\nGửi file .txt/.json/.zip vào đây rồi bấm lại.",
        "proxy_report": (
            "🔌 KẾT QUẢ NẠP PROXY\n"
            "\n"
            "📂 Thư mục: {folder}\n"
            "📁 File quét: {files}\n"
            "✅ Proxy thêm vào file: {added}\n"
            "🗑️ File xóa (trùng/đã xử lý): {deleted}\n"
            "📊 Tổng proxy trong PROXY_URLS.txt: {total}"
        ),
        "proxy_empty": "⚠️ Không tìm thấy dòng proxy hợp lệ nào trong thư mục:\n📂 {folder}",
        "proxy_chat_report": (
            "🔌 KẾT QUẢ NẠP PROXY\n"
            "\n"
            "🔍 Dòng proxy phát hiện trong file: {detected}\n"
            "♻️ Trùng lặp (Bỏ qua): {duplicate}\n"
            "✅ Proxy thêm vào PROXY_URLS.txt: {added}\n"
            "📊 Tổng proxy trong file: {total}"
        ),
        "proxy_chat_empty": "\n⚠️ Không tìm thấy dòng proxy hợp lệ nào trong file.",
        "cookie_report_empty": "\n⚠️ Không tìm thấy dữ liệu hợp lệ",
        "cookie_zip_limited": "⚠️ Chỉ xử lý {limit} file đầu trong ZIP\n\n",
        "cookie_file_not_received": "⚠️ Không nhận được file.",
        "cookie_file_too_big": "❌ File quá lớn (max 20MB).",
        "cookie_file_download_error": "❌ Lỗi tải file: {error}",
        "cookie_file_json_error": "❌ Lỗi đọc JSON: {error}",
        "cookie_file_zip_error": "❌ Lỗi đọc ZIP: {error}",
        "cookie_file_bad_type": "❌ Chỉ nhận file .txt, .zip hoặc .json.",
        "cookie_file_process_error": "❌ Lỗi xử lý file: {error}",
        "addluot_usage": "Cách dùng:\n/addluot <số_lượt>\n/addluot <user_id> <số_lượt>\nLệnh này cộng bonus không cần vượt trong ngày hôm nay.",
        "addluot_bad_format": "Sai định dạng. Ví dụ: /addluot 123456789 5",
        "addluot_positive": "Số lượt phải > 0",
        "addluot_done": "✅ Đã cộng {amount} lượt bonus không cần vượt cho user <code>{target_id}</code>\nCòn lại hôm nay: <b>{new_total}</b>",
        "setprice_usage": "Cách dùng:\n/setprice <basic|pro> <giá_VND> <giá_USDT> [số_link/ngày]\nVí dụ: /setprice basic 15000 1.5 15",
        "setprice_bad_format": "Sai định dạng. Ví dụ: /setprice basic 15000 1.5",
        "setprice_invalid_plan": "Gói không hợp lệ. Chỉ chấp nhận <code>basic</code> hoặc <code>pro</code>.",
        "setprice_invalid_vnd": "Giá VND phải là số nguyên > 0.",
        "setprice_invalid_usdt": "Giá USDT phải là số > 0.",
        "setprice_invalid_quota": "Số link/ngày phải là số nguyên > 0.",
        "setprice_done": "✅ Đã cập nhật gói <b>{plan}</b>\nGiá mới: <b>{vnd} VND</b> / <b>{usdt} USDT</b>\nSố link/ngày: <b>{quota}</b>",
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
            "<code>/msg 🔥 BẢO TRÌ\nBot sẽ bảo trì lúc 23:00</code>\n\n"
            "Nội dung gửi <b>nguyên văn</b> — tự gõ tiêu đề ở đầu."
        ),
        "no_users": "⚠️ Chưa có user nào trong hệ thống.",
        "msg_sending": "📢 Đang gửi tin nhắn tới {count} users...",
        "msg_done": (
            "✅ Đã gửi xong!\n"
            "📨 Thành công: <b>{sent}/{total}</b>\n"
            "🚫 Bị chặn bot: <b>{blocked}</b>\n"
            "⚠️ Lỗi tạm thời (rate-limit/khác): <b>{retryable}</b>"
        ),
        "delusers_run": "🧹 Đang quét {count} user (gửi tín hiệu typing, KHÔNG hiện tin nhắn)...",
        "delusers_done": (
            "🧹 <b>HOÀN TẤT QUÉT</b>\n"
            "🗑️ Đã xóa (chặn bot / deactivated): <b>{removed}</b>\n"
            "✅ Giữ lại (hoạt động / lỗi tạm thời): <b>{kept}</b>\n"
            "📊 Tổng: {total}\n\n"
            "💡 User bị xóa nếu quay lại gõ /start sẽ được tạo mới bình thường."
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
            "\n"
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
        "btn_checkin": "📅 Check-in",
        "btn_ref": "👥 Referral",
        "btn_loginlink": "🍿 Get Movie Link 🍿",
        "btn_buy_plan": "👑 Buy Plan 👑",
        "btn_stats": "📊 My Status",
        "btn_lang": "🌐 Language",
        "btn_help": "❓ Help",
        "btn_back": "🔙 Back",
        "btn_join": "📢 Join Group",
        "btn_check_joined": "🔄 Check Again",
        "btn_join_group": "📢 Join {group}",
        "btn_private_chat": "💬 Message the bot privately",
        "btn_contact_admin": "📩 Contact Admin",
        "admin_btn_import": "🍪 Import Cookies",
        "admin_btn_loadcookies": "📂 Scan Cookies",
        "admin_btn_loadproxy": "🔌 Load Proxy",
        "admin_btn_addproxy": "📎 Add Proxy",
        "admin_btn_stats": "📊 Stats",
        "admin_btn_orders": "📦 Orders",
        "admin_btn_resources": "🔧 Resources",
        "admin_btn_plans": "👑 Active Plans",
        "admin_btn_user_search": "🔍 Find user",
        "admin_user_search_prompt": "Enter <b>User ID</b> to look up:",
        "admin_user_not_found": "❌ User not found.",
        "admin_user_bonus_bad": "❌ Invalid amount.",
        "admin_user_view": (
            "👤 <b>USER</b> <code>{user_id}</code>\n"
            "👑 Plan: <b>{plan_name}</b>\n"
            "📅 Expires: {plan_expires}\n"
            "🎟️ Left: {plan_left}/{plan_quota}"
        ),
        "admin_user_grant_done": "✅ Plan <b>{plan}</b> granted to user.",
        "admin_user_remove_done": "✅ Plan removed.",
        "admin_removeplan_usage": "Usage: /removeplan <user_id>",
        "admin_removeplan_done": "✅ Removed plan for user <code>{user_id}</code>.",
        "admin_removeplan_not_found": "❌ User not found.",
        "admin_user_bonus_prompt": "Enter bonus amount for user <code>{user_id}</code>:",
        "admin_user_bonus_done": "✅ Added <b>{amount}</b> bonus uses for user <code>{user_id}</code>.\nLeft today: <b>{left}</b>.",
        "admin_btn_grant_basic": "👑 Grant Basic",
        "admin_btn_grant_pro": "👑 Grant Pro",
        "admin_btn_remove_plan": "↩️ Remove plan",
        "admin_btn_add_bonus": "➕ Bonus",
        "admin_btn_filter_all": "All",
        "admin_btn_filter_pending": "⏳ Pending",
        "admin_btn_filter_done": "✅ Done",
        "admin_btn_filter_closed": "🚫 Closed",

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

        # ── Link4m gate ──
        "shrinkme_gate_msg": (
            "🔐 <b>VERIFY TO GET YOUR NETFLIX LINK</b>\n"
            "\n"
            "💡 <i>Free users always need to complete the gate. If you have ref bonus or an active plan, the bot skips this automatically.</i>\n\n"
            "1️⃣ Copy the link below and open in an external browser (Chrome/Safari):\n"
            "🔗 <code>{url}</code>\n\n"
            "2️⃣ Wait ~15-30s and complete the steps on that page\n"
            "3️⃣ You'll be brought back to the bot → get your Netflix link\n\n"
            "💡 <i>Closed the page? Copy the link above.\n"
            "No Netflix link yet? Type /loginlink to get a new one.</i>"
        ),
        "shrinkme_invalid": (
            "⌛ The verification link has expired or was already used.\n\n"
            "👉 Please type /loginlink to get a new one!"
        ),
        "gate_maintenance": "⚠️ The gate link system is under maintenance. Please try again later.",
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
        "link_remaining": "📊 Plan left today: {left}/{limit} no-gate uses",
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

        "plan_menu": (
            "👑 <b>BUY NO-GATE PLAN</b>\n"
            "\n"
            "• Basic: {basic_vnd} VND / {basic_usdt} USDT\n"
            "  {basic_daily} links/day for {days} days\n\n"
            "• Pro: {pro_vnd} VND / {pro_usdt} USDT\n"
            "  {pro_daily} links/day for {days} days\n\n"
            "Choose a plan to buy."
        ),
        "plan_basic_btn": "⭐️ Basic",
        "plan_pro_btn": "👑 Pro",
        "plan_payment_step": (
            "💳 <b>CHOOSE PAYMENT</b>\n"
            "\n"
            "Plan: <b>{plan}</b>\n"
            "Price: <b>{price}</b>\n"
            "• Duration: {days} days ({daily} links/day)\n\n"
            "Choose a payment method below."
        ),
        "pay_sepay": "Basic • Vietnam Bank",
        "pay_binance": "Basic • USDT Payment",
        "pay_sepay_pro": "Pro • Vietnam Bank",
        "pay_binance_pro": "Pro • USDT Payment",
        "plan_basic_sepay_btn": "🏦 Vietnam Bank",
        "plan_basic_binance_btn": "💵 USDT (Crypto)",
        "plan_pro_sepay_btn": "🏦 Vietnam Bank",
        "plan_pro_binance_btn": "💵 USDT (Crypto)",
        "payment_bank": "Vietnam Bank",
        "payment_usdt": "USDT Payment",
        "sepay_payment": (
            "🏦 <b>PAY FOR PLAN {plan}</b>\n\n"
            "• Price: <b>{amount_vnd} VND</b>\n"
            "• Duration: <b>{days} days</b> ({daily} links/day)\n\n"
            "📋 Transfer details:\n"
            "• Bank: <b>{bank_bin}</b>\n"
            "• Account No: <code>{bank_account}</code>\n"
            "• Name: <code>{bank_holder}</code>\n"
            "• Reference: <code>{order_code}</code>\n\n"
            "⚡ Your plan will be activated automatically after payment is received."
        ),
        "binance_payment": (
            "🌐 <b>USDT PAYMENT</b>\n\n"
            "• Plan: <b>{plan}</b>\n"
            "• Amount: <b>{amount_usdt} USDT</b>\n\n"
            "📌 Choose 1 of 2 transfer methods:\n\n"
            "1. Binance Pay ID:\n<code>{pay_id}</code>\n\n"
            "2. BEP20 (BSC) wallet:\n<code>{wallet}</code>\n\n"
            "• Order code: <code>{order_code}</code>\n\n"
            "⚠️ After payment, please send the Transaction ID (TxID / Order ID) in chat for admin approval."
        ),
        "binance_tx_received": "✅ Your Binance transaction code was received. Admin will review it soon.",
        "binance_tx_invalid": "❌ No pending Binance order was found. Please create a new order first.",
        "plan_approved": "✅ Your <b>{plan}</b> plan has been activated successfully.",
        "plan_rejected": "❌ Your Binance payment request was rejected. Please check the transaction and create a new order.",
        "plan_cancelled": "❌ Your order has been cancelled. If you want to buy again, tap 👑 Buy Plan.",
        "order_status": (
            "🧾 <b>ORDER STATUS</b>\n\n"
            "• Status: <b>{status}</b>\n"
            "• Plan: <b>{plan}</b>\n"
            "• Method: <b>{provider}</b>\n"
            "• Amount: <b>{amount}</b>\n\n"
            "📌 Order details:\n"
            "• Ref code: <code>{order_code}</code>\n"
            "• Expires: {expires_at} (VN time)\n"
            "• Transaction: <code>{tx}</code>"
        ),
        "order_pending": "Pending payment",
        "order_paid": "Payment received",
        "order_approved": "Plan activated",
        "order_rejected": "Rejected",
        "order_expired": "Expired",
        "order_cancelled": "Cancelled",
        "btn_cancel_order": "❌ Cancel order",
        "order_expired_text": "⏰ Your order has expired. Please create a new one if you still want to buy.",
        "gift_removed": "⚠️ Gift codes were removed from this bot.",
        "checkin_removed": "⚠️ Check-in was removed from this bot.",
        "generic_error": "❌ Something went wrong. Please try again later.",

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
            "\n"
            "2️⃣ If it does not auto-login when the Netflix app opens:\n"
            "1. Tap Open App.\n"
            "2. If Netflix opens but you are not logged in:\n"
            "   • Go back to the browser.\n"
            "   • Tap Open App again.\n"
            "3. Repeat 2–3 times.\n"
            "4. Get a new link.\n"
            "5. Still not working? Uninstall the app, reinstall it, and get another link.\n\n"
            "\n"
            "3️⃣ If another login error appears:\n"
            "Open your browser and go to:\n"
            "https://www.netflix.com/unsupported\n"
            "Then reload or visit it 2–3 times and try logging in again.\n\n"
            "\n"
            "4️⃣ If you still cannot get in:\n"
            "✅ Switch to your device's main browser (Safari/Chrome).\n"
            "✅ Enable Desktop Site mode (IPAD ONLY).\n"
            "✅ Log in and use Netflix in the web browser.\n\n"
            "\n"
            "5️⃣ Recommendations:\n"
            "🔹 Update iOS/Android to the latest version.\n"
            "🔹 Clear browser cache and cookies.\n"
            "🔹 Switch to another Wi-Fi or 4G/5G network.\n"
            "🔹 If you tried everything and it still fails, contact the Admin for help."
        ),

        # ── Stats ──
        "stats": (
            "📊 <b>Your Status</b>\n"
            "\n"
            "👤 User: <b>{name}</b>\n"
            "📅 Today: {today}\n"
            "👑 Current plan: <b>{plan_name}</b>\n"
            "🎟️ Plan left today: <b>{plan_left}/{plan_quota}</b> no-gate uses\n"
            "🎁 Today's refs: <b>{ref_today}</b>, <b>{ref_free_left}</b> no-gate uses left\n"
            "⏰ Daily quota resets at: {reset} (VN time)\n"
            "📆 Plan expiry: <b>{plan_expires}</b> (VN time)\n"
            "\n"
            "💡 Free users can request unlimited links, but must always complete the gate."
        ),

        # ── Referral ──
        "ref_info": (
            "👥 <b>REFERRAL PROGRAM — GET FREE USES</b> 👥\n"
            "\n"
            "Share your referral link with friends!\n"
            "When a friend taps the link, opens the bot and <b>joins all groups</b> — you get rewarded instantly!\n\n"
            "🎁 <b>How it works:</b>\n"
            "• Each successful ref = <b>+{bonus_per_ref} no-verification uses</b>\n"
            "• Stacks within the day, up to <b>{max_ref} refs/day</b> (+{max_bonus} free uses)\n"
            "• Resets every day at 00:00\n\n"
            "📊 <b>Your stats:</b>\n"
            "• Today's refs: <b>{ref_today}</b> ({ref_free_left} no-verification uses left)\n\n"
            "🔗 <b>Your referral link:</b>\n"
            "<code>{ref_link}</code>\n"
            "\n"
            "<i>(Tap the link above to copy it)</i>"
        ),
        "ref_new": "🎉 {name} referred you! Welcome!",
        "ref_got": "🔔 You got <b>+{bonus_per_ref} no-verification uses today</b>! ({ref_today}/{max_ref} refs today) thanks to {name}.",

        # ── Check-in ──
        "checkin_done": (
            "🎉 <b>CHECK-IN SUCCESS!</b>\n"
            "\n"
            "📅 Consecutive check-in days: <b>{streak}</b>\n"
            "🎁 Got: <b>+{bonus} uses today</b>\n"
            "{milestone_text}"
            "⏰ Resets at 00:00.\n\n"
            "💡 Reach <b>{milestone_days} consecutive days</b> for an extra reward!"
        ),
        "checkin_milestone": "🎊 <b>{milestone_days}-DAY STREAK BONUS! +{milestone_bonus} USES!</b>\n",
        "checkin_already": "⏰ You already checked in today!\n🔥 Current streak: <b>{streak} days</b>\n\n📅 Come back after 00:00 to check in again.",

        # ── Admin ──
        "not_admin": "⛔ You are not an Admin.",
        "admin_denied": "⛔ No permission.",
        "admin_stats": (
            "📊 <b>BOT STATS</b>\n"
            "\n"
            "👥 <b>USERS</b>\n"
            "Total: {users} · Today: {users_today}\n"
            "7 days: {users_7d} · 30 days: {users_30d}\n"
            "\n"
            "⚡ <b>LINKS</b>\n"
            "Today: {gets_today} · Total: {gets_total}\n"
            "\n"
            "👑 <b>PLANS</b>: Basic {active_basic} · Pro {active_pro}\n"
            "\n"
            "💰 <b>REVENUE</b>\n"
            "Today: {revenue_today_vnd} VND\n"
            "Month: {revenue_month_vnd} VND\n"
            "Total: {revenue_total_vnd} VND\n"
            "\n"
            "📦 <b>ORDERS</b>\n"
            "SePay: {sepay_paid} · Binance: {binance_paid}\n"
            "Pending: {orders_pending} · Approved: {orders_approved}\n"
            "Rejected: {orders_rejected} · Expired: {orders_expired}\n"
            "\n"
            "🍪 <b>RESOURCES</b>\n"
            "Cookies: {cookies_remaining}/{cookies_total} (💀 {cookies_dead})\n"
            "Buffer: {buffer_validated}/{buffer_total}\n"
            "Proxies: {proxies_live} live"
        ),
        "admin_orders": "<b>BINANCE PENDING APPROVAL</b>",
        "admin_orders_all_text": "<b>RECENT ORDERS</b>",
        "admin_order_row": "• <code>{order_id}</code> | {user_display} | {plan} | {amount} | {status} | Tx: <code>{tx}</code>",
        "admin_order_row_full": "• <code>{order_id}</code> | {user_display} | {provider} | {plan} | {status}",
        "admin_binance_pending": (
            "🧾 <b>ORDER DETAIL</b>\n\n"
            "• Status: <b>{status}</b>\n"
            "• Plan: <b>{plan}</b>\n"
            "• Method: <b>{provider}</b>\n"
            "• Amount: <b>{amount}</b>\n\n"
            "📌 Details:\n"
            "• Order ID: <code>{order_id}</code>\n"
            "• User: {user_display}\n"
            "• Ref code: <code>{order_code}</code>\n"
            "• Created: {created_at}\n"
            "• Expires: {expires_at}\n"
            "• Transaction: <code>{tx}</code>"
        ),
        "admin_order_detail": (
            "🧾 <b>ORDER DETAIL</b>\n\n"
            "• Status: <b>{status}</b>\n"
            "• Plan: <b>{plan}</b>\n"
            "• Method: <b>{provider}</b>\n"
            "• Amount: <b>{amount}</b>\n\n"
            "📌 Details:\n"
            "• Order ID: <code>{order_id}</code>\n"
            "• User: {user_display}\n"
            "• Ref code: <code>{order_code}</code>\n"
            "• Created: {created_at}\n"
            "• Expires: {expires_at}\n"
            "• Paid: {paid_at}\n"
            "• Approved: {approved_at}\n"
            "• Transaction: <code>{tx}</code>"
        ),
        "admin_order_expired": "⏰ Order <code>{order_id}</code> expired.",
        "admin_order_cancelled": "🚫 Order <code>{order_id}</code> was cancelled by user.",
        "admin_plan_overview_text": "<b>ACTIVE PLANS</b>\n\n• BASIC: <b>{basic}</b>\n• PRO: <b>{pro}</b>",
        "admin_binance_approved": "✅ Approved Binance order <code>{order_id}</code>.",
        "admin_binance_rejected": "❌ Rejected Binance order <code>{order_id}</code>.",
        "admin_import_prompt": (
            "📎 Send <b>text</b> or a <b>.txt/.zip/.json</b> file containing cookies.\n"
            "Only <code>NetflixId</code> is required; <code>SecureNetflixId</code> is optional."
        ),
        "admin_proxy_prompt": (
            "📎 Send <b>text</b> or a <b>.txt/.zip/.json</b> file containing proxies.\n"
            "One proxy per line, format <code>ip:port</code>."
        ),
        "file_upload_no_state": (
            "ℹ️ File not accepted.\n\n"
            "Tap <b>📎 Add Proxy</b> or run <code>/addproxy</code> to open the "
            "file window (20 seconds), then send the file again.\n"
            "🍪 For cookies: tap <b>🍪 Import Cookies</b> or run <code>/addcookie</code>."
        ),
        "cookie_report": (
            "📥 COOKIE POOL IMPORT RESULT\n"
            "\n"
            "🔍 Lines scanned: {total_parsed}\n"
            "🧹 Expired/old cookies (skipped): {expired}\n"
            "♻️ Duplicate cookies (skipped): {duplicate}\n"
            "⏭️ Lines without NetflixId (skipped): {skipped}\n"
            "✅ Valid cookies added to Pool: {added}\n"
            "📊 Current Cookie Pool: {pool}"
        ),
        "cookie_report_empty": "\n⚠️ No valid data found",
        "cookie_zip_limited": "⚠️ Only first {limit} files in ZIP processed\n\n",
        "folder_report": (
            "📥 FOLDER SCAN RESULT\n"
            "\n"
            "📂 Folder: {folder}\n"
            "📁 Files scanned: {files}\n"
            "✅ Cookies added to Pool: {added}\n"
            "⏭️ Lines without NetflixId (skipped): {skipped}\n"
            "🗑️ Files deleted (duplicate/processed): {deleted}\n"
            "📊 Total Cookie Pool: {pool}"
        ),
        "folder_empty": "⚠️ No cookie files found in folder:\n📂 {folder}\n\nPut .txt/.json/.zip files there and try again.",
        "proxy_report": (
            "🔌 PROXY LOAD RESULT\n"
            "\n"
            "📂 Folder: {folder}\n"
            "📁 Files scanned: {files}\n"
            "✅ Proxies added to file: {added}\n"
            "🗑️ Files deleted (duplicate/processed): {deleted}\n"
            "📊 Total proxies in PROXY_URLS.txt: {total}"
        ),
        "proxy_empty": "⚠️ No valid proxy lines found in folder:\n📂 {folder}",
        "proxy_chat_report": (
            "🔌 PROXY IMPORT RESULT\n"
            "\n"
            "🔍 Proxy lines found in file: {detected}\n"
            "♻️ Duplicates (skipped): {duplicate}\n"
            "✅ Proxies added to PROXY_URLS.txt: {added}\n"
            "📊 Total proxies in file: {total}"
        ),
        "proxy_chat_empty": "\n⚠️ No valid proxy lines found in the file.",
        "cookie_file_not_received": "⚠️ File not received.",
        "cookie_file_too_big": "❌ File too large (max 20MB).",
        "cookie_file_download_error": "❌ Download error: {error}",
        "cookie_file_json_error": "❌ JSON parse error: {error}",
        "cookie_file_zip_error": "❌ ZIP parse error: {error}",
        "cookie_file_bad_type": "❌ Only .txt, .zip or .json files are accepted.",
        "cookie_file_process_error": "❌ File processing error: {error}",
        "addluot_usage": "Usage:\n/addluot <amount>\n/addluot <user_id> <amount>\nThis adds no-gate bonus uses for today.",
        "addluot_bad_format": "Invalid format. Example: /addluot 123456789 5",
        "addluot_positive": "Amount must be > 0",
        "addluot_done": "✅ Added {amount} no-gate bonus uses for user <code>{target_id}</code>\nLeft today: <b>{new_total}</b>",
        "setprice_usage": "Usage:\n/setprice <basic|pro> <VND_price> <USDT_price> [links_per_day]\nExample: /setprice basic 15000 1.5 15",
        "setprice_bad_format": "Invalid format. Example: /setprice basic 15000 1.5",
        "setprice_invalid_plan": "Invalid plan. Only <code>basic</code> or <code>pro</code>.",
        "setprice_invalid_vnd": "VND price must be a positive integer.",
        "setprice_invalid_usdt": "USDT price must be a positive number.",
        "setprice_invalid_quota": "Links per day must be a positive integer.",
        "setprice_done": "✅ Updated plan <b>{plan}</b>\nNew price: <b>{vnd} VND</b> / <b>{usdt} USDT</b>\nLinks per day: <b>{quota}</b>",
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
            "<code>/msg 🔥 MAINTENANCE\nBot will be down at 23:00</code>\n\n"
            "Content is sent <b>verbatim</b> — type your own header."
        ),
        "no_users": "⚠️ No users in the system yet.",
        "msg_sending": "📢 Sending message to {count} users...",
        "msg_done": (
            "✅ Done!\n"
            "📨 Success: <b>{sent}/{total}</b>\n"
            "🚫 Blocked the bot: <b>{blocked}</b>\n"
            "⚠️ Temporary errors (rate-limit/other): <b>{retryable}</b>"
        ),
        "delusers_run": "🧹 Scanning {count} users (sending typing signal, NO visible message)...",
        "delusers_done": (
            "🧹 <b>SCAN COMPLETE</b>\n"
            "🗑️ Removed (blocked / deactivated): <b>{removed}</b>\n"
            "✅ Kept (active / temporary errors): <b>{kept}</b>\n"
            "📊 Total: {total}\n\n"
            "💡 Removed users who return and type /start will be recreated normally."
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
