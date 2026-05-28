import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ChatMessage, User
from app.schemas import ChatMessageOut, ChatSend
from app.services.gemini import chat_reply
from app.services.nutrition_context import build_chat_nutrition_context
from app.services.rate_limit import assert_ai_budget, log_ai_call

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

@router.get("/messages", response_model=list[ChatMessageOut])
def get_messages(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    q = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(200)
    )
    return list(db.execute(q).scalars().all())


@router.post("/messages", response_model=list[ChatMessageOut])
def send_message(
    body: ChatSend,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    assert_ai_budget(db, user)
    user_msg = ChatMessage(user_id=user.id, role="user", content=body.message)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    prior = db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id, ChatMessage.id < user_msg.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    ).scalars().all()
    prior = list(reversed(list(prior)))
    lines = [f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in prior]
    history_text = "\n".join(lines)[-4000:]

    try:
        nutrition_ctx = build_chat_nutrition_context(db, user)
        reply = chat_reply(history_text, body.message, nutrition_ctx)
    except Exception as e:
        logger.exception("Chat AI failed for user_id=%s", user.id)
        raise HTTPException(status_code=502, detail=f"AI chat failed: {e!s}") from e

    asst = ChatMessage(user_id=user.id, role="assistant", content=reply)
    db.add(asst)
    log_ai_call(db, user.id, "chat")
    db.commit()
    db.refresh(asst)

    return [
        ChatMessageOut(id=user_msg.id, role="user", content=user_msg.content, created_at=user_msg.created_at),
        ChatMessageOut(id=asst.id, role="assistant", content=asst.content, created_at=asst.created_at),
    ]
