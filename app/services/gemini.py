import json
import re

import google.generativeai as genai

from app.config import settings

SAFETY_BLOCK = """
Always follow these rules:
- This is not medical advice. Include the exact sentence: "This is not medical advice."
- Be a friendly, slightly motivational coach.
- Do not suggest extreme diets, unsafe deficits, or dangerous exercise. Prefer balanced, sustainable guidance.
- English only for v1.
"""

FOOD_ANSWER_FORMAT = """
When the user asks about eating a specific food, a snack, a portion ("I want to eat…", "how many calories in…", "is X healthy"), you MUST answer in this exact layout (use plain text, one value per line; numbers are reasonable estimates—state the serving size you assumed, e.g. "one medium apple ~182g"):

Calories: <number> kcal (<serving you assumed>)
Protein: <number> g
Vitamins & minerals: <one line—main micronutrients, e.g. vitamin C, fiber, potassium; say "minimal" if very low>

Description:
<2–5 sentences: why it’s a good or okay choice, any caveat (sugar, sodium), and one practical tip (pairing, timing, variety). Be specific and helpful.>

Your plan (personalized — only if PERSONALIZATION data was provided above; otherwise omit this subsection):
- How this food fits today: compare the food's calories to their remaining daily budget (target minus logged today). Give approximate remaining kcal after eating this food at the stated serving.
- Tie to goal: one line on how it supports their weight goal if weight/goal/target are known.

Example (follow this style, not the numbers—they vary by serving):
Calories: 95 kcal (one medium apple, ~182 g)
Protein: 0.5 g
Vitamins & minerals: Good vitamin C and fiber; small amounts of potassium.

Description:
Apples are a convenient, low-calorie snack with fiber that helps fullness. Pair with a protein source (yogurt, nuts) if you want a more balanced mini-meal. Wash thoroughly; variety in fruit intake is ideal.

Your plan (personalized):
- If your target is 2000 kcal and you've logged 800 kcal today, this apple uses ~95 kcal, leaving about 1105 kcal for the rest of the day.

For questions that are NOT about a concrete food or meal (training, sleep, motivation, general chat), answer in normal sentences—do NOT force the block format above.
"""

CHAT_SYSTEM = f"""You are GymGuide, a supportive AI coach for fitness, nutrition, training, recovery, sleep, stress, and motivation.
Users may ask you anything related to health and wellbeing. {SAFETY_BLOCK}
{FOOD_ANSWER_FORMAT}
Keep non-food answers concise unless the user asks for detail. If the user shares weight goals, encourage sustainable pace and healthy habits.
"""


def _ensure_configured() -> None:
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        from pathlib import Path

        env_hint = Path(__file__).resolve().parent.parent.parent / ".env"
        raise RuntimeError(
            f"GEMINI_API_KEY is empty. Add to {env_hint} a line: GEMINI_API_KEY=your_key "
            "(no quotes). Restart uvicorn after saving. Name must be GEMINI_API_KEY exactly."
        )
    genai.configure(api_key=settings.gemini_api_key)


def chat_reply(history_text: str, user_message: str, nutrition_context: str | None = None) -> str:
    _ensure_configured()
    system = CHAT_SYSTEM
    if nutrition_context and nutrition_context.strip():
        system = f"{CHAT_SYSTEM}\n\n{nutrition_context.strip()}"
    model = genai.GenerativeModel(
        "gemini-3.5-flash",
        system_instruction=system,
    )
    prompt = f"""Recent conversation (may be truncated):\n{history_text}\n\nUser:\n{user_message}\n\nAssistant (if the user names a food or asks what happens if they eat something, use the Calories / Protein / Vitamins & minerals / Description format from your instructions, including Your plan (personalized) when profile data exists):"""
    resp = model.generate_content(prompt)
    text = (resp.text or "").strip()
    if "not medical advice" not in text.lower():
        text += "\n\nThis is not medical advice."
    return text


def _meal_prompt(nutrition_context: str) -> str:
    return f"""Analyze this food photo. Respond with ONLY valid JSON (no markdown) in this exact shape:
{{
  "calories": <number, estimated total for the visible meal>,
  "protein_g": <number>,
  "carbs_g": <number>,
  "fat_g": <number>,
  "healthier_tip": "<one short sentence with a healthier alternative or tweak>",
  "plan_fit_note": "<2-5 sentences: REQUIRED. Use the USER CONTEXT below. State their daily calorie target (if any), kcal logged today BEFORE this meal, estimated kcal of THIS meal, and approximate kcal remaining for the day after this meal. Mention goal weight if relevant. If target is missing, say so and still give practical guidance.>"
}}
USER CONTEXT (personalize plan_fit_note with these facts):
{nutrition_context}
{SAFETY_BLOCK}
Values are estimates. The app will show "Estimated values" to the user.
"""


