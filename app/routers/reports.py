from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import WeeklyReportOut
from app.services.weekly_report import build_weekly_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/weekly", response_model=WeeklyReportOut)
def weekly_report(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    data = build_weekly_report(db, user.id)
    return WeeklyReportOut(**data)
