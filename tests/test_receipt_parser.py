"""Unit tests for app/parsers/receipt_parser.py.

No DB or network required — all tests run against pure Python logic.
"""
from decimal import Decimal
from datetime import datetime

import pytest

from app.parsers.receipt_parser import (
    _extract_amount,
    _extract_service_name,
    _parse_date,
    parse_receipt,
)


# ── _extract_amount ────────────────────────────────────────────────────────────


class TestExtractAmountTWD:
    def test_nt_dollar_sign_prefix(self):
        amount, currency = _extract_amount("Your charge: NT$150")
        assert amount == Decimal("150")
        assert currency == "TWD"

    def test_ntd_prefix(self):
        amount, currency = _extract_amount("NTD 299 charged this month")
        assert amount == Decimal("299")
        assert currency == "TWD"

    def test_twd_suffix(self):
        amount, currency = _extract_amount("Total 599 TWD")
        assert amount == Decimal("599")
        assert currency == "TWD"

    def test_twd_with_comma_thousands(self):
        amount, currency = _extract_amount("NT$1,200 annual fee")
        assert amount == Decimal("1200")
        assert currency == "TWD"

    def test_twd_with_decimal(self):
        amount, currency = _extract_amount("NT$150.00 billed")
        assert amount == Decimal("150.00")
        assert currency == "TWD"


class TestExtractAmountUSD:
    def test_dollar_sign_with_cents(self):
        # Pattern requires two decimal places to avoid false positives
        amount, currency = _extract_amount("Total: $9.99")
        assert amount == Decimal("9.99")
        assert currency == "USD"

    def test_usd_explicit_prefix(self):
        amount, currency = _extract_amount("USD 29.99 charged")
        assert amount == Decimal("29.99")
        assert currency == "USD"

    def test_us_dollar_prefix(self):
        amount, currency = _extract_amount("US$ 14.99 per month")
        assert amount == Decimal("14.99")
        assert currency == "USD"


class TestExtractAmountEUR:
    def test_euro_symbol(self):
        amount, currency = _extract_amount("€12.50 debited")
        assert amount == Decimal("12.50")
        assert currency == "EUR"

    def test_eur_prefix(self):
        amount, currency = _extract_amount("EUR 9.99 monthly")
        assert amount == Decimal("9.99")
        assert currency == "EUR"


class TestExtractAmountJPY:
    def test_yen_symbol(self):
        amount, currency = _extract_amount("¥1,200 請求")
        assert amount == Decimal("1200")
        assert currency == "JPY"

    def test_jpy_suffix(self):
        amount, currency = _extract_amount("請求金額 980 JPY")
        assert amount == Decimal("980")
        assert currency == "JPY"


class TestExtractAmountEdgeCases:
    def test_no_amount_returns_none_and_empty_currency(self):
        amount, currency = _extract_amount("Thank you for subscribing!")
        assert amount is None
        assert currency == ""

    def test_twd_pattern_wins_over_usd_when_both_present(self):
        # NT$ appears first — should match TWD before falling through to USD
        amount, currency = _extract_amount("NT$150 receipt (approx $4.50 USD)")
        assert currency == "TWD"
        assert amount == Decimal("150")


# ── _extract_service_name ──────────────────────────────────────────────────────


class TestExtractServiceName:
    def test_exact_domain_in_sender_map(self):
        assert _extract_service_name("billing@netflix.com", "Receipt") == "Netflix"

    def test_subdomain_match(self):
        # mail.spotify.com ends with spotify.com → still maps to "Spotify"
        assert _extract_service_name("no-reply@mail.spotify.com", "") == "Spotify"

    def test_openai_domain(self):
        assert _extract_service_name("billing@openai.com", "OpenAI receipt") == "OpenAI"

    def test_github_domain(self):
        assert _extract_service_name("noreply@github.com", "GitHub Sponsors") == "GitHub"

    def test_unknown_domain_capitalises_second_level(self):
        # myapp.io → "io" is TLD, second-level is "myapp" → "Myapp"
        assert _extract_service_name("billing@myapp.io", "") == "Myapp"

    def test_well_known_subdomain_still_resolves(self):
        # accounts.google.com ends with google.com → "Google"
        assert _extract_service_name("no-reply@accounts.google.com", "") == "Google"


# ── _parse_date ────────────────────────────────────────────────────────────────


class TestParseDate:
    def test_valid_rfc2822_date(self):
        dt = _parse_date("Mon, 01 Jan 2026 12:00:00 +0000")
        assert isinstance(dt, datetime)
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 1

    def test_valid_rfc2822_with_positive_offset(self):
        dt = _parse_date("Fri, 09 Jun 2026 08:00:00 +0800")
        assert dt.year == 2026
        assert dt.month == 6

    def test_invalid_date_falls_back_to_current_time(self):
        before = datetime.now()
        dt = _parse_date("not-a-date-string")
        after = datetime.now()
        assert before <= dt <= after

    def test_empty_date_string_falls_back(self):
        before = datetime.now()
        dt = _parse_date("")
        after = datetime.now()
        assert before <= dt <= after


# ── parse_receipt ──────────────────────────────────────────────────────────────


def _make_email(**overrides) -> dict:
    base = {
        "message_id": "msg_test_001",
        "subject": "Netflix Monthly Charge NT$150",
        "sender": "billing@netflix.com",
        "date": "Mon, 01 Jan 2026 00:00:00 +0000",
        "body_text": "",
    }
    return {**base, **overrides}


class TestParseReceipt:
    def test_returns_fully_populated_receipt(self):
        result = parse_receipt(_make_email())
        assert result is not None
        assert result.message_id == "msg_test_001"
        assert result.service_name == "Netflix"
        assert result.amount == Decimal("150")
        assert result.currency == "TWD"
        assert result.raw_subject == "Netflix Monthly Charge NT$150"
        assert result.sender == "billing@netflix.com"

    def test_returns_none_when_no_extractable_amount(self):
        email = _make_email(
            subject="Hello from Netflix — update your account",
            body_text="No billing information in this email.",
        )
        assert parse_receipt(email) is None

    def test_extracts_amount_from_body_when_subject_lacks_it(self):
        email = _make_email(
            subject="Payment confirmation",
            body_text="Your total is $9.99 USD",
            sender="no-reply@example-saas.com",
        )
        result = parse_receipt(email)
        assert result is not None
        assert result.currency == "USD"
        assert result.amount == Decimal("9.99")

    def test_billed_at_reflects_email_date_header(self):
        email = _make_email(date="Fri, 09 Jun 2026 08:00:00 +0800")
        result = parse_receipt(email)
        assert result is not None
        assert result.billed_at.year == 2026
        assert result.billed_at.month == 6

    def test_spotify_sender_resolved_correctly(self):
        email = _make_email(
            subject="Spotify Premium NT$99",
            sender="no-reply@mail.spotify.com",
        )
        result = parse_receipt(email)
        assert result is not None
        assert result.service_name == "Spotify"
        assert result.amount == Decimal("99")
