import base64
import re
from typing import Any

from utils.logger_config import get_logger

logger = get_logger(__name__)

# Gmail search query — cast a wide net for receipt/billing emails
_RECEIPT_QUERY = (
    "subject:(receipt OR invoice OR payment OR confirmation OR "
    "訂閱 OR 扣款 OR 收據 OR 發票 OR 付款) "
    "-in:trash -in:spam"
)


def fetch_receipt_emails(
    service,
    max_results: int = 100,
    query: str = _RECEIPT_QUERY,
) -> list[dict[str, Any]]:
    """Return a list of raw email dicts matching the receipt query."""
    logger.info("Fetching receipt emails (max=%d)", max_results)

    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    message_stubs = result.get("messages", [])
    logger.info("Found %d candidate emails", len(message_stubs))

    emails = []
    for stub in message_stubs:
        try:
            email = _fetch_full_message(service, stub["id"])
            emails.append(email)
        except Exception:
            logger.exception("Failed to fetch message id=%s", stub["id"])

    return emails


def _fetch_full_message(service, message_id: str) -> dict[str, Any]:
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    headers: dict[str, str] = {
        h["name"]: h["value"] for h in msg["payload"].get("headers", [])
    }

    return {
        "message_id": message_id,
        "subject": headers.get("Subject", ""),
        "sender": headers.get("From", ""),
        "date": headers.get("Date", ""),
        "body_text": _extract_body(msg["payload"]),
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a MIME payload."""
    mime_type = payload.get("mimeType", "")

    # Leaf node with data
    if "data" in payload.get("body", {}):
        if mime_type in ("text/plain", "text/html"):
            raw = payload["body"]["data"]
            decoded = base64.urlsafe_b64decode(raw + "==").decode("utf-8", errors="replace")
            if mime_type == "text/html":
                decoded = _strip_html(decoded)
            return decoded

    # Multipart: recurse into parts, prefer text/plain
    parts = payload.get("parts", [])
    plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
    if plain:
        return _extract_body(plain)

    # Fall back to first available part
    for part in parts:
        text = _extract_body(part)
        if text:
            return text

    return ""


def _strip_html(html: str) -> str:
    """Very lightweight HTML tag stripper."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"\s{2,}", " ", text).strip()
