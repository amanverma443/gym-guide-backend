import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dates import utc_today
from app.deps import get_current_user
from app.models import ExerciseBurnLog, User
from app.schemas import ExerciseBurnCreate, ExerciseBurnOut, ExerciseSummaryOut

router = APIRouter(prefix="/exercise", tags=["exercise"])
UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


def _burn_to_out(row: ExerciseBurnLog) -> ExerciseBurnOut:
    img: str | None = None
    if row.image_path:
        rel = row.image_path.replace("\\", "/")
        if not rel.startswith("/"):
            rel = "/" + rel
        img = rel
    return ExerciseBurnOut(
        id=row.id,
        logged_on=row.logged_on,
        calories_burned=row.calories_burned,
        notes=row.notes,
        image_url=img,
        created_at=row.created_at,
    )


@router.get("/summary", response_model=ExerciseSummaryOut)
def exercise_summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    today = utc_today()
    rows = db.execute(
        select(ExerciseBurnLog)
        .where(ExerciseBurnLog.user_id == user.id, ExerciseBurnLog.logged_on == today)
        .order_by(ExerciseBurnLog.created_at.desc())
    ).scalars().all()
    burned = float(sum(r.calories_burned for r in rows))
    return ExerciseSummaryOut(
        daily_exercise_guidance=user.daily_exercise_guidance,
        calories_burned_today=burned,
        burns_today=[_burn_to_out(r) for r in rows],
    )


@router.post("/burn", response_model=ExerciseBurnOut)
def log_burn(
    body: ExerciseBurnCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    day = body.logged_on or utc_today()
    row = ExerciseBurnLog(
        user_id=user.id,
        logged_on=day,
        calories_burned=body.calories_burned,
        notes=body.notes,
        image_path=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _burn_to_out(row)


@router.post("/burn-upload", response_model=ExerciseBurnOut)
async def log_burn_upload(
    user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    calories_burned: float = Form(...),
    notes: str | None = Form(None),
):
    if calories_burned <= 0 or calories_burned > 100_000:
        raise HTTPException(status_code=400, detail="calories_burned must be between 0 and 100000")
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    user_dir = UPLOAD_ROOT / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "photo.jpg").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
        ext = ".jpg"
    fname = f"exercise_{uuid.uuid4().hex}{ext}"
    path = user_dir / fname
    path.write_bytes(raw)
    rel_path = f"/uploads/{user.id}/{fname}"

    row = ExerciseBurnLog(
        user_id=user.id,
        logged_on=utc_today(),
        calories_burned=calories_burned,
        notes=notes,
        image_path=rel_path,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _burn_to_out(row)
