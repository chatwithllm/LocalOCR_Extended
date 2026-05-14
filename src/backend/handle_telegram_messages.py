"""
Step 8: Implement Telegram Webhook Handler
===========================================
PROMPT Reference: Phase 2, Step 8

Handles incoming Telegram webhook POST requests. Extracts photos or PDF
documents from messages, saves them, routes to OCR, and sends feedback
to the user.

Feedback paths:
    ✅ Success: "Processed: $X.XX at Store | Y items"
    ⚠️ Low confidence: "Low confidence — please review in Home Assistant"
    ❌ Failure: "Could not process receipt. Saved for manual review."

Auth: Telegram signature validation (not Bearer token)
"""

import os
import logging
from uuid import uuid4
from datetime import datetime
from typing import Any

import requests as http_requests
from flask import Blueprint, request, jsonify, g

logger = logging.getLogger(__name__)

telegram_bp = Blueprint("telegram", __name__, url_prefix="/telegram")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


@telegram_bp.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Receive and process Telegram webhook updates."""
    if TELEGRAM_WEBHOOK_SECRET:
        provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if provided_secret != TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Rejected Telegram webhook request with invalid secret token.")
            return jsonify({"error": "Invalid webhook secret"}), 403

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"error": "Invalid update"}), 400

    logger.info(f"Telegram update: {update.get('update_id', '?')}")

    callback_query = update.get("callback_query")
    if callback_query:
        return _handle_callback_query(callback_query)

    message = update.get("message") or update.get("edited_message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not chat_id:
        return jsonify({"status": "ok"}), 200

    # Handle commands
    text = message.get("text", "")
    if text.startswith("/"):
        response_text = _handle_command(text, chat_id=chat_id)
        if response_text:
            send_telegram_message(chat_id, response_text)
        return jsonify({"status": "ok"}), 200

    # Handle photos and PDF documents
    photos = message.get("photo", [])
    document = message.get("document") or {}
    file_id = None
    file_label = "receipt"

    if photos:
        largest_photo = max(photos, key=lambda p: p.get("file_size", 0))
        file_id = largest_photo.get("file_id")
        file_label = "receipt image"
    elif _is_supported_receipt_document(document):
        file_id = document.get("file_id")
        file_label = "receipt PDF"
    else:
        send_telegram_message(chat_id, "📸 Please send a receipt photo or PDF to get started.")
        return jsonify({"status": "ok"}), 200

    message_id = str(message.get("message_id", ""))

    try:
        image_path = download_telegram_file(file_id)
        receipt_record_id = _create_pending_receipt(chat_id, message_id, image_path)
    except Exception as e:
        logger.error(f"Failed to prepare Telegram receipt: {e}")
        send_telegram_message(chat_id, f"❌ Could not download the {file_label}. Please try again.")
        return jsonify({"status": "error"}), 200

    send_telegram_message(
        chat_id,
        f"🧾 I received your {file_label}. Do you want me to process it?",
        reply_markup={
            "inline_keyboard": [[
                {"text": "Process", "callback_data": f"process_receipt:{receipt_record_id}"},
                {"text": "Cancel", "callback_data": f"cancel_receipt:{receipt_record_id}"},
            ]]
        },
    )

    return jsonify({"status": "ok"}), 200


def _handle_command(command: str, chat_id: str = "") -> str:
    """Handle bot commands."""
    cmd = command.split()[0].lower()
    if cmd == "/inventory":
        from src.backend.handle_inventory_walk import is_walk_enabled, start_walk
        if not is_walk_enabled(chat_id):
            return "Inventory walk is not enabled for this chat."
        start_walk(g.db_session, chat_id)
        return ""  # start_walk side-channels via send_telegram_message
    commands = {
        "/start": "👋 Welcome to Grocery Manager! Send me a receipt photo or PDF to get started.",
        "/help": (
            "📸 Send a receipt photo or PDF → I'll extract items and update your inventory.\n"
            "📦 /inventory → Walk through stale items and update what's left\n"
            "📊 /status → Check system status\n"
            "❓ /help → Show this message"
        ),
        "/status": "✅ System is running. Send a receipt photo or PDF to test!",
    }
    return commands.get(cmd, "❓ Unknown command. Type /help for available commands.")


def send_telegram_message(chat_id: str, text: str, reply_markup: dict[str, Any] | None = None):
    """Send a message back to a Telegram user."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — cannot send message")
        return

    try:
        response = http_requests.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                **({"reply_markup": reply_markup} if reply_markup else {}),
            },
            timeout=10,
        )
        if response.status_code != 200:
            logger.warning(f"Telegram sendMessage failed: {response.text}")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


