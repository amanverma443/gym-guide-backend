from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WeightLog
from app.schemas import WeightLogCreate, WeightLogOut

router = APIRouter(prefix="/weight", tags=["weight"])


@router.get("/logs", response_model=list[WeightLogOut])
def list_logs(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    q = select(WeightLog).where(WeightLog.user_id == user.id).order_by(WeightLog.logged_on.desc())
    return list(db.execute(q).scalars().all())


@router.post("/logs", response_model=WeightLogOut)
def add_log(
    body: WeightLogCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    existing = db.execute(
        select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on == body.logged_on)
    ).scalar_one_or_none()
    if existing:
        existing.weight_kg = body.weight_kg
        db.commit()
        db.refresh(existing)
        wl = existing
    else:
        wl = WeightLog(user_id=user.id, logged_on=body.logged_on, weight_kg=body.weight_kg)
        db.add(wl)
        db.commit()
        db.refresh(wl)

    latest = db.execute(
        select(WeightLog).where(WeightLog.user_id == user.id).order_by(WeightLog.logged_on.desc()).limit(1)
    ).scalar_one_or_none()
    if latest and latest.id == wl.id:
        user.current_weight_kg = body.weight_kg
        db.commit()
    return wl
