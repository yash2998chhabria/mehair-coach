from __future__ import annotations

from app.main import workout_plan_for_activity


def test_planned_chest_day_downshifts_for_red_readiness_and_back_soreness() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-02",
        "readiness": {
            "score": 42,
            "label": "red",
            "recommendation": "Prioritize recovery, mobility, walking, and sleep.",
            "evidence": [
                "Latest sleep is moderate at 6.1h.",
                "HRV is below recent baseline: 31.3 ms vs 90.5 ms.",
                "Resting heart rate is slightly elevated: 64 bpm.",
                "Recent training load is high: 63 zone minutes on 2026-07-02.",
            ],
        },
        "today": {
            "steps": 136,
            "active_minutes": 17,
            "active_zone_minutes": 0,
            "hrv_ms": 31.3,
            "resting_heart_rate": 64,
            "sleep": {"asleep_hours": 6.07, "sessions_count": 2},
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 63},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="chest day",
        target_areas=["chest"],
        planned_date="tomorrow",
        constraints="left lower back soreness after squash",
        duration_minutes=60,
        checkins=[{"checkin": {"soreness": 6, "energy": 5}, "created_at": "2026-07-03T09:00:00Z"}],
    )

    assert plan["status"] == "ok"
    assert plan["recommended_intensity"] == "easy"
    assert plan["rpe_cap"] <= 7
    assert any("Do not chase PRs" in item for item in plan["session_guidance"])
    assert any("Aggressive bench arch" in item for item in plan["avoid"])
    assert any("HRV is below recent baseline" in item for item in plan["limiting_factors"])
    assert plan["data_used"]["sleep_asleep_hours"] == 6.07
    assert plan["data_used"]["latest_training_load"]["active_zone_minutes"] == 63


def test_green_readiness_allows_normal_planned_session() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 82,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.0h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 8500,
            "active_minutes": 54,
            "active_zone_minutes": 35,
            "hrv_ms": 48.5,
            "resting_heart_rate": 57,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 35},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="chest and triceps",
        target_areas=["chest"],
    )

    assert plan["recommended_intensity"] == "moderate-to-hard"
    assert plan["rpe_cap"] == 8
    assert any("normal session" in item.lower() for item in plan["session_guidance"])
