import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import OnboardingCompleteResult, OnboardingPatch, OnboardingStateOut
from app.services.onboarding_nutrition import suggested_daily_calories

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)


def _parse_data(user: User) -> dict:
    if not user.onboarding_data:
        return {}
    try:
        return json.loads(user.onboarding_data)
    except json.JSONDecodeError:
        return {}


def _save_data(user: User, data: dict) -> None:
    user.onboarding_data = json.dumps(data, ensure_ascii=False)


@router.get("/state", response_model=OnboardingStateOut)
def get_state(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    db.refresh(user)
    return OnboardingStateOut(
        completed=bool(user.onboarding_completed),
        step=int(user.onboarding_step or 0),
        data=_parse_data(user),
    )


@router.put("/state", response_model=OnboardingStateOut)
def put_state(
    body: OnboardingPatch,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    data = _parse_data(user)
    # Shallow merge: new keys overwrite
    for k, v in body.data.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    user.onboarding_step = max(int(user.onboarding_step or 0), body.step)
    _save_data(user, data)
    db.commit()
    db.refresh(user)
    return OnboardingStateOut(
        completed=bool(user.onboarding_completed),
        step=user.onboarding_step,
        data=_parse_data(user),
    )


@router.post("/reopen", response_model=OnboardingStateOut)
def reopen_onboarding(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Reset onboarding so the client can show the setup wizard again (e.g. after testing or a new device)."""
    user.onboarding_completed = False
    user.onboarding_step = 0
    user.onboarding_data = "{}"
    db.commit()
    db.refresh(user)
    return OnboardingStateOut(
        completed=False,
        step=0,
        data={},
    )


@router.post("/complete", response_model=OnboardingCompleteResult)
def complete_onboarding(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    data = _parse_data(user)
    if not data.get("terms_accepted"):
        raise HTTPException(status_code=400, detail="Accept terms before completing onboarding")

    # Apply profile fields from onboarding answers
    if name := data.get("preferred_name") or data.get("first_name"):
        user.full_name = str(name).strip()[:255] or user.full_name
    if (x := data.get("current_weight_kg")) is not None:
        try:
            user.current_weight_kg = float(x)
        except (TypeError, ValueError):
            pass
    if (x := data.get("goal_weight_kg")) is not None:
        try:
            user.goal_weight_kg = float(x)
        except (TypeError, ValueError):
            pass
    if (x := data.get("height_cm")) is not None:
        try:
            user.height_cm = float(x)
        except (TypeError, ValueError):
            pass

    suggested = suggested_daily_calories(data)
    if suggested is not None:
        user.daily_calorie_target = suggested

    user.onboarding_completed = True
    user.onboarding_step = max(int(user.onboarding_step or 0), 99)
    _save_data(user, data)
    db.commit()
    db.refresh(user)

    msg = "Your profile is ready."
    if suggested is not None:
        msg += f" Suggested daily calories: ~{suggested} kcal (estimate — not medical advice)."
    return OnboardingCompleteResult(ok=True, message=msg, suggested_daily_calories=suggested)
