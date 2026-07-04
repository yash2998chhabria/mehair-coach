from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import app.health_store as health_store_module
from app.auth import AuthService
from app.crypto import generate_key
from app.db import Database
from app.health_store import HealthStore
from app.main import workout_recommendation
from app.settings import Settings
from app.time_utils import iso_now


def make_store(tmp_path) -> tuple[Database, HealthStore]:
    settings = Settings(
        public_base_url="http://localhost:8787",
        database_url=f"sqlite:///{tmp_path / 'eval.sqlite3'}",
        token_encryption_key=generate_key(),
    )
    db = Database(settings.sqlite_path)
    db.init()
    auth = AuthService(db, settings)
    return db, HealthStore(db, auth, settings)


def create_user(db: Database, user_id: str = "eval_user") -> str:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO users (id, google_email, google_subject, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, f"{user_id}@example.com", f"{user_id}-google", iso_now(), iso_now()),
        )
    return user_id


def freeze_now(monkeypatch, value: datetime | None = None) -> None:
    fixed = value or datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed)
    monkeypatch.setattr(health_store_module, "iso_now", lambda: fixed.isoformat())


def seed_day(
    store: HealthStore,
    user_id: str,
    day: str,
    *,
    sleep_hours: float | None = None,
    hrv_ms: float | None = None,
    resting_hr: int | None = None,
    active_zone_minutes: int | None = None,
    steps: int | None = None,
    active_minutes: int | None = None,
    respiratory_rate: float | None = None,
    spo2: float | None = None,
    sleep_temperature_delta_c: float | None = None,
    vo2_max: float | None = None,
) -> None:
    year, month, day_num = [int(part) for part in day.split("-")]
    if steps is not None:
        store.upsert_records(
            user_id,
            "steps",
            [
                {
                    "name": f"steps-{day}",
                    "steps": {"count": steps},
                    "interval": {"startTime": f"{day}T12:00:00Z"},
                }
            ],
        )
    if active_zone_minutes is not None:
        store.upsert_records(
            user_id,
            "active-zone-minutes",
            [
                {
                    "name": f"azm-{day}",
                    "activeZoneMinutes": {"activeZoneMinutes": active_zone_minutes},
                    "interval": {"startTime": f"{day}T17:30:00Z"},
                }
            ],
        )
    if active_minutes is not None:
        store.upsert_records(
            user_id,
            "active-minutes",
            [
                {
                    "name": f"active-{day}",
                    "activeMinutes": {
                        "activeMinutesByActivityLevel": [
                            {"activityLevel": "MODERATE", "activeMinutes": active_minutes}
                        ]
                    },
                    "interval": {"startTime": f"{day}T17:00:00Z"},
                }
            ],
        )
    if sleep_hours is not None:
        minutes = int(round(sleep_hours * 60))
        store.upsert_records(
            user_id,
            "sleep",
            [
                {
                    "name": f"sleep-{day}",
                    "sleep": {
                        "interval": {
                            "startTime": f"{day}T00:00:00Z",
                            "endTime": f"{day}T08:00:00Z",
                        },
                        "summary": {
                            "minutesAsleep": str(minutes),
                            "minutesAwake": "30",
                            "minutesInSleepPeriod": str(minutes + 30),
                        },
                    },
                }
            ],
        )
    if hrv_ms is not None:
        store.upsert_records(
            user_id,
            "daily-heart-rate-variability",
            [
                {
                    "name": f"hrv-{day}",
                    "dailyHeartRateVariability": {
                        "averageHeartRateVariabilityMilliseconds": hrv_ms
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
    if resting_hr is not None:
        store.upsert_records(
            user_id,
            "daily-resting-heart-rate",
            [
                {
                    "name": f"rhr-{day}",
                    "dailyRestingHeartRate": {"beatsPerMinute": resting_hr},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
    if respiratory_rate is not None:
        store.upsert_records(
            user_id,
            "daily-respiratory-rate",
            [
                {
                    "name": f"resp-{day}",
                    "dailyRespiratoryRate": {"breathsPerMinute": respiratory_rate},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
    if spo2 is not None:
        store.upsert_records(
            user_id,
            "daily-oxygen-saturation",
            [
                {
                    "name": f"spo2-{day}",
                    "dailyOxygenSaturation": {"averagePercentage": spo2},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
    if sleep_temperature_delta_c is not None:
        baseline_c = 36.5
        store.upsert_records(
            user_id,
            "daily-sleep-temperature-derivations",
            [
                {
                    "name": f"temp-{day}",
                    "dailySleepTemperatureDerivations": {
                        "nightlyTemperatureCelsius": baseline_c + sleep_temperature_delta_c,
                        "baselineTemperatureCelsius": baseline_c,
                        "relativeNightlyStddev30dCelsius": abs(sleep_temperature_delta_c) / 0.2,
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
    if vo2_max is not None:
        store.upsert_records(
            user_id,
            "daily-vo2-max",
            [
                {
                    "name": f"vo2-{day}",
                    "dailyVo2Max": {
                        "vo2Max": vo2_max,
                        "estimated": True,
                        "cardioFitnessLevel": "GOOD",
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )


def seed_workout(store: HealthStore, user_id: str, day: str, name: str, azm: int = 28) -> None:
    store.upsert_records(
        user_id,
        "exercise",
        [
            {
                "name": f"exercise-{day}-{name}",
                "exercise": {
                    "exerciseType": "RUNNING",
                    "displayName": name,
                    "activeDuration": "2400s",
                    "interval": {
                        "startTime": f"{day}T17:00:00Z",
                        "endTime": f"{day}T17:40:00Z",
                    },
                    "metricsSummary": {
                        "activeZoneMinutes": azm,
                        "caloriesKcal": 360,
                        "averageHeartRateBeatsPerMinute": 138,
                    },
                },
            }
        ],
    )


def seed_heart_samples(store: HealthStore, user_id: str, day: str, count: int = 24) -> None:
    records = []
    for hour in range(count):
        bpm = 58 + (hour % 10) * 7
        records.append(
            {
                "name": f"hr-{day}-{hour}",
                "heartRate": {"beatsPerMinute": bpm},
                "sampleTime": {"physicalTime": f"{day}T{hour % 24:02d}:15:00Z"},
            }
        )
    store.upsert_records(user_id, "heart-rate", records)


def metric_ids(result: dict) -> set[str]:
    return {item["id"] for item in result.get("relevant_metrics", [])}


def test_eval_under_recovered_user_gets_easy_day_with_specific_evidence(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "under_recovered")

    seed_day(
        store,
        user_id,
        "2026-06-30",
        sleep_hours=7.4,
        hrv_ms=58,
        resting_hr=57,
        active_zone_minutes=24,
        steps=8200,
    )
    seed_day(
        store,
        user_id,
        "2026-07-01",
        sleep_hours=7.2,
        hrv_ms=55,
        resting_hr=58,
        active_zone_minutes=30,
        steps=8800,
    )
    seed_day(
        store,
        user_id,
        "2026-07-02",
        sleep_hours=5.4,
        hrv_ms=41,
        resting_hr=64,
        active_zone_minutes=72,
        steps=12800,
    )
    seed_day(store, user_id, "2026-07-03", sleep_hours=5.1, hrv_ms=36, resting_hr=67, steps=1600)
    seed_workout(store, user_id, "2026-07-02", "Hard squash match", azm=72)
    store.save_goal(user_id, {"goal_type": "fitness", "target": "Train four days per week", "days_per_week": 4})
    store.save_checkin(user_id, {"energy": 3, "soreness": 7, "stress": 6, "notes": "Legs heavy after squash"})

    clues = store.health_question_clues(user_id, "I feel cooked. How hard should I work out today?", days=7)
    day_plan_clues = store.health_question_clues(user_id, "What should I do today?", days=7)
    comparison = store.recovery_signal_comparison(user_id, days=7)
    recommendation = workout_recommendation(
        context=store.latest_context(user_id),
        goal=store.latest_goal(user_id),
        checkins=store.recent_checkins(user_id),
        workout_history=store.workout_history(user_id, 7),
    )

    assert {
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "active-zone-minutes",
    } <= metric_ids(clues)
    assert clues["personal_context"]["recent_checkins"][0]["checkin"]["energy"] == 3
    assert clues["personal_context"]["goal"]["goal"]["days_per_week"] == 4
    assert clues["data_used"]["goal_present"] is True
    assert clues["data_used"]["recent_checkins_count"] == 1
    assert clues["data_used"]["recent_workout_count"] == 1
    assert "Latest energy check-in is 3/10." in clues["clues"]
    assert "Latest soreness check-in is 7/10." in clues["clues"]
    assert "Latest check-in note: Legs heavy after squash." in clues["clues"]
    assert "Current goal: Train four days per week." in clues["clues"]
    assert "Goal progress in this window: 1/4 workout sessions logged." in clues["clues"]
    assert any("Low self-reported energy" in item for item in clues["watchouts"])
    assert any("High soreness" in item for item in clues["watchouts"])
    assert any("3 goal session(s) remain" in item for item in clues["next_actions"])
    assert "get_recovery_signal_comparison" in clues["recommended_tool_sequence"]
    assert "daily_plan" in day_plan_clues["intent_hints"]
    assert "get_health_overview" in day_plan_clues["recommended_tool_sequence"]
    assert "recommend_workout_today" in day_plan_clues["recommended_tool_sequence"]
    assert day_plan_clues["overview_context"]["daily_brief"]["training_bias"] == "recovery-first"
    assert any(
        item["label"] == "Goal progress"
        for item in day_plan_clues["overview_context"]["daily_brief"]["priority_signals"]
    )
    assert comparison["current_vs_baseline"]["hrv_percent_delta"] <= -20
    assert comparison["current_vs_baseline"]["resting_heart_rate_delta"] >= 6
    assert any("Short sleep" in item or "HRV" in item for item in comparison["insights"] + comparison["watchouts"])
    assert recommendation["intensity"] == "easy"
    assert recommendation["rpe_cap"] <= 6
    assert recommendation["subjective_context"]["energy"] == 3
    assert recommendation["subjective_context"]["soreness"] == 7
    assert any("recovery" in item.lower() for item in recommendation["next_actions"])
    assert any("HRV" in item or "Resting heart rate" in item for item in recommendation["evidence"])
    assert "Latest energy check-in is 3/10." in recommendation["evidence"]
    assert "Latest soreness check-in is 7/10." in recommendation["evidence"]
    assert "Goal progress: 1/4 sessions logged; 3 remaining." in recommendation["evidence"]
    assert "Hardest recent workout: Hard squash match (72 Active Zone Minutes, 2026-07-02)." in recommendation["evidence"]


def test_eval_green_day_keeps_training_available_but_grounded_in_data(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "green_day")

    seed_day(
        store,
        user_id,
        "2026-06-30",
        sleep_hours=7.3,
        hrv_ms=52,
        resting_hr=58,
        active_zone_minutes=18,
        steps=7200,
    )
    seed_day(
        store,
        user_id,
        "2026-07-01",
        sleep_hours=7.6,
        hrv_ms=55,
        resting_hr=57,
        active_zone_minutes=24,
        steps=8300,
    )
    seed_day(
        store,
        user_id,
        "2026-07-02",
        sleep_hours=7.7,
        hrv_ms=56,
        resting_hr=57,
        active_zone_minutes=20,
        steps=7600,
    )
    seed_day(
        store,
        user_id,
        "2026-07-03",
        sleep_hours=8.1,
        hrv_ms=62,
        resting_hr=56,
        active_zone_minutes=22,
        steps=6900,
        respiratory_rate=14.2,
        spo2=98.1,
    )
    seed_workout(store, user_id, "2026-07-01", "Easy run", azm=24)
    seed_workout(store, user_id, "2026-07-02", "Strength", azm=20)
    store.save_goal(user_id, {"goal_type": "strength", "target": "Lift three days this week", "days_per_week": 3})
    store.save_checkin(user_id, {"energy": 8, "soreness": 2, "stress": 3, "notes": "Feel good"})

    clues = store.health_question_clues(user_id, "Can I train hard today or should I keep it easy?", days=7)
    recommendation = workout_recommendation(
        context=store.latest_context(user_id),
        goal=store.latest_goal(user_id),
        checkins=store.recent_checkins(user_id),
        workout_history=store.workout_history(user_id, 7),
    )

    assert "workout_decision" in clues["intent_hints"]
    assert clues["readiness"]["label"] == "green"
    assert {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"} <= metric_ids(clues)
    assert any("sleep" in item.lower() for item in clues["clues"] + clues["positives"])
    assert "Latest energy check-in is 8/10." in clues["clues"]
    assert "Latest soreness check-in is 2/10." in clues["clues"]
    assert "Goal progress in this window: 2/3 workout sessions logged." in clues["clues"]
    assert clues["data_used"]["goal_present"] is True
    assert clues["data_used"]["recent_checkins_count"] == 1
    assert clues["data_used"]["recent_workout_count"] == 2
    assert "Self-reported energy is strong." in clues["positives"]
    assert "Self-reported soreness is low." in clues["positives"]
    assert any("1 goal session(s) remain" in item for item in clues["next_actions"])
    assert recommendation["intensity"] == "moderate-to-hard"
    assert recommendation["rpe_cap"] == 8
    assert "sleep supports training" in recommendation["coach_response"]["data_story"]
    assert "your check-in changes the plan" not in recommendation["coach_response"]["data_story"]
    assert recommendation["data_used"]["recent_workouts"] == 2
    assert recommendation["goal_context"]["remaining_sessions"] == 1
    assert any("normal" in item.lower() or "train" in item.lower() for item in recommendation["next_actions"])
    assert "Latest energy check-in is 8/10." in recommendation["evidence"]
    assert "Latest soreness check-in is 2/10." in recommendation["evidence"]
    assert "Goal progress: 2/3 sessions logged; 1 remaining." in recommendation["evidence"]
    assert "Hardest recent workout: Easy run (24 Active Zone Minutes, 2026-07-01)." in recommendation["evidence"]


def test_eval_natural_prompt_mix_is_not_biased_to_off_day_language(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "natural_prompt_mix")

    for offset, (day, sleep, hrv, resting, azm, steps) in enumerate([
        ("2026-06-30", 7.2, 51, 59, 18, 7100),
        ("2026-07-01", 7.5, 53, 58, 22, 7800),
        ("2026-07-02", 7.6, 54, 58, 24, 8200),
        ("2026-07-03", 8.0, 60, 56, 16, 5200),
    ]):
        seed_day(
            store,
            user_id,
            day,
            sleep_hours=sleep,
            hrv_ms=hrv,
            resting_hr=resting,
            active_zone_minutes=azm,
            steps=steps,
            respiratory_rate=15.4 + (resting % 3) * 0.3,
            spo2=97.4 - (azm % 3) * 0.2,
            sleep_temperature_delta_c=0.03 + offset * 0.01,
            vo2_max=45.5 + offset * 0.2,
        )
    seed_workout(store, user_id, "2026-07-01", "Easy run", azm=22)
    seed_workout(store, user_id, "2026-07-02", "Lift", azm=24)
    store.save_goal(user_id, {"goal_type": "fitness", "target": "Train four days per week", "days_per_week": 4})
    store.save_checkin(user_id, {"energy": 8, "soreness": 2, "stress": 3, "notes": "Normal day"})

    scenarios = [
        (
            "Can I train hard today or should I keep it controlled?",
            {"workout_decision", "recovery", "activity_load"},
            {"recommend_workout_today"},
        ),
        (
            "I only have 30 minutes today. What is the best use of it?",
            {"daily_plan", "general_overview", "workout_decision"},
            {"get_health_overview", "recommend_workout_today"},
        ),
        (
            "How did sleep, HRV, and resting heart rate affect today's plan?",
            {"sleep", "heart", "recovery"},
            {"get_recovery_signal_comparison"},
        ),
        (
            "How am I doing on my weekly training goal?",
            {"goal"},
            {"get_health_overview"},
        ),
        (
            "During my workout HR 150, RPE 7, pain 0/10, no dizziness. Keep going?",
            {"active_workout", "workout_decision"},
            {"guide_active_workout"},
        ),
        (
            "I feel good and want to push my run today. What data would make you say yes or no?",
            {"workout_decision", "recovery", "heart", "sleep"},
            {"recommend_workout_today", "get_recovery_signal_comparison"},
        ),
        (
            "I am busy today and only have 20 minutes after work. What should I do?",
            {"daily_plan", "general_overview", "workout_decision"},
            {"get_health_overview", "recommend_workout_today"},
        ),
        (
            "I walked a lot this morning. Does my step count matter for training later?",
            {"activity_load", "workout_decision"},
            {"get_activity_load", "recommend_workout_today"},
        ),
        (
            "I slept great and my heart numbers look good. Should I add intervals?",
            {"sleep", "heart", "workout_decision"},
            {"recommend_workout_today", "get_recovery_signal_comparison"},
        ),
        (
            "I want to stay consistent with my weekly goal but not overdo it. What is today's useful move?",
            {"daily_plan", "goal", "workout_decision"},
            {"get_health_overview", "recommend_workout_today"},
        ),
        (
            "I want a useful plan for the next 3 days. I care about getting fitter, not feeling wrecked, and I might play squash one evening.",
            {"daily_plan", "general_overview", "workout_decision", "activity_load", "goal"},
            {"get_health_overview", "recommend_workout_today", "plan_workout_with_health_context"},
        ),
        (
            "My oxygen looked a little lower last night. What does that change for training?",
            {"recovery", "sleep", "heart", "workout_decision"},
            {"get_recovery_signal_comparison", "recommend_workout_today"},
        ),
        (
            "I want to get fitter without feeling wrecked this week. What is the smart plan?",
            {"daily_plan", "goal", "workout_decision", "activity_load"},
            {"get_health_overview", "recommend_workout_today"},
        ),
        (
            "I slept fine but feel flat. Should I do easy miles or lift?",
            {"workout_decision", "subjective", "recovery", "activity_load"},
            {"recommend_workout_today", "plan_workout_with_health_context"},
        ),
        (
            "I am not saying I feel off or sore. What should I focus on today from the data?",
            {"daily_plan", "general_overview", "workout_decision"},
            {"get_health_overview", "recommend_workout_today"},
        ),
        (
            "Can I work out today if I feel normal?",
            {"workout_decision", "recovery", "activity_load"},
            {"recommend_workout_today"},
        ),
    ]

    for question, expected_intents, expected_tools in scenarios:
        clues = store.health_question_clues(user_id, question, days=7)
        joined = json.dumps(clues).lower()

        assert expected_intents <= set(clues["intent_hints"])
        assert expected_tools <= set(clues["recommended_tool_sequence"])
        assert "symptom_safety" not in clues["intent_hints"]
        assert any("match the user's situation" in item.lower() for item in clues["answer_rubric"])
        assert any("date/window" in item.lower() for item in clues["answer_rubric"])
        assert "i feel a little off" not in joined
        assert "feel cooked" not in joined

    plain_workout = store.health_question_clues(user_id, "Can I work out today if I feel normal?", days=7)
    plain_cues = {item["cue"] for item in plain_workout["decision_frame"]["user_context_cues"]}
    assert "reserve_energy_or_future_event" not in plain_cues
    assert "no_special_constraint_detected" in plain_cues

    informal_training = store.health_question_clues(
        user_id,
        "Do I have the green light to send it at the gym today?",
        days=7,
    )
    flows = {item["flow"]: item for item in informal_training["conversation_flow_options"]}
    daily_flow = flows["daily_training_decision"]
    assert "recommend_workout_today" in daily_flow["primary_tools"]
    assert "available_signal_snapshot" in daily_flow["data_surfaces_to_use"]
    assert "training_decision" in daily_flow["data_surfaces_to_use"]
    assert any("conversation_flow_options" in item for item in informal_training["answering_guidance"])
    assert any("model_decision_policy" in item for item in informal_training["answering_guidance"])
    assert {
        "daily-vo2-max",
        "oxygen-saturation",
        "respiratory-rate-sleep-summary",
        "daily-sleep-temperature-derivations",
        "active-minutes",
        "activity-level",
    } <= metric_ids(informal_training)
    assert any("SpO2 / oxygen saturation" in item for item in informal_training["clues"])
    assert any("Respiratory rate" in item for item in informal_training["clues"])
    assert any("Sleep temp" in item for item in informal_training["clues"])
    assert any("VO2 max" in item for item in informal_training["clues"])
    policy = informal_training["decision_frame"]["model_decision_policy"]
    axes = {item["axis"]: item for item in policy["decision_axes"]}
    assert {
        "safety_override",
        "recovery_capacity",
        "breathing_oxygen_temperature_caution",
        "activity_load_window",
        "capacity_progress",
        "user_context_and_goal",
        "in_session_control",
    } <= set(axes)
    assert {"spo2", "respiratory_rate", "sleep_temperature"} <= set(
        axes["breathing_oxygen_temperature_caution"]["available_signal_ids"]
    )
    assert "vo2_max" in axes["capacity_progress"]["available_signal_ids"]
    assert any("Select the smallest useful set of axes" in item for item in policy["question_parsing_steps"])
    assert informal_training["model_signal_context"]["decision_policy"]["decision_axes"]

    multi_day_plan = store.health_question_clues(
        user_id,
        "I want a useful plan for the next 3 days. I care about getting fitter, not feeling wrecked, and I might play squash one evening.",
        days=7,
    )
    multi_day_metric_ids = metric_ids(multi_day_plan)
    assert {
        "daily-oxygen-saturation",
        "daily-respiratory-rate",
        "daily-sleep-temperature-derivations",
        "time-in-heart-rate-zone",
        "daily-vo2-max",
    } <= multi_day_metric_ids
    assert {"daily-oxygen-saturation", "daily-respiratory-rate"} <= set(multi_day_plan["available_metric_ids"])
    assert any(item["purpose"] == "recovery" for item in multi_day_plan["query_suggestions"])

    generalizable_prompts = [
        "Make the call for my body today; I want something useful without being dumb.",
        "What clues from the band would talk me out of a big session?",
        "Build the day around what my body can absorb.",
    ]
    for question in generalizable_prompts:
        clues = store.health_question_clues(user_id, question, days=7)
        prompt_policy = clues["decision_frame"]["model_decision_policy"]
        prompt_axes = {item["axis"]: item for item in prompt_policy["decision_axes"]}
        assert "recovery_capacity" in prompt_axes
        assert "breathing_oxygen_temperature_caution" in prompt_axes
        assert "activity_load_window" in prompt_axes
        assert "capacity_progress" in prompt_axes
        assert any("Human answer first" in item for item in prompt_policy["answer_style"])
        assert "i feel a little off" not in json.dumps(clues).lower()


def test_eval_question_clues_include_human_decision_frame_for_life_constraints(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "life_constraints")

    for day, sleep, hrv, resting, azm, steps in [
        ("2026-06-30", 7.4, 50, 60, 18, 7600),
        ("2026-07-01", 7.8, 52, 59, 20, 8300),
        ("2026-07-02", 7.3, 49, 61, 28, 9100),
        ("2026-07-03", 8.1, 58, 57, 14, 5400),
    ]:
        seed_day(
            store,
            user_id,
            day,
            sleep_hours=sleep,
            hrv_ms=hrv,
            resting_hr=resting,
            active_zone_minutes=azm,
            steps=steps,
        )
    store.save_goal(user_id, {"goal_type": "fitness", "target": "Lift three days per week", "days_per_week": 3})
    store.save_checkin(user_id, {"energy": 8, "soreness": 2, "stress": 3, "notes": "Normal day"})

    clues = store.health_question_clues(
        user_id,
        "I feel normal and want an upper-body lift, but I have a long walk and dinner later and do not want to feel drained.",
        days=7,
    )

    joined = json.dumps(clues).lower()
    frame = clues["decision_frame"]
    context_cues = {item["cue"] for item in frame["user_context_cues"]}
    role_signals = {item["signal"] for item in frame["signal_roles"]}

    assert clues["status"] == "ok"
    assert "workout_decision" in clues["intent_hints"]
    assert "reserve_energy_or_future_event" in context_cues
    assert "load_stacking" in context_cues
    assert {
        "readiness",
        "sleep",
        "heart_recovery",
        "training_load",
        "capacity_progress",
        "personal_context",
    } <= role_signals
    assert any("rpe cap" in item.lower() for item in frame["output_contract"])
    assert any("SpO2" in item and "VO2 max" in item for item in frame["output_contract"])
    assert any("azm =" in item.lower() for item in frame["plain_language_labels"])
    assert any("green readiness" in item.lower() or "green" in item.lower() for item in frame["do_not_do"])
    assert "i feel a little off" not in joined
    assert "feel cooked" not in joined


def test_eval_stale_data_for_time_sensitive_workout_pushes_sync_first(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "stale_user")

    seed_day(
        store,
        user_id,
        "2026-07-01",
        sleep_hours=7.0,
        hrv_ms=50,
        resting_hr=59,
        active_zone_minutes=16,
        steps=6400,
    )

    clues = store.health_question_clues(user_id, "Should I do intervals today?", days=7)
    recommendation = workout_recommendation(context=store.latest_context(user_id))

    assert clues["data_freshness"]["freshness_level"] == "stale"
    assert clues["next_actions"][0] == "Run sync_latest_fitbit_data before answering time-sensitive training questions."
    assert "sync_latest_fitbit_data" in clues["recommended_tool_sequence"]
    assert recommendation["data_used"]["freshness_level"] == "stale"
    assert recommendation["next_actions"][0] == "Sync latest Fitbit data before making a time-sensitive hard training decision."
    assert recommendation["rpe_cap"] <= 7
    assert any("Data freshness is stale" in item for item in recommendation["evidence"])


def test_eval_heart_safety_question_returns_caution_not_just_training_advice(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "heart_safety")

    seed_day(
        store,
        user_id,
        "2026-07-01",
        sleep_hours=7.2,
        hrv_ms=48,
        resting_hr=64,
        active_zone_minutes=18,
        steps=7200,
    )
    seed_day(
        store,
        user_id,
        "2026-07-02",
        sleep_hours=6.8,
        hrv_ms=45,
        resting_hr=68,
        active_zone_minutes=22,
        steps=8200,
    )
    seed_day(
        store,
        user_id,
        "2026-07-03",
        sleep_hours=6.9,
        hrv_ms=38,
        resting_hr=92,
        active_zone_minutes=8,
        steps=1200,
    )

    clues = store.health_question_clues(
        user_id,
        "Should I worry about my high heart rate and dizziness?",
        days=7,
    )

    assert "heart" in clues["intent_hints"]
    assert {"daily-resting-heart-rate", "heart-rate", "daily-heart-rate-variability"} <= metric_ids(clues)
    assert clues["safety_flags"]
    assert any("medical" in item.lower() or "urgent care" in item.lower() for item in clues["safety_flags"])
    assert any("92 bpm" in item for item in clues["watchouts"])
    assert any("clinical" in item.lower() or "diagnos" in item.lower() for item in clues["answering_guidance"])


def test_eval_illness_safety_intent_selects_the_matching_health_surfaces(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "illness_safety")

    for offset, day in enumerate(["2026-07-01", "2026-07-02", "2026-07-03"]):
        seed_day(
            store,
            user_id,
            day,
            sleep_hours=7.2 - offset * 0.3,
            hrv_ms=52 - offset * 6,
            resting_hr=58 + offset * 4,
            active_zone_minutes=18,
            steps=6800,
            respiratory_rate=15.8 + offset * 0.7,
            spo2=97.2 - offset * 0.5,
            sleep_temperature_delta_c=0.05 + offset * 0.18,
        )

    clues = store.health_question_clues(
        user_id,
        "I have chills and a sore throat but want to keep momentum. What should I do?",
        days=7,
    )

    assert "symptom_safety" in clues["intent_hints"]
    assert {
        "daily-resting-heart-rate",
        "heart-rate",
        "daily-heart-rate-variability",
        "sleep",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
    } <= metric_ids(clues)
    assert any(item["purpose"] == "symptom_safety" for item in clues["query_suggestions"])
    assert clues["safety_flags"]
    safety_axis = {
        item["axis"]: item for item in clues["decision_frame"]["model_decision_policy"]["decision_axes"]
    }["safety_override"]
    assert {"resting_heart_rate", "respiratory_rate", "spo2", "sleep_temperature"} <= set(
        safety_axis["available_signal_ids"]
    )


def test_eval_large_synced_dataset_keeps_question_clues_fast_and_compact(tmp_path, monkeypatch) -> None:
    freeze_now(monkeypatch)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "large_dataset")

    for offset in range(30):
        day_num = offset + 1
        day = f"2026-06-{day_num:02d}" if day_num <= 30 else "2026-07-01"
        seed_day(
            store,
            user_id,
            day,
            sleep_hours=7.0 + (offset % 5) * 0.15,
            hrv_ms=48 + (offset % 7),
            resting_hr=57 + (offset % 4),
            active_zone_minutes=18 + (offset % 6) * 4,
            steps=6500 + offset * 120,
        )
        seed_heart_samples(store, user_id, day, count=24)
    seed_workout(store, user_id, "2026-06-28", "Long run", azm=44)
    store.save_goal(user_id, {"goal_type": "endurance", "target": "Build aerobic base", "days_per_week": 5})
    store.save_checkin(user_id, {"energy": 7, "soreness": 3, "stress": 4, "notes": "Solid week"})

    started = time.perf_counter()
    clues = store.health_question_clues(
        user_id,
        "Give me a smart overview of what matters before I train today.",
        days=30,
    )
    elapsed = time.perf_counter() - started
    serialized = json.dumps(clues)

    assert clues["status"] == "ok"
    assert elapsed < 1.5
    assert len(serialized) < 80_000
    assert clues["data_used"]["synced_metric_count"] >= 6
    assert clues["data_used"]["recent_workout_count"] == 1
    assert clues["data_used"]["recent_checkins_count"] == 1
    assert "payload_json" not in serialized
    assert "sampleTime" not in serialized
    assert "heart-rate" in clues["available_metric_ids"]
