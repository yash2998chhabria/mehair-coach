from __future__ import annotations

from app.main import active_workout_guidance, workout_plan_for_activity, workout_recommendation


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
    assert any(block["exercise"] == "Machine chest press" for block in plan["exercise_blocks"])
    assert any(block["exercise"] == "Chest-supported row" for block in plan["exercise_blocks"])
    assert any("Bent-over row -> chest-supported row" in item for item in plan["substitutions"])
    assert any("lower-back" in item for item in plan["limiting_factors"])
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
    assert not any("lower-back" in item for item in plan["limiting_factors"])
    assert any(block["exercise"] == "Machine chest press" for block in plan["exercise_blocks"])


def test_short_between_meetings_plan_caps_intensity_without_hard_request() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 9.4h.",
                "HRV is above recent baseline, but the baseline is low confidence.",
                "Resting heart rate is steady: 60 bpm.",
            ],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 44,
            "active_zone_minutes": 18,
            "hrv_ms": 92.1,
            "resting_heart_rate": 60,
            "sleep": {"asleep_hours": 9.4, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 9},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="useful movement session",
        target_areas=[],
        constraints="I feel normal today but only have 20 minutes between meetings.",
        duration_minutes=20,
    )
    joined_guidance = " ".join(
        [plan["coach_response"]["short_answer"], *plan["focus"], *plan["session_guidance"], *plan["avoid"]]
    ).lower()

    assert plan["recommended_intensity"] == "moderate"
    assert plan["rpe_cap"] == 7
    assert plan["data_used"]["short_constrained_session"] is True
    assert plan["data_used"]["explicit_high_intensity_request"] is False
    assert plan["data_used"]["requested_duration_minutes"] == 20
    assert any("Short time box" in item for item in plan["limiting_factors"])
    assert "compact and useful" in joined_guidance
    assert "leave one gear unused" in joined_guidance
    assert "all-out workout" in joined_guidance


def test_short_session_keeps_high_intensity_when_user_explicitly_requests_it() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 86,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.5h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 4500,
            "active_minutes": 18,
            "active_zone_minutes": 6,
            "hrv_ms": 72.0,
            "resting_heart_rate": 54,
            "sleep": {"asleep_hours": 8.5, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 6},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="hard intervals",
        target_areas=[],
        constraints="I only have 20 minutes and specifically want hard intervals.",
        duration_minutes=20,
    )

    assert plan["recommended_intensity"] == "moderate-to-hard"
    assert plan["rpe_cap"] == 8
    assert plan["data_used"]["short_constrained_session"] is True
    assert plan["data_used"]["explicit_high_intensity_request"] is True
    assert not any("Short time box" in item for item in plan["limiting_factors"])


def test_upper_body_plan_with_sore_legs_stays_useful_and_leg_sparing() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 9.4h.",
                "HRV is above recent baseline: 92.1 ms vs 61.7 ms.",
                "Resting heart rate is steady: 60 bpm.",
            ],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 44,
            "active_zone_minutes": 18,
            "hrv_ms": 92.1,
            "resting_heart_rate": 60,
            "sleep": {"asleep_hours": 9.4, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 17},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="upper body lift",
        target_areas=["chest", "back", "shoulders"],
        constraints="My legs are sore from yesterday, but I want to train upper body today.",
        duration_minutes=45,
        checkins=[
            {
                "checkin": {
                    "energy": 7,
                    "soreness": 2,
                    "stress": 3,
                    "notes": "Earlier test note mentioned fever and chills.",
                }
            }
        ],
    )

    joined = " ".join(
        [
            plan["summary"],
            plan["coach_response"]["short_answer"],
            plan["coach_response"]["data_story"],
            *plan["coach_response"]["session_blueprint"],
            *plan["avoid"],
        ]
    ).lower()

    assert plan["recommended_intensity"] == "moderate"
    assert plan["rpe_cap"] == 7
    assert plan["data_used"]["localized_soreness_away_from_target"] is True
    assert plan["data_used"]["illness_flags"] == []
    assert plan["data_used"]["checkin_illness_flags_used"] is False
    assert "rest or very easy movement" not in joined
    assert "not-100" not in joined
    assert "sore areas should shape exercise choice" in plan["coach_response"]["data_story"]
    assert any("sore legs out of the job" in item for item in plan["focus"])
    assert any("Leg drive" in item for item in plan["avoid"])
    assert any(block["exercise"] == "Chest-supported row" for block in plan["exercise_blocks"])
    assert any(item["label"] == "RPE" for item in plan["coach_response"]["labels_explained"])


def test_back_workout_without_soreness_is_not_treated_as_lower_back_constraint() -> None:
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
        planned_activity="back day",
        target_areas=["back"],
        constraints="keep it efficient",
    )

    assert plan["rpe_cap"] == 8
    assert not any("lower-back" in item for item in plan["limiting_factors"])
    assert any(block["exercise"] == "Chest-supported row" for block in plan["exercise_blocks"])


