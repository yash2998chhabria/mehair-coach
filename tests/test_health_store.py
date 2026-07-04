from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic

import pytest
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


def test_readiness_marks_sparse_baselines_as_low_confidence(tmp_path) -> None:
    _, store = make_store(tmp_path)
    db = store.db
    user_id = create_user(db, "sparse_baseline")

    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep-today",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-03T00:00:00Z",
                        "endTime": "2026-07-03T08:15:00Z",
                    },
                    "summary": {
                        "minutesAsleep": "480",
                        "minutesAwake": "15",
                        "minutesInSleepPeriod": "495",
                    },
                },
            }
        ],
    )
    for day, hrv, resting_hr in [
        ("2026-07-02", 31.3, 62),
        ("2026-07-03", 92.1, 60),
    ]:
        year, month, day_num = [int(part) for part in day.split("-")]
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

    context = store.latest_context(user_id)
    evidence = context["readiness"]["evidence"]

    assert context["readiness"]["label"] == "green"
    assert any("only 1 prior HRV day(s)" in item for item in evidence)
    assert any("only 1 prior resting-heart-rate day(s)" in item for item in evidence)
    assert not any("92.1 ms vs 31.3 ms" in item for item in evidence)


def test_freshness_uses_15_and_60_minute_sync_windows(monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed_now)

    fresh = health_store_module.freshness_details(
        "2026-07-03",
        "2026-07-03T11:46:00+00:00",
    )
    aging = health_store_module.freshness_details(
        "2026-07-03",
        "2026-07-03T11:20:00+00:00",
    )
    stale = health_store_module.freshness_details(
        "2026-07-03",
        "2026-07-03T10:59:00+00:00",
    )

    assert fresh["freshness_level"] == "fresh"
    assert fresh["freshness_label"] == "fresh <15 min"
    assert fresh["needs_sync_before_time_sensitive_advice"] is False
    assert aging["freshness_level"] == "aging"
    assert aging["freshness_label"] == "aging 15-60 min"
    assert aging["needs_sync_before_time_sensitive_advice"] is True
    assert stale["freshness_level"] == "stale"
    assert stale["freshness_label"] == "stale >1 hour"
    assert stale["needs_sync_before_time_sensitive_advice"] is True


