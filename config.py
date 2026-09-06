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
ORDER_FILE = os.path.join(BASE_DIR, "orders.json")
PLAN_PRICE_FILE = os.path.join(BASE_DIR, "plan_prices.json")

# ── Quotas / Plans ──
REF_FREE_PER_REF = 3       # Mỗi ref thành công = +3 lượt KHÔNG cần vượt gate (HÔM NAY)
REF_DAILY_CAP = 10         # Tối đa 10 ref tính bonus/ngày (+30 lượt free), reset mỗi ngày
PLAN_DURATION_DAYS = 30
PLAN_BASIC_PRICE_VND = 10_000
PLAN_PRO_PRICE_VND = 20_000
PLAN_BASIC_DAILY = 10
PLAN_PRO_DAILY = 20
PLAN_BASIC_PRICE_USDT = "1"
PLAN_PRO_PRICE_USDT = "2"
BINANCE_PAY_ID = "121748976"
USDT_BEP20_ADDRESS = "0xb88468a95aff2427069c2e96c0a81ffca7e56b42"
MANUAL_BONUS_COMMAND = "addluot"
SEPAY_ORDER_TTL_MINUTES = 15
BINANCE_ORDER_TTL_MINUTES = 30
COOKIE_UPLOAD_WINDOW = 20 # Cửa sổ nhận nhiều file cookie liên tiếp (giây)
ZIP_FILE_LIMIT = 5000      # Tối đa file nội trong 1 ZIP (cookie & proxy)
ADMIN_IDS = [1208795685]
GROUP_USERNAME = "sharefreeall"  # nhóm chính (hiển thị welcome)
GROUP_USERNAMES = ["sharefreeall", "allchatisfree", "allchatisfreebackup", "sharefreeall_backup"]  # phải tham gia tất cả
ADMIN_TAG = "@lucasng22"

# ── Gate shortener (/loginlink phải qua link rút gọn) ──
SHRINKME_API_KEY = "d7985ea69fc3d8dbf93091cf78fde7031b4d4e28"  # rỗng = tắt gate
SHRINKME_GATE_TTL = 1800   # token gate sống 30 phút (giây)

# ── Payment ──
BANK_BIN = "ACB"
BANK_ACCOUNT = "243951569"
BANK_HOLDER = "NGUYEN TAN TAI"
SEPAY_WEBHOOK_API_KEY = os.getenv("SEPAY_WEBHOOK_API_KEY", "")
SEPAY_API_ACCESS_TOKEN = os.getenv("SEPAY_API_ACCESS_TOKEN", "")
SEPAY_WEBHOOK_HOST = "0.0.0.0"
SEPAY_WEBHOOK_PORT = 8080
SEPAY_WEBHOOK_PATH = "/sepay-webhook"

try:
    from local_config import *  # noqa: F401,F403
except Exception:
    pass

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
