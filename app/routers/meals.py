import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import MealLog, User
from app.schemas import MealOut
from app.services.gemini import meal_from_image
from app.services.nutrition_context import build_meal_scan_nutrition_context
from app.services.rate_limit import assert_ai_budget, log_ai_call

router = APIRouter(prefix="/meals", tags=["meals"])
logger = logging.getLogger(__name__)
UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
TEXT_MEAL_IMAGE = "/__text__/none"


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in {".jpg", ".jpeg", ".png", ".webp", ".heic"} else ".jpg"


@router.get("", response_model=list[MealOut])
def list_meals(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    rows = db.execute(select(MealLog).where(MealLog.user_id == user.id).order_by(MealLog.created_at.desc())).scalars().all()
    return [_to_out(m) for m in rows]


def _to_out(m: MealLog) -> MealOut:
    kind = getattr(m, "entry_kind", None) or "photo"
    if kind == "text":
        image_url = ""
    else:
        rel = m.image_path.replace("\\", "/")
        if not rel.startswith("/"):
            rel = "/" + rel
        image_url = rel
    return MealOut(
        id=m.id,
        image_url=image_url,
        calories=m.calories,
        protein_g=m.protein_g,
        carbs_g=m.carbs_g,
        fat_g=m.fat_g,
        healthier_tip=m.healthier_tip,
        created_at=m.created_at,
        plan_fit_note=m.raw_notes,
        entry_kind="text" if kind == "text" else "photo",
        meal_slot=getattr(m, "meal_slot", None),
        user_description=getattr(m, "user_description", None),
    )


@router.post("/analyze", response_model=MealOut)
async def analyze_meal(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    assert_ai_budget(db, user)
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    mime = file.content_type or "image/jpeg"
    nutrition_ctx = build_meal_scan_nutrition_context(db, user)
    try:
        data = meal_from_image(raw, mime, nutrition_ctx)
    except Exception as e:
        logger.exception("Meal AI analysis failed for user_id=%s", user.id)
        raise HTTPException(status_code=502, detail=f"AI meal analysis failed: {e!s}") from e

    user_dir = UPLOAD_ROOT / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    ext = _safe_ext(file.filename or "photo.jpg")
    fname = f"{uuid.uuid4().hex}{ext}"
    path = user_dir / fname
    path.write_bytes(raw)
    rel_path = f"/uploads/{user.id}/{fname}"

    row = MealLog(
        user_id=user.id,
        image_path=rel_path,
        calories=data["calories"],
        protein_g=data["protein_g"],
        carbs_g=data["carbs_g"],
        fat_g=data["fat_g"],
        healthier_tip=data["healthier_tip"],
        raw_notes=data.get("plan_fit_note") or None,
    )
    db.add(row)
    log_ai_call(db, user.id, "vision")
    db.commit()
    db.refresh(row)
    return _to_out(row)