def download_telegram_file(file_id: str) -> str:
    """Download a photo or document from Telegram CDN.

    Returns:
        Path to the saved file.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    # Get file path from Telegram
    response = http_requests.get(
        f"{TELEGRAM_API_BASE}/getFile",
        params={"file_id": file_id},
        timeout=10,
    )
    response.raise_for_status()
    file_path = response.json()["result"]["file_path"]

    # Download the file
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    file_response = http_requests.get(download_url, timeout=30)
    file_response.raise_for_status()

    # Save to receipts directory
    from src.backend.handle_receipt_upload import _get_receipts_root

    year_month = datetime.now().strftime("%Y/%m")
    save_dir = os.path.join(_get_receipts_root(), year_month)
    os.makedirs(save_dir, exist_ok=True)

    ext = os.path.splitext(file_path)[1] or ".jpg"
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}{ext}"
    save_path = os.path.join(save_dir, filename)

    with open(save_path, "wb") as f:
        f.write(file_response.content)

    logger.info(f"Telegram file saved: {save_path}")
    return save_path


def _is_supported_receipt_document(document: dict[str, Any]) -> bool:
    """Return True when the Telegram attachment is a supported receipt PDF."""
    if not document:
        return False

    mime_type = str(document.get("mime_type", "")).lower()
    file_name = str(document.get("file_name", "")).lower()
    return mime_type == "application/pdf" or file_name.endswith(".pdf")


def _create_pending_receipt(chat_id: str, message_id: str, image_path: str) -> int:
    """Persist a pending Telegram receipt before OCR begins."""
    from src.backend.initialize_database_schema import TelegramReceipt

    session = g.db_session
    record = TelegramReceipt(
        telegram_user_id=chat_id,
        message_id=message_id,
        image_path=image_path,
        status="pending",
    )
    session.add(record)
    session.commit()
    return record.id


def _handle_callback_query(callback_query: dict):
    """Handle Telegram inline button callbacks."""
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    callback_message_id = message.get("message_id")

    _answer_callback_query(callback_id)

    if not chat_id or not data:
        return jsonify({"status": "ok"}), 200

    if data.startswith("inv:"):
        from src.backend.handle_inventory_walk import (
            is_walk_enabled, dispatch_inv_callback,
        )
        if is_walk_enabled(chat_id):
            dispatch_inv_callback(g.db_session, chat_id, data, callback_message_id)
            g.db_session.commit()
        return jsonify({"status": "ok"}), 200

    if data.startswith("nudge:"):
        from src.backend.handle_inventory_walk import (
            is_walk_enabled, dispatch_nudge_callback,
        )
        if is_walk_enabled(chat_id):
            dispatch_nudge_callback(g.db_session, chat_id, data, callback_message_id)
            g.db_session.commit()
        return jsonify({"status": "ok"}), 200

    if ":" not in data:
        return jsonify({"status": "ok"}), 200

    action, record_id = data.split(":", 1)
    if action == "process_receipt":
        _process_pending_receipt(chat_id, record_id, callback_message_id)
    elif action == "cancel_receipt":
        _cancel_pending_receipt(chat_id, record_id, callback_message_id)

    return jsonify({"status": "ok"}), 200


def _process_pending_receipt(chat_id: str, record_id: str, message_id: int | None):
    from src.backend.extract_receipt_data import process_receipt
    from src.backend.initialize_database_schema import TelegramReceipt

    session = g.db_session
    record = session.query(TelegramReceipt).filter_by(id=int(record_id)).first()
    if not record:
        send_telegram_message(chat_id, "❌ Receipt not found.")
        return

    _edit_telegram_message(
        chat_id,
        message_id,
        "⏳ Processing receipt...",
    )

    try:
        result = process_receipt(
            image_path=record.image_path,
            source="telegram",
            chat_id=chat_id,
            receipt_record_id=record.id,
        )
        record.status = result.get("status", record.status)
        record.ocr_engine = result.get("ocr_engine")
        record.ocr_confidence = result.get("confidence")
        record.purchase_id = result.get("purchase_id")
        session.commit()
    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        record.status = "failed"
        session.commit()
        send_telegram_message(chat_id, "❌ Could not process receipt. Saved for manual review.")


def _cancel_pending_receipt(chat_id: str, record_id: str, message_id: int | None):
    from src.backend.initialize_database_schema import TelegramReceipt

    session = g.db_session
    record = session.query(TelegramReceipt).filter_by(id=int(record_id)).first()
    if record:
        record.status = "cancelled"
        session.commit()

    _edit_telegram_message(chat_id, message_id, "🛑 Receipt was not processed.")


def _answer_callback_query(callback_id: str | None):
    if not callback_id:
        return
    try:
        http_requests.post(
            f"{TELEGRAM_API_BASE}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Failed to answer Telegram callback query: {e}")


def _edit_telegram_message(chat_id: str, message_id: int | None, text: str,
                           reply_markup: dict | None = None):
    if not message_id:
        send_telegram_message(chat_id, text, reply_markup=reply_markup)
        return
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        response = http_requests.post(
            f"{TELEGRAM_API_BASE}/editMessageText",
            json=payload,
            timeout=10,
        )
        if response.status_code != 200:
            send_telegram_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Failed to edit Telegram message: {e}")
        send_telegram_message(chat_id, text, reply_markup=reply_markup)
