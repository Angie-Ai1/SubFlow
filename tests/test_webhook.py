"""Tests for LINE Bot webhook signature validation.

Covers: valid signature → 200, invalid signature → 400, missing header → 422.
No real LINE channel credentials required — the module-level parser is patched
with a known test secret for each signature test.
"""
import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from linebot.v3.webhook import WebhookParser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from database.base import Base
from database.session import get_db

# ── Test infrastructure ────────────────────────────────────────────────────────

TEST_SECRET = "subflow_test_channel_secret_abc"

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
Base.metadata.create_all(_engine)
_TestingSession = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    """TestClient with SQLite DB injected — no MySQL connection required."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ── Helpers ────────────────────────────────────────────────────────────────────

_TEST_PARSER = WebhookParser(TEST_SECRET)

# Minimal valid LINE webhook payload — no events to dispatch, just validates plumbing
_EMPTY_EVENTS_BODY = json.dumps(
    {"destination": "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "events": []}
)


def _sign(body: str) -> str:
    """Compute the HMAC-SHA256 signature LINE expects for the given body."""
    digest = hmac.new(
        TEST_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestWebhookSignature:
    def test_valid_signature_returns_200_ok(self, client):
        sig = _sign(_EMPTY_EVENTS_BODY)
        with (
            patch("app.webhook.router.parser", new=_TEST_PARSER),
            patch("app.webhook.router.get_messaging_api", return_value=MagicMock()),
        ):
            resp = client.post(
                "/webhook/callback",
                content=_EMPTY_EVENTS_BODY,
                headers={
                    "x-line-signature": sig,
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_invalid_signature_returns_400(self, client):
        # Signature is valid base64 but computed with the wrong key
        wrong_sig = base64.b64encode(b"wrong" * 8).decode()
        with patch("app.webhook.router.parser", new=_TEST_PARSER):
            resp = client.post(
                "/webhook/callback",
                content=_EMPTY_EVENTS_BODY,
                headers={
                    "x-line-signature": wrong_sig,
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == 400
        assert "Invalid signature" in resp.json()["detail"]

    def test_missing_signature_header_returns_422(self, client):
        # FastAPI rejects missing required Header before the handler runs
        resp = client.post(
            "/webhook/callback",
            content=_EMPTY_EVENTS_BODY,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    def test_tampered_body_returns_400(self, client):
        original_body = _EMPTY_EVENTS_BODY
        sig = _sign(original_body)
        tampered_body = original_body.replace("events", "evnets")  # corrupt the body
        with patch("app.webhook.router.parser", new=_TEST_PARSER):
            resp = client.post(
                "/webhook/callback",
                content=tampered_body,
                headers={
                    "x-line-signature": sig,
                    "content-type": "application/json",
                },
            )
        assert resp.status_code == 400
