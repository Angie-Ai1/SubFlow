"""Integration tests for app/parsers/importer.py.

Uses SQLite in-memory DB (via conftest.db_session).
Gmail service and fetcher are mocked — no network or OAuth flow required.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.parsers.importer import run_gmail_import
from database.models import BillingCycle, BillingRecord, Subscription


# ── Helpers ────────────────────────────────────────────────────────────────────


def _email(
    message_id: str = "msg001",
    subject: str = "Netflix Monthly Charge NT$150",
    sender: str = "billing@netflix.com",
    body_text: str = "",
    date: str = "Mon, 01 Jan 2026 00:00:00 +0000",
) -> dict:
    return {
        "message_id": message_id,
        "subject": subject,
        "sender": sender,
        "date": date,
        "body_text": body_text,
    }


def _run(db, emails: list[dict]):
    """Invoke run_gmail_import with mocked external dependencies."""
    with (
        patch("app.parsers.importer.get_gmail_service", return_value=MagicMock()),
        patch("app.parsers.importer.fetch_receipt_emails", return_value=emails),
    ):
        return run_gmail_import(db)


# ── New email — happy path ─────────────────────────────────────────────────────


class TestNewEmailHappyPath:
    def test_creates_subscription_stub_and_billing_record(self, db_session):
        result = _run(db_session, [_email()])

        assert result.total_fetched == 1
        assert result.parsed == 1
        assert result.inserted == 1
        assert result.skipped_duplicate == 0
        assert result.skipped_no_amount == 0

    def test_stub_subscription_has_correct_fields(self, db_session):
        _run(db_session, [_email()])

        sub = db_session.query(Subscription).one()
        assert sub.name == "Netflix"
        assert sub.is_active is True
        assert sub.billing_cycle == BillingCycle.monthly  # default for stubs

    def test_billing_record_linked_to_stub(self, db_session):
        _run(db_session, [_email()])

        sub = db_session.query(Subscription).one()
        rec = db_session.query(BillingRecord).one()
        assert rec.gmail_message_id == "msg001"
        assert rec.subscription_id == sub.id
        assert rec.currency == "TWD"


# ── Deduplication ──────────────────────────────────────────────────────────────


class TestDeduplication:
    def test_same_message_id_skipped_on_second_run(self, db_session):
        _run(db_session, [_email()])
        result = _run(db_session, [_email()])  # same message_id

        assert result.skipped_duplicate == 1
        assert result.inserted == 0
        assert db_session.query(BillingRecord).count() == 1

    def test_different_message_ids_different_dates_both_inserted(self, db_session):
        # Different dates → different billing months, both should be inserted
        emails = [
            _email(message_id="msg001", date="Mon, 01 Jan 2026 00:00:00 +0000"),
            _email(message_id="msg002", date="Sun, 01 Feb 2026 00:00:00 +0000"),
        ]
        result = _run(db_session, emails)

        assert result.inserted == 2
        assert db_session.query(BillingRecord).count() == 2

    def test_mix_of_new_and_duplicate(self, db_session):
        _run(db_session, [_email(message_id="msg001")])
        result = _run(
            db_session,
            [
                _email(message_id="msg001"),  # duplicate (message_id)
                _email(message_id="msg002", date="Sun, 01 Feb 2026 00:00:00 +0000"),  # new (different date)
            ],
        )

        assert result.skipped_duplicate == 1
        assert result.inserted == 1
        assert db_session.query(BillingRecord).count() == 2


# ── Emails without extractable amount ─────────────────────────────────────────


class TestNoAmount:
    def test_email_without_amount_counted_as_skipped(self, db_session):
        result = _run(
            db_session,
            [_email(subject="Hello from Netflix", body_text="No billing info here")],
        )

        assert result.skipped_no_amount == 1
        assert result.parsed == 0
        assert result.inserted == 0

    def test_no_subscription_stub_created_for_unparseable_email(self, db_session):
        _run(
            db_session,
            [_email(subject="Account update", body_text="Nothing to charge")],
        )
        assert db_session.query(Subscription).count() == 0


# ── ProposedChange detection ───────────────────────────────────────────────────


class TestProposedChanges:
    def _add_subscription(self, db_session, amount: float, currency: str = "TWD") -> Subscription:
        sub = Subscription(
            name="Netflix",
            amount=amount,
            currency=currency,
            billing_cycle=BillingCycle.monthly,
            is_active=True,
        )
        db_session.add(sub)
        db_session.commit()
        return sub

    def test_amount_diff_generates_proposed_change(self, db_session):
        self._add_subscription(db_session, amount=100.0)
        result = _run(db_session, [_email()])  # email carries NT$150

        assert len(result.proposed_changes) == 1
        change = result.proposed_changes[0]
        assert change.subscription_name == "Netflix"
        assert change.current_amount == pytest.approx(100.0)
        assert float(change.new_amount) == pytest.approx(150.0)

    def test_same_amount_produces_no_proposed_change(self, db_session):
        self._add_subscription(db_session, amount=150.0)  # matches NT$150 in email
        result = _run(db_session, [_email()])

        assert len(result.proposed_changes) == 0

    def test_currency_diff_generates_proposed_change(self, db_session):
        self._add_subscription(db_session, amount=150.0, currency="USD")
        result = _run(db_session, [_email()])  # email is TWD

        assert len(result.proposed_changes) == 1
        change = result.proposed_changes[0]
        assert change.current_currency == "USD"
        assert change.new_currency == "TWD"

    def test_inactive_subscription_does_not_generate_proposed_change(self, db_session):
        sub = self._add_subscription(db_session, amount=100.0)
        sub.is_active = False
        db_session.commit()

        result = _run(db_session, [_email()])  # amount differs but sub is inactive
        assert len(result.proposed_changes) == 0

    def test_only_latest_change_kept_per_subscription(self, db_session):
        self._add_subscription(db_session, amount=100.0)
        emails = [
            _email(message_id="m1", subject="Netflix NT$120"),  # first email: 120
            _email(message_id="m2", subject="Netflix NT$150"),  # second email: 150
        ]
        result = _run(db_session, emails)

        # Both trigger ProposedChange for same subscription; only the last one survives
        assert len(result.proposed_changes) == 1
        assert float(result.proposed_changes[0].new_amount) == pytest.approx(150.0)


# ── Multiple services ──────────────────────────────────────────────────────────


class TestFuzzyMatch:
    def test_uppercase_existing_subscription_matched_case_insensitively(self, db_session):
        """_find_or_create_subscription uses ilike — 'NETFLIX' in DB should match email 'Netflix'."""
        sub = Subscription(
            name="NETFLIX",
            amount=100.0,
            currency="TWD",
            billing_cycle=BillingCycle.monthly,
            is_active=True,
        )
        db_session.add(sub)
        db_session.commit()

        result = _run(db_session, [_email()])  # parser extracts service_name="Netflix"

        assert db_session.query(Subscription).count() == 1  # no new stub created
        assert result.inserted == 1

    def test_partial_name_match_finds_existing_subscription(self, db_session):
        """'Netflix Premium' in DB should match email 'Netflix' (ilike %netflix%)."""
        sub = Subscription(
            name="Netflix Premium",
            amount=150.0,
            currency="TWD",
            billing_cycle=BillingCycle.monthly,
            is_active=True,
        )
        db_session.add(sub)
        db_session.commit()

        result = _run(db_session, [_email()])

        assert db_session.query(Subscription).count() == 1
        assert result.inserted == 1


class TestMultipleServices:
    def test_different_services_create_separate_stubs(self, db_session):
        emails = [
            _email(message_id="m1", subject="Netflix NT$150", sender="billing@netflix.com"),
            _email(message_id="m2", subject="Spotify NT$99", sender="billing@spotify.com"),
        ]
        result = _run(db_session, emails)

        assert result.total_fetched == 2
        assert result.inserted == 2
        assert db_session.query(Subscription).count() == 2
        assert db_session.query(BillingRecord).count() == 2

    def test_same_service_multiple_bills_share_one_subscription(self, db_session):
        # Different dates → legitimate monthly recurrence, both should be inserted
        emails = [
            _email(message_id="m1", subject="Netflix NT$150", sender="billing@netflix.com"),
            _email(
                message_id="m2",
                subject="Netflix NT$150",
                sender="billing@netflix.com",
                date="Mon, 01 Feb 2026 00:00:00 +0000",
            ),
        ]
        _run(db_session, emails)

        assert db_session.query(Subscription).count() == 1
        assert db_session.query(BillingRecord).count() == 2

    def test_content_duplicate_different_message_id_skipped(self, db_session):
        # Same date + same amount but different message_id (forwarded/resent) → deduped
        emails = [
            _email(message_id="m1", subject="Netflix NT$150"),
            _email(message_id="m2", subject="Netflix NT$150"),
        ]
        result = _run(db_session, emails)

        assert result.inserted == 1
        assert result.skipped_duplicate == 1
        assert db_session.query(BillingRecord).count() == 1
