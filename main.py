"""
WhatsApp Cloud API proof-of-concept.

Just the messaging plumbing: webhook verification, signature-checked inbound
webhook handling, a canned text reply, and manual template-send trigger.
No AI, no agent logic, no platform integration.
"""

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

load_dotenv()

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")

GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
PAYLOADS_LOG_FILE = Path(__file__).parent / "payloads.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("whatsapp-poc")

app = FastAPI(title="WhatsApp Cloud API POC")


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta calls this once, when you configure the webhook URL, to confirm you own it."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verification succeeded")
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning("Webhook verification failed (mode=%s)", mode)
    return PlainTextResponse(content="Forbidden", status_code=403)


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Check X-Hub-Signature-256 against an HMAC-SHA256 of the raw body using the app secret."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header.removeprefix("sha256=")
    computed_signature = hmac.new(
        key=WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, computed_signature)


def _log_payload_to_file(payload: dict) -> None:
    """Append the raw payload as one JSON line, for building a sample payload collection."""
    try:
        with open(PAYLOADS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        logger.exception("Failed to write payload to %s", PAYLOADS_LOG_FILE)


@app.post("/webhook")
async def receive_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    """Receives incoming WhatsApp messages and status updates from Meta."""
    raw_body = await request.body()

    if not _verify_signature(raw_body, x_hub_signature_256):
        logger.warning("Rejected webhook call: invalid or missing signature")
        return PlainTextResponse(content="Forbidden", status_code=403)

    # Everything past this point must never raise, or Meta will retry the webhook.
    try:
        payload = json.loads(raw_body)
        logger.info("Incoming webhook payload:\n%s", json.dumps(payload, indent=2))
        _log_payload_to_file(payload)

        await _handle_payload(payload)
    except Exception:
        logger.exception("Error while handling webhook payload")

    return PlainTextResponse(content="OK", status_code=200)


async def _handle_payload(payload: dict) -> None:
    """Pull out a message or status update and act on it. Tolerates either shape, or neither."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError):
        logger.info("Webhook payload had no entry/changes/value to process")
        return

    messages = value.get("messages")
    statuses = value.get("statuses")

    if messages:
        message = messages[0]
        sender = message.get("from")
        message_type = message.get("type")

        if message_type == "text" and sender:
            logger.info("Incoming text message from %s: %s", sender, message["text"]["body"])
            await send_text_message(to=sender, body="Hi, this is a test")
        else:
            logger.info("Incoming message from %s with type=%s (not handled)", sender, message_type)

    elif statuses:
        status = statuses[0]
        logger.info(
            "Status update: message_id=%s status=%s recipient=%s",
            status.get("id"),
            status.get("status"),
            status.get("recipient_id"),
        )

    else:
        logger.info("Webhook value had neither messages nor statuses")


async def send_text_message(to: str, body: str) -> None:
    """Send a free-form text message via the WhatsApp Cloud API."""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(GRAPH_API_URL, headers=headers, json=payload)

    logger.info("send_text_message -> status=%s body=%s", response.status_code, response.text)


async def send_template_message(to: str, template_name: str = "hello_world", lang_code: str = "en_US") -> None:
    """Send a pre-approved template message via the WhatsApp Cloud API."""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template_name, "language": {"code": lang_code}},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(GRAPH_API_URL, headers=headers, json=payload)

    logger.info("send_template_message -> status=%s body=%s", response.status_code, response.text)


class SendTemplateRequest(BaseModel):
    to: str


@app.post("/send-template")
async def trigger_template_send(req: SendTemplateRequest):
    """Manual trigger (e.g. via curl or /docs) to send the default template to a number."""
    await send_template_message(to=req.to)
    return {"status": "sent", "to": req.to}
