"""
Layma backup shortener for gate links.
"""

import logging

from curl_cffi import requests as curl_requests

from config import LAYMA_API_KEY

logger = logging.getLogger("NetflixBot")

_API_URL = "https://api.layma.net/api/admin/shortlink/quicklink"


def shorten(url, fallback_url=None):
    if not LAYMA_API_KEY or not url:
        return None
    try:
        resp = curl_requests.get(
            _API_URL,
            params={
                "tokenUser": LAYMA_API_KEY,
                "format": "json",
                "url": url,
                "link_du_phong": fallback_url or url,
            },
            timeout=10,
            impersonate="chrome",
        )
        data = resp.json()
    except Exception as e:
        logger.warning(f"[Layma] shorten failed: {type(e).__name__}")
        return None
    if not isinstance(data, dict) or not data.get("success"):
        logger.warning("[Layma] API error")
        return None
    short = data.get("html")
    return short if isinstance(short, str) and short.startswith("http") else None