def test_workout_plan_uses_overview_section_recovery_values() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "data_used": {"activity_date": "2026-07-03", "recovery_date": "2026-07-02"},
        "readiness": {
            "score": 44,
            "label": "red",
            "recommendation": "Prioritize recovery, mobility, walking, and sleep.",
            "evidence": ["Recent training load is high: 63 zone minutes on 2026-07-02."],
        },
        "today": {
            "steps": 136,
            "active_minutes": 17,
            "active_zone_minutes": 0,
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 63},
        },
        "sections": {
            "sleep": {"latest_asleep_hours": 6.07, "days_with_sleep": 4},
            "heart": {"latest_hrv_ms": 31.3, "latest_resting_heart_rate": 65},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="chest and back gym session",
        target_areas=["chest", "back"],
        constraints="lower back feels tight from sitting",
    )

    assert plan["data_used"]["activity_date"] == "2026-07-03"
    assert plan["data_used"]["recovery_date"] == "2026-07-02"
    assert plan["data_used"]["sleep_asleep_hours"] == 6.07
    assert plan["data_used"]["hrv_ms"] == 31.3
    assert plan["data_used"]["resting_heart_rate"] == 65


def test_specific_lift_plan_uses_stated_energy_pain_and_tomorrow_sport() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-02",
        "readiness": {
            "score": 44,
            "label": "red",
            "recommendation": "Prioritize recovery, mobility, walking, and sleep.",
            "evidence": [
                "Latest sleep is moderate at 6.1h.",
                "HRV is below recent baseline: 31.3 ms vs 60.9 ms.",
                "Resting heart rate is slightly elevated: 65 bpm.",
                "Recent training load is high: 63 zone minutes on 2026-07-02.",
            ],
        },
        "today": {
            "steps": 136,
            "active_minutes": 17,
            "active_zone_minutes": 0,
            "hrv_ms": 31.3,
            "resting_heart_rate": 65,
            "sleep": {"asleep_hours": 6.07, "sessions_count": 2},
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 63},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="45-minute upper-body lift",
        target_areas=["chest", "back", "shoulders"],
        constraints="left lower back feels tight at 2/10, energy is 4/10, and I want to play squash tomorrow",
        duration_minutes=45,
    )

    assert plan["recommended_intensity"] == "easy"
    assert plan["rpe_cap"] <= 6
    assert plan["data_used"]["stated_energy"] == 4
    assert plan["data_used"]["stated_pain"] == 2
    assert plan["data_used"]["preserving_next_session"] is True
    assert any("energy is low at 4/10" in item for item in plan["limiting_factors"])
    assert any("pain or tightness is 2/10" in item for item in plan["limiting_factors"])
    assert any("preserve readiness" in item for item in plan["limiting_factors"])
    assert any("tomorrow's sport session" in item for item in plan["session_guidance"])
    assert any("tomorrow's sport or workout session" in item for item in plan["avoid"])


def test_planned_run_with_tomorrow_sport_does_not_match_row_inside_tomorrow() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 8.3h.",
                "HRV is above recent baseline.",
                "Resting heart rate is steady.",
            ],
        },
        "today": {
            "steps": 6400,
            "active_minutes": 42,
            "active_zone_minutes": 10,
            "hrv_ms": 62,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.3, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 10},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="run",
        target_areas=["legs"],
        constraints="I have soccer tomorrow and want to preserve freshness.",
        duration_minutes=35,
    )

    exercises = [block["exercise"] for block in plan["exercise_blocks"]]

    assert plan["rpe_cap"] <= 6
    assert any("Easy aerobic warm-up" == exercise for exercise in exercises)
    assert any("Technique block" == exercise for exercise in exercises)
    assert not any("Chest-supported row" == exercise for exercise in exercises)
    assert not any("Neutral-grip lat pulldown" == exercise for exercise in exercises)
    assert not any("Leg press" in exercise for exercise in exercises)
    assert not any("Hamstring curl" == exercise for exercise in exercises)
    assert any("tomorrow's sport session" in item for item in plan["session_guidance"])
    assert "row" not in " ".join(plan["substitutions"]).lower()
    assert not any("keep every set" in item.lower() for item in plan["coach_response"]["session_blueprint"])
    assert any("keep effort" in item.lower() for item in plan["coach_response"]["session_blueprint"])


def test_preserving_tomorrow_does_not_imply_user_feels_off() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 9.4h.",
                "HRV is above recent baseline: 92.1 ms vs 31.3 ms.",
                "Resting heart rate is steady: 60 bpm.",
            ],
        },
        "today": {
            "steps": 6400,
            "active_minutes": 42,
            "active_zone_minutes": 10,
            "hrv_ms": 92.1,
            "resting_heart_rate": 60,
            "sleep": {"asleep_hours": 9.4, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 10},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="leg day strength session",
        target_areas=["legs"],
        constraints=(
            "thinking about doing legs today. What should I do so I don't cook myself for tomorrow? "
            "Important: I have pickup basketball tomorrow."
        ),
        duration_minutes=35,
    )

    coach = plan["coach_response"]
    joined = " ".join(
        [
            coach["short_answer"],
            coach["data_story"],
            *coach["what_to_do"],
            *coach["session_blueprint"],
        ]
    ).lower()

    assert plan["data_used"]["preserving_next_session"] is True
    assert plan["rpe_cap"] <= 6
    assert "tomorrow still stays available" in coach["short_answer"]
    assert "not-100" not in joined
    assert "feel off" not in joined
    assert "do not feel fully right" not in joined


