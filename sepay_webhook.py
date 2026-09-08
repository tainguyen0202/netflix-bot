"""
Minimal SePay webhook server running alongside Telegram polling.
"""

import asyncio
import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape

from config import ADMIN_IDS, SEPAY_WEBHOOK_API_KEY, SEPAY_WEBHOOK_HOST, SEPAY_WEBHOOK_PATH, SEPAY_WEBHOOK_PORT
from storage import (
    find_pending_order_by_code,
    find_order_by_code,
    find_processed_transaction,
    grant_plan,
    get_plan_snapshot,
    get_user,
    mark_order_paid,
    get_user_lang,
    _parse_iso_dt,
)
from lang import t

logger = logging.getLogger("NetflixBot")
_server = None
_ORDER_CODE_RE = re.compile(r"NF-?([A-Z0-9]{6})")


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _json_response(handler, status, payload):
    raw = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _extract_order_code(content):
    content = str(content or "").upper()
    m = _ORDER_CODE_RE.search(content)
    if not m:
        return None
    return f"NF{m.group(1)}"


def _run_async(coro):
    try:
        asyncio.run(coro)
    except Exception as e:
        logger.warning(f"[SePay] async notify failed: {e}")


def _fmt_time(iso_str):
    try:
        dt = _parse_iso_dt(iso_str)
        if not dt:
            return iso_str
        return dt.strftime("%H:%M - %d/%m/%Y")
    except Exception:
        return iso_str


def _fmt_admin_user(user_id: int) -> str:
    info = get_user(user_id)
    username = (info.get("username") or "").strip().lstrip("@")
    first_name = (info.get("first_name") or "").strip()

    extra = []
    if username:
        extra.append(f"@{escape(username)}")
    if first_name:
        extra.append(escape(first_name))
    suffix = f" ({' | '.join(extra)})" if extra else ""
    return f"<code>{user_id}</code>{suffix}"


def _build_user_order_text(order, lang):
    amount = f"{order.get('amount_vnd')} VND"
    return t(
        "order_status",
        lang,
        plan=str(order.get("plan") or "").upper(),
        provider=t("payment_bank", lang),
        amount=amount,
        order_code=order.get("order_code") or "-",
        status=str(order.get("status") or "-").upper(),
        expires_at=_fmt_time(order.get("expires_at")) if order.get("expires_at") else "-",
        tx=order.get("transaction_note") or "-",
    )


def _edit_user_order(bot, order, lang):
    chat_id = order.get("user_chat_id")
    message_id = order.get("user_message_id")
    if not chat_id or not message_id:
        return
    # SePay order là ảnh QR -> xoá ảnh; text xác nhận do caller gửi sau
    _run_async(bot.delete_message(chat_id=int(chat_id), message_id=int(message_id)))


