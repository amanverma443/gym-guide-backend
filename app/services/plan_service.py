from sqlalchemy.orm import Session

from app.models import AIPlan, User
from app.services.gemini import generate_weight_plan
from app.services.plan_logic import deactivate_old_plans, weight_logs_ordered_asc
from app.services.rate_limit import assert_ai_budget, log_ai_call


def build_plan(db: Session, user: User, reason: str, source: str) -> tuple[str, str, int]:
    assert_ai_budget(db, user)
    logs = weight_logs_ordered_asc(db, user.id)
    recent = [(w.logged_on.isoformat(), w.weight_kg) for w in logs[-14:]]
    full, summary, cal, exercise_guidance = generate_weight_plan(
        user.current_weight_kg,
        user.goal_weight_kg,
        user.height_cm,
        recent,
        reason,
    )
    deactivate_old_plans(db, user.id)
    db.add(
        AIPlan(
            user_id=user.id,
            content=full,
            summary_line=summary,
            source=source,
            is_current=True,
        )
    )
    user.daily_calorie_target = cal
    user.daily_exercise_guidance = exercise_guidance
    log_ai_call(db, user.id, "plan")
    db.commit()
    db.refresh(user)
    return full, summary, cal