def test_hike_tomorrow_card_preserves_legs_instead_of_prescribing_leg_blocks() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 78,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 9.4h.",
                "HRV is above recent baseline: 92.1 ms vs 61.7 ms.",
                "Resting heart rate is steady: 60 bpm.",
            ],
        },
        "today": {
            "steps": 5200,
            "active_minutes": 44,
            "active_zone_minutes": 17,
            "hrv_ms": 92.1,
            "resting_heart_rate": 60,
            "sleep": {"asleep_hours": 9.4, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 17},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="train today",
        target_areas=[],
        constraints="I have a long hike tomorrow morning and want to train today, but I don't want tired legs.",
        duration_minutes=40,
    )

    exercises = " ".join(block["exercise"] for block in plan["exercise_blocks"]).lower()
    card_text = " ".join(
        [
            *plan["coach_response"]["session_blueprint"],
            *plan["coach_response"]["what_to_do"],
            *plan["avoid"],
            *plan["substitutions"],
        ]
    ).lower()

    assert plan["data_used"]["protect_lower_body"] is True
    assert plan["intent_context"]["primary_job"] == (
        "train today while preserving fresh legs for an upcoming walk, hike, sport, or long day"
    )
    assert "lower_body_protection" in plan["intent_context"]["constraint_roles"]
    assert "upper_body" in plan["intent_context"]["exercise_bias"]
    assert "legs" in plan["intent_context"]["do_not_treat_as_targets"]
    assert plan["rpe_cap"] <= 6
    assert "dead bug + side plank" in exercises
    assert "machine chest press" in exercises
    assert "chest-supported row" in exercises
    assert "leg press" not in exercises
    assert "goblet squat" not in exercises
    assert "hamstring curl" not in exercises
    assert "calf raise" not in exercises
    assert "protect your legs" in card_text
    assert "leg-heavy plan -> upper-body lift" in card_text


def test_active_workout_stops_for_dizziness_even_when_readiness_is_green() -> None:
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
        "available_signal_snapshot": {
            "status": "ok",
            "available_signal_ids": ["heart_rate_samples", "heart_rate_zones", "spo2"],
            "signals": [
                {
                    "id": "heart_rate_samples",
                    "label": "Heart rate samples",
                    "display": "142 bpm avg",
                    "coaching_use": "Use sample heart rate for recent effort context; use live user-reported HR for in-session decisions.",
                    "use_when": ["active_workout"],
                },
                {
                    "id": "heart_rate_zones",
                    "label": "Heart-rate zones",
                    "display": "cardio 18m, peak 2m",
                    "coaching_use": "More peak/cardio zone time should push the next session toward easy volume, technique, or strength away from fatigue.",
                    "use_when": ["active_workout"],
                },
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "96.5%",
                    "coaching_use": "Use low or unusual SpO2 with respiratory rate, resting HR, sleep, and symptoms to lower intensity or recommend caution.",
                    "use_when": ["breathing"],
                },
            ],
        },
    }

    guidance = active_workout_guidance(
        context=context,
        planned_activity="interval run",
        current_heart_rate_bpm=178,
        current_rpe=9,
        pain_level=2,
        symptoms="I feel dizzy and a little chest tight during the interval",
        elapsed_minutes=18,
        planned_duration_minutes=35,
    )

    assert guidance["decision"] == "stop_and_assess"
    assert guidance["safety_flags"]
    assert any("urgent care" in item for item in guidance["safety_flags"])
    assert any("Stop the set or interval now" in item for item in guidance["immediate_actions"])
    assert any("Live heart rate reported: 178 bpm" in item for item in guidance["evidence"])
    assert guidance["live_inputs"]["current_rpe"] == 9
    assert guidance["model_signal_context"]["status"] == "ok"
    assert any(
        "not direct band telemetry" in item
        for item in guidance["model_signal_context"]["decision_order"]
    )
    assert any(
        item["id"] == "heart_rate_samples"
        for item in guidance["model_signal_context"]["signal_groups"]["in_session_context"]
    )


def test_active_workout_downshifts_for_high_effort_without_urgent_symptoms() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 70,
            "label": "yellow",
            "recommendation": "Choose moderate cardio, technique, or strength without max efforts.",
            "evidence": ["Latest sleep is moderate at 6.8h."],
        },
        "today": {
            "steps": 5000,
            "active_minutes": 30,
            "active_zone_minutes": 20,
            "sleep": {"asleep_hours": 6.8, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 20},
        },
    }

    guidance = active_workout_guidance(
        context=context,
        planned_activity="strength circuit",
        current_heart_rate_bpm=165,
        current_rpe=9,
        pain_level=1,
        symptoms="no symptoms, just very hard",
        elapsed_minutes=28,
        planned_duration_minutes=45,
    )

    assert guidance["decision"] == "downshift_now"
    assert guidance["safety_flags"] == []
    assert any("Take 3-5 minutes easy" in item for item in guidance["immediate_actions"])
    assert any("Cut the next block" in item for item in guidance["modifications"])


def test_active_workout_stops_for_lightheadedness_even_with_no_pain() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 9.4h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 5000,
            "active_minutes": 30,
            "active_zone_minutes": 9,
            "sleep": {"asleep_hours": 9.4, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 9},
        },
    }

    guidance = active_workout_guidance(
        context=context,
        planned_activity="run",
        current_heart_rate_bpm=158,
        current_rpe=8,
        pain_level=0,
        symptoms="I feel a little lightheaded and more wiped than normal.",
        elapsed_minutes=18,
        planned_duration_minutes=40,
    )

    assert guidance["decision"] == "stop_and_assess"
    assert guidance["safety_flags"]
    assert any("Stop the set or interval now" in item for item in guidance["immediate_actions"])
    assert guidance["coach_response"]["short_answer"].startswith("Stop the hard part now")
    assert any(item["label"] == "HR" for item in guidance["coach_response"]["labels_explained"])


