"""Derive daily calorie target from onboarding answers (Mifflin–St Jeor + PAL + weekly loss)."""

from __future__ import annotations

import math

# Physical activity level multipliers (not including workouts — matches standard TDEE)
PAL_BY_KEY: dict[str, float] = {
    "not_very_active": 1.2,
    "lightly_active": 1.375,
    "active": 1.55,
    "very_active": 1.725,
}


def bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """kcal/day. sex: male | female | other (other uses male formula as neutral default)."""
    s = (sex or "male").lower()
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * float(age)
    if s == "female":
        return base - 161.0
    return base + 5.0


def suggested_daily_calories(onboarding: dict) -> int | None:
    """
    TDEE = BMR * PAL; daily target = TDEE - (weekly_kg_loss * 7700 / 7).
    Rough rule: ~7700 kcal per kg fat mass equivalent per week.
    """
    try:
        w = float(onboarding["current_weight_kg"])
        h = float(onboarding["height_cm"])
        age = int(onboarding["age"])
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0 or age < 13 or age > 120:
        return None

    sex = str(onboarding.get("sex") or "male")
    pal_key = str(onboarding.get("activity_level") or "lightly_active")
    pal = PAL_BY_KEY.get(pal_key, 1.375)

    weekly_loss = float(onboarding.get("weekly_weight_loss_kg") or 0.5)
    weekly_loss = max(0.1, min(weekly_loss, 1.5))

    bmr = bmr_mifflin_st_jeor(w, h, age, sex)
    tdee = bmr * pal
    daily_deficit = (weekly_loss * 7700.0) / 7.0
    target = tdee - daily_deficit
    # Reasonable floor for adults dieting (not medical advice)
    target = max(1200.0, min(target, 6000.0))
    return int(math.floor(target + 0.5))
