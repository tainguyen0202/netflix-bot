"""
Config & Constants for Netflix Bot
"""

import os

# ── Bot Config ──
BOT_TOKEN = "REDACTED"
BOT_USERNAME = "@autologinnetflix_bot"

# ── Files ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, "cookie.txt")      # Single merged cookie pool
USER_FILE = os.path.join(BASE_DIR, "user.json")
GIFT_CODE_FILE = os.path.join(BASE_DIR, "giftcodes.json")

# ── Limits ──
DAILY_LIMIT = 10           # Everyone gets 10 uses/day
REF_FREE_PER_REF = 2      # Mỗi ref thành công = +2 lượt KHÔNG cần vượt gate (HÔM NAY)
REF_DAILY_CAP = 10        # Tối đa 10 ref tính bonus/ngày (+20 lượt free), reset mỗi ngày
CHECKIN_DAILY_BONUS = 1    # Mỗi ngày điểm danh = +1 lượt dùng HÔM NAY
CHECKIN_MILESTONE_DAYS = 7 # Đủ 7 ngày liên tiếp → thưởng
CHECKIN_MILESTONE_BONUS = 5  # +5 lượt hôm đó khi đạt mốc 7 ngày
COOKIE_UPLOAD_WINDOW = 20 # Cửa sổ nhận nhiều file cookie liên tiếp (giây)
ZIP_FILE_LIMIT = 5000      # Tối đa file nội trong 1 ZIP (cookie & proxy)
ADMIN_IDS = [1208795685]
GROUP_USERNAME = "sharefreeall"  # nhóm chính (hiển thị welcome)
GROUP_USERNAMES = ["sharefreeall", "allchatisfree", "allchatisfreebackup", "sharefreeall_backup"]  # phải tham gia tất cả
ADMIN_TAG = "@lucasnguyen0202"

# ── Link4m gate (/loginlink phải qua link rút gọn) ──
LINK4M_API_KEY = "6a8965337ba684187a4e9eed"  # rỗng = tắt gate
LINK4M_GATE_TTL = 1800     # token gate sống 30 phút (giây)
LINK4M_FREE_PER_DAY = 2    # Số lượt ĐẦU TIÊN mỗi ngày không cần vượt gate

# ── Donate ──
DONATE_QR_URL = "https://img.vietqr.io/image/ACB-243951569-compact2.png?addInfo=UNGHONGUOINGHEO&accountName=NGUYEN%20TAN%20TAI"
BINANCE_PAY_ID = "121748976"
USDT_BEP20_ADDRESS = "0xb88468a95aff2427069c2e96c0a81ffca7e56b42"

# ── Currency Map ──
CURRENCY_MAP = {
    "US": "USD", "GB": "GBP", "CA": "CAD", "AU": "AUD",
    "BR": "BRL", "MX": "MXN", "AR": "ARS$", "CL": "CLP",
    "CO": "COP", "PE": "PEN", "VN": "VND", "TH": "THB",
    "MY": "MYR", "SG": "SGD", "PH": "PHP", "ID": "IDR",
    "IN": "INR", "JP": "JPY", "KR": "KRW", "TR": "TRY",
    "ZA": "ZAR", "NG": "NGN", "EG": "EGP", "SA": "SAR",
    "AE": "AED", "IL": "ILS", "PL": "PLN", "SE": "SEK",
    "NO": "NOK", "DK": "DKK", "CZ": "CZK", "HU": "HUF",
    "RO": "RON", "UA": "UAH", "FR": "EUR", "DE": "EUR",
    "IT": "EUR", "ES": "EUR", "NL": "EUR", "BE": "EUR",
    "AT": "EUR", "PT": "EUR", "FI": "EUR", "IE": "EUR",
    "GR": "EUR", "SK": "EUR", "SI": "EUR", "LT": "EUR",
    "LV": "EUR", "EE": "EUR", "HR": "EUR", "BG": "BGN",
    "CH": "CHF", "TW": "TWD", "HK": "HKD", "NZ": "NZD",
}