def test_active_workout_does_not_treat_negated_red_flags_as_symptoms() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 70,
            "label": "yellow",
            "recommendation": "Choose moderate cardio, technique, or strength without max efforts.",
            "evidence": ["Latest sleep is moderate at 6.8h."],
        },
        "today": {
            "steps": 5000,
            "active_minutes": 30,
            "active_zone_minutes": 20,
            "sleep": {"asleep_hours": 6.8, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 20},
        },
    }

    guidance = active_workout_guidance(
        context=context,
        planned_activity="strength circuit",
        current_heart_rate_bpm=165,
        current_rpe=9,
        pain_level=1,
        symptoms="no dizziness, no chest pain, no chest tightness, breathing feels normal",
        elapsed_minutes=24,
        planned_duration_minutes=45,
    )

    assert guidance["decision"] == "downshift_now"
    assert guidance["safety_flags"] == []
    assert any("Take 3-5 minutes easy" in item for item in guidance["immediate_actions"])


def test_active_workout_preserves_zero_pain_level() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 82,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.0h."],
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

    guidance = active_workout_guidance(
        context=context,
        planned_activity="easy treadmill run",
        current_heart_rate_bpm=142,
        current_rpe=6,
        pain_level=0,
        symptoms="no dizziness, no chest pain, no chest tightness, breathing feels normal",
        elapsed_minutes=18,
        planned_duration_minutes=35,
    )

    assert guidance["live_inputs"]["pain_level"] == 0
    assert guidance["safety_flags"] == []
    assert any("Live pain reported: 0/10." in item for item in guidance["evidence"])
    assert any("Hold steady" in item for item in guidance["coach_response"]["what_to_do"])
    assert any("RPE 6/10" in item for item in guidance["coach_response"]["what_to_do"])


def test_active_workout_translates_high_rpe_into_human_next_action() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.0h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 5200,
            "active_minutes": 36,
            "active_zone_minutes": 9,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 9},
        },
    }

    guidance = active_workout_guidance(
        context=context,
        planned_activity="active workout",
        current_heart_rate_bpm=158,
        current_rpe=8,
        pain_level=0,
        symptoms="no dizziness, no chest pain, breathing is controlled",
        elapsed_minutes=18,
        planned_duration_minutes=35,
    )

    coach = guidance["coach_response"]
    joined = " ".join([coach["short_answer"], *coach["what_to_do"], *coach["next_check"]])
    assert guidance["decision"] == "continue_controlled"
    assert "RPE 8/10 is already challenging" in coach["short_answer"]
    assert "only the next 3-5 minutes" in joined
    assert "back off one notch" in joined
    assert any(item["label"] == "AZM" for item in coach["labels_explained"])


def test_today_recommendation_uses_goal_checkins_and_history() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "data_freshness": {
            "freshness_level": "fresh",
            "needs_sync_before_time_sensitive_advice": False,
        },
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

    recommendation = workout_recommendation(
        context=context,
        goal={
            "goal": {
                "goal_type": "running",
                "target": "Run three easy days and one long run per week",
                "days_per_week": 4,
            }
        },
        checkins=[{"checkin": {"energy": 5, "soreness": 6, "stress": 4}}],
        workout_history={"status": "ok", "summary": {"workout_count": 1}},
    )

    assert recommendation["status"] == "ok"
    assert recommendation["intensity"] == "moderate"
    assert recommendation["rpe_cap"] == 7
    assert recommendation["subjective_context"]["soreness"] == 6
    assert recommendation["goal_context"]["remaining_sessions"] == 3
    assert recommendation["data_used"]["recent_workouts"] == 1
    assert any("3 session(s) remain" in item for item in recommendation["next_actions"])
    assert "soreness check-in is moderate" in recommendation["recommendation"]
    assert recommendation["context_gaps"] == []
    assert any("Latest energy check-in is 5/10." in item for item in recommendation["evidence"])
    assert any("Latest soreness check-in is 6/10." in item for item in recommendation["evidence"])
    assert any("Goal progress: 1/4 sessions logged; 3 remaining." in item for item in recommendation["evidence"])
    assert any("Recent workout history: 1 workout(s)" in item for item in recommendation["evidence"])
    assert any("Latest training load: 35 Active Zone Minutes" in item for item in recommendation["evidence"])


def test_today_recommendation_downshifts_for_current_not_one_hundred_feeling() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "data_freshness": {
            "freshness_level": "fresh",
            "needs_sync_before_time_sensitive_advice": False,
        },
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.3h.", "HRV is above recent baseline."],
        },
        "today": {
            "steps": 4200,
            "active_minutes": 28,
            "active_zone_minutes": 8,
            "hrv_ms": 62.0,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.3, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 8},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 62.0,
                "average_hrv_ms": 50.0,
                "latest_resting_heart_rate": 56,
                "average_resting_heart_rate": 58.0,
            }
        },
    }

    recommendation = workout_recommendation(
        context=context,
        current_feeling="I do not feel 100 percent but still want to work out today.",
    )

    assert recommendation["intensity"] == "moderate"
    assert recommendation["rpe_cap"] == 7
    assert recommendation["subjective_context"]["subjective_limiter"] is True
    assert recommendation["data_used"]["current_feeling"].startswith("I do not feel 100 percent")
    assert recommendation["recommendation"].startswith("Do a controlled, useful session")
    assert "do enough to feel better" in recommendation["recommendation"]
    assert "Train normally" not in recommendation["recommendation"]
    assert any("10-15 minutes" in item for item in recommendation["next_actions"])
    assert any("warm-up" in item.lower() for item in recommendation["stop_conditions"])
    assert any("subjective readiness caps" in item for item in recommendation["evidence"])
    assert any(
        "HRV (recovery stress signal) is 24% above recent average: 62 ms vs 50 ms." in item
        for item in recommendation["evidence"]
    )
    assert not any("HRV is above recent baseline" in item for item in recommendation["evidence"])
    assert any("free-text feeling was used" in item for item in recommendation["context_gaps"])


