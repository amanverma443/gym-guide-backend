from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _normalize_email(v: object) -> str:
    if not isinstance(v, str):
        raise ValueError("email must be a string")
    s = v.strip().lower()
    if len(s) < 3 or "@" not in s or s.startswith("@") or s.endswith("@"):
        raise ValueError("invalid email")
    return s


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)
    full_name: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def email_ok(cls, v: object) -> str:
        return _normalize_email(v)


class UserLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def email_ok(cls, v: object) -> str:
        return _normalize_email(v)


class GoogleAuthBody(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    current_weight_kg: float | None
    goal_weight_kg: float | None
    height_cm: float | None
    daily_calorie_target: int | None
    daily_exercise_guidance: str | None = None
    onboarding_completed: bool = False
    onboarding_step: int = 0
    premium_active: bool = False

    class Config:
        from_attributes = True


class OnboardingStateOut(BaseModel):
    completed: bool
    step: int
    data: dict = Field(default_factory=dict)


class OnboardingPatch(BaseModel):
    step: int = Field(ge=0, le=30)
    data: dict = Field(default_factory=dict)


class OnboardingCompleteResult(BaseModel):
    ok: bool
    message: str
    suggested_daily_calories: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    current_weight_kg: float | None = None
    goal_weight_kg: float | None = None
    height_cm: float | None = None


class WeightLogCreate(BaseModel):
    logged_on: date
    weight_kg: float = Field(gt=0, le=500)


class WeightLogOut(BaseModel):
    id: int
    logged_on: date
    weight_kg: float
    created_at: datetime

    class Config:
        from_attributes = True


class MealOut(BaseModel):
    id: int
    image_url: str = ""
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    healthier_tip: str
    created_at: datetime
    plan_fit_note: str | None = Field(default=None, description="How this meal fits daily target vs profile")
    entry_kind: Literal["photo", "text"] = "photo"
    meal_slot: str | None = None
    user_description: str | None = None

    class Config:
        from_attributes = True


class DayMealPlanOut(BaseModel):
    id: int
    plan_date: date
    breakfast_suggestion: str
    lunch_suggestion: str
    dinner_suggestion: str
    created_at: datetime

    class Config:
        from_attributes = True


class DayMealPlanResponse(BaseModel):
    plan: DayMealPlanOut | None = None


class LogActualMealBody(BaseModel):
    slot: Literal["breakfast", "lunch", "dinner"]
    description: str = Field(min_length=2, max_length=2000)


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSend(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class DashboardOut(BaseModel):
    daily_calorie_target: int | None
    calories_consumed_today: float
    calories_burned_today: float = 0
    net_calories_today: float = 0
    daily_exercise_guidance: str | None = None
    weight_kg_latest: float | None
    goal_weight_kg: float | None
    plan_summary: str | None
    plan_detail: str | None
    ai_calls_today: int
    ai_daily_limit: int
    auto_regenerated_plan: bool = False


class ExerciseBurnCreate(BaseModel):
    calories_burned: float = Field(gt=0, le=100_000)
    notes: str | None = Field(default=None, max_length=2000)
    logged_on: date | None = None


class ExerciseBurnOut(BaseModel):
    id: int
    logged_on: date
    calories_burned: float
    notes: str | None
    image_url: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExerciseSummaryOut(BaseModel):
    daily_exercise_guidance: str | None
    calories_burned_today: float
    burns_today: list[ExerciseBurnOut]


class PlanRegenerateResult(BaseModel):
    ok: bool
    message: str
    plan_summary: str | None = None


class NotificationOut(BaseModel):
    id: int
    title: str
    body: str
    kind: str
    read_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class UserSummaryOut(BaseModel):
    streak_days: int
    kg_lost: float
    unread_notifications: int
    premium_active: bool
    preferences: dict = Field(default_factory=dict)
    server_time_utc: datetime
    last_sync_at: datetime | None = None


class PreferencesPatch(BaseModel):
    reminders_enabled: bool | None = None
    intermittent_fasting_enabled: bool | None = None
    sleep_reminders: bool | None = None
    apps_devices_connected: bool | None = None


class WeeklyReportOut(BaseModel):
    period_start: date
    period_end: date
    total_calories_consumed: float
    total_calories_burned: float
    weight_logs_count: int
    weight_change_kg: float | None
    headline: str
