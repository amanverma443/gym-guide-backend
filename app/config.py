from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_BACKEND = _BACKEND_DIR / ".env"
_ENV_ROOT = _REPO_ROOT / ".env"

# Load into os.environ before Settings() — reliable with BOM, quotes, and override order.
# Later load_dotenv(override=True) wins.
if _ENV_ROOT.is_file():
    load_dotenv(_ENV_ROOT, override=False, encoding="utf-8-sig")
if _ENV_BACKEND.is_file():
    load_dotenv(_ENV_BACKEND, override=True, encoding="utf-8-sig")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    gemini_api_key: str = ""
    jwt_secret: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./gym_guide.db"
    google_client_id: str = ""
    max_upload_bytes: int = 5 * 1024 * 1024
    #: When True, enforce AI_DAILY_LIMIT and record each AI call. Default off for local testing.
    ai_rate_limit_enabled: bool = False
    ai_daily_limit: int = 10
    cors_origins: str = "http://localhost:8081,http://127.0.0.1:8081,exp://"


settings = Settings()
