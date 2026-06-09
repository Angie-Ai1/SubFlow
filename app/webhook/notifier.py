from datetime import date, timedelta

from linebot.v3.messaging import PushMessageRequest, TextMessage
from sqlalchemy.orm import Session

from app.config import settings
from app.webhook.line_client import get_messaging_api
from database.models import LineUser, Subscription
from utils.logger_config import get_logger

logger = get_logger(__name__)


def run_daily_billing_check(db: Session) -> None:
    """Push upcoming billing reminders to all active LINE users."""
    cutoff = date.today() + timedelta(days=settings.notify_days_advance)

    upcoming = (
        db.query(Subscription)
        .filter(
            Subscription.is_active.is_(True),
            Subscription.next_billing_date.isnot(None),
            Subscription.next_billing_date <= cutoff,
        )
        .order_by(Subscription.next_billing_date)
        .all()
    )

    if not upcoming:
        logger.info("billing check: no subscriptions due within %d days", settings.notify_days_advance)
        return

    active_users = db.query(LineUser).filter(LineUser.is_active.is_(True)).all()

    if not active_users:
        logger.info("billing check: no active LINE users to notify")
        return

    lines = [f"💳 未來 {settings.notify_days_advance} 天內扣款提醒\n"]
    for s in upcoming:
        date_str = s.next_billing_date.strftime("%Y-%m-%d")
        lines.append(f"• {s.name}  {s.amount} {s.currency}")
        lines.append(f"  扣款日：{date_str}")
    message_text = "\n".join(lines)

    api = get_messaging_api()
    for user in active_users:
        try:
            api.push_message(
                PushMessageRequest(
                    to=user.line_user_id,
                    messages=[TextMessage(text=message_text)],
                )
            )
            logger.info("billing reminder sent to %s", user.line_user_id)
        except Exception as exc:
            logger.error("push failed for %s: %s", user.line_user_id, exc)


def run_scheduled_gmail_import(db: Session) -> None:
    """Trigger the Gmail receipt import pipeline."""
    from app.parsers.importer import run_gmail_import

    try:
        result = run_gmail_import(db)
        logger.info(
            "scheduled gmail import | fetched=%d parsed=%d inserted=%d dup=%d",
            result.total_fetched,
            result.parsed,
            result.inserted,
            result.skipped_duplicate,
        )
    except Exception as exc:
        logger.error("scheduled gmail import failed: %s", exc)
