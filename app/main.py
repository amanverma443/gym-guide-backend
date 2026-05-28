import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine, run_sqlite_migrations
from app.routers import auth, chat, dashboard, exercise, meal_plan, meals, notifications, onboarding, plans, reports, users, weight

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("gym_guide")

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Gym Guide API", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log 422 bodies in the terminal (otherwise FastAPI only returns JSON to the client)."""
    log.warning("422 validation failed %s %s — %s", request.method, request.url.path, exc.errors())
    return await request_validation_exception_handler(request, exc)


origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(reports.router)
app.include_router(onboarding.router)
app.include_router(weight.router)
app.include_router(meals.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
app.include_router(plans.router)
app.include_router(meal_plan.router)
app.include_router(exercise.router)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations()
    if not (settings.gemini_api_key and settings.gemini_api_key.strip()):
        log.warning(
            "GEMINI_API_KEY is empty — meal/chat AI will fail. Set it in backend/.env and restart uvicorn."
        )
    else:
        log.info("GEMINI_API_KEY is set (%s characters)", len(settings.gemini_api_key.strip()))


@app.get("/health")
def health():
    return {"status": "ok"}
