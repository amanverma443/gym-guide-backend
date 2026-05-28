"""Streak and weight-loss stats from weight logs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dates import utc_today
from app.models import Notification, User, WeightLog
from app.schemas import UserSummaryOut


def logging_streak_days(db: Session, user_id: int) -> int:
    """Consecutive days with at least one weight log, counting backward from today (UTC date)."""
    rows = db.execute(
        select(WeightLog.logged_on).where(WeightLog.user_id == user_id).distinct()
    ).all()
    days = {r[0] for r in rows if r[0] is not None}
    if not days:
        return 0
    streak = 0
    d = utc_today()
    for _ in range(400):
        if d in days:
            streak += 1
            d = d - timedelta(days=1)
        else:
            break
    return streak


def kg_lost_since_first_log(db: Session, user_id: int, current_weight_kg: float | None) -> float:
    """Positive kg lost from earliest log to latest (profile current or newest log)."""
    logs = db.execute(
        select(WeightLog).where(WeightLog.user_id == user_id).order_by(WeightLog.logged_on.asc())
    ).scalars().all()
    if not logs:
        return 0.0
    first = logs[0].weight_kg
    latest = current_weight_kg if current_weight_kg is not None else logs[-1].weight_kg
    lost = first - latest
    return round(max(0.0, lost), 2)


def merge_preferences(raw: str | None, patch: dict) -> dict:
    base: dict = {}
    if raw:
        try:
            base = json.loads(raw)
            if not isinstance(base, dict):
                base = {}
        except json.JSONDecodeError:
            base = {}
    for k, v in patch.items():
        if v is None:
            base.pop(k, None)
        else:
            base[k] = v
    return base


def build_user_summary(db: Session, user: User) -> UserSummaryOut:
    streak = logging_streak_days(db, user.id)
    kg = kg_lost_since_first_log(db, user.id, user.current_weight_kg)
    unread = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
    )
    prefs: dict = {}
    if user.app_preferences:
        try:
            p = json.loads(user.app_preferences)
            if isinstance(p, dict):
                prefs = p
        except json.JSONDecodeError:
            prefs = {}
    return UserSummaryOut(
        streak_days=streak,
        kg_lost=kg,
        unread_notifications=int(unread or 0),
        premium_active=bool(user.premium_active),
        preferences=prefs,
        server_time_utc=datetime.utcnow(),
        last_sync_at=user.last_sync_at,
    )
