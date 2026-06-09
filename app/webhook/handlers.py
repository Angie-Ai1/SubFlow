from datetime import date, timedelta

from linebot.v3.messaging import (
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks.models import FollowEvent, MessageEvent, TextMessageContent, UnfollowEvent
from sqlalchemy.orm import Session

from app.config import settings
from database.models import LineUser, Subscription
from utils.logger_config import get_logger

logger = get_logger(__name__)

_MAX_INPUT_LEN = 100

# ── Command keywords & quick reply labels ─────────────────────────────────────
_CMD_LIST     = "訂閱清單"
_CMD_UPCOMING = "即將到期"
_CMD_SEARCH   = "搜尋"
_CMD_DISABLE  = "停用"
_CMD_HELP     = "說明"
_CMD_MENU     = "選單"

_LBL_LIST     = "📋 訂閱清單"
_LBL_UPCOMING = "⏰ 即將到期"
_LBL_SEARCH   = "🔍 搜尋訂閱"
_LBL_DISABLE  = "⏸ 停用訂閱"
_LBL_HELP     = "❓ 使用說明"

_WELCOME = (
    "歡迎使用 SubFlow 訂閱管理！\n\n"
    "📋 訂閱清單 — 查看所有啟用中訂閱\n"
    "⏰ 即將到期 — 查看近期扣款提醒\n"
    "🔍 搜尋 <名稱> — 搜尋特定訂閱\n"
    "⏸ 停用 <名稱> — 停用指定訂閱\n"
    "❓ 說明 — 顯示完整指令說明\n\n"
    "點選下方按鈕快速開始："
)


def _help_text() -> str:
    return (
        "SubFlow 指令說明：\n\n"
        "📋 訂閱清單 — 列出所有啟用中的訂閱\n"
        f"⏰ 即將到期 — 列出 {settings.notify_days_advance} 天內扣款的訂閱\n"
        "🔍 搜尋 <名稱> — 搜尋包含關鍵字的訂閱\n"
        "   範例：搜尋 Netflix\n"
        "⏸ 停用 <名稱> — 停用符合名稱的啟用中訂閱\n"
        "   範例：停用 Netflix\n"
        "❓ 說明 — 顯示此說明"
    )


def _main_quick_reply() -> QuickReply:
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label=_LBL_LIST,     text=_CMD_LIST)),
            QuickReplyItem(action=MessageAction(label=_LBL_UPCOMING, text=_CMD_UPCOMING)),
            QuickReplyItem(action=MessageAction(label=_LBL_SEARCH,   text=_CMD_SEARCH)),
            QuickReplyItem(action=MessageAction(label=_LBL_DISABLE,  text=_CMD_DISABLE)),
            QuickReplyItem(action=MessageAction(label=_LBL_HELP,     text=_CMD_HELP)),
        ]
    )


def _msg(text: str, *, menu: bool = False) -> TextMessage:
    return TextMessage(text=text, quick_reply=_main_quick_reply() if menu else None)


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
            messages=[_msg(_WELCOME, menu=True)],
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

    if len(text) > _MAX_INPUT_LEN:
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[_msg("輸入內容過長，請使用下方按鈕操作。", menu=True)],
            )
        )
        return

    message = _dispatch_command(text, db)

    api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[message],
        )
    )


def _dispatch_command(text: str, db: Session) -> TextMessage:
    normalized = text.lower()

    # ── 說明 ──────────────────────────────────────────────────────────────────
    if normalized in (_CMD_HELP, "help", "?", "？"):
        return _msg(_help_text(), menu=True)

    # ── 選單 ──────────────────────────────────────────────────────────────────
    if normalized in (_CMD_MENU, "menu", "菜單"):
        return _msg("請選擇功能：", menu=True)

    # ── 訂閱清單 ──────────────────────────────────────────────────────────────
    if normalized in (_CMD_LIST, "清單", "list"):
        return _msg(_build_subscription_list(db))

    # ── 即將到期 ──────────────────────────────────────────────────────────────
    if normalized in (_CMD_UPCOMING, "到期", "upcoming"):
        return _msg(_build_upcoming_list(db))

    # ── 搜尋 <keyword> ────────────────────────────────────────────────────────
    if normalized.startswith(_CMD_SEARCH) or normalized.startswith("search"):
        prefix = _CMD_SEARCH if normalized.startswith(_CMD_SEARCH) else "search"
        keyword = text[len(prefix):].strip()
        if not keyword:
            return _msg(f"請輸入搜尋關鍵字，範例：\n{_CMD_SEARCH} Netflix", menu=True)
        return _msg(_search_subscriptions(db, keyword))

    # ── 停用 <keyword> ────────────────────────────────────────────────────────
    if normalized.startswith(_CMD_DISABLE) or normalized.startswith("disable"):
        prefix = _CMD_DISABLE if normalized.startswith(_CMD_DISABLE) else "disable"
        keyword = text[len(prefix):].strip()
        if not keyword:
            return _msg(f"請輸入要停用的訂閱名稱，範例：\n{_CMD_DISABLE} Netflix", menu=True)
        return _msg(_deactivate_subscription(db, keyword), menu=True)

    # ── 未知指令 ──────────────────────────────────────────────────────────────
    return _msg(f"未知指令：「{text}」\n\n輸入「{_CMD_HELP}」查看可用指令，或點選下方按鈕。", menu=True)


