"""Build text blocks so Gemini can personalize chat and meal scan to the user's profile and today's intake."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dates import utc_today
from app.models import MealLog, User, WeightLog


def calories_logged_today(db: Session, user_id: int) -> float:
    today = utc_today()
    q = select(func.coalesce(func.sum(MealLog.calories), 0)).where(
        MealLog.user_id == user_id,
        func.date(MealLog.created_at) == today,
    )
    return float(db.execute(q).scalar() or 0)


def latest_weight_kg(db: Session, user: User) -> float | None:
    w = db.execute(
        select(WeightLog).where(WeightLog.user_id == user.id).order_by(WeightLog.logged_on.desc()).limit(1)
    ).scalar_one_or_none()
    if w is not None:
        return float(w.weight_kg)
    if user.current_weight_kg is not None:
        return float(user.current_weight_kg)
    return None


def build_chat_nutrition_context(db: Session, user: User) -> str:
    """Context for AI coach chat: profile + today's kcal vs target."""
    cal_today = calories_logged_today(db, user.id)
    w = latest_weight_kg(db, user)

    lines: list[str] = [
        "PERSONALIZATION (this user's data from the app — use it in every relevant answer):",
    ]
    if w is not None:
        lines.append(f"- Latest / current weight: {w:.1f} kg")
    else:
        lines.append("- Weight: not logged yet")
    if user.goal_weight_kg is not None:
        lines.append(f"- Goal weight: {user.goal_weight_kg:.1f} kg")
    else:
        lines.append("- Goal weight: not set")
    if user.height_cm is not None:
        lines.append(f"- Height: {user.height_cm:.0f} cm")
    if user.daily_calorie_target is not None:
        t = user.daily_calorie_target
        rem = t - cal_today
        lines.append(f"- Daily calorie target (from their AI plan): {t} kcal")
        lines.append(f"- Calories already logged today (meals in app): {cal_today:.0f} kcal")
        lines.append(f"- Approx. remaining toward today's target: {rem:.0f} kcal (target minus logged so far)")
    else:
        lines.append("- Daily calorie target: not set — suggest Profile + regenerate plan if they want numbers")
        lines.append(f"- Calories logged today: {cal_today:.0f} kcal")

    lines.append("")
    lines.append(
        "When the user asks about food, snacks, or diet, relate your answer to these numbers "
        "(remaining budget, whether a food fits today, progress toward goal). "
        "If they ask something unrelated, you can ignore this block."
    )
    return "\n".join(lines)


def build_meal_scan_nutrition_context(db: Session, user: User) -> str:
    """Context for meal photo analysis — kcal today *before* this meal is logged."""
    cal_before = calories_logged_today(db, user.id)
    w = latest_weight_kg(db, user)

    lines: list[str] = [
        "User profile (personalize the analysis and plan_fit_note):",
    ]
    if w is not None:
        lines.append(f"- Weight: {w:.1f} kg")
    if user.goal_weight_kg is not None:
        lines.append(f"- Goal weight: {user.goal_weight_kg:.1f} kg")
    if user.daily_calorie_target is not None:
        t = user.daily_calorie_target
        lines.append(f"- Daily calorie target: {t} kcal")
        lines.append(
            f"- Calories already logged TODAY before this meal photo: {cal_before:.0f} kcal "
            f"(after you estimate this meal, 'remaining for the day' ≈ {t} - {cal_before:.0f} - this meal's calories)"
        )
    else:
        lines.append("- Daily calorie target: not set in app")
        lines.append(f"- Calories logged today before this meal: {cal_before:.0f} kcal")

    lines.append("")
    lines.append(
        "In plan_fit_note, MUST compare this meal's estimated calories to their daily target and today's pre-meal total. "
        "Give concrete numbers (e.g. remaining kcal after this meal)."
    )
    return "\n".join(lines)
