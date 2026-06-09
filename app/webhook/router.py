from fastapi import APIRouter, Depends, Header, HTTPException, Request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks.models import FollowEvent, MessageEvent, TextMessageContent, UnfollowEvent
from sqlalchemy.orm import Session

from app.webhook.handlers import handle_follow, handle_text_message, handle_unfollow
from app.webhook.line_client import get_messaging_api, parser
from database.session import get_db
from utils.logger_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/callback")
async def callback(
    request: Request,
    x_line_signature: str = Header(),
    db: Session = Depends(get_db),
) -> dict:
    body = await request.body()

    if not x_line_signature.strip():
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        events = parser.parse(body.decode(), x_line_signature)
    except InvalidSignatureError:
        logger.warning("LINE webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    api = get_messaging_api()

    for event in events:
        try:
            if isinstance(event, FollowEvent):
                handle_follow(event, db, api)
            elif isinstance(event, UnfollowEvent):
                handle_unfollow(event, db)
            elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                handle_text_message(event, db, api)
            else:
                logger.debug("Unhandled event type: %s", type(event).__name__)
        except Exception:
            logger.exception("Error handling LINE event type=%s", type(event).__name__)

    return {"status": "ok"}
