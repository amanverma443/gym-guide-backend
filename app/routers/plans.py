import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import AIPlan, User
from app.schemas import PlanRegenerateResult
from app.services.plan_service import build_plan

router = APIRouter(prefix="/plans", tags=["plans"])
logger = logging.getLogger(__name__)

@router.post("/regenerate", response_model=PlanRegenerateResult)
def regenerate(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    if user.goal_weight_kg is None:
        raise HTTPException(status_code=400, detail="Set a goal weight in your profile first")
    try:
        _, summary, _ = build_plan(db, user, reason="User requested plan refresh", source="manual")
    except RuntimeError as e:
        logger.warning("Plan regenerate: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("Plan generation failed user_id=%s", user.id)
        raise HTTPException(status_code=502, detail=f"Plan generation failed: {e!s}") from e
    return PlanRegenerateResult(ok=True, message="Plan updated", plan_summary=summary)
