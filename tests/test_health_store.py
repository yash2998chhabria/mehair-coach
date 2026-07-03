from __future__ import annotations

from datetime import UTC, datetime

import app.health_store as health_store_module
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


def test_synthetic_records_calculate_context(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed_now)
    monkeypatch.setattr(health_store_module, "iso_now", lambda: fixed_now.isoformat())
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
    assert "Choose metrics from the user's question" in catalog["model_guidance"]["principles"][0]
    assert "query_health_metrics for model-selected metric details" in catalog["model_guidance"][
        "general_tool_flow"
    ]
    assert "sleep" in catalog["model_guidance"]["metric_groups"]["recovery_readiness"]
    assert "daily-heart-rate-variability" in catalog["model_guidance"]["metric_groups"]["recovery_readiness"]
    assert "active-zone-minutes" in catalog["model_guidance"]["metric_groups"]["training_load"]
    assert "daily-vo2-max" not in catalog["model_guidance"]["metric_groups"]["capacity"]

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
    assert overview["data_freshness"]["freshness_level"] == "fresh"
    assert overview["sync_state"]["needs_sync_before_time_sensitive_advice"] is False
    synced_ids = {item["id"] for item in overview["data_used"]["synced_metrics"]}
    assert {"steps", "sleep", "heart-rate", "oxygen-saturation"} <= synced_ids
    assert overview["daily"][-1]["time_in_hr_zones_minutes"]["fat_burn"] == 20.0
    assert overview["positives"]
    assert overview["next_actions"]
    brief = overview["daily_brief"]
    assert brief["training_bias"] == "train-ready"
    assert brief["confidence"] == "high"
    assert "Training is available today" in brief["summary"]
    signal_labels = {item["label"] for item in brief["priority_signals"]}
    assert {"Readiness", "Sleep", "HRV", "Energy", "Current goal"} <= signal_labels
    assert any("Run four days per week" in item["detail"] for item in brief["priority_signals"])
    assert brief["context_gaps"] == []


def test_overview_flags_stale_data_before_time_sensitive_advice(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed_now)
    monkeypatch.setattr(health_store_module, "iso_now", lambda: fixed_now.isoformat())
    db, store = make_store(tmp_path)
    user_id = create_user(db)

    store.upsert_records(
        user_id,
        "steps",
        [
            {
                "name": "old-steps",
                "steps": {"count": 7200},
                "interval": {"startTime": "2026-07-01T17:00:00Z"},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "old-sleep",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-01T00:00:00Z",
                        "endTime": "2026-07-01T07:30:00Z",
                    }
                },
            }
        ],
    )

    freshness = store.freshness(user_id)
    overview = store.health_overview(user_id, days=7)

    assert freshness["freshness_level"] == "stale"
    assert freshness["observed_days_ago"] == 2
    assert overview["sync_state"]["needs_sync_before_time_sensitive_advice"] is True
    assert overview["data_freshness"]["freshness_label"] == "sync recommended"
    assert any("stale" in item.lower() for item in overview["watchouts"])
    assert overview["next_actions"][0] == "Run sync_latest_fitbit_data before time-sensitive workout decisions."
    assert overview["daily_brief"]["training_bias"] == "sync-first"
    assert "Sync first" in overview["daily_brief"]["summary"]
    assert any(item["label"] == "Data freshness" for item in overview["daily_brief"]["priority_signals"])
    assert any("No recent subjective check-in" in item for item in overview["daily_brief"]["context_gaps"])
    assert any("No coaching goal" in item for item in overview["daily_brief"]["context_gaps"])
    assert any("Heart recovery data is missing" in item for item in overview["daily_brief"]["context_gaps"])
    assert "Log a quick energy, soreness, and stress check-in." in overview["daily_brief"]["prompt_suggestions"]


