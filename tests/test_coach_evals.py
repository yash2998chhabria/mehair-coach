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
    assert recommendation["data_used"]["recent_workouts"] == 2
    assert recommendation["goal_context"]["remaining_sessions"] == 1
    assert any("normal" in item.lower() or "train" in item.lower() for item in recommendation["next_actions"])
    assert "Latest energy check-in is 8/10." in recommendation["evidence"]
    assert "Latest soreness check-in is 2/10." in recommendation["evidence"]
    assert "Goal progress: 2/3 sessions logged; 1 remaining." in recommendation["evidence"]
    assert "Hardest recent workout: Easy run (24 Active Zone Minutes, 2026-07-01)." in recommendation["evidence"]


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
