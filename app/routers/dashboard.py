import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.dates import utc_today
from app.database import get_db
from app.deps import get_current_user
from app.models import AIPlan, ExerciseBurnLog, MealLog, User, WeightLog
from app.schemas import DashboardOut
from app.services.plan_logic import should_auto_regenerate
from app.services.plan_service import build_plan
from app.services.rate_limit import ai_calls_today

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)


@router.get("", response_model=DashboardOut)
def dashboard(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    # Match MealLog.created_at (naive UTC) — do not use server local date.today()
    today = utc_today()
    cal_q = select(func.coalesce(func.sum(MealLog.calories), 0)).where(
        MealLog.user_id == user.id,
        func.date(MealLog.created_at) == today,
    )
    calories_today = float(db.execute(cal_q).scalar() or 0)

    burn_q = select(func.coalesce(func.sum(ExerciseBurnLog.calories_burned), 0)).where(
        ExerciseBurnLog.user_id == user.id,
        ExerciseBurnLog.logged_on == today,
    )
    burned_today = float(db.execute(burn_q).scalar() or 0)
    net_today = calories_today - burned_today

    latest_w = db.execute(
        select(WeightLog).where(WeightLog.user_id == user.id).order_by(WeightLog.logged_on.desc()).limit(1)
    ).scalar_one_or_none()

    plan = db.execute(
        select(AIPlan).where(AIPlan.user_id == user.id, AIPlan.is_current.is_(True)).order_by(AIPlan.created_at.desc())
    ).scalar_one_or_none()

    auto_flag = False
    if should_auto_regenerate(db, user) and user.goal_weight_kg is not None:
        try:
            build_plan(db, user, reason="No clear progress toward goal in the last 7 days", source="auto")
            auto_flag = True
            plan = db.execute(
                select(AIPlan).where(AIPlan.user_id == user.id, AIPlan.is_current.is_(True)).order_by(AIPlan.created_at.desc())
            ).scalar_one_or_none()
        except Exception:
            logger.exception("Auto plan regenerate failed user_id=%s", user.id)

    calls = ai_calls_today(db, user.id)
    return DashboardOut(
        daily_calorie_target=user.daily_calorie_target,
        calories_consumed_today=calories_today,
        calories_burned_today=burned_today,
        net_calories_today=net_today,
        daily_exercise_guidance=user.daily_exercise_guidance,
        weight_kg_latest=latest_w.weight_kg if latest_w else user.current_weight_kg,
        goal_weight_kg=user.goal_weight_kg,
        plan_summary=plan.summary_line if plan else None,
        plan_detail=plan.content if plan else None,
        ai_calls_today=calls,
        ai_daily_limit=settings.ai_daily_limit,
        auto_regenerated_plan=auto_flag,
    )