def test_question_clues_choose_recovery_heart_and_load_metrics(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed_now)
    monkeypatch.setattr(health_store_module, "iso_now", lambda: fixed_now.isoformat())
    db, store = make_store(tmp_path)
    user_id = create_user(db)

    for day, asleep_minutes, hrv, resting_hr, zone_minutes in [
        ("2026-07-01", 450, 56.0, 58, 22),
        ("2026-07-02", 455, 54.0, 58, 28),
        ("2026-07-03", 305, 39.0, 65, 52),
    ]:
        year, month, day_num = [int(part) for part in day.split("-")]
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
                            "minutesAsleep": str(asleep_minutes),
                            "minutesAwake": "35",
                            "minutesInSleepPeriod": str(asleep_minutes + 35),
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
                    "name": f"hrv-{day}",
                    "dailyHeartRateVariability": {
                        "averageHeartRateVariabilityMilliseconds": hrv
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
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
        store.upsert_records(
            user_id,
            "active-zone-minutes",
            [
                {
                    "name": f"azm-{day}",
                    "activeZoneMinutes": {"activeZoneMinutes": zone_minutes},
                    "interval": {"startTime": f"{day}T18:00:00Z"},
                }
            ],
        )
        store.upsert_records(
            user_id,
            "steps",
            [
                {
                    "name": f"steps-{day}",
                    "steps": {"count": 9000},
                    "interval": {"startTime": f"{day}T12:00:00Z"},
                }
            ],
        )

    comparison = store.recovery_signal_comparison(user_id, days=7)
    clues = store.health_question_clues(
        user_id,
        "How hard should I work out today, and why am I so tired?",
        days=7,
    )

    assert comparison["status"] == "ok"
    assert comparison["comparison_type"] == "sleep_heart_recovery"
    assert comparison["current_vs_baseline"]["hrv_percent_delta"] < -20
    assert comparison["current_vs_baseline"]["resting_heart_rate_delta"] >= 7
    assert any("HRV" in item for item in comparison["watchouts"])
    assert any("hard conditioning" in item for item in comparison["next_actions"])

    assert clues["status"] == "ok"
    assert clues["clue_type"] == "health_question_clues"
    assert "workout_decision" in clues["intent_hints"]
    assert "recovery" in clues["intent_hints"]
    metric_ids = {item["id"] for item in clues["relevant_metrics"]}
    assert {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"} <= metric_ids
    assert "recommend_workout_today" in clues["recommended_tool_sequence"]
    assert "get_recovery_signal_comparison" in clues["recommended_tool_sequence"]
    assert any("HRV" in item for item in clues["clues"] + clues["watchouts"])

    day_plan = store.health_question_clues(user_id, "What should I do today?", days=7)

    assert "daily_plan" in day_plan["intent_hints"]
    assert "general_overview" in day_plan["intent_hints"]
    assert "workout_decision" in day_plan["intent_hints"]
    assert "get_health_overview" in day_plan["recommended_tool_sequence"]
    assert "recommend_workout_today" in day_plan["recommended_tool_sequence"]
    assert "plan_workout_with_health_context" in day_plan["recommended_tool_sequence"]
    assert day_plan["headline"].startswith("Use the daily brief")
    assert day_plan["overview_context"]["daily_brief"]["training_bias"] == "recovery-first"
    assert day_plan["overview_context"]["daily_brief"]["today_plan"]

    active_prompt = store.health_question_clues(
        user_id,
        "During my workout: 12 minutes into cycling, heart rate 150 bpm, RPE 7/10, pain 0/10, should I push or back off?",
        days=7,
    )

    assert "active_workout" in active_prompt["intent_hints"]
    assert "guide_active_workout" in active_prompt["recommended_tool_sequence"]
    assert active_prompt["recommended_tool_sequence"].index("guide_active_workout") < active_prompt[
        "recommended_tool_sequence"
    ].index("recommend_workout_today")


def test_question_clues_surface_illness_checkin_before_workout_advice(tmp_path) -> None:
    db, store = make_store(tmp_path)
    user_id = create_user(db, "illness_user")

    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep-today",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-03T00:00:00Z",
                        "endTime": "2026-07-03T08:00:00Z",
                    },
                    "summary": {
                        "minutesAsleep": "485",
                        "minutesAwake": "20",
                        "minutesInSleepPeriod": "505",
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
                "name": "hrv-today",
                "dailyHeartRateVariability": {
                    "averageHeartRateVariabilityMilliseconds": 60.0
                },
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-resting-heart-rate",
        [
            {
                "name": "rhr-today",
                "dailyRestingHeartRate": {"beatsPerMinute": 56},
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "active-zone-minutes",
        [
            {
                "name": "azm-today",
                "activeZoneMinutes": {"activeZoneMinutes": 16},
                "interval": {"startTime": "2026-07-03T12:00:00Z"},
            }
        ],
    )
    store.save_checkin(
        user_id,
        {
            "energy": 7,
            "soreness": 2,
            "stress": 3,
            "notes": "Woke up with fever, chills, and a sore throat.",
        },
    )

    clues = store.health_question_clues(user_id, "Can I work out today?", days=7)

    assert "symptom_safety" in clues["intent_hints"]
    assert clues["safety_flags"]
    assert any("Illness symptoms" in item for item in clues["safety_flags"])
    assert any("avoid hard training" in item for item in clues["watchouts"])
    assert "Latest check-in note: Woke up with fever, chills, and a sore throat." in clues["clues"]
    assert "recommend_workout_today" in clues["recommended_tool_sequence"]


def test_question_clues_do_not_flag_negated_illness_checkin(tmp_path) -> None:
    db, store = make_store(tmp_path)
    user_id = create_user(db, "no_illness_user")

    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep-today",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-03T00:00:00Z",
                        "endTime": "2026-07-03T08:00:00Z",
                    },
                    "summary": {
                        "minutesAsleep": "485",
                        "minutesAwake": "20",
                        "minutesInSleepPeriod": "505",
                    },
                },
            }
        ],
    )
    store.save_checkin(
        user_id,
        {
            "energy": 7,
            "soreness": 2,
            "stress": 3,
            "notes": "No fever, no chills, no sore throat, and no dizziness.",
        },
    )

    clues = store.health_question_clues(user_id, "Can I work out today?", days=7)

    assert clues["safety_flags"] == []
    assert not any("Illness symptoms" in item for item in clues["watchouts"])


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