def start_sepay_webhook_server(bot):
    global _server
    if _server is not None:
        return _server

    class SePayHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != SEPAY_WEBHOOK_PATH:
                _json_response(self, 404, {"success": False})
                return

            auth = self.headers.get("Authorization", "")
            if auth != f"Apikey {SEPAY_WEBHOOK_API_KEY}":
                _json_response(self, 401, {"success": False})
                return

            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length or 0)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                _json_response(self, 400, {"success": False})
                return

            transaction_id = str(payload.get("id") or "").strip()
            order_code = _extract_order_code(payload.get("content"))
            logger.info(
                "[SePay] tx=%s type=%s amount=%s code=%s content=%r",
                transaction_id,
                payload.get("transferType"),
                payload.get("transferAmount"),
                order_code,
                payload.get("content"),
            )
            if transaction_id and find_processed_transaction(transaction_id):
                logger.info("[SePay] tx=%s duplicate, skipped", transaction_id)
                _json_response(self, 200, {"success": True})
                return

            if payload.get("transferType") != "in":
                logger.info("[SePay] tx=%s transferType!=in, skipped", transaction_id)
                _json_response(self, 200, {"success": True})
                return

            order = find_pending_order_by_code(order_code, provider="sepay") if order_code else None
            if not order:
                late_order = find_order_by_code(order_code, provider="sepay") if order_code else None
                logger.info(
                    "[SePay] tx=%s no pending order (late=%s)",
                    transaction_id,
                    (late_order or {}).get("status"),
                )
                # Đơn hàng web (tạo từ web, lưu trên Supabase) - xử lý qua Supabase.
                if order_code:
                    try:
                        from supabase_sync import get_web_order_status, grant_web_order
                        web_order = get_web_order_status(order_code)
                        if web_order:
                            amount = int(payload.get("transferAmount", 0) or 0)
                            if amount == int(web_order.get("amount_vnd", 0) or 0):
                                granted = grant_web_order(
                                    order_code,
                                    transaction_id=transaction_id,
                                    transaction_note=payload.get("referenceCode") or payload.get("content"),
                                )
                                if granted:
                                    logger.info("[SePay] tx=%s web order %s granted", transaction_id, order_code)
                                    if ADMIN_IDS:
                                        try:
                                            _run_async(bot.send_message(
                                                chat_id=ADMIN_IDS[0],
                                                text=(
                                                    "<b>SEPAY CAP GOI WEB THANH CONG</b>\n"
                                                    f"User: <code>{web_order.get('user_id')}</code>\n"
                                                    f"Goi: <b>{str(web_order.get('plan') or '').upper()}</b>\n"
                                                    f"So tien: <b>{web_order.get('amount_vnd')}</b> VND\n"
                                                    f"Ma don: <code>{order_code}</code>\n"
                                                    f"Transaction: <code>{transaction_id or '-'}</code>"
                                                ),
                                                parse_mode="HTML",
                                            ))
                                        except Exception as e:
                                            logger.warning(f"[SePay] admin web notify failed: {e}")
                                    _json_response(self, 200, {"success": True})
                                    return
                            else:
                                logger.info(
                                    "[SePay] tx=%s web order amount mismatch got=%s want=%s",
                                    transaction_id,
                                    amount,
                                    web_order.get("amount_vnd"),
                                )
                                _json_response(self, 200, {"success": True})
                                return
                    except Exception as e:
                        logger.warning("[SePay] web order handling failed: %s", e)

                if late_order and late_order.get("status") == "expired" and ADMIN_IDS:
                    _run_async(bot.send_message(
                        chat_id=ADMIN_IDS[0],
                        text=(
                            "<b>GIAO DICH DEN MUON</b>\n"
                            f"User: {_fmt_admin_user(int(late_order['user_id']))}\n"
                            f"Goi: <b>{str(late_order.get('plan') or '').upper()}</b>\n"
                            f"So tien: <b>{payload.get('transferAmount', 0)}</b> VND\n"
                            f"Ma don: <code>{late_order.get('order_code')}</code>\n"
                            f"Transaction: <code>{transaction_id or '-'}</code>"
                        ),
                        parse_mode="HTML",
                    ))
                _json_response(self, 200, {"success": True})
                return

            amount = int(payload.get("transferAmount", 0) or 0)
            if amount != int(order.get("amount_vnd", 0) or 0):
                logger.info(
                    "[SePay] tx=%s amount mismatch got=%s want=%s",
                    transaction_id,
                    amount,
                    order.get("amount_vnd"),
                )
                _json_response(self, 200, {"success": True})
                return

            paid_order = mark_order_paid(
                order["order_id"],
                transaction_id=transaction_id,
                transaction_note=payload.get("referenceCode") or payload.get("content"),
            )
            if not paid_order:
                _json_response(self, 200, {"success": True})
                return

            grant_plan(
                paid_order["user_id"],
                paid_order["plan"],
                approved_by=ADMIN_IDS[0] if ADMIN_IDS else None,
                source="sepay",
                order_id=paid_order["order_id"],
            )
            paid_order = find_order_by_code(order_code, provider="sepay") or paid_order
            plan = get_plan_snapshot(paid_order["user_id"])

            try:
                user_lang = get_user_lang(paid_order["user_id"]) or "vi"
                _edit_user_order(bot, paid_order, user_lang)
                _run_async(bot.send_message(
                    chat_id=paid_order["user_id"],
                    text=t("plan_approved", user_lang, plan=str(paid_order.get("plan") or "").upper()),
                    parse_mode="HTML",
                ))
            except Exception as e:
                logger.warning(f"[SePay] user notify failed: {e}")

            if ADMIN_IDS:
                try:
                    _run_async(bot.send_message(
                        chat_id=ADMIN_IDS[0],
                        text=(
                            "<b>SEPAY CAP GOI THANH CONG</b>\n"
                            f"User: {_fmt_admin_user(int(paid_order['user_id']))}\n"
                            f"Goi: <b>{str(paid_order.get('plan') or '').upper()}</b>\n"
                            f"Han goi: <b>{_fmt_time(plan.get('expires_at')) if plan.get('expires_at') else '-'}</b>\n"
                            f"So tien: <b>{paid_order.get('amount_vnd')}</b> VND\n"
                            f"Ma don: <code>{paid_order.get('order_code')}</code>\n"
                            f"Transaction: <code>{transaction_id or '-'}</code>"
                        ),
                        parse_mode="HTML",
                    ))
                except Exception as e:
                    logger.warning(f"[SePay] admin notify failed: {e}")

            _json_response(self, 200, {"success": True})

        def log_message(self, fmt, *args):
            logger.info("[SePay] " + fmt, *args)

    _server = ReusableThreadingHTTPServer((SEPAY_WEBHOOK_HOST, SEPAY_WEBHOOK_PORT), SePayHandler)
    thread = threading.Thread(target=_server.serve_forever, daemon=True, name="sepay-webhook")
    thread.start()
    logger.info("[SePay] Webhook listening at http://%s:%s%s", SEPAY_WEBHOOK_HOST, SEPAY_WEBHOOK_PORT, SEPAY_WEBHOOK_PATH)
    return _server
