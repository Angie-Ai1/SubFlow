import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

from utils.logger_config import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedReceipt:
    message_id: str
    service_name: str
    amount: Decimal
    currency: str
    billed_at: datetime
    raw_subject: str
    sender: str


# ── Amount patterns (priority order) ─────────────────────────────────────────

_AMOUNT_PATTERNS: list[tuple[str, str]] = [
    # TWD / NTD
    (r"(?:NT\$|NTD|TWD)\s*([\d,]+(?:\.\d{1,2})?)", "TWD"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*(?:TWD|NTD)", "TWD"),
    # USD
    (r"(?:USD|US\$)\s*([\d,]+(?:\.\d{1,2})?)", "USD"),
    (r"\$\s*([\d,]+\.\d{2})\b", "USD"),          # $X.XX — require cents to reduce FP
    (r"([\d,]+(?:\.\d{1,2})?)\s*USD", "USD"),
    # EUR
    (r"(?:EUR|€)\s*([\d,]+(?:\.\d{1,2})?)", "EUR"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*EUR", "EUR"),
    # JPY
    (r"(?:JPY|¥|JP¥)\s*([\d,]+)", "JPY"),
    (r"([\d,]+)\s*(?:JPY|円)", "JPY"),
]

# ── Well-known sender → service name map ─────────────────────────────────────

_SENDER_MAP: dict[str, str] = {
    "netflix.com": "Netflix",
    "spotify.com": "Spotify",
    "apple.com": "Apple",
    "google.com": "Google",
    "youtube.com": "YouTube",
    "amazon.com": "Amazon",
    "microsoft.com": "Microsoft",
    "adobe.com": "Adobe",
    "dropbox.com": "Dropbox",
    "notion.so": "Notion",
    "github.com": "GitHub",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "chatgpt.com": "ChatGPT",
    "figma.com": "Figma",
    "canva.com": "Canva",
    "zoom.us": "Zoom",
    "slack.com": "Slack",
    "discord.com": "Discord",
    "twitch.tv": "Twitch",
    "hbo.com": "HBO",
    "disneyplus.com": "Disney+",
    "hulu.com": "Hulu",
    "kktv.me": "KKTV",
    "linetv.tw": "LINE TV",
    "catchplay.com": "CatchPlay",
    "friday.tw": "friDay",
}


# ── Public API ────────────────────────────────────────────────────────────────

def parse_receipt(email: dict[str, Any]) -> ParsedReceipt | None:
    """Return a ParsedReceipt or None if amount cannot be extracted."""
    search_text = f"{email['subject']} {email['body_text']}"

    amount, currency = _extract_amount(search_text)
    if amount is None:
        logger.info("No amount found | subject=%r sender=%r", email["subject"], email["sender"])
        return None

    service_name = _extract_service_name(email["sender"], email["subject"])
    billed_at = _parse_date(email["date"])

    return ParsedReceipt(
        message_id=email["message_id"],
        service_name=service_name,
        amount=amount,
        currency=currency,
        billed_at=billed_at,
        raw_subject=email["subject"],
        sender=email["sender"],
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_amount(text: str) -> tuple[Decimal | None, str]:
    for pattern, currency in _AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                return Decimal(raw), currency
            except InvalidOperation:
                continue
    return None, ""


def _extract_service_name(sender: str, subject: str) -> str:
    # Try known sender domain first
    domain_match = re.search(r"@([\w.-]+)", sender)
    if domain_match:
        domain = domain_match.group(1).lower()
        for key, name in _SENDER_MAP.items():
            if domain.endswith(key):
                return name
        # Fallback: capitalise the second-level domain
        parts = domain.split(".")
        if len(parts) >= 2:
            return parts[-2].capitalize()

    # Try to extract service name from subject (first capitalised word group)
    subject_match = re.match(r"([A-Z][A-Za-z0-9+\s]{1,30}?)(?:\s+receipt|\s+invoice|\s+payment|$)", subject)
    if subject_match:
        return subject_match.group(1).strip()

    return "Unknown"


def _parse_date(date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        logger.warning("Could not parse date %r, using now()", date_str)
        return datetime.now()