def meal_from_image(image_bytes: bytes, mime: str, nutrition_context: str) -> dict:
    _ensure_configured()
    model = genai.GenerativeModel("gemini-3.5-flash")
    safe_mime = mime if mime.startswith("image/") else "image/jpeg"
    image_part = {"mime_type": safe_mime, "data": image_bytes}
    prompt = _meal_prompt(nutrition_context)
    resp = model.generate_content([prompt, image_part])
    raw = (resp.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    for k in ("calories", "protein_g", "carbs_g", "fat_g"):
        data[k] = float(data[k])
    data["healthier_tip"] = str(data.get("healthier_tip", "")).strip()
    data["plan_fit_note"] = str(data.get("plan_fit_note", "")).strip()
    return data


def generate_daily_meal_plan(nutrition_context: str) -> dict[str, str]:
    """Returns breakfast, lunch, dinner suggestion strings for one day."""
    _ensure_configured()
    model = genai.GenerativeModel("gemini-3.5-flash")
    prompt = f"""You are a nutrition coach. Propose simple, realistic breakfast, lunch, and dinner ideas for TODAY only.
Each value is 1–4 short lines: concrete foods + approximate portions (e.g. "2 boiled eggs, 1 slice whole-wheat toast, black coffee").
If a daily calorie target appears in USER CONTEXT, split calories sensibly across meals (rough guide: ~25–30% breakfast, ~35–40% lunch, ~30–35% dinner — adjust for hunger and training).
Respond with ONLY valid JSON (no markdown fences):
{{
  "breakfast": "<string>",
  "lunch": "<string>",
  "dinner": "<string>"
}}
USER CONTEXT:
{nutrition_context}
{SAFETY_BLOCK}
"""
    resp = model.generate_content(prompt)
    raw = (resp.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    return {
        "breakfast": str(data.get("breakfast", "")).strip(),
        "lunch": str(data.get("lunch", "")).strip(),
        "dinner": str(data.get("dinner", "")).strip(),
    }


def estimate_meal_from_text(user_description: str, meal_slot: str, nutrition_context: str) -> dict:
    """Estimate macros from a free-text description (e.g. '3 medium bananas')."""
    _ensure_configured()
    model = genai.GenerativeModel("gemini-3.5-flash")
    prompt = f"""The user says they ate this for {meal_slot} (today). Estimate total nutrition for what they described.
Respond with ONLY valid JSON (no markdown fences):
{{
  "calories": <number>,
  "protein_g": <number>,
  "carbs_g": <number>,
  "fat_g": <number>,
  "healthier_tip": "<one short sentence>",
  "plan_fit_note": "<2–5 sentences: REQUIRED. Use USER CONTEXT. State daily target if any, kcal logged today BEFORE this entry, estimated kcal for THIS food, and approximate kcal remaining after. Mention slot ({meal_slot}).>"
}}
WHAT THEY ATE (user's words):
{user_description}
USER CONTEXT:
{nutrition_context}
{SAFETY_BLOCK}
Values are estimates.
"""
    resp = model.generate_content(prompt)
    raw = (resp.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    for k in ("calories", "protein_g", "carbs_g", "fat_g"):
        data[k] = float(data[k])
    data["healthier_tip"] = str(data.get("healthier_tip", "")).strip()
    data["plan_fit_note"] = str(data.get("plan_fit_note", "")).strip()
    return data


def generate_weight_plan(
    current_kg: float | None,
    goal_kg: float | None,
    height_cm: float | None,
    recent_weights: list[tuple[str, float]],
    reason: str,
) -> tuple[str, str, int, str]:
    """Returns (full_plan_markdown, one_line_summary, daily_calorie_target, daily_exercise_guidance)."""
    _ensure_configured()
    model = genai.GenerativeModel(
        "gemini-3.5-flash",
        system_instruction=f"You create practical, safe weekly-style guidance for fat loss or maintenance. {SAFETY_BLOCK}",
    )
    lines = "\n".join(f"- {d}: {w} kg" for d, w in recent_weights[-14:])
    prompt = f"""User profile:
- Current weight (kg): {current_kg}
- Goal weight (kg): {goal_kg}
- Height (cm): {height_cm}
- Reason for (re)plan: {reason}

Recent weight log (date: weight):
{lines}

Return ONLY valid JSON (no markdown fences) with keys:
- "summary": string, max 120 characters, dashboard one-liner
- "daily_calorie_target": integer, a single reasonable daily calorie target number for this user (not a range)
- "daily_exercise_guidance": string, 3-6 sentences: concrete weekly activity targets (minutes of moderate cardio per week, how to split across days), 2 resistance/full-body strength sessions per week if appropriate, and one sentence on daily movement (steps or short walks). Be specific (e.g. "About 30-45 minutes brisk walking or cycling on 5 days, plus two 20-minute strength sessions"). Safe for general population.
- "plan_markdown": string, Markdown with sections: Overview, Daily calorie target (reasonable range), Protein focus, Example day of eating, Training ideas (moderate), Check-in tips

End plan_markdown with the sentence: This is not medical advice.
"""
    resp = model.generate_content(prompt)
    raw = (resp.text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    full = str(data.get("plan_markdown", "")).strip()
    summary = str(data.get("summary", "")).strip() or "Your personalized plan is ready — small steps, big consistency."
    dct = int(data.get("daily_calorie_target", 0)) or 2000
    ex = str(data.get("daily_exercise_guidance", "")).strip()
    if not ex:
        ex = (
            "Aim for at least 150 minutes of moderate cardio per week (e.g. 30 minutes on 5 days), "
            "plus two full-body strength sessions of about 20–30 minutes. Add light daily movement like walking when you can."
        )
    if "not medical advice" not in full.lower():
        full += "\n\nThis is not medical advice."
    return full, summary, dct, ex
