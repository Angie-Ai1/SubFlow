"""Unit tests for app/parsers/receipt_parser.py and gmail_fetcher._strip_html.

No DB or network required — all tests run against pure Python logic.
"""
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from app.parsers.receipt_parser import (
    _extract_amount,
    _extract_service_name,
    _parse_date,
    parse_receipt,
)
from app.parsers.gmail_fetcher import _strip_html


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


class TestExtractAmountGBP:
    def test_pound_symbol(self):
        amount, currency = _extract_amount("£9.99 per month")
        assert amount == Decimal("9.99")
        assert currency == "GBP"

    def test_gbp_prefix(self):
        amount, currency = _extract_amount("GBP 14.99 charged")
        assert amount == Decimal("14.99")
        assert currency == "GBP"

    def test_gbp_suffix(self):
        amount, currency = _extract_amount("You were charged 7.99 GBP")
        assert amount == Decimal("7.99")
        assert currency == "GBP"


class TestExtractAmountKRW:
    def test_won_symbol(self):
        amount, currency = _extract_amount("₩9,900 결제")
        assert amount == Decimal("9900")
        assert currency == "KRW"

    def test_krw_suffix(self):
        amount, currency = _extract_amount("결제금액: 9900 KRW")
        assert amount == Decimal("9900")
        assert currency == "KRW"


class TestExtractAmountAdditionalCurrencies:
    def test_sgd_prefix(self):
        amount, currency = _extract_amount("SGD 5.99 billed")
        assert amount == Decimal("5.99")
        assert currency == "SGD"

    def test_aud_prefix(self):
        amount, currency = _extract_amount("AUD 12.99 monthly")
        assert amount == Decimal("12.99")
        assert currency == "AUD"

    def test_hkd_prefix(self):
        amount, currency = _extract_amount("HK$78 subscription")
        assert amount == Decimal("78")
        assert currency == "HKD"

    def test_cad_prefix(self):
        amount, currency = _extract_amount("CA$14.99 per month")
        assert amount == Decimal("14.99")
        assert currency == "CAD"


class TestExtractAmountChineseFormats:
    def test_yuan_suffix(self):
        amount, currency = _extract_amount("月費 150元")
        assert amount == Decimal("150")
        assert currency == "TWD"

    def test_yuan_suffix_with_space(self):
        amount, currency = _extract_amount("合計 299 元")
        assert amount == Decimal("299")
        assert currency == "TWD"

    def test_yuan_suffix_with_decimal(self):
        amount, currency = _extract_amount("費用 99.00元")
        assert amount == Decimal("99.00")
        assert currency == "TWD"

    def test_chinese_label_heti(self):
        amount, currency = _extract_amount("合計：299")
        assert amount == Decimal("299")
        assert currency == "TWD"

    def test_chinese_label_jine(self):
        amount, currency = _extract_amount("金額:150")
        assert amount == Decimal("150")
        assert currency == "TWD"

    def test_chinese_label_feiyong(self):
        amount, currency = _extract_amount("訂閱費用：490")
        assert amount == Decimal("490")
        assert currency == "TWD"

    def test_xintaibei_prefix(self):
        amount, currency = _extract_amount("新台幣 320 元")
        assert amount == Decimal("320")
        assert currency == "TWD"

    def test_yuan_no_false_positive_on_word(self):
        # 元素 (element) must NOT match
        amount, currency = _extract_amount("共有3元素組成")
        assert amount is None

    def test_yuan_comma_thousands(self):
        amount, currency = _extract_amount("費用 1,200元")
        assert amount == Decimal("1200")
        assert currency == "TWD"


class TestExtractAmountContextAnchored:
    def test_total_label_whole_dollar(self):
        amount, currency = _extract_amount("Total: $9")
        assert amount == Decimal("9")
        assert currency == "USD"

    def test_amount_due_label(self):
        amount, currency = _extract_amount("Amount Due: $50.00")
        assert amount == Decimal("50.00")
        assert currency == "USD"

    def test_charged_label(self):
        amount, currency = _extract_amount("You were charged: $25")
        assert amount == Decimal("25")
        assert currency == "USD"

    def test_payment_label(self):
        amount, currency = _extract_amount("Payment: $14.99")
        assert amount == Decimal("14.99")
        assert currency == "USD"


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

    def test_cctld_domain_extracts_brand_not_tld(self):
        # shop.brand.com.au → multi-part TLD (.com.au) should be skipped, brand extracted
        assert _extract_service_name("no-reply@shop.amazon.com.au", "") == "Amazon"

    def test_multiple_amounts_selects_maximum(self):
        # Email has subtotal + tax + total; should return the total (maximum)
        from app.parsers.receipt_parser import _extract_amount
        amount, currency = _extract_amount("Subtotal $8.99  Tax $0.90  Total $9.89")
        assert amount == Decimal("9.89")
        assert currency == "USD"


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
        before = datetime.now(timezone.utc)
        dt = _parse_date("not-a-date-string")
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_empty_date_string_falls_back(self):
        before = datetime.now(timezone.utc)
        dt = _parse_date("")
        after = datetime.now(timezone.utc)
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

    def test_chinese_yuan_body(self):
        email = _make_email(
            subject="訂閱確認",
            body_text="本月費用 150元，感謝訂閱。",
            sender="billing@kktv.me",
        )
        result = parse_receipt(email)
        assert result is not None
        assert result.amount == Decimal("150")
        assert result.currency == "TWD"

    def test_gbp_body(self):
        email = _make_email(
            subject="Your Subscription Invoice",
            body_text="Total: £9.99",
            sender="billing@nordvpn.com",
        )
        result = parse_receipt(email)
        assert result is not None
        assert result.amount == Decimal("9.99")
        assert result.currency == "GBP"
        assert result.service_name == "NordVPN"


# ── _strip_html HTML entity decoding ──────────────────────────────────────────


class TestStripHtml:
    def test_dollar_numeric_entity(self):
        assert "$" in _strip_html("&#36;9.99")

    def test_dollar_hex_entity(self):
        assert "$" in _strip_html("&#x24;9.99")

    def test_pound_entity(self):
        assert "£" in _strip_html("&pound;9.99")

    def test_yen_entity(self):
        assert "¥" in _strip_html("&yen;1200")

    def test_euro_entity(self):
        assert "€" in _strip_html("&euro;9.99")

    def test_won_entity(self):
        assert "₩" in _strip_html("&won;9900")

    def test_strips_html_tags(self):
        result = _strip_html("<td>NT$150</td>")
        assert "<td>" not in result
        assert "NT$150" in result

    def test_entity_decoded_amount_extractable(self):
        decoded = _strip_html("<td>&#36;9.99</td>")
        amount, currency = _extract_amount(decoded)
        assert amount == Decimal("9.99")
        assert currency == "USD"
