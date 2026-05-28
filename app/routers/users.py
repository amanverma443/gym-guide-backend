import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import PreferencesPatch, UserOut, UserSummaryOut, UserUpdate
from app.services.user_summary import build_user_summary, merge_preferences

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/summary", response_model=UserSummaryOut)
def me_summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    db.refresh(user)
    return build_user_summary(db, user)


@router.patch("/me/preferences", response_model=UserSummaryOut)
def patch_preferences(
    body: PreferencesPatch,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    raw = body.model_dump(exclude_unset=True)
    patch = {k: v for k, v in raw.items() if v is not None}
    merged = merge_preferences(user.app_preferences, patch)
    user.app_preferences = json.dumps(merged)
    db.commit()
    db.refresh(user)
    return build_user_summary(db, user)


@router.post("/me/premium/trial")
def start_premium_trial(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    user.premium_active = True
    db.commit()
    return {"ok": True, "premium_active": True}


@router.post("/me/sync", response_model=UserSummaryOut)
def sync_me(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    user.last_sync_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return build_user_summary(db, user)