# ── Query helpers ─────────────────────────────────────────────────────────────

def _build_subscription_list(db: Session) -> str:
    subs = (
        db.query(Subscription)
        .filter(Subscription.is_active.is_(True))
        .order_by(Subscription.next_billing_date)
        .all()
    )

    if not subs:
        return "目前沒有啟用中的訂閱。"

    lines = [f"📋 訂閱清單（共 {len(subs)} 筆）\n"]
    for s in subs:
        date_str = s.next_billing_date.strftime("%Y-%m-%d") if s.next_billing_date else "未設定"
        lines.append(f"• {s.name}  {s.amount} {s.currency} / {s.billing_cycle.value}")
        lines.append(f"  下次扣款：{date_str}")

    return "\n".join(lines)


def _build_upcoming_list(db: Session) -> str:
    cutoff = date.today() + timedelta(days=settings.notify_days_advance)
    subs = (
        db.query(Subscription)
        .filter(
            Subscription.is_active.is_(True),
            Subscription.next_billing_date.isnot(None),
            Subscription.next_billing_date <= cutoff,
        )
        .order_by(Subscription.next_billing_date)
        .all()
    )

    if not subs:
        return f"未來 {settings.notify_days_advance} 天內沒有即將扣款的訂閱。"

    lines = [f"⏰ 即將到期（{settings.notify_days_advance} 天內，共 {len(subs)} 筆）\n"]
    for s in subs:
        date_str = s.next_billing_date.strftime("%Y-%m-%d")
        lines.append(f"• {s.name}  {s.amount} {s.currency}")
        lines.append(f"  扣款日：{date_str}")

    return "\n".join(lines)


def _search_subscriptions(db: Session, keyword: str) -> str:
    subs = (
        db.query(Subscription)
        .filter(Subscription.name.ilike(f"%{keyword}%"))
        .order_by(Subscription.is_active.desc(), Subscription.next_billing_date)
        .all()
    )

    if not subs:
        return f"找不到名稱包含「{keyword}」的訂閱。"

    lines = [f"🔍 搜尋結果：「{keyword}」（共 {len(subs)} 筆）\n"]
    for s in subs:
        status = "啟用" if s.is_active else "停用"
        date_str = s.next_billing_date.strftime("%Y-%m-%d") if s.next_billing_date else "未設定"
        lines.append(f"• [{status}] {s.name}  {s.amount} {s.currency} / {s.billing_cycle.value}")
        lines.append(f"  下次扣款：{date_str}")

    return "\n".join(lines)


def _deactivate_subscription(db: Session, keyword: str) -> str:
    matches = (
        db.query(Subscription)
        .filter(
            Subscription.is_active.is_(True),
            Subscription.name.ilike(f"%{keyword}%"),
        )
        .all()
    )

    if not matches:
        return f"找不到名稱包含「{keyword}」的啟用中訂閱。"

    if len(matches) > 1:
        names = "\n".join(f"• {s.name}" for s in matches)
        return f"找到多筆符合「{keyword}」的訂閱，請輸入更精確的名稱：\n\n{names}"

    sub = matches[0]
    sub.is_active = False
    db.commit()
    logger.info("subscription deactivated via LINE: id=%d name=%r", sub.id, sub.name)
    return f"已停用訂閱：{sub.name}"
