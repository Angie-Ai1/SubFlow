from dataclasses import dataclass, field
from decimal import Decimal

from database.models import BillingRecord, RecordSource, Subscription
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.parsers.gmail_auth import get_gmail_service
from app.parsers.gmail_fetcher import fetch_receipt_emails
from app.parsers.receipt_parser import ParsedReceipt, parse_receipt
from utils.logger_config import get_logger

logger = get_logger(__name__)


class _ContentDuplicate(Exception):
    """Raised when a billing record with identical (sub, date, amount) already exists."""


@dataclass
class ProposedChange:
    subscription_id: int
    subscription_name: str
    current_amount: float
    current_currency: str
    new_amount: float
    new_currency: str
    raw_subject: str


@dataclass
class ImportResult:
    total_fetched: int
    parsed: int
    inserted: int
    skipped_duplicate: int
    skipped_no_amount: int
    proposed_changes: list[ProposedChange] = field(default_factory=list)


def run_gmail_import(db: Session, max_results: int = 2000) -> ImportResult:
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

    # keyed by subscription_id so only the latest proposed change per sub is kept
    _proposed: dict[int, ProposedChange] = {}

    try:
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

            try:
                proposed = _save_receipt(db, receipt)
                if proposed:
                    _proposed[proposed.subscription_id] = proposed
                result.inserted += 1
            except _ContentDuplicate:
                result.skipped_duplicate += 1
                logger.debug("Content duplicate skipped for message_id=%s", receipt.message_id)

        db.commit()
    except Exception:
        db.rollback()
        raise
    result.proposed_changes = list(_proposed.values())
    logger.info(
        "Gmail import done | fetched=%d parsed=%d inserted=%d dup=%d no_amount=%d changes=%d",
        result.total_fetched,
        result.parsed,
        result.inserted,
        result.skipped_duplicate,
        result.skipped_no_amount,
        len(result.proposed_changes),
    )
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_duplicate(db: Session, message_id: str) -> bool:
    return (
        db.query(BillingRecord).filter(BillingRecord.gmail_message_id == message_id).first()
    ) is not None


def _is_content_duplicate(db: Session, subscription_id: int, billed_at, amount: Decimal) -> bool:
    """Secondary dedup: catch the same bill arriving from a forwarded/resent email."""
    billed_date = billed_at.date() if hasattr(billed_at, "date") else billed_at
    return (
        db.query(BillingRecord)
        .filter(
            BillingRecord.subscription_id == subscription_id,
            func.date(BillingRecord.billed_at) == billed_date,
            BillingRecord.amount == float(amount),
        )
        .first()
    ) is not None


def _save_receipt(db: Session, receipt: ParsedReceipt) -> ProposedChange | None:
    subscription, is_existing = _find_or_create_subscription(db, receipt)

    if is_existing and _is_content_duplicate(
        db, subscription.id, receipt.billed_at, receipt.amount
    ):
        raise _ContentDuplicate()

    proposed = None
    if is_existing and subscription.is_active:
        amount_diff = abs(float(receipt.amount) - float(subscription.amount)) > 0.01
        currency_diff = receipt.currency != subscription.currency
        if amount_diff or currency_diff:
            proposed = ProposedChange(
                subscription_id=subscription.id,
                subscription_name=subscription.name,
                current_amount=float(subscription.amount),
                current_currency=subscription.currency,
                new_amount=float(receipt.amount),
                new_currency=receipt.currency,
                raw_subject=receipt.raw_subject,
            )

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
    return proposed


def _find_or_create_subscription(db: Session, receipt: ParsedReceipt) -> tuple[Subscription, bool]:
    """Return (subscription, is_existing). Creates a stub if not found."""
    name_lower = receipt.service_name.lower()
    subscription = db.query(Subscription).filter(Subscription.name.ilike(f"%{name_lower}%")).first()

    if subscription:
        return subscription, True

    subscription = Subscription(
        name=receipt.service_name,
        amount=float(receipt.amount),
        currency=receipt.currency,
        is_active=True,
    )
    db.add(subscription)
    db.flush()
    logger.info("Auto-created subscription stub: %r", receipt.service_name)
    return subscription, False