def test_today_recommendation_keeps_sync_first_when_data_is_stale() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-01",
        "activity_date": "2026-07-01",
        "recovery_date": "2026-07-01",
        "data_freshness": {
            "freshness_level": "stale",
            "needs_sync_before_time_sensitive_advice": True,
            "recommendation": "Run sync_latest_fitbit_data before time-sensitive workout decisions.",
        },
        "readiness": {
            "score": 72,
            "label": "yellow",
            "recommendation": "Choose moderate cardio, technique, or strength without max efforts.",
            "evidence": ["Data is not from today."],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 42,
            "active_zone_minutes": 20,
            "sleep": {"asleep_hours": 7.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-01", "active_zone_minutes": 20},
        },
    }

    recommendation = workout_recommendation(context=context)

    assert recommendation["intensity"] == "moderate"
    assert recommendation["next_actions"][0] == (
        "Sync latest Fitbit data before making a time-sensitive hard training decision."
    )
    assert recommendation["next_actions"][1] == "Do a controlled session: zone 2, technique, or submax strength."
    assert recommendation["data_used"]["freshness_level"] == "stale"
    assert any("No recent subjective check-in" in item for item in recommendation["context_gaps"])
    assert any("No coaching goal" in item for item in recommendation["context_gaps"])
    assert any("tell me your energy, soreness, stress, and pain" in item for item in recommendation["next_actions"])
    assert any("Data freshness is stale" in item for item in recommendation["evidence"])
    assert any("Latest sleep used for recommendation: 7.0h" in item for item in recommendation["evidence"])


def test_today_recommendation_downshifts_when_checkin_mentions_illness() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "data_freshness": {
            "freshness_level": "fresh",
            "needs_sync_before_time_sensitive_advice": False,
        },
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.1h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 44,
            "active_zone_minutes": 18,
            "hrv_ms": 62.0,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.1, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 18},
        },
    }

    recommendation = workout_recommendation(
        context=context,
        goal={"goal": {"target": "Lift three days this week", "days_per_week": 3}},
        checkins=[
            {
                "checkin": {
                    "energy": 7,
                    "soreness": 2,
                    "stress": 3,
                    "notes": "Woke up with fever, chills, and a sore throat.",
                }
            }
        ],
        workout_history={"status": "ok", "summary": {"workout_count": 1}},
    )

    assert recommendation["intensity"] == "easy"
    assert recommendation["rpe_cap"] <= 4
    assert "Illness signs override normal training pressure" in recommendation["recommendation"]
    assert recommendation["next_actions"][0].startswith("Rest today")
    assert any("sick" in item or "feverish" in item for item in recommendation["avoid"])
    assert recommendation["subjective_context"]["illness_flags"]
    assert recommendation["data_used"]["illness_flags"]
    assert any("Illness symptoms" in item for item in recommendation["evidence"])


def test_current_feeling_overrides_old_illness_checkin_for_day_plan() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "data_freshness": {
            "freshness_level": "fresh",
            "needs_sync_before_time_sensitive_advice": False,
        },
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.1h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 44,
            "active_zone_minutes": 18,
            "hrv_ms": 62.0,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.1, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 18},
        },
    }

    recommendation = workout_recommendation(
        context=context,
        current_feeling="I feel normal today and have 35 minutes.",
        checkins=[
            {
                "checkin": {
                    "energy": 7,
                    "soreness": 2,
                    "stress": 3,
                    "notes": "Earlier test note mentioned fever and chills.",
                }
            }
        ],
    )

    assert recommendation["intensity"] == "moderate-to-hard"
    assert recommendation["rpe_cap"] == 8
    assert recommendation["data_used"]["illness_flags"] == []
    assert recommendation["data_used"]["checkin_illness_flags_used"] is False
    assert "training is available today" in recommendation["coach_response"]["short_answer"].lower()


def test_workout_plan_downshifts_for_illness_even_with_green_readiness() -> None:
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
            "active_zone_minutes": 20,
            "hrv_ms": 48.5,
            "resting_heart_rate": 57,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 20},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="upper body lift",
        target_areas=["chest", "back"],
        constraints="No chest pain and no dizziness, but I have fever and cold symptoms today.",
        duration_minutes=45,
    )

    assert plan["recommended_intensity"] == "easy"
    assert plan["rpe_cap"] <= 4
    assert "Illness signs should override" in plan["summary"]
    assert plan["data_used"]["illness_flags"]
    assert any("illness" in item.lower() for item in plan["limiting_factors"])
    assert any("Do not train hard" in item for item in plan["session_guidance"])
    assert any("Sweat-it-out" in item for item in plan["avoid"])


def test_workout_plan_makes_not_one_hundred_day_a_minimum_useful_session() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 86,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.2h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 5300,
            "active_minutes": 35,
            "active_zone_minutes": 12,
            "hrv_ms": 64.0,
            "resting_heart_rate": 55,
            "sleep": {"asleep_hours": 8.2, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 12},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="general strength and cardio",
        target_areas=[],
        constraints="I do not feel 100 percent but still want a useful session.",
        duration_minutes=30,
    )

    assert plan["recommended_intensity"] == "moderate"
    assert plan["rpe_cap"] == 7
    assert plan["data_used"]["subjective_limiter"] is True
    assert any("minimum useful session" in item for item in plan["focus"])
    assert any("pass/fail readiness screen" in item for item in plan["session_guidance"])
    assert any("warm-up" in item.lower() for item in plan["stop_conditions"])
    assert any("not feel 100%" in item for item in plan["limiting_factors"])


