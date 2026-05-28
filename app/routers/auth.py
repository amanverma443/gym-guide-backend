from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import GoogleAuthBody, Token, UserCreate, UserLogin
from app.security import create_access_token, hash_password, verify_password
from app.services.notifications_seed import ensure_welcome_notification

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(body: UserCreate, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email.lower().strip(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        onboarding_completed=False,
        onboarding_step=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_welcome_notification(db, user.id)
    return Token(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=Token)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.lower().strip())).scalar_one_or_none()
    if user is None or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return Token(access_token=create_access_token(str(user.id)))


@router.post("/google", response_model=Token)
def google_auth(body: GoogleAuthBody, db: Session = Depends(get_db)):
    from google.auth.transport import requests
    from google.oauth2 import id_token

    from app.config import settings

    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google Sign-In is not configured on the server")
    try:
        info = id_token.verify_oauth2_token(body.id_token, requests.Request(), settings.google_client_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    email = (info.get("email") or "").lower().strip()
    sub = info.get("sub")
    if not email or not sub:
        raise HTTPException(status_code=400, detail="Google token missing email")

    user = db.execute(select(User).where(User.google_sub == sub)).scalar_one_or_none()
    if user:
        return Token(access_token=create_access_token(str(user.id)))

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        user.google_sub = sub
        db.commit()
        db.refresh(user)
        return Token(access_token=create_access_token(str(user.id)))

    user = User(email=email, google_sub=sub, full_name=info.get("name"), hashed_password=None)
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_welcome_notification(db, user.id)
    return Token(access_token=create_access_token(str(user.id)))
