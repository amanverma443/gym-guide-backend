"""Aggregate stats for the last 7 calendar days."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dates import utc_today
from app.models import ExerciseBurnLog, MealLog, WeightLog


def build_weekly_report(db: Session, user_id: int) -> dict:
    end = utc_today()
    start = end - timedelta(days=6)

    cal_q = select(func.coalesce(func.sum(MealLog.calories), 0)).where(
        MealLog.user_id == user_id,
        func.date(MealLog.created_at) >= start,
        func.date(MealLog.created_at) <= end,
    )
    calories_in = float(db.execute(cal_q).scalar() or 0)

    burn_q = select(func.coalesce(func.sum(ExerciseBurnLog.calories_burned), 0)).where(
        ExerciseBurnLog.user_id == user_id,
        ExerciseBurnLog.logged_on >= start,
        ExerciseBurnLog.logged_on <= end,
    )
    calories_burned = float(db.execute(burn_q).scalar() or 0)

    wlogs = db.scalars(
        select(WeightLog)
        .where(
            WeightLog.user_id == user_id,
            WeightLog.logged_on >= start,
            WeightLog.logged_on <= end,
        )
        .order_by(WeightLog.logged_on.asc())
    ).all()

    weight_change: float | None = None
    if len(wlogs) >= 2:
        weight_change = round(wlogs[0].weight_kg - wlogs[-1].weight_kg, 2)
    elif len(wlogs) == 1:
        weight_change = 0.0

    headline = f"You logged {len(wlogs)} weigh-ins and tracked about {calories_in:.0f} kcal from meals this week."
    if weight_change is not None and weight_change > 0.05:
        headline += f" Weight down ~{weight_change:.1f} kg from your first to last log in this window."

    return {
        "period_start": start,
        "period_end": end,
        "total_calories_consumed": round(calories_in, 1),
        "total_calories_burned": round(calories_burned, 1),
        "weight_logs_count": len(wlogs),
        "weight_change_kg": weight_change,
        "headline": headline,
    }