def test_generic_workout_payload_stays_human_readable_for_cached_cards() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 9.4h.",
                "HRV is above recent baseline: 92.1 ms vs 31.3 ms.",
                "Resting heart rate is steady: 60 bpm.",
            ],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 44,
            "active_zone_minutes": 18,
            "hrv_ms": 92.1,
            "resting_heart_rate": 60,
            "sleep": {"asleep_hours": 9.4, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-02", "active_zone_minutes": 9},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 92.1,
                "average_hrv_ms": 61.7,
                "latest_resting_heart_rate": 60,
                "average_resting_heart_rate": 62,
            }
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="general workout",
        target_areas=[],
        constraints="I do not feel 100 percent but still want a useful session.",
        duration_minutes=45,
    )

    assert plan["planned_activity"] == "Useful Controlled Workout"
    assert plan["planned_activity_raw"] == "general workout"
    assert "Useful Controlled Workout" in plan["summary"]
    assert "not-100% day" in plan["coach_response"]["short_answer"]
    assert any(item["label"] == "HRV" for item in plan["coach_response"]["labels_explained"])
    assert any(item["label"] == "RPE" for item in plan["coach_response"]["labels_explained"])
    assert plan["coach_response"]["session_blueprint"]
    assert any("RPE <=" in item for item in plan["coach_response"]["session_blueprint"])
    assert "The useful read:" in plan["coach_response"]["data_story"]
    assert any("RPE (how hard it feels)" in item for item in plan["coach_response"]["what_to_do"])
    assert any("recovery stress signal" in item for item in plan["coach_response"]["why"])
    assert any("HRV (recovery stress signal)" in item for item in plan["limiting_factors"])
    assert any(
        "Resting HR (resting heart rate; heart stress at rest) is below recent average: 60 bpm vs 62 bpm." in item
        for item in plan["limiting_factors"]
    )
    assert not any("6 bpm vs 62 bpm" in item for item in plan["limiting_factors"])


def test_today_recommendation_returns_human_coach_response_without_losing_labels() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 8.3h.",
                "HRV is above recent baseline.",
                "Resting heart rate is steady.",
            ],
        },
        "today": {
            "steps": 6400,
            "active_minutes": 42,
            "active_zone_minutes": 10,
            "hrv_ms": 62,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.3, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 10},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 62,
                "average_hrv_ms": 50,
                "latest_resting_heart_rate": 56,
                "average_resting_heart_rate": 58,
            }
        },
        "available_signal_snapshot": {
            "status": "ok",
            "available_signal_ids": [
                "spo2",
                "respiratory_rate",
                "sleep_temperature",
                "heart_rate_zones",
                "steps",
                "vo2_max",
            ],
            "signals": [
                {
                    "id": "spo2",
                    "label": "SpO2 / oxygen saturation",
                    "display": "96.5%",
                    "coaching_use": "Use low or unusual SpO2 with respiratory rate, resting HR, sleep, and symptoms to lower intensity or recommend caution.",
                },
                {
                    "id": "respiratory_rate",
                    "label": "Respiratory rate",
                    "display": "16.6 breaths/min",
                    "coaching_use": "Use elevated or unusual respiratory rate as a reason to cap intensity, especially with symptoms or low sleep.",
                },
                {
                    "id": "sleep_temperature",
                    "label": "Sleep temperature",
                    "display": "+0.45 C vs baseline",
                    "coaching_use": "Use an elevated deviation as context to keep training controlled; do not diagnose from it.",
                },
                {
                    "id": "heart_rate_zones",
                    "label": "Heart-rate zones",
                    "display": "fat burn 12m, cardio 4m",
                    "coaching_use": "More peak/cardio zone time should push the next session toward easy volume, technique, or strength away from fatigue.",
                },
                {
                    "id": "steps",
                    "label": "Steps",
                    "display": "6,400 steps",
                    "window_summary": {
                        "display": "18,897 steps across 4 recorded days in the 14-day lookback",
                        "average_display": "4,724/day across recorded step days",
                    },
                    "coaching_use": "Use high step volume as fatigue context; low steps alone do not mean the user needs hard training.",
                },
                {
                    "id": "vo2_max",
                    "label": "VO2 max",
                    "display": "44.4 ml/kg/min",
                    "coaching_use": "Use it for endurance planning and progress, not as the main same-day train-or-rest signal.",
                },
            ],
        },
    }

    recommendation = workout_recommendation(
        context=context,
        current_feeling="I feel a little off today but still want to work out.",
    )

    assert recommendation["intensity"] == "moderate"
    assert "let the first 10-15 minutes decide" in recommendation["coach_response"]["short_answer"]
    assert any(item["label"] == "Readiness" for item in recommendation["coach_response"]["labels_explained"])
    assert any(item["label"] == "AZM" for item in recommendation["coach_response"]["labels_explained"])
    assert any(item["label"] == "SpO2" for item in recommendation["coach_response"]["labels_explained"])
    assert any(item["label"] == "Respiratory rate" for item in recommendation["coach_response"]["labels_explained"])
    assert any(item["label"] == "Sleep temperature" for item in recommendation["coach_response"]["labels_explained"])
    assert any(item["label"] == "VO2 max" for item in recommendation["coach_response"]["labels_explained"])
    assert any("10-15 minutes" in item for item in recommendation["coach_response"]["session_blueprint"])
    assert "current body feel caps the ceiling" in recommendation["coach_response"]["data_story"]
    assert "breathing or oxygen context should cap intensity" not in recommendation["coach_response"]["data_story"]
    assert any("RPE (how hard it feels)" in item for item in recommendation["coach_response"]["what_to_do"])
    assert any("HRV (recovery stress signal)" in item for item in recommendation["coach_response"]["why"])
    assert any("Resting HR" in item for item in recommendation["coach_response"]["why"])
    assert any("SpO2" in item for item in recommendation["coach_response"]["why"])
    assert any("Respiratory rate" in item for item in recommendation["coach_response"]["why"])
    assert any("Sleep temperature" in item for item in recommendation["coach_response"]["why"])
    assert any("18,897 steps across 4 recorded days" in item for item in recommendation["coach_response"]["why"])
    assert recommendation["data_used"]["available_signal_ids"] == context["available_signal_snapshot"]["available_signal_ids"]
    assert recommendation["available_signal_snapshot"]["status"] == "ok"
    assert recommendation["training_decision"]["hard_training"] == "conditional"
    assert recommendation["training_decision"]["rpe_cap"] == 7
    assert any("breathing" in item.lower() or "oxygen" in item.lower() for item in recommendation["training_decision"]["reasons_for"])
    assert recommendation["model_signal_context"]["status"] == "ok"
    assert any(
        item["id"] == "vo2_max"
        for item in recommendation["model_signal_context"]["signal_groups"]["capacity_progress"]
    )
    assert any(
        "normal SpO2" in item
        for item in recommendation["model_signal_context"]["answer_contract"]
    )
    assert any("I only have 30 minutes" in item for item in recommendation["coach_response"]["realistic_follow_ups"])
    assert any("If I still feel off" in item for item in recommendation["coach_response"]["realistic_follow_ups"])


