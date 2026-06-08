from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings
from utils.logger_config import get_logger

logger = get_logger(__name__)

# Read-only scope is sufficient for receipt scraping
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Return an authenticated Gmail API service object.

    On first run, opens a browser for OAuth2 consent and caches the token
    at settings.google_token_path.  Subsequent runs refresh silently.
    """
    creds = _load_token()

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail token")
            creds.refresh(Request())
        else:
            logger.info("Starting OAuth2 flow for Gmail (browser will open)")
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.google_credentials_path, _SCOPES
            )
            creds = flow.run_local_server(port=0)

        _save_token(creds)

    try:
        service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail service authenticated OK")
        return service
    except HttpError as exc:
        logger.error("Failed to build Gmail service: %s", exc)
        raise


def _load_token() -> Credentials | None:
    path = Path(settings.google_token_path)
    if path.exists():
        return Credentials.from_authorized_user_file(str(path), _SCOPES)
    return None


def _save_token(creds: Credentials) -> None:
    path = Path(settings.google_token_path)
    path.write_text(creds.to_json(), encoding="utf-8")
    logger.debug("Gmail token saved to %s", path)
