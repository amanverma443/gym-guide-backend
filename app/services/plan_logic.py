from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIPlan, User, WeightLog


def weight_logs_ordered_asc(db: Session, user_id: int) -> list[WeightLog]:
    q = select(WeightLog).where(WeightLog.user_id == user_id).order_by(WeightLog.logged_on.asc())
    return list(db.execute(q).scalars().all())


def should_auto_regenerate(db: Session, user: User) -> bool:
    """Trigger if weight-loss goal exists and ~7d window shows no downward trend."""
    if user.goal_weight_kg is None:
        return False

    logs = weight_logs_ordered_asc(db, user.id)
    if len(logs) < 2:
        return False

    latest = logs[-1]
    if user.goal_weight_kg >= latest.weight_kg:
        return False

    cutoff = date.today() - timedelta(days=7)
    old = None
    for w in logs:
        if w.logged_on <= cutoff:
            old = w
        else:
            break
    if old is None:
        old = logs[0]

    if latest.weight_kg < old.weight_kg - 0.15:
        return False

    recent_auto = db.execute(
        select(AIPlan)
        .where(AIPlan.user_id == user.id, AIPlan.source == "auto")
        .order_by(AIPlan.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if recent_auto:
        if recent_auto.created_at > datetime.utcnow() - timedelta(days=3):
            return False

    return True


def deactivate_old_plans(db: Session, user_id: int) -> None:
    for p in db.execute(select(AIPlan).where(AIPlan.user_id == user_id)).scalars():
        p.is_current = False
