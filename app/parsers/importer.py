from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.parsers.gmail_auth import get_gmail_service
from app.parsers.gmail_fetcher import fetch_receipt_emails
from app.parsers.receipt_parser import ParsedReceipt, parse_receipt
from database.models import BillingRecord, RecordSource, Subscription
from utils.logger_config import get_logger

logger = get_logger(__name__)


@dataclass
class ImportResult:
    total_fetched: int
    parsed: int
    inserted: int
    skipped_duplicate: int
    skipped_no_amount: int


def run_gmail_import(db: Session, max_results: int = 100) -> ImportResult:
    """Full pipeline: authenticate → fetch → parse → deduplicate → save."""
    service = get_gmail_service()
    emails = fetch_receipt_emails(service, max_results=max_results)

    result = ImportResult(
        total_fetched=len(emails),
        parsed=0,
        inserted=0,
        skipped_duplicate=0,
        skipped_no_amount=0,
    )

    for email in emails:
        receipt = parse_receipt(email)

        if receipt is None:
            result.skipped_no_amount += 1
            continue

        result.parsed += 1

        if _is_duplicate(db, receipt.message_id):
            result.skipped_duplicate += 1
            logger.debug("Duplicate gmail_message_id=%s, skipping", receipt.message_id)
            continue

        _save_receipt(db, receipt)
        result.inserted += 1

    db.commit()
    logger.info(
        "Gmail import done | fetched=%d parsed=%d inserted=%d dup=%d no_amount=%d",
        result.total_fetched,
        result.parsed,
        result.inserted,
        result.skipped_duplicate,
        result.skipped_no_amount,
    )
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_duplicate(db: Session, message_id: str) -> bool:
    return (
        db.query(BillingRecord)
        .filter(BillingRecord.gmail_message_id == message_id)
        .first()
    ) is not None


def _save_receipt(db: Session, receipt: ParsedReceipt) -> None:
    subscription = _find_or_create_subscription(db, receipt)

    record = BillingRecord(
        subscription_id=subscription.id,
        amount=float(receipt.amount),
        currency=receipt.currency,
        billed_at=receipt.billed_at,
        source=RecordSource.gmail,
        gmail_message_id=receipt.message_id,
        raw_subject=receipt.raw_subject,
    )
    db.add(record)
    logger.debug(
        "Inserting BillingRecord service=%r amount=%s %s",
        receipt.service_name,
        receipt.amount,
        receipt.currency,
    )


def _find_or_create_subscription(db: Session, receipt: ParsedReceipt) -> Subscription:
    """Match by service name (case-insensitive). Create a stub if not found."""
    name_lower = receipt.service_name.lower()
    subscription = (
        db.query(Subscription)
        .filter(Subscription.name.ilike(f"%{name_lower}%"))
        .first()
    )

    if subscription:
        return subscription

    # Auto-create a minimal subscription stub; user can fill details in dashboard
    subscription = Subscription(
        name=receipt.service_name,
        amount=float(receipt.amount),
        currency=receipt.currency,
        is_active=True,
    )
    db.add(subscription)
    db.flush()  # get subscription.id before creating BillingRecord
    logger.info("Auto-created subscription stub: %r", receipt.service_name)
    return subscription
