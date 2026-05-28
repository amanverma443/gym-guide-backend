import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dates import utc_today
from app.deps import get_current_user
from app.models import DayMealPlan, MealLog, User
from app.routers.meals import TEXT_MEAL_IMAGE, _to_out
from app.schemas import DayMealPlanOut, DayMealPlanResponse, LogActualMealBody, MealOut
from app.services.gemini import estimate_meal_from_text, generate_daily_meal_plan
from app.services.nutrition_context import build_chat_nutrition_context, build_meal_scan_nutrition_context
from app.services.rate_limit import assert_ai_budget, log_ai_call

router = APIRouter(prefix="/meal-plan", tags=["meal-plan"])
logger = logging.getLogger(__name__)


@router.get("/today", response_model=DayMealPlanResponse)
def get_today_plan(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    today = utc_today()
    row = db.execute(
        select(DayMealPlan).where(DayMealPlan.user_id == user.id, DayMealPlan.plan_date == today)
    ).scalar_one_or_none()
    return DayMealPlanResponse(plan=DayMealPlanOut.model_validate(row) if row else None)


@router.post("/today/generate", response_model=DayMealPlanOut)
def generate_today_plan(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    assert_ai_budget(db, user)
    today = utc_today()
    ctx = build_chat_nutrition_context(db, user)
    try:
        data = generate_daily_meal_plan(ctx)
    except Exception as e:
        logger.exception("Day meal plan AI failed user_id=%s", user.id)
        raise HTTPException(status_code=502, detail=f"AI meal plan failed: {e!s}") from e

    if not data.get("breakfast") or not data.get("lunch") or not data.get("dinner"):
        raise HTTPException(status_code=502, detail="AI returned an incomplete meal plan")

    existing = db.execute(
        select(DayMealPlan).where(DayMealPlan.user_id == user.id, DayMealPlan.plan_date == today)
    ).scalar_one_or_none()
    if existing:
        existing.breakfast_suggestion = data["breakfast"]
        existing.lunch_suggestion = data["lunch"]
        existing.dinner_suggestion = data["dinner"]
        row = existing
    else:
        row = DayMealPlan(
            user_id=user.id,
            plan_date=today,
            breakfast_suggestion=data["breakfast"],
            lunch_suggestion=data["lunch"],
            dinner_suggestion=data["dinner"],
        )
        db.add(row)

    log_ai_call(db, user.id, "day_plan")
    db.commit()
    db.refresh(row)
    return DayMealPlanOut.model_validate(row)


@router.post("/log-actual", response_model=MealOut)
def log_actual_meal(
    body: LogActualMealBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    assert_ai_budget(db, user)
    nutrition_ctx = build_meal_scan_nutrition_context(db, user)
    try:
        est = estimate_meal_from_text(body.description, body.slot, nutrition_ctx)
    except Exception as e:
        logger.exception("Text meal estimate failed user_id=%s", user.id)
        raise HTTPException(status_code=502, detail=f"AI estimate failed: {e!s}") from e

    row = MealLog(
        user_id=user.id,
        image_path=TEXT_MEAL_IMAGE,
        calories=est["calories"],
        protein_g=est["protein_g"],
        carbs_g=est["carbs_g"],
        fat_g=est["fat_g"],
        healthier_tip=est["healthier_tip"],
        raw_notes=est.get("plan_fit_note") or None,
        entry_kind="text",
        meal_slot=body.slot,
        user_description=body.description,
    )
    db.add(row)
    log_ai_call(db, user.id, "text_meal")
    db.commit()
    db.refresh(row)
    return _to_out(row)
