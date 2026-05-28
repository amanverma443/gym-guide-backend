"""Calendar dates aligned with naive UTC datetimes stored on models (datetime.utcnow)."""

from datetime import date, datetime, timezone


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
