from sqlalchemy.orm import Session
from linebot.v3.messaging import MessagingApi, PushMessageRequest, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks.models import FollowEvent, MessageEvent, TextMessageContent, UnfollowEvent

from database.models import LineUser, Subscription
from utils.logger_config import get_logger

logger = get_logger(__name__)

_WELCOME = (
    "歡迎使用 SubFlow 訂閱管理！\n\n"
    "可用指令：\n"
    "📋 訂閱清單 — 查看所有訂閱\n"
    "❓ 說明 — 顯示指令列表"
)

_HELP = (
    "SubFlow 指令說明：\n\n"
    "📋 訂閱清單 — 列出所有啟用中的訂閱\n"
    "❓ 說明 — 顯示此說明"
)


# ── FollowEvent ───────────────────────────────────────────────────────────────

def handle_follow(event: FollowEvent, db: Session, api: MessagingApi) -> None:
    uid = event.source.user_id
    user = db.query(LineUser).filter(LineUser.line_user_id == uid).first()

    if user is None:
        db.add(LineUser(line_user_id=uid, is_active=True))
        logger.info("LINE user registered: %s", uid)
    elif not user.is_active:
        user.is_active = True
        logger.info("LINE user reactivated: %s", uid)

    db.commit()

    api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=_WELCOME)],
        )
    )


# ── UnfollowEvent ─────────────────────────────────────────────────────────────

def handle_unfollow(event: UnfollowEvent, db: Session) -> None:
    uid = event.source.user_id
    user = db.query(LineUser).filter(LineUser.line_user_id == uid).first()
    if user:
        user.is_active = False
        db.commit()
        logger.info("LINE user deactivated: %s", uid)


# ── MessageEvent ──────────────────────────────────────────────────────────────

def handle_text_message(event: MessageEvent, db: Session, api: MessagingApi) -> None:
    assert isinstance(event.message, TextMessageContent)
    text = event.message.text.strip()
    reply = _dispatch_command(text, db)

    api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply)],
        )
    )


def _dispatch_command(text: str, db: Session) -> str:
    normalized = text.lower()

    if normalized in ("說明", "help", "?", "？"):
        return _HELP

    if normalized in ("訂閱清單", "清單", "list"):
        return _build_subscription_list(db)

    return f"未知指令：「{text}」\n\n輸入「說明」查看可用指令。"


def _build_subscription_list(db: Session) -> str:
    subs = (
        db.query(Subscription)
        .filter(Subscription.is_active.is_(True))
        .order_by(Subscription.next_billing_date)
        .all()
    )

    if not subs:
        return "目前沒有啟用中的訂閱。"

    lines = ["📋 訂閱清單\n"]
    for s in subs:
        date_str = s.next_billing_date.strftime("%Y-%m-%d") if s.next_billing_date else "未設定"
        lines.append(f"• {s.name}  {s.amount} {s.currency} / {s.billing_cycle.value}")
        lines.append(f"  下次扣款：{date_str}")

    return "\n".join(lines)