@pytest.mark.asyncio
async def test_sync_returns_at_live_budget_when_answer_ready(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed_now)
    db, store = make_store(tmp_path)
    user_id = create_user(db, "live_budget_user")
    store.settings.sync_live_return_budget_seconds = 1
    store.settings.sync_request_budget_seconds = 8
    store.settings.sync_metric_timeout_seconds = 4
    monkeypatch.setattr(store.auth, "refresh_token_available", lambda _user_id: True)

    async def fake_access_token(_user_id: str) -> str:
        return "test-access-token"

    monkeypatch.setattr(store.auth, "ensure_google_access_token", fake_access_token)
    quick_metrics = {
        "sleep",
        "daily-resting-heart-rate",
        "daily-heart-rate-variability",
    }

    async def fake_fetch_metric_records(_access_token, spec, **_kwargs):
        if spec.id not in quick_metrics:
            await asyncio.sleep(10)
            return []
        await asyncio.sleep(0.01)
        if spec.id == "sleep":
            return [
                {
                    "name": "sleep-live-budget",
                    "sleep": {
                        "interval": {
                            "startTime": "2026-07-03T00:00:00Z",
                            "endTime": "2026-07-03T08:00:00Z",
                        },
                        "summary": {
                            "minutesAsleep": "450",
                            "minutesAwake": "30",
                            "minutesInSleepPeriod": "480",
                        },
                    },
                }
            ]
        if spec.id == "daily-resting-heart-rate":
            return [
                {
                    "name": "rhr-live-budget",
                    "dailyRestingHeartRate": {"beatsPerMinute": 58},
                    "date": {"year": 2026, "month": 7, "day": 3},
                }
            ]
        return [
            {
                "name": "hrv-live-budget",
                "dailyHeartRateVariability": {
                    "averageHeartRateVariabilityMilliseconds": 71.0
                },
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ]

    monkeypatch.setattr(store, "_fetch_metric_records", fake_fetch_metric_records)

    started = monotonic()
    result = await store.sync_latest(user_id, force=True, include_context=False)
    elapsed = monotonic() - started

    assert result["status"] == "ok"
    assert elapsed < 2.5
    assert result["partial_sync"] is True
    assert result["sync_window"]["live_return_cutoff"] is True
    assert result["sync_window"]["answer_ready_metrics"] == sorted(quick_metrics)
    assert set(result["metrics_synced"]) == quick_metrics


def test_sync_storage_prep_aggregates_high_volume_activity_metrics() -> None:
    records = [
        {
            "name": f"steps-{index}",
            "steps": {"count": 100 + index},
            "interval": {"startTime": f"2026-07-03T0{index}:00:00Z"},
        }
        for index in range(3)
    ]

    prepared = health_store_module._prepare_records_for_sync("steps", records, 600)

    assert len(prepared) == 1
    assert prepared[0]["name"] == "summary/steps/2026-07-03"
    assert prepared[0]["steps"]["count"] == 303
    assert prepared[0]["summary"]["sourceRecords"] == 3


def test_sync_storage_prep_preserves_heart_zone_totals() -> None:
    records = [
        {
            "name": "zone-1",
            "timeInHeartRateZone": {
                "heartRateZoneType": "FAT_BURN",
                "interval": {
                    "startTime": "2026-07-03T10:00:00Z",
                    "endTime": "2026-07-03T10:30:00Z",
                },
            },
        },
        {
            "name": "zone-2",
            "timeInHeartRateZone": {
                "heartRateZoneType": "CARDIO",
                "interval": {
                    "startTime": "2026-07-03T10:30:00Z",
                    "endTime": "2026-07-03T10:45:00Z",
                },
            },
        },
    ]

    prepared = health_store_module._prepare_records_for_sync(
        "time-in-heart-rate-zone",
        records,
        600,
    )

    assert len(prepared) == 1
    zones = prepared[0]["timeInHeartRateZone"]["heartRateZonesMinutes"]
    assert zones["CARDIO"] == 15
    assert zones["FAT_BURN"] == 30


def test_sync_storage_prep_compacts_raw_sample_metrics_to_daily_summary() -> None:
    records = [
        {
            "name": f"hr-{index}",
            "heartRate": {"beatsPerMinute": 60 + index},
            "sampleTime": {"physicalTime": f"2026-07-03T10:{index:02d}:00Z"},
        }
        for index in range(10)
    ]

    prepared = health_store_module._prepare_records_for_sync("heart-rate", records, 4)

    assert len(prepared) == 1
    assert prepared[0]["name"] == "summary/heart-rate/2026-07-03"
    assert prepared[0]["heartRate"]["summary"]["samples"] == 10
    assert prepared[0]["heartRate"]["summary"]["averageBeatsPerMinute"] == 64.5
    assert prepared[0]["heartRate"]["summary"]["minBeatsPerMinute"] == 60
    assert prepared[0]["heartRate"]["summary"]["maxBeatsPerMinute"] == 69

    summary = health_store_module.summarize_records(
        [
            {
                "data_type": "heart-rate",
                "observed_date": "2026-07-03",
                "payload": prepared[0],
            }
        ]
    )
    assert summary["daily"]["2026-07-03"]["heart"] == {
        "avg_bpm": 64.5,
        "min_bpm": 60,
        "max_bpm": 69,
        "samples": 10,
    }


def test_compact_sync_summary_wins_over_legacy_raw_rows() -> None:
    raw = {
        "data_type": "steps",
        "observed_date": "2026-07-03",
        "payload": {
            "name": "legacy-raw-steps",
            "steps": {"count": 1000},
            "interval": {"startTime": "2026-07-03T09:00:00Z"},
        },
    }
    compact = {
        "data_type": "steps",
        "observed_date": "2026-07-03",
        "payload": {
            "name": "summary/steps/2026-07-03",
            "date": {"year": 2026, "month": 7, "day": 3},
            "steps": {"count": 2500},
            "summary": {"sourceRecords": 15},
        },
    }

    summary = health_store_module.summarize_records([raw, compact])

    assert summary["daily"]["2026-07-03"]["steps"] == 2500


def test_compact_sync_write_replaces_legacy_raw_rows_for_same_metric_day(tmp_path) -> None:
    db, store = make_store(tmp_path)
    user_id = create_user(db)
    store.upsert_records(
        user_id,
        "steps",
        [
            {
                "name": "legacy-steps-1",
                "steps": {"count": 100},
                "interval": {"startTime": "2026-07-03T09:00:00Z"},
            },
            {
                "name": "legacy-steps-2",
                "steps": {"count": 200},
                "interval": {"startTime": "2026-07-03T10:00:00Z"},
            },
        ],
    )
    compact = health_store_module._prepare_records_for_sync(
        "steps",
        [
            {
                "name": "new-steps-1",
                "steps": {"count": 500},
                "interval": {"startTime": "2026-07-03T11:00:00Z"},
            },
            {
                "name": "new-steps-2",
                "steps": {"count": 700},
                "interval": {"startTime": "2026-07-03T12:00:00Z"},
            },
        ],
        600,
    )

    store.upsert_records(user_id, "steps", compact)

    rows = db.all(
        """
        SELECT data_type, record_key, observed_date, payload_json
        FROM raw_health_records
        WHERE user_id = ? AND data_type = 'steps'
        """,
        (user_id,),
    )
    assert len(rows) == 1
    assert rows[0]["record_key"] == "summary/steps/2026-07-03"
    assert store.latest_context(user_id)["today"]["steps"] == 1200


def test_empty_states_do_not_fabricate_data(tmp_path) -> None:
    _, store = make_store(tmp_path)

    setup = store.connection_status(None)
    assert setup["status"] == "setup_required"
    assert setup["conversation_flow_options"][0]["flow"] == "connect_first"
    assert "cannot see Fitbit or Google Health data" in setup["plain_english_state"]
    empty_context = store.latest_context("missing-user")
    assert empty_context["status"] == "empty"
    assert "No Fitbit data" in empty_context["message"]
    assert empty_context["conversation_flow_options"][0]["flow"] == "first_sync_after_connect"
    assert "sync_latest_fitbit_data" in empty_context["conversation_flow_options"][0]["primary_tools"]


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
    store.upsert_records(
        user_id,
        "daily-respiratory-rate",
        [
            {
                "name": "resp-1",
                "dailyRespiratoryRate": {"breathsPerMinute": 15.8},
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "respiratory-rate-sleep-summary",
        [
            {
                "name": "resp-sleep-1",
                "respiratoryRateSleepSummary": {
                    "sampleTime": {"physicalTime": "2026-07-03T06:00:00Z"},
                    "fullSleepStats": {
                        "breathsPerMinute": 15.7,
                        "standardDeviation": 0.9,
                        "signalToNoise": 12.5,
                    },
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-sleep-temperature-derivations",
        [
            {
                "name": "temp-1",
                "dailySleepTemperatureDerivations": {
                    "date": {"year": 2026, "month": 7, "day": 3},
                    "nightlyTemperatureCelsius": 35.92,
                    "baselineTemperatureCelsius": 35.71,
                    "relativeNightlyStddev30dCelsius": 0.31,
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-vo2-max",
        [
            {
                "name": "vo2-1",
                "dailyVo2Max": {
                    "date": {"year": 2026, "month": 7, "day": 3},
                    "vo2Max": 43.6,
                    "cardioFitnessLevel": "GOOD",
                    "estimated": False,
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
    assert context["today"]["respiratory_rate"] == 15.8
    assert context["today"]["sleep_temperature"]["delta_celsius"] == 0.21
    assert context["readiness"]["label"] == "green"
    assert context["readiness"]["score"] >= 75
    context_signal_ids = set(context["available_signal_snapshot"]["available_signal_ids"])
    assert {"spo2", "respiratory_rate", "sleep_temperature", "vo2_max", "heart_rate_zones", "steps"} <= context_signal_ids

    sleep = store.sleep_analysis(user_id)
    activity = store.activity_load(user_id)
    heart = store.heart_trends(user_id)

    assert sleep["latest"]["duration_hours"] == 8.0
    assert sleep["summary"]["average_asleep_hours"] == 8.0
    assert sleep["data_freshness"]["latest_observed_date"] == "2026-07-03"
    assert sleep["data_freshness"]["last_sync"]
    assert sleep["date_range"]["end"] == "2026-07-03"
    assert activity["days"][-1]["steps"] == 8500
    assert activity["totals"]["steps"] == 8500
    assert activity["coverage"]["days_with_activity"] == 1
    assert activity["data_freshness"]["latest_observed_date"] == "2026-07-03"
    assert activity["date_range"]["end"] == "2026-07-03"
    assert heart["days"][-1]["avg_bpm"] == 80.0
    assert heart["summary"]["average_hrv_ms"] == 45.2
    assert heart["coverage"]["days_with_heart_data"] == 1
    assert heart["data_freshness"]["latest_observed_date"] == "2026-07-03"
    assert heart["date_range"]["end"] == "2026-07-03"

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
    assert "daily-vo2-max" in catalog["model_guidance"]["metric_groups"]["capacity"]

    metrics = store.query_metrics(user_id, metrics=["steps", "sleep"], days=1)
    assert metrics["status"] == "ok"
    assert metrics["metrics"]["steps"]["daily"][-1]["steps"] == 8500
    assert metrics["metrics"]["sleep"]["daily"][-1]["sleep"]["duration_hours"] == 8.0
    assert metrics["missing_metrics"] == []
    assert metrics["data_freshness"]["latest_observed_date"] == "2026-07-03"
    assert metrics["data_freshness"]["last_sync"]

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

    store.upsert_records(
        user_id,
        "total-calories",
        [
            {
                "name": "calories-1",
                "date": {"year": 2026, "month": 7, "day": 3},
                "totalCalories": {"energyKilocalories": 2400},
            }
        ],
    )
    broad_metrics = store.query_metrics(user_id, metrics=["*"], days=1)
    broad_requested = set(broad_metrics["requested_metrics"])
    assert broad_metrics["status"] == "ok"
    assert broad_metrics["metric_selection"]["mode"] == "curated_default"
    assert broad_metrics["metric_selection"]["next_step"]
    assert {
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "heart-rate",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "activity-level",
        "steps",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    } <= broad_requested
    assert "total-calories" in broad_metrics["full_requested_metrics"]
    assert "total-calories" in broad_metrics["omitted_metrics"]
    assert "total-calories" not in broad_metrics["metrics"]

    explicit_low_priority = store.query_metrics(user_id, metrics=["total-calories"], days=1)
    assert explicit_low_priority["status"] == "ok"
    assert explicit_low_priority["metric_selection"]["mode"] == "explicit"
    assert explicit_low_priority["requested_metrics"] == ["total-calories"]
    assert "total-calories" in explicit_low_priority["metrics"]

    store.save_goal(user_id, {"goal_type": "running", "target": "Run four days per week"})
    store.save_checkin(user_id, {"energy": 8, "soreness": 2, "stress": 3, "notes": "Feeling good"})

    overview = store.health_overview(user_id, days=7)

    assert overview["status"] == "ok"
    assert overview["overview_type"] == "health_overview"
    assert overview["sections"]["activity"]["totals"]["steps"] == 8500
    assert overview["sections"]["activity"]["coverage"]["days_with_steps"] == 1
    assert overview["sections"]["activity"]["coverage"]["days_in_lookback"] == 7
    assert overview["sections"]["activity"]["average_denominators"]["steps_per_day"] == "recorded_step_days"
    assert "recorded day" in overview["sections"]["activity"]["step_window_summary"]["display"]
    assert overview["sections"]["activity"]["time_in_heart_rate_zones_minutes"]["fat_burn"] == 20.0
    assert overview["sections"]["sleep"]["latest_asleep_hours"] == 8.0
    assert overview["sections"]["heart"]["latest_hrv_ms"] == 45.2
    assert overview["sections"]["recovery"]["latest_spo2"] == 98.4
    assert overview["sections"]["recovery"]["latest_respiratory_rate"] == 15.8
    assert overview["sections"]["recovery"]["latest_sleep_temperature"]["delta_celsius"] == 0.21
    assert overview["sections"]["recovery"]["latest_vo2_max"] == 43.6
    readiness_breakdown = overview["readiness"]["score_breakdown"]
    assert readiness_breakdown["base"] == 50
    assert readiness_breakdown["score"] == overview["readiness"]["score"]
    assert "composite summary" in readiness_breakdown["model_guidance"]
    assert "component contributions" in readiness_breakdown["model_guidance"]
    contribution_ids = {item["signal"] for item in readiness_breakdown["contributions"]}
    assert {"sleep", "hrv", "resting_heart_rate", "spo2"} <= contribution_ids
    spo2_contribution = next(item for item in readiness_breakdown["contributions"] if item["signal"] == "spo2")
    assert spo2_contribution["role"] == "context_input"
    assert "not a standalone green light" in spo2_contribution["explanation"]
    assert overview["personal_context"]["goal"]["goal"]["target"] == "Run four days per week"
    assert overview["personal_context"]["recent_checkins"][0]["checkin"]["energy"] == 8
    assert overview["data_freshness"]["freshness_level"] == "fresh"
    assert overview["sync_state"]["needs_sync_before_time_sensitive_advice"] is False
    synced_ids = {item["id"] for item in overview["data_used"]["synced_metrics"]}
    assert {
        "steps",
        "sleep",
        "heart-rate",
        "oxygen-saturation",
        "daily-respiratory-rate",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    } <= synced_ids
    snapshot = overview["available_signal_snapshot"]
    signal_ids = {item["id"] for item in snapshot["signals"]}
    assert {"spo2", "respiratory_rate", "sleep_temperature", "vo2_max", "heart_rate_zones"} <= signal_ids
    spo2_signal = next(item for item in snapshot["signals"] if item["id"] == "spo2")
    assert spo2_signal["latest"] == 98.4
    assert "not a green light by themselves" in spo2_signal["why_it_matters"]
    assert overview["data_used"]["available_signal_count"] == len(snapshot["signals"])
    assert overview["unusual_signals"]["status"] == "ok"
    assert overview["unusual_signals"]["checked_context"]
    signal_context = overview["model_signal_context"]
    assert signal_context["status"] == "ok"
    assert "spo2" in signal_context["all_available_signal_ids"]
    assert any(
        item["id"] == "spo2"
        for item in signal_context["signal_groups"]["breathing_temperature_caution"]
    )
    assert any("green readiness score" in item for item in signal_context["answer_contract"])
    assert overview["daily"][-1]["time_in_hr_zones_minutes"]["fat_burn"] == 20.0
    assert overview["positives"]
    assert overview["next_actions"]
    brief = overview["daily_brief"]
    assert brief["training_bias"] == "train-ready"
    assert brief["confidence"] == "high"
    assert "Training is available today" in brief["summary"]
    signal_labels = {item["label"] for item in brief["priority_signals"]}
    assert {"Readiness", "Sleep", "HRV", "SpO2", "Respiratory rate", "VO2 max", "Energy", "Current goal"} <= signal_labels
    assert any("Run four days per week" in item["detail"] for item in brief["priority_signals"])
    assert brief["context_gaps"] == []


def test_overview_treats_very_low_spo2_as_watchout(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(health_store_module, "utc_now", lambda: fixed_now)
    monkeypatch.setattr(health_store_module, "iso_now", lambda: fixed_now.isoformat())
    db, store = make_store(tmp_path)
    user_id = create_user(db)

    store.upsert_records(
        user_id,
        "oxygen-saturation",
        [
            {
                "name": "spo2-low",
                "oxygenSaturation": {
                    "percentage": 80.4,
                    "sampleTime": {"physicalTime": "2026-07-03T06:00:00Z"},
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-respiratory-rate",
        [
            {
                "name": "resp-context",
                "dailyRespiratoryRate": {"breathsPerMinute": 16.6},
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )

    overview = store.health_overview(user_id, days=1)

    assert overview["sections"]["recovery"]["latest_spo2"] == 80.4
    assert any("very low wearable oxygen context" in item for item in overview["watchouts"])
    assert any("avoid hard training" in item for item in overview["next_actions"])
    assert not any("Latest SpO2 is 80.4% as context" in item for item in overview["positives"])
    spo2_signal = next(item for item in overview["daily_brief"]["priority_signals"] if item["label"] == "SpO2")
    assert spo2_signal["status"] == "watchout"
    assert "Very low wearable oxygen context" in spo2_signal["impact"]


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
    assert "What should I focus on today based on my data?" in overview["daily_brief"]["prompt_suggestions"]
    assert "I only have 30 minutes. What is the best use of it?" in overview["daily_brief"]["prompt_suggestions"]
    assert "Log how my energy, soreness, and stress feel right now." in overview["daily_brief"]["prompt_suggestions"]


def test_question_clues_reuses_summary_for_nested_context(tmp_path, monkeypatch) -> None:
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
                "name": "steps",
                "steps": {"count": 7200},
                "interval": {"startTime": "2026-07-03T12:00:00Z"},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "sleep",
        [
            {
                "name": "sleep",
                "sleep": {
                    "interval": {
                        "startTime": "2026-07-03T00:00:00Z",
                        "endTime": "2026-07-03T07:30:00Z",
                    },
                    "summary": {"minutesAsleep": "420"},
                },
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-heart-rate-variability",
        [
            {
                "name": "hrv",
                "dailyHeartRateVariability": {"averageHeartRateVariabilityMilliseconds": 52.0},
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )
    store.upsert_records(
        user_id,
        "daily-resting-heart-rate",
        [
            {
                "name": "rhr",
                "dailyRestingHeartRate": {"beatsPerMinute": 58},
                "date": {"year": 2026, "month": 7, "day": 3},
            }
        ],
    )

    real_summarize = health_store_module.summarize_records
    summarize_calls = 0

    def counting_summarize(records):
        nonlocal summarize_calls
        summarize_calls += 1
        return real_summarize(records)

    monkeypatch.setattr(health_store_module, "summarize_records", counting_summarize)

    clues = store.health_question_clues(
        user_id,
        "What should I know before training today?",
        days=7,
    )

    assert clues["status"] == "ok"
    assert clues["overview_context"]["daily_brief"]
    assert clues["recovery_comparison"]["status"] == "ok"
    assert summarize_calls == 1


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
        store.upsert_records(
            user_id,
            "daily-respiratory-rate",
            [
                {
                    "name": f"resp-{day}",
                    "dailyRespiratoryRate": {"breathsPerMinute": 15.0 if day != "2026-07-03" else 17.4},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
        store.upsert_records(
            user_id,
            "daily-oxygen-saturation",
            [
                {
                    "name": f"spo2-{day}",
                    "dailyOxygenSaturation": {"averagePercentage": 97.8 if day != "2026-07-03" else 96.1},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ],
        )
        store.upsert_records(
            user_id,
            "daily-sleep-temperature-derivations",
            [
                {
                    "name": f"temp-{day}",
                    "dailySleepTemperatureDerivations": {
                        "nightlyTemperatureCelsius": 36.0 if day != "2026-07-03" else 36.55,
                        "baselineTemperatureCelsius": 36.0,
                    },
                    "date": {"year": year, "month": month, "day": day_num},
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
    assert comparison["current_vs_baseline"]["respiratory_rate_delta"] >= 2
    assert {"spo2", "respiratory_rate", "sleep_temperature"} <= set(comparison["data_used"]["signals"])
    assert {"spo2", "respiratory_rate"} <= set(
        comparison["available_signal_snapshot"]["available_signal_ids"]
    )
    assert any("HRV" in item for item in comparison["watchouts"])
    assert any("Respiratory rate" in item for item in comparison["watchouts"])
    assert any("hard conditioning" in item for item in comparison["next_actions"])

    assert clues["status"] == "ok"
    assert clues["clue_type"] == "health_question_clues"
    assert "workout_decision" in clues["intent_hints"]
    assert "recovery" in clues["intent_hints"]
    metric_ids = {item["id"] for item in clues["relevant_metrics"]}
    assert {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"} <= metric_ids
    assert "recommend_workout_today" in clues["recommended_tool_sequence"]
    assert "get_recovery_signal_comparison" in clues["recommended_tool_sequence"]
    recovery_query = next(item for item in clues["query_suggestions"] if item["purpose"] == "recovery")
    assert recovery_query["tool"] == "query_health_metrics"
    assert recovery_query["arguments"]["days"] == 7
    assert {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"} <= set(
        recovery_query["arguments"]["metrics"]
    )
    assert any("intensity" in item.lower() for item in clues["answer_rubric"])
    assert any("HRV" in item for item in clues["clues"] + clues["watchouts"])
    assert any("SpO2" in item for item in clues["clues"])
    assert any("Respiratory rate" in item for item in clues["clues"] + clues["watchouts"])
    unusual = clues["unusual_signals"]
    assert unusual["status"] == "ok"
    unusual_labels = {item["signal"] for item in unusual["ranked_watchouts"]}
    assert {
        "Sleep",
        "HRV",
        "Resting HR",
        "Respiratory rate",
        "Sleep temperature",
        "Active Zone Minutes (AZM)",
    } <= unusual_labels
    assert unusual["ranked_watchouts"][0]["signal"] in {"Readiness", "Sleep"}
    assert any("anything unusual" in item.lower() or "what changed" in item.lower() for item in [unusual["model_guidance"]])
    assert "spo2" in clues["data_used"]["available_signal_ids"]
    assert any(
        "Movement context: 27,000 steps across 3 recorded days in the 7-day lookback" in item
        for item in clues["clues"]
    )
    assert any("recorded step days" in item for item in clues["clues"])
    assert any("not as a standalone reason to train or rest" in item for item in clues["clues"])
    assert clues["model_signal_context"]["status"] == "ok"
    assert any(
        "VO2 max" in item
        for item in clues["model_signal_context"]["decision_order"]
    )
    assert {
        "primary_recovery",
        "breathing_temperature_caution",
        "activity_load_window",
        "capacity_progress",
    } <= set(clues["model_signal_context"]["signal_groups"])

    day_plan = store.health_question_clues(user_id, "What should I do today?", days=7)

    assert "daily_plan" in day_plan["intent_hints"]
    assert "general_overview" in day_plan["intent_hints"]
    assert "workout_decision" in day_plan["intent_hints"]
    assert "get_health_overview" in day_plan["recommended_tool_sequence"]
    assert "recommend_workout_today" in day_plan["recommended_tool_sequence"]
    assert "plan_workout_with_health_context" in day_plan["recommended_tool_sequence"]
    assert day_plan["recommended_tool_sequence"].index("recommend_workout_today") < day_plan[
        "recommended_tool_sequence"
    ].index("get_health_overview")
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
    assert any(item["purpose"] == "heart" for item in active_prompt["query_suggestions"])
    assert any("in-session" in item for item in active_prompt["answer_rubric"])


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
    symptom_query = next(item for item in clues["query_suggestions"] if item["purpose"] == "symptom_safety")
    assert symptom_query["tool"] == "query_health_metrics"
    assert "daily-resting-heart-rate" in symptom_query["arguments"]["metrics"]
    assert any("avoid diagnosis" in item for item in clues["answer_rubric"])
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
