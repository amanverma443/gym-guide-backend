import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_sqlite_migrations() -> None:
    """Add columns to existing SQLite DBs (create_all does not alter tables)."""
    if not settings.database_url.startswith("sqlite"):
        return
    insp = inspect(engine)
    with engine.begin() as conn:
        if insp.has_table("meal_logs"):
            cols = {c["name"] for c in insp.get_columns("meal_logs")}
            statements: list[str] = []
            if "entry_kind" not in cols:
                statements.append("ALTER TABLE meal_logs ADD COLUMN entry_kind VARCHAR(16) DEFAULT 'photo'")
            if "meal_slot" not in cols:
                statements.append("ALTER TABLE meal_logs ADD COLUMN meal_slot VARCHAR(20)")
            if "user_description" not in cols:
                statements.append("ALTER TABLE meal_logs ADD COLUMN user_description TEXT")
            for sql in statements:
                conn.execute(text(sql))
            if statements:
                conn.execute(text("UPDATE meal_logs SET entry_kind = 'photo' WHERE entry_kind IS NULL"))
                log.info("SQLite migrations applied to meal_logs: %s", statements)

        if insp.has_table("users"):
            ucols = {c["name"] for c in insp.get_columns("users")}
            if "daily_exercise_guidance" not in ucols:
                conn.execute(text("ALTER TABLE users ADD COLUMN daily_exercise_guidance TEXT"))
                log.info("SQLite migration: users.daily_exercise_guidance added")
            # onboarding_completed DEFAULT 1 so existing users skip onboarding; new signups get False from the ORM.
            for name, ddl in (
                ("onboarding_completed", "INTEGER DEFAULT 1"),
                ("onboarding_step", "INTEGER DEFAULT 0"),
                ("onboarding_data", "TEXT"),
                ("app_preferences", "TEXT"),
                ("premium_active", "INTEGER DEFAULT 0"),
                ("last_sync_at", "DATETIME"),
            ):
                if name not in ucols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
                    log.info("SQLite migration: users.%s added", name)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
