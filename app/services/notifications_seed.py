from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Notification


def ensure_welcome_notification(db: Session, user_id: int) -> None:
    n = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user_id))
    if n and n > 0:
        return
    db.add(
        Notification(
            user_id=user_id,
            title="Welcome to Gym Guide",
            body="Tap Sync anytime to refresh your data. Explore Diary, Progress, and More for the full experience.",
            kind="welcome",
        )
    )
    db.commit()