def test_today_recommendation_for_normal_green_day_does_not_assume_off_day() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 86,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": [
                "Latest sleep is strong at 8.1h.",
                "HRV is above recent baseline.",
                "Resting heart rate is steady.",
            ],
        },
        "today": {
            "steps": 7200,
            "active_minutes": 46,
            "active_zone_minutes": 18,
            "hrv_ms": 64,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.1, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 18},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 64,
                "average_hrv_ms": 54,
                "latest_resting_heart_rate": 56,
                "average_resting_heart_rate": 58,
            }
        },
    }

    recommendation = workout_recommendation(context=context)
    coach = recommendation["coach_response"]
    joined = " ".join(
        [
            coach["short_answer"],
            coach["data_story"],
            *coach["realistic_follow_ups"],
            *coach["session_blueprint"],
        ]
    ).lower()

    assert recommendation["intensity"] == "moderate-to-hard"
    assert "training is available today" in coach["short_answer"].lower()
    assert "feel off" not in joined
    assert "not-100" not in joined
    assert "do not feel fully right" not in joined
    assert any("Can I train hard today" in item for item in coach["realistic_follow_ups"])
    assert any("I only have 30 minutes" in item for item in coach["realistic_follow_ups"])
    assert any(item["label"] == "Readiness" for item in coach["labels_explained"])
    assert any("HRV (recovery stress signal)" in item for item in coach["why"])

    positive_feeling = workout_recommendation(
        context=context,
        current_feeling="I feel good and want to run today.",
    )
    positive_story = positive_feeling["coach_response"]["data_story"]
    assert "if the warm-up matches how good or normal you feel" in positive_feeling["coach_response"]["short_answer"]
    assert "current body feel caps the ceiling" not in positive_story
    assert "sleep supports training" in positive_story

    negated_feeling = workout_recommendation(
        context=context,
        current_feeling="I am not saying I feel off or sore. I just want a normal data-based plan.",
    )
    negated_coach = negated_feeling["coach_response"]
    negated_joined = " ".join(
        [
            negated_coach["short_answer"],
            negated_coach["data_story"],
            *negated_coach["session_blueprint"],
        ]
    ).lower()
    assert negated_feeling["subjective_context"]["subjective_limiter"] is False
    assert "training is available today" in negated_coach["short_answer"].lower()
    assert "current body feel caps the ceiling" not in negated_joined
    assert "do not feel fully right" not in negated_joined


def test_today_recommendation_for_busy_normal_day_is_compact_without_off_day_bias() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "data_freshness": {
            "freshness_level": "fresh",
            "needs_sync_before_time_sensitive_advice": False,
        },
        "readiness": {
            "score": 68,
            "label": "yellow",
            "recommendation": "Choose moderate cardio, technique, or strength without max efforts.",
            "evidence": [
                "Latest sleep is moderate at 6.7h.",
                "HRV is slightly below recent baseline.",
                "Resting heart rate is slightly elevated.",
            ],
        },
        "today": {
            "steps": 5400,
            "active_minutes": 32,
            "active_zone_minutes": 18,
            "hrv_ms": 47,
            "resting_heart_rate": 60,
            "sleep": {"asleep_hours": 6.7, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 18},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 47,
                "average_hrv_ms": 52,
                "latest_resting_heart_rate": 60,
                "average_resting_heart_rate": 57,
            }
        },
    }

    recommendation = workout_recommendation(
        context=context,
        current_feeling="I feel normal today and only have 20 minutes after work.",
    )
    coach = recommendation["coach_response"]
    joined = " ".join([coach["short_answer"], *coach["session_blueprint"], *coach["what_to_do"]]).lower()

    assert recommendation["intensity"] == "moderate"
    assert recommendation["data_used"]["time_limit_minutes"] == 20
    assert "focused controlled session" in coach["short_answer"]
    assert "20 minutes" in coach["short_answer"]
    assert any("3-5 minute gradual warm-up" in item for item in coach["session_blueprint"])
    assert any("12-18 minutes" in item for item in coach["session_blueprint"])
    assert any("Use the 20 minutes" in item for item in recommendation["next_actions"])
    assert "feel better" not in joined
    assert "survive" not in joined
    assert "not-100" not in joined
    assert "do not feel fully right" not in joined
    assert any(item["label"] == "RPE" for item in coach["labels_explained"])
    assert any(item["label"] == "HRV" for item in coach["labels_explained"])


