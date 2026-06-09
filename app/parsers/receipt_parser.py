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
    # ── TWD / NTD (explicit) ─────────────────────────────────────────────────
    (r"(?:NT\$|NTD|TWD)\s*([\d,]+(?:\.\d{1,2})?)", "TWD"),
    (r"新台幣\s*([\d,]+(?:\.\d{1,2})?)", "TWD"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*(?:TWD|NTD)", "TWD"),
    # Chinese billing labels → assume TWD (台灣 context)
    (
        r"(?:合計|小計|金額|費用|消費金額|應付金額|交易金額|訂閱費用|帳單金額)[：:]\s*([\d,]+(?:\.\d{1,2})?)",
        "TWD",
    ),
    # ── USD ───────────────────────────────────────────────────────────────────
    (r"(?:USD|US\$)\s*([\d,]+(?:\.\d{1,2})?)", "USD"),
    (r"(?<![A-Za-z])\$\s*([\d,]+\.\d{2})\b", "USD"),  # $X.XX — not preceded by letter (avoids CA$/HK$/A$/S$/C$)
    (r"([\d,]+(?:\.\d{1,2})?)\s*USD", "USD"),
    # Billing-label anchored $ — allows whole-dollar amounts (e.g. "Total: $9")
    (
        r"(?:total|amount\s+due|grand\s+total|charge[sd]?|invoice\s+total|billed|payment)[:\s]+\$\s*([\d,]+(?:\.\d{1,2})?)\b",
        "USD",
    ),
    # ── EUR ───────────────────────────────────────────────────────────────────
    (r"(?:EUR|€)\s*([\d,]+(?:\.\d{1,2})?)", "EUR"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*EUR", "EUR"),
    # ── GBP ───────────────────────────────────────────────────────────────────
    (r"(?:GBP|£)\s*([\d,]+(?:\.\d{1,2})?)", "GBP"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*GBP", "GBP"),
    # ── JPY ───────────────────────────────────────────────────────────────────
    (r"(?:JPY|¥|JP¥)\s*([\d,]+)", "JPY"),
    (r"([\d,]+)\s*(?:JPY|円)", "JPY"),
    # ── KRW ───────────────────────────────────────────────────────────────────
    (r"(?:KRW|₩)\s*([\d,]+)", "KRW"),
    (r"([\d,]+)\s*KRW", "KRW"),
    # ── SGD ───────────────────────────────────────────────────────────────────
    (r"(?:SGD|(?<![A-Za-z])S\$)\s*([\d,]+(?:\.\d{1,2})?)", "SGD"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*SGD", "SGD"),
    # ── AUD ───────────────────────────────────────────────────────────────────
    (r"(?:AUD|(?<![A-Za-z])A\$)\s*([\d,]+(?:\.\d{1,2})?)", "AUD"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*AUD", "AUD"),
    # ── HKD ───────────────────────────────────────────────────────────────────
    (r"(?:HKD|(?<![A-Za-z])HK\$)\s*([\d,]+(?:\.\d{1,2})?)", "HKD"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*HKD", "HKD"),
    # ── CAD ───────────────────────────────────────────────────────────────────
    (r"(?:CAD|(?<![A-Za-z])CA\$|(?<![A-Za-z])C\$)\s*([\d,]+(?:\.\d{1,2})?)", "CAD"),
    (r"([\d,]+(?:\.\d{1,2})?)\s*CAD", "CAD"),
    # ── 元/圓 suffix (TWD/CNY in Chinese subscription emails) ─────────────────
    # Negative lookahead prevents matching 元素/元年/元旦 etc.
    (r"([\d,]+(?:\.\d{1,2})?)\s*(?:元|圓)(?![a-zA-Z一-鿿])", "TWD"),
]

# ── Well-known sender → service name map ─────────────────────────────────────

_SENDER_MAP: dict[str, str] = {
    # ── Streaming / Media ────────────────────────────────────────────────────
    "netflix.com": "Netflix",
    "spotify.com": "Spotify",
    "apple.com": "Apple",
    "youtube.com": "YouTube",
    "amazon.com": "Amazon",
    "primevideo.com": "Prime Video",
    "primevideoemail.com": "Prime Video",
    "hbo.com": "HBO",
    "max.com": "Max",
    "disneyplus.com": "Disney+",
    "hulu.com": "Hulu",
    "paramountplus.com": "Paramount+",
    "twitch.tv": "Twitch",
    "kktv.me": "KKTV",
    "linetv.tw": "LINE TV",
    "catchplay.com": "CatchPlay",
    "friday.tw": "friDay",
    "kkbox.com": "KKBOX",
    "kkbox.com.tw": "KKBOX",
    "hami.tw": "Hami Video",
    "tidal.com": "Tidal",
    "deezer.com": "Deezer",
    # ── Cloud / Productivity ─────────────────────────────────────────────────
    "google.com": "Google",
    "microsoft.com": "Microsoft",
    "icloud.com": "iCloud",
    "dropbox.com": "Dropbox",
    "box.com": "Box",
    "notion.so": "Notion",
    "evernote.com": "Evernote",
    "todoist.com": "Todoist",
    "airtable.com": "Airtable",
    "asana.com": "Asana",
    "atlassian.com": "Atlassian",
    "monday.com": "Monday.com",
    "miro.com": "Miro",
    # ── Design ───────────────────────────────────────────────────────────────
    "adobe.com": "Adobe",
    "figma.com": "Figma",
    "canva.com": "Canva",
    "sketch.com": "Sketch",
    "framer.com": "Framer",
    # ── Communication ────────────────────────────────────────────────────────
    "zoom.us": "Zoom",
    "slack.com": "Slack",
    "discord.com": "Discord",
    "loom.com": "Loom",
    "calendly.com": "Calendly",
    "line.me": "LINE",
    # ── Dev / Hosting ────────────────────────────────────────────────────────
    "github.com": "GitHub",
    "digitalocean.com": "DigitalOcean",
    "linode.com": "Linode",
    "heroku.com": "Heroku",
    "vercel.com": "Vercel",
    "netlify.com": "Netlify",
    "cloudflare.com": "Cloudflare",
    "render.com": "Render",
    "railway.app": "Railway",
    "replit.com": "Replit",
    # ── AI / LLM ─────────────────────────────────────────────────────────────
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "chatgpt.com": "ChatGPT",
    "midjourney.com": "Midjourney",
    "cursor.sh": "Cursor",
    "perplexity.ai": "Perplexity",
    "elevenlabs.io": "ElevenLabs",
    "runway.ml": "Runway",
    # ── Security / VPN ───────────────────────────────────────────────────────
    "1password.com": "1Password",
    "nordvpn.com": "NordVPN",
    "expressvpn.com": "ExpressVPN",
    "surfshark.com": "Surfshark",
    "proton.me": "Proton",
    "protonmail.com": "Proton",
    # ── Payments / E-commerce ────────────────────────────────────────────────
    "paypal.com": "PayPal",
    "shopify.com": "Shopify",
    "stripe.com": "Stripe",
    "paddle.com": "Paddle",
    "gumroad.com": "Gumroad",
    "patreon.com": "Patreon",
    "fastspring.com": "FastSpring",
    # ── Taiwan-specific ───────────────────────────────────────────────────────
    "mycard.com.tw": "MyCard",
    "gash.com.tw": "Gash",
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
