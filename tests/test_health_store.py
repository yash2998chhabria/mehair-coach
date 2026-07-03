from __future__ import annotations

from app.auth import AuthService
from app.crypto import generate_key
from app.db import Database
from app.health_store import HealthStore
from app.settings import Settings
from app.time_utils import iso_now


def make_store(tmp_path) -> tuple[Database, HealthStore]:
    settings = Settings(
        public_base_url="http://localhost:8787",
        database_url=f"sqlite:///{tmp_path / 'health.sqlite3'}",
        token_encryption_key=generate_key(),
    )
    db = Database(settings.sqlite_path)
    db.init()
    auth = AuthService(db, settings)
    return db, HealthStore(db, auth, settings)


def create_user(db: Database, user_id: str = "user_test") -> str:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO users (id, google_email, google_subject, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, "tester@example.com", "google-subject", iso_now(), iso_now()),
        )
    return user_id


def test_empty_states_do_not_fabricate_data(tmp_path) -> None:
    _, store = make_store(tmp_path)

    assert store.connection_status(None)["status"] == "setup_required"
    empty_context = store.latest_context("missing-user")
    assert empty_context["status"] == "empty"
    assert "No Fitbit data" in empty_context["message"]


def test_synthetic_records_calculate_context(tmp_path) -> None:
    db, store = make_store(tmp_path)
    user_id = create_user(db)

    store.upsert_records(
        user_id,
        "steps",
        [
            {
                "name": "steps-1",
                "steps": {"count": 8500},
                "interval": {"startTime": "2026-07-03T12:00:00Z"},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "active-zone-minutes",
        [
            {
                "name": "azm-1",
                "activeZoneMinutes": {"activeZoneMinutes": 35},
                "interval": {"startTime": "2026-07-03T12:00:00Z"},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep-1",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-03T00:00:00Z",
                        "endTime": "2026-07-03T08:00:00Z",
                    },
                    "stages": [
                        {
                            "type": "DEEP",
                            "startTime": "2026-07-03T01:00:00Z",
                            "endTime": "2026-07-03T02:00:00Z",
                        }
                    ],
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "heart-rate",
        [
            {
                "name": "hr-1",
                "heartRate": {"beatsPerMinute": 70},
                "sampleTime": {"physicalTime": "2026-07-03T12:00:00Z"},
            },
            {
                "name": "hr-2",
                "heartRate": {"beatsPerMinute": 90},
                "sampleTime": {"physicalTime": "2026-07-03T12:05:00Z"},
            },
        ],
    )
    store.upsert_records(
        user_id,
        "daily-resting-heart-rate",
        [
            {
                "name": "rhr-1",
                "dailyRestingHeartRate": {"beatsPerMinute": 58},
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-heart-rate-variability",
        [
            {
                "name": "hrv-1",
                "dailyHeartRateVariability": {
                    "averageHeartRateVariabilityMilliseconds": 45.2
                },
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "time-in-heart-rate-zone",
        [
            {
                "name": "fat-burn-zone",
                "timeInHeartRateZone": {
                    "heartRateZoneType": "FAT_BURN",
                    "interval": {
                        "startTime": "2026-07-03T12:00:00Z",
                        "endTime": "2026-07-03T12:20:00Z",
                    },
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "activity-level",
        [
            {
                "name": "vigorous-level",
                "activityLevel": {
                    "activityLevelType": "VIGOROUS",
                    "interval": {
                        "startTime": "2026-07-03T12:20:00Z",
                        "endTime": "2026-07-03T12:35:00Z",
                    },
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "oxygen-saturation",
        [
            {
                "name": "spo2-sample",
                "oxygenSaturation": {
                    "percentage": 98.4,
                    "sampleTime": {"physicalTime": "2026-07-03T06:00:00Z"},
                },
            }
        ],
    )

    context = store.latest_context(user_id)

    assert context["status"] == "ok"
    assert context["latest_date"] == "2026-07-03"
    assert context["today"]["steps"] == 8500
    assert context["today"]["active_zone_minutes"] == 35
    assert context["today"]["sleep"]["duration_hours"] == 8.0
    assert context["today"]["heart"]["avg_bpm"] == 80.0
    assert context["readiness"]["label"] == "green"
    assert context["readiness"]["score"] >= 75

    sleep = store.sleep_analysis(user_id)
    activity = store.activity_load(user_id)
    heart = store.heart_trends(user_id)

    assert sleep["latest"]["duration_hours"] == 8.0
    assert sleep["summary"]["average_asleep_hours"] == 8.0
    assert activity["days"][-1]["steps"] == 8500
    assert activity["totals"]["steps"] == 8500
    assert heart["days"][-1]["avg_bpm"] == 80.0
    assert heart["summary"]["average_hrv_ms"] == 45.2

    catalog = store.available_metrics(user_id)
    steps_metric = next(item for item in catalog["metrics"] if item["id"] == "steps")
    assert catalog["status"] == "ok"
    assert steps_metric["records"] == 1
    assert "food" in catalog["excluded_categories"]

    metrics = store.query_metrics(user_id, metrics=["steps", "sleep"], days=1)
    assert metrics["status"] == "ok"
    assert metrics["metrics"]["steps"]["daily"][-1]["steps"] == 8500
    assert metrics["metrics"]["sleep"]["daily"][-1]["sleep"]["duration_hours"] == 8.0
    assert metrics["missing_metrics"] == []

    richer_metrics = store.query_metrics(
        user_id,
        metrics=["time-in-heart-rate-zone", "activity-level", "oxygen-saturation"],
        days=1,
    )
    assert richer_metrics["metrics"]["time-in-heart-rate-zone"]["daily"][-1][
        "time_in_hr_zones_minutes"
    ]["fat_burn"] == 20.0
    assert richer_metrics["metrics"]["activity-level"]["daily"][-1]["activity_levels_minutes"][
        "vigorous"
    ] == 15.0
    assert richer_metrics["metrics"]["oxygen-saturation"]["daily"][-1]["spo2_sample"]["avg"] == 98.4

    store.save_goal(user_id, {"goal_type": "running", "target": "Run four days per week"})
    store.save_checkin(user_id, {"energy": 8, "soreness": 2, "stress": 3, "notes": "Feeling good"})

    overview = store.health_overview(user_id, days=7)

    assert overview["status"] == "ok"
    assert overview["overview_type"] == "health_overview"
    assert overview["sections"]["activity"]["totals"]["steps"] == 8500
    assert overview["sections"]["activity"]["time_in_heart_rate_zones_minutes"]["fat_burn"] == 20.0
    assert overview["sections"]["sleep"]["latest_asleep_hours"] == 8.0
    assert overview["sections"]["heart"]["latest_hrv_ms"] == 45.2
    assert overview["sections"]["recovery"]["latest_spo2"] == 98.4
    assert overview["personal_context"]["goal"]["goal"]["target"] == "Run four days per week"
    assert overview["personal_context"]["recent_checkins"][0]["checkin"]["energy"] == 8
    synced_ids = {item["id"] for item in overview["data_used"]["synced_metrics"]}
    assert {"steps", "sleep", "heart-rate", "oxygen-saturation"} <= synced_ids
    assert overview["daily"][-1]["time_in_hr_zones_minutes"]["fat_burn"] == 20.0
    assert overview["positives"]
    assert overview["next_actions"]


def test_partial_today_uses_latest_completed_recovery_signals(tmp_path) -> None:
    db, store = make_store(tmp_path)
    user_id = create_user(db)

    store.upsert_records(
        user_id,
        "steps",
        [
            {
                "name": "steps-partial-today",
                "steps": {"count": 136},
                "interval": {"startTime": "2026-07-03T07:32:00Z"},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "active-zone-minutes",
        [
            {
                "name": "azm-yesterday",
                "activeZoneMinutes": {"activeZoneMinutes": 63},
                "interval": {"startTime": "2026-07-02T20:00:00Z"},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep-yesterday",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-02T10:15:00Z",
                        "endTime": "2026-07-02T14:40:00Z",
                    },
                    "summary": {
                        "minutesAsleep": "235",
                        "minutesAwake": "30",
                        "minutesInSleepPeriod": "265",
                    },
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-heart-rate-variability",
        [
            {
                "name": "hrv-baseline",
                "dailyHeartRateVariability": {
                    "averageHeartRateVariabilityMilliseconds": 90.5
                },
                "date": {"year": 2026, "month": 7, "day": 1},
            },
            {
                "name": "hrv-yesterday",
                "dailyHeartRateVariability": {
                    "averageHeartRateVariabilityMilliseconds": 31.3
                },
                "date": {"year": 2026, "month": 7, "day": 2},
            },
        ],
    )
    store.upsert_records(
        user_id,
        "daily-resting-heart-rate",
        [
            {
                "name": "rhr-yesterday",
                "dailyRestingHeartRate": {"beatsPerMinute": 64},
                "date": {"year": 2026, "month": 7, "day": 2},
            }
        ],
    )

    context = store.latest_context(user_id)

    assert context["latest_date"] == "2026-07-03"
    assert context["activity_date"] == "2026-07-03"
    assert context["recovery_date"] == "2026-07-02"
    assert context["today"]["steps"] == 136
    assert context["today"]["active_zone_minutes"] == 0
    assert context["today"]["latest_training_load"]["active_zone_minutes"] == 63
    assert context["today"]["sleep"]["asleep_hours"] == 3.92
    assert context["today"]["hrv_ms"] == 31.3
    assert context["readiness"]["label"] == "red"
    assert any("Recovery signals are from 2026-07-02" in item for item in context["evidence"])


def test_same_day_sleep_sessions_are_aggregated(tmp_path) -> None:
    db, store = make_store(tmp_path)
    user_id = create_user(db)

    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep-main",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-02T06:15:00Z",
                        "endTime": "2026-07-02T10:40:00Z",
                    },
                    "summary": {
                        "minutesAsleep": "235",
                        "minutesAwake": "30",
                        "minutesInSleepPeriod": "265",
                        "stagesSummary": [
                            {"type": "DEEP", "minutes": "45"},
                            {"type": "REM", "minutes": "58"},
                        ],
                    },
                },
            },
            {
                "name": "sleep-nap",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-02T20:00:00Z",
                        "endTime": "2026-07-02T22:15:00Z",
                    },
                    "summary": {
                        "minutesAsleep": "129",
                        "minutesAwake": "6",
                        "minutesInSleepPeriod": "135",
                        "stagesSummary": [
                            {"type": "DEEP", "minutes": "25"},
                            {"type": "LIGHT", "minutes": "80"},
                        ],
                    },
                },
            },
        ],
    )

    sleep = store.sleep_analysis(user_id)
    latest = sleep["latest"]

    assert latest["sessions_count"] == 2
    assert latest["asleep_hours"] == 6.07
    assert latest["duration_hours"] == 6.67
    assert latest["awake_minutes"] == 36.0
    assert latest["stages_minutes"]["deep"] == 70.0
    assert sleep["summary"]["latest_asleep_hours"] == 6.07
