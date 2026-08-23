"""
Link4m gate — rút gọn deep link qua API link4m.co
Trả về shortenedUrl hoặc None (caller fallback luồng cũ). KHÔNG log API key.
"""

import logging

from curl_cffi import requests as curl_requests

from config import LINK4M_API_KEY

logger = logging.getLogger("NetflixBot")

_API_URL = "https://link4m.co/api-shorten/v2"


def shorten(url):
    """Rút gọn url qua link4m API. Returns shortened str or None on any failure."""
    if not LINK4M_API_KEY or not url:
        return None
    try:
        resp = curl_requests.get(
            _API_URL,
            params={"api": LINK4M_API_KEY, "url": url},
            timeout=10,
            impersonate="chrome",
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"[Link4m] shorten failed: {type(e).__name__}")
        return None
    if not isinstance(data, dict) or data.get("status") != "success":
        msg = (data or {}).get("message") if isinstance(data, dict) else None
        logger.warning(f"[Link4m] API error: {msg or 'unknown'}")
        return None
    short = data.get("shortenedUrl")
    return short if isinstance(short, str) and short.startswith("http") else None
