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
    assert activity["days"][-1]["steps"] == 8500
    assert heart["days"][-1]["avg_bpm"] == 80.0
