from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.dates import utc_today
from app.models import AICall, User


def ai_calls_today(db: Session, user_id: int) -> int:
    if not settings.ai_rate_limit_enabled:
        return 0
    today = utc_today()
    q = select(func.count()).select_from(AICall).where(
        AICall.user_id == user_id,
        func.date(AICall.created_at) == today,
    )
    return db.execute(q).scalar() or 0


def assert_ai_budget(db: Session, user: User) -> None:
    if not settings.ai_rate_limit_enabled:
        return
    if ai_calls_today(db, user.id) >= settings.ai_daily_limit:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily AI limit reached ({settings.ai_daily_limit} calls). Try again tomorrow.",
        )


def log_ai_call(db: Session, user_id: int, call_type: str) -> None:
    if not settings.ai_rate_limit_enabled:
        return
    db.add(AICall(user_id=user_id, call_type=call_type, created_at=datetime.now(timezone.utc)))