def test_today_recommendation_downshifts_stale_green_data_before_hard_work() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "data_freshness": {
            "freshness_level": "stale",
            "freshness_label": "sync recommended",
            "needs_sync_before_time_sensitive_advice": True,
            "recommendation": "Run sync_latest_fitbit_data before time-sensitive workout decisions.",
        },
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable.",
            "evidence": [
                "Latest sleep is strong at 8.0h.",
                "HRV is above recent baseline.",
                "Resting heart rate is steady.",
            ],
        },
        "today": {
            "steps": 5200,
            "active_minutes": 36,
            "active_zone_minutes": 12,
            "hrv_ms": 60,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 12},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 60,
                "average_hrv_ms": 52,
                "latest_resting_heart_rate": 56,
                "average_resting_heart_rate": 59,
            }
        },
    }

    recommendation = workout_recommendation(
        context=context,
        current_feeling="I slept great, feel good, and only have 20 minutes after work.",
    )

    assert recommendation["intensity"] == "moderate"
    assert recommendation["rpe_cap"] == 7
    assert recommendation["coach_response"]["short_answer"].startswith("Sync latest Fitbit data")
    assert any("RPE <= 7/10" in item for item in recommendation["coach_response"]["session_blueprint"])
    assert any("All-out intervals" in item for item in recommendation["avoid"])


def test_today_recommendation_uses_high_steps_as_leg_load_context() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable.",
            "evidence": [
                "Latest sleep is strong at 8.0h.",
                "HRV is above recent baseline.",
                "Resting heart rate is steady.",
            ],
        },
        "today": {
            "steps": 18500,
            "active_minutes": 120,
            "active_zone_minutes": 8,
            "hrv_ms": 60,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 8},
        },
        "sections": {
            "heart": {
                "latest_hrv_ms": 60,
                "average_hrv_ms": 52,
                "latest_resting_heart_rate": 56,
                "average_resting_heart_rate": 59,
            }
        },
    }

    recommendation = workout_recommendation(
        context=context,
        current_feeling="I walked a ton today. Does that change my lift tonight?",
    )
    coach = recommendation["coach_response"]
    joined = " ".join([coach["short_answer"], coach["data_story"], *coach["why"], *recommendation["avoid"]]).lower()

    assert recommendation["intensity"] == "moderate"
    assert recommendation["rpe_cap"] == 7
    assert "movement volume already adds load" in coach["short_answer"]
    assert "movement volume may affect legs" in coach["data_story"]
    assert "18,500 steps on 2026-07-03 so far" in " ".join(coach["why"])
    assert "not a standalone recovery score" in joined
    assert "hard lower-body work" in joined


def test_planned_workout_uses_high_movement_as_leg_load_context() -> None:
    context = {
        "status": "ok",
        "latest_date": "2026-07-03",
        "activity_date": "2026-07-03",
        "recovery_date": "2026-07-03",
        "readiness": {
            "score": 84,
            "label": "green",
            "recommendation": "A normal training day is reasonable if you feel good.",
            "evidence": ["Latest sleep is strong at 8.0h.", "Resting heart rate is steady."],
        },
        "today": {
            "steps": 18500,
            "active_minutes": 120,
            "active_zone_minutes": 8,
            "hrv_ms": 60,
            "resting_heart_rate": 56,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 8},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="upper body lift",
        target_areas=["chest", "back"],
        constraints="I walked a lot today and my legs feel okay.",
        duration_minutes=45,
    )
    joined = " ".join([plan["summary"], *plan["focus"], *plan["session_guidance"], *plan["avoid"]]).lower()

    assert plan["recommended_intensity"] == "moderate"
    assert plan["rpe_cap"] == 7
    assert plan["data_used"]["stated_high_movement"] is True
    assert "18,500 steps on 2026-07-03 so far" in " ".join(plan["limiting_factors"])
    assert "leg/load context" in joined
    assert "hard lower-body work" in joined
    assert any("upper-body lift" in item for item in plan["substitutions"])


def test_workout_plan_does_not_flag_negated_illness_terms() -> None:
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
            "active_zone_minutes": 20,
            "hrv_ms": 48.5,
            "resting_heart_rate": 57,
            "sleep": {"asleep_hours": 8.0, "sessions_count": 1},
            "latest_training_load": {"date": "2026-07-03", "active_zone_minutes": 20},
        },
    }

    plan = workout_plan_for_activity(
        context=context,
        planned_activity="upper body lift",
        target_areas=["chest", "back"],
        constraints="No fever, no chills, no sore throat, and no dizziness.",
        duration_minutes=45,
    )

    assert plan["recommended_intensity"] == "moderate-to-hard"
    assert plan["rpe_cap"] == 8
    assert plan["data_used"]["illness_flags"] == []
