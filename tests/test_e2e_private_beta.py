from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.crypto import generate_key
from app.db import dumps
from app.google_health import DataTypeSpec
from app.main import ServerBundle, create_server
from app.settings import Settings
from app.time_utils import iso_now


def make_bundle(tmp_path) -> ServerBundle:
    return create_server(
        Settings(
            public_base_url="http://localhost:8787",
            database_url=f"sqlite:///{tmp_path / 'e2e.sqlite3'}",
            token_encryption_key=generate_key(),
            google_client_id="fake-google-client",
            google_client_secret="fake-google-secret",
            google_redirect_uri="http://localhost:8787/oauth/callback/google",
        )
    )


def pkce_pair() -> tuple[str, str]:
    verifier = "realistic-private-beta-verifier"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def redirect_param(location: str, name: str) -> str:
    values = parse_qs(urlparse(location).query).get(name)
    assert values, f"Missing {name} in redirect: {location}"
    return values[0]


async def mcp_request(
    client: httpx.AsyncClient,
    access_token: str,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any] | None:
    response = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert response.status_code in {200, 202}, response.text
    return response.json() if response.text else None


def tool_content(response: dict[str, Any]) -> dict[str, Any]:
    return response["result"]["structuredContent"]


class FakeGoogleHealth:
    def __init__(self) -> None:
        self.requested_specs: list[str] = []
        self.requested_windows: list[tuple[str, str, str]] = []
        self.requested_rollups: list[tuple[str, str, str]] = []
        self.today = datetime.now(UTC).date().isoformat()

    async def list_data_points(
        self,
        access_token: str,
        spec: DataTypeSpec,
        start_time: str,
        end_time: str,
        timeout_seconds: int = 8,
        max_pages: int = 8,
    ) -> list[dict[str, Any]]:
        assert access_token == "fake-google-access"
        assert start_time < end_time
        assert timeout_seconds >= 1
        assert max_pages >= 1
        self.requested_specs.append(spec.id)
        self.requested_windows.append((spec.id, start_time, end_time))
        day = self.today
        if spec.id == "steps":
            return [
                {
                    "name": "steps-realistic",
                    "steps": {"count": 9200},
                    "interval": {"startTime": f"{day}T09:00:00Z", "endTime": f"{day}T18:00:00Z"},
                }
            ]
        if spec.id == "active-zone-minutes":
            return [
                {
                    "name": "azm-realistic",
                    "activeZoneMinutes": {"activeZoneMinutes": 38},
                    "interval": {"startTime": f"{day}T17:00:00Z", "endTime": f"{day}T18:00:00Z"},
                }
            ]
        if spec.id == "active-minutes":
            return [
                {
                    "name": "active-minutes-realistic",
                    "activeMinutes": {
                        "activeMinutesByActivityLevel": [
                            {"activityLevel": "MODERATE", "activeMinutes": 42},
                            {"activityLevel": "VIGOROUS", "activeMinutes": 12},
                        ]
                    },
                    "interval": {"startTime": f"{day}T17:00:00Z", "endTime": f"{day}T18:00:00Z"},
                }
            ]
        if spec.id == "distance":
            return [
                {
                    "name": "distance-realistic",
                    "distance": {"millimeters": 7_100_000},
                    "interval": {"startTime": f"{day}T09:00:00Z", "endTime": f"{day}T18:00:00Z"},
                }
            ]
        if spec.id == "sleep":
            return [
                {
                    "name": "sleep-realistic",
                    "sleep": {
                        "interval": {
                            "startTime": f"{day}T00:10:00Z",
                            "endTime": f"{day}T07:40:00Z",
                        },
                        "stages": [
                            {
                                "type": "DEEP",
                                "startTime": f"{day}T01:00:00Z",
                                "endTime": f"{day}T02:05:00Z",
                            },
                            {
                                "type": "REM",
                                "startTime": f"{day}T05:30:00Z",
                                "endTime": f"{day}T06:20:00Z",
                            },
                        ],
                    },
                }
            ]
        if spec.id == "heart-rate":
            return [
                {
                    "name": "hr-realistic-1",
                    "heartRate": {"beatsPerMinute": 62},
                    "sampleTime": {"physicalTime": f"{day}T08:00:00Z"},
                },
                {
                    "name": "hr-realistic-2",
                    "heartRate": {"beatsPerMinute": 138},
                    "sampleTime": {"physicalTime": f"{day}T17:30:00Z"},
                },
            ]
        if spec.id == "daily-resting-heart-rate":
            year, month, day_num = [int(part) for part in day.split("-")]
            return [
                {
                    "name": "rhr-realistic",
                    "dailyRestingHeartRate": {"beatsPerMinute": 57},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "daily-heart-rate-variability":
            year, month, day_num = [int(part) for part in day.split("-")]
            return [
                {
                    "name": "hrv-realistic",
                    "dailyHeartRateVariability": {
                        "averageHeartRateVariabilityMilliseconds": 48.5
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "daily-oxygen-saturation":
            year, month, day_num = [int(part) for part in day.split("-")]
            return [
                {
                    "name": "spo2-realistic",
                    "dailyOxygenSaturation": {"averagePercentage": 97.2},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "daily-respiratory-rate":
            year, month, day_num = [int(part) for part in day.split("-")]
            return [
                {
                    "name": "resp-realistic",
                    "dailyRespiratoryRate": {"breathsPerMinute": 16.1},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "daily-sleep-temperature-derivations":
            year, month, day_num = [int(part) for part in day.split("-")]
            return [
                {
                    "name": "sleep-temp-realistic",
                    "dailySleepTemperatureDerivations": {
                        "nightlyTemperatureCelsius": 36.13,
                        "baselineTemperatureCelsius": 36.0,
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "daily-vo2-max":
            year, month, day_num = [int(part) for part in day.split("-")]
            return [
                {
                    "name": "vo2-realistic",
                    "dailyVo2Max": {
                        "vo2Max": 44.4,
                        "cardioFitnessLevel": "GOOD",
                        "estimated": False,
                    },
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "exercise":
            return [
                {
                    "name": "exercise-realistic",
                    "exercise": {
                        "exerciseType": "RUNNING",
                        "displayName": "Easy run",
                        "interval": {
                            "startTime": f"{day}T17:00:00Z",
                            "endTime": f"{day}T17:40:00Z",
                        },
                        "activeDuration": "2400s",
                        "metricsSummary": {"averageHeartRateBeatsPerMinute": 132},
                    },
                }
            ]
        return []

    async def daily_rollup(
        self,
        access_token: str,
        spec: DataTypeSpec,
        start_date: str,
        end_date: str,
        timeout_seconds: int = 8,
    ) -> list[dict[str, Any]]:
        assert access_token == "fake-google-access"
        assert start_date < end_date
        assert timeout_seconds >= 1
        self.requested_specs.append(spec.id)
        self.requested_rollups.append((spec.id, start_date, end_date))
        year, month, day_num = [int(part) for part in self.today.split("-")]
        if spec.id == "total-calories":
            return [
                {
                    "name": "total-calories-realistic",
                    "totalCalories": {"kcalSum": 2350},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        if spec.id == "floors":
            return [
                {
                    "name": "floors-realistic",
                    "floors": {"count": 7},
                    "date": {"year": year, "month": month, "day": day_num},
                }
            ]
        return []


@pytest.mark.asyncio
async def test_private_beta_oauth_mcp_sync_and_coaching_flow(tmp_path, monkeypatch) -> None:
    bundle = make_bundle(tmp_path)
    fake_health = FakeGoogleHealth()
    bundle.health_store.google = fake_health

    async def fake_exchange_google_code(code: str) -> dict[str, Any]:
        assert code == "google-code"
        return {
            "access_token": "fake-google-access",
            "refresh_token": "fake-google-refresh",
            "expires_in": 3600,
            "scope": " ".join(bundle.settings.google_scopes),
        }

    async def fake_load_google_user_info(access_token: str) -> dict[str, Any]:
        assert access_token == "fake-google-access"
        return {"email": "tester@example.com", "sub": "google-subject"}

    monkeypatch.setattr(bundle.auth_service, "_exchange_google_code", fake_exchange_google_code)
    monkeypatch.setattr(bundle.auth_service, "_load_google_user_info", fake_load_google_user_info)

    verifier, challenge = pkce_pair()
    transport = httpx.ASGITransport(app=bundle.app)

    async with bundle.app.router.lifespan_context(bundle.app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost:8787",
            follow_redirects=False,
        ) as client:
            registration = await client.post(
                "/oauth/register",
                json={
                    "client_name": "ChatGPT private beta connector",
                    "redirect_uris": ["https://chatgpt.com/connector/oauth/test-callback"],
                    "token_endpoint_auth_method": "none",
                },
            )
            assert registration.status_code == 201
            client_id = registration.json()["client_id"]

            authorize = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": client_id,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/test-callback",
                    "response_type": "code",
                    "scope": "health.read",
                    "state": "chatgpt-state",
                    "resource": "http://localhost:8787",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            )
            assert authorize.status_code == 307
            google_location = authorize.headers["location"]
            assert google_location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
            assert redirect_param(google_location, "client_id") == "fake-google-client"
            assert "googlehealth.nutrition" not in redirect_param(google_location, "scope")

            callback = await client.get(
                "/oauth/callback/google",
                params={"code": "google-code", "state": redirect_param(google_location, "state")},
            )
            assert callback.status_code == 307
            app_code = redirect_param(callback.headers["location"], "code")
            assert redirect_param(callback.headers["location"], "state") == "chatgpt-state"

            token = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": app_code,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/test-callback",
                    "code_verifier": verifier,
                    "resource": "http://localhost:8787",
                },
            )
            assert token.status_code == 200
            access_token = token.json()["access_token"]
            refresh_token = token.json()["refresh_token"]
            assert token.json()["scope"] == "health.read"

            replay = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": app_code,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/test-callback",
                    "code_verifier": verifier,
                },
            )
            assert replay.status_code == 400
            assert replay.json()["error"] == "invalid_grant"

            initialize = await mcp_request(
                client,
                access_token,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ChatGPT E2E", "version": "test"},
                },
                1,
            )
            assert initialize
            assert initialize["result"]["serverInfo"]["name"] == "Mehair Coach"

            initialized = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json, text/event-stream",
                },
            )
            assert initialized.status_code == 202

            tools = await mcp_request(client, access_token, "tools/list", request_id=2)
            tool_names = {item["name"] for item in tools["result"]["tools"]}
            assert "sync_latest_fitbit_data" in tool_names
            assert "sync_and_get_health_overview" in tool_names
            assert "get_today_context" in tool_names
            assert "get_health_overview" in tool_names
            assert "plan_workout_with_health_context" in tool_names
            assert "guide_active_workout" in tool_names
            assert "get_health_question_clues" in tool_names
            assert "get_recovery_signal_comparison" in tool_names
            assert "list_available_health_metrics" in tool_names
            assert "query_health_metrics" in tool_names

            after_connect_context = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "get_today_context", "arguments": {}},
                    3,
                )
            )
            assert after_connect_context["status"] == "ok"
            assert after_connect_context["today"]["steps"] == 9200
            assert after_connect_context["readiness"]["label"] == "green"
            bootstrap_records = after_connect_context["data_freshness"]["records"]
            assert bootstrap_records >= 10
            assert "food" not in fake_health.requested_specs
            assert "heart-rate" in fake_health.requested_specs
            assert "exercise" in fake_health.requested_specs
            assert "time-in-heart-rate-zone" in fake_health.requested_specs
            assert "daily-oxygen-saturation" in fake_health.requested_specs

            sync = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "sync_latest_fitbit_data", "arguments": {}},
                    4,
                )
            )
            assert sync["status"] == "ok"
            assert sync["sync_skipped"] is True
            assert sync["records_upserted"] == 0
            assert sync["sync_window"]["mode"] == "recent_skip"
            assert sync["context"]["today"]["steps"] == 9200
            assert sync["readiness"]["label"] == "green"

            skipped_sync = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "sync_latest_fitbit_data", "arguments": {}},
                    40,
                )
            )
            assert skipped_sync["status"] == "ok"
            assert skipped_sync["sync_skipped"] is True
            assert skipped_sync["sync_window"]["mode"] == "recent_skip"
            assert skipped_sync["records_upserted"] == 0
            assert skipped_sync["context"]["today"]["steps"] == 9200

            incremental_sync = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "sync_latest_fitbit_data", "arguments": {"force": True}},
                    41,
                )
            )
            assert incremental_sync["status"] == "ok"
            assert incremental_sync["partial_sync"] is False
            assert incremental_sync["metrics_deferred"] == []
            assert incremental_sync["sync_diagnostics"]["coverage_summary"]["usable_for_today_plan"] is True
            assert incremental_sync["sync_window"]["mode"] == "incremental"
            assert incremental_sync["sync_window"]["lookback_days"] <= 2
            assert incremental_sync["sync_window"]["configured_overlap_hours"] == 2
            assert incremental_sync["sync_window"]["existing_records"] >= bootstrap_records

            fresh_overview = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "sync_and_get_health_overview", "arguments": {"days": 7}},
                    401,
                )
            )
            assert fresh_overview["status"] == "ok"
            assert fresh_overview["overview_type"] == "health_overview"
            assert fresh_overview["sections"]["activity"]["totals"]["steps"] == 9200
            assert fresh_overview["fresh_sync"]["status"] == "ok"
            assert fresh_overview["fresh_sync"]["sync_skipped"] is True
            assert fresh_overview["fresh_sync"]["sync_window"]["mode"] == "recent_skip"
            assert fresh_overview["fresh_sync"]["records_upserted"] == 0

            catalog = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "list_available_health_metrics", "arguments": {}},
                    41,
                )
            )
            assert catalog["supported_metric_count"] >= 20
            assert any(item["id"] == "heart-rate" for item in catalog["metrics"])
            assert "food" in catalog["excluded_categories"]

            queried = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "query_health_metrics",
                        "arguments": {"metrics": ["steps", "sleep"], "days": 1},
                    },
                    42,
                )
            )
            assert queried["status"] == "ok"
            assert queried["metrics"]["steps"]["daily"][-1]["steps"] == 9200
            assert queried["metrics"]["sleep"]["daily"][-1]["sleep"]["duration_hours"] == 7.5

            today = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "get_today_context", "arguments": {}},
                    5,
                )
            )
            assert today["status"] == "ok"
            assert today["today"]["steps"] == 9200
            assert today["today"]["sleep"]["duration_hours"] == 7.5
            assert today["today"]["resting_heart_rate"] == 57
            assert today["readiness"]["label"] == "green"

            recommendation = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "recommend_workout_today", "arguments": {}},
                    6,
                )
            )
            assert recommendation["status"] == "ok"
            assert recommendation["intensity"] == "moderate-to-hard"
            assert recommendation["today"]["steps"] == 9200
            assert recommendation["activity_date"] == today["activity_date"]
            assert any("No recent subjective check-in" in item for item in recommendation["context_gaps"])
            assert any("No coaching goal" in item for item in recommendation["context_gaps"])
            assert any("tell me your energy" in item for item in recommendation["next_actions"])
            assert "medical advice" in recommendation["safety_note"]

            active_guidance = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "guide_active_workout",
                        "arguments": {
                            "planned_activity": "interval run",
                            "current_heart_rate_bpm": 178,
                            "current_rpe": 9,
                            "pain_level": 2,
                            "symptoms": "I feel dizzy during the interval",
                            "elapsed_minutes": 18,
                            "planned_duration_minutes": 35,
                        },
                    },
                    601,
                )
            )
            assert active_guidance["status"] == "ok"
            assert active_guidance["decision"] == "stop_and_assess"
            assert active_guidance["safety_flags"]
            assert any("Stop the set or interval now" in item for item in active_guidance["immediate_actions"])

            sleep = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "get_sleep_analysis", "arguments": {"days": 7}},
                    7,
                )
            )
            assert sleep["latest"]["stages_minutes"]["deep"] == 65.0

            goal = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "set_goal",
                        "arguments": {
                            "goal_type": "running",
                            "target": "Run three easy days and one long run per week",
                            "days_per_week": 4,
                        },
                    },
                    8,
                )
            )
            assert goal["status"] == "ok"
            assert goal["goal"]["days_per_week"] == 4

            checkin = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "log_checkin",
                        "arguments": {
                            "energy": 5,
                            "soreness": 6,
                            "stress": 4,
                            "notes": "left lower back soreness after squash",
                        },
                    },
                    9,
                )
            )
            assert checkin["status"] == "ok"
            assert checkin["checkin"]["soreness"] == 6

            overview = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "get_health_overview", "arguments": {"days": 7}},
                    10,
                )
            )
            assert overview["status"] == "ok"
            assert overview["overview_type"] == "health_overview"
            assert overview["sections"]["activity"]["totals"]["steps"] == 9200
            assert overview["sections"]["sleep"]["latest_asleep_hours"] == 7.5
            assert overview["sections"]["heart"]["latest_hrv_ms"] == 48.5
            assert overview["sections"]["workouts"]["workout_count"] == 1
            assert overview["available_signal_snapshot"]["status"] == "ok"
            assert "spo2" in overview["available_signal_snapshot"]["available_signal_ids"]
            assert overview["data_freshness"]["freshness_level"] == "fresh"
            assert overview["sync_state"]["needs_sync_before_time_sensitive_advice"] is False
            assert overview["personal_context"]["goal"]["goal"]["days_per_week"] == 4
            assert overview["personal_context"]["recent_checkins"][0]["checkin"]["soreness"] == 6
            assert "food" not in {item["id"] for item in overview["data_used"]["synced_metrics"]}
            assert overview["positives"]
            assert overview["next_actions"]
            assert overview["daily_brief"]["training_bias"] in {"train-ready", "controlled", "recovery-first"}
            assert overview["daily_brief"]["today_plan"]
            brief_signal_labels = {item["label"] for item in overview["daily_brief"]["priority_signals"]}
            assert {"Readiness", "Sleep", "Goal progress"} <= brief_signal_labels

            comparison = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "get_recovery_signal_comparison", "arguments": {"days": 7}},
                    101,
                )
            )
            assert comparison["status"] == "ok"
            assert comparison["comparison_type"] == "sleep_heart_recovery"
            assert comparison["latest"]["sleep_hours"] == 7.5
            assert "sleep_hours" in comparison["data_used"]["signals"]
            assert "spo2" in comparison["data_used"]["available_signal_ids"]

            clues = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "get_health_question_clues",
                        "arguments": {
                            "question": "How hard should I work out today, and why?",
                            "days": 7,
                        },
                    },
                    102,
                )
            )
            assert clues["status"] == "ok"
            assert clues["clue_type"] == "health_question_clues"
            assert "workout_decision" in clues["intent_hints"]
            assert "recommend_workout_today" in clues["recommended_tool_sequence"]
            assert "get_recovery_signal_comparison" in clues["recommended_tool_sequence"]
            assert "available_signal_snapshot" in clues
            assert "spo2" in clues["data_used"]["available_signal_ids"]
            assert {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"} <= {
                item["id"] for item in clues["relevant_metrics"]
            }
            recovery_query = next(item for item in clues["query_suggestions"] if item["purpose"] == "recovery")
            assert recovery_query["tool"] == "query_health_metrics"
            assert recovery_query["arguments"]["days"] == 7
            assert {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"} <= set(
                recovery_query["arguments"]["metrics"]
            )
            assert any("RPE cap" in item for item in clues["answer_rubric"])

            day_plan_clues = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "get_health_question_clues",
                        "arguments": {
                            "question": "What should I do today?",
                            "days": 7,
                        },
                    },
                    103,
                )
            )
            assert "daily_plan" in day_plan_clues["intent_hints"]
            assert "get_health_overview" in day_plan_clues["recommended_tool_sequence"]
            assert "recommend_workout_today" in day_plan_clues["recommended_tool_sequence"]
            assert day_plan_clues["overview_context"]["daily_brief"]["today_plan"]

            plan = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {
                        "name": "plan_workout_with_health_context",
                        "arguments": {
                            "planned_activity": "chest day",
                            "target_areas": ["chest"],
                            "planned_date": "tomorrow",
                            "constraints": "left lower back soreness after squash",
                            "duration_minutes": 60,
                        },
                    },
                    11,
                )
            )
            assert plan["status"] == "ok"
            assert plan["planned_activity"] == "chest day"
            assert plan["recommended_intensity"] == "moderate"
            assert plan["rpe_cap"] == 7
            assert plan["data_used"]["soreness_checkin"] == 6
            assert plan["data_used"]["goal"]["goal"]["days_per_week"] == 4
            assert any("Aggressive bench arch" in item for item in plan["avoid"])
            assert "medical advice" in plan["safety_note"]

            personalized_recommendation = tool_content(
                await mcp_request(
                    client,
                    access_token,
                    "tools/call",
                    {"name": "recommend_workout_today", "arguments": {}},
                    12,
                )
            )
            assert personalized_recommendation["status"] == "ok"
            assert personalized_recommendation["intensity"] == "moderate"
            assert personalized_recommendation["rpe_cap"] == 7
            assert personalized_recommendation["subjective_context"]["soreness"] == 6
            assert personalized_recommendation["goal_context"]["remaining_sessions"] == 3
            assert personalized_recommendation["context_gaps"] == []
            assert "soreness check-in is moderate" in personalized_recommendation["recommendation"]

            refresh = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "refresh_token": refresh_token,
                },
            )
            assert refresh.status_code == 200
            assert refresh.json()["access_token"] != access_token


@pytest.mark.asyncio
async def test_oauth_rejects_realistic_client_and_pkce_misuse(tmp_path) -> None:
    bundle = make_bundle(tmp_path)
    verifier, challenge = pkce_pair()
    transport = httpx.ASGITransport(app=bundle.app)

    async with bundle.app.router.lifespan_context(bundle.app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost:8787",
            follow_redirects=False,
        ) as client:
            missing_redirects = await client.post(
                "/oauth/register",
                json={
                    "client_name": "bad connector",
                    "token_endpoint_auth_method": "none",
                },
            )
            assert missing_redirects.status_code == 400
            assert missing_redirects.json()["error"] == "invalid_client_metadata"

            registration = await client.post(
                "/oauth/register",
                json={
                    "client_name": "ChatGPT private beta connector",
                    "redirect_uris": ["https://chatgpt.com/connector/oauth/allowed"],
                    "token_endpoint_auth_method": "none",
                },
            )
            assert registration.status_code == 201
            client_id = registration.json()["client_id"]

            bad_method = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": client_id,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/allowed",
                    "response_type": "code",
                    "scope": "health.read",
                    "state": "chatgpt-state",
                    "resource": "http://localhost:8787",
                    "code_challenge": challenge,
                    "code_challenge_method": "plain",
                },
            )
            assert bad_method.status_code == 400
            assert bad_method.json()["error"] == "invalid_request"

            bad_redirect = await client.get(
                "/oauth/authorize",
                params={
                    "client_id": client_id,
                    "redirect_uri": "https://evil.example/callback",
                    "response_type": "code",
                    "scope": "health.read",
                    "state": "chatgpt-state",
                    "resource": "http://localhost:8787",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            )
            assert bad_redirect.status_code == 400
            assert "redirect_uri" in bad_redirect.json()["error_description"]

            user_id = bundle.auth_service._create_user_from_google(
                {
                    "access_token": "fake-google-access",
                    "refresh_token": "fake-google-refresh",
                    "expires_in": 3600,
                    "scope": " ".join(bundle.settings.google_scopes),
                },
                {"email": "tester@example.com", "sub": "google-subject"},
            )
            app_code = bundle.auth_service._create_authorization_code(
                user_id,
                {
                    "client_id": client_id,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/allowed",
                    "code_challenge": challenge,
                    "scope": "health.read",
                    "resource": "http://localhost:8787",
                },
            )

            wrong_redirect_token = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": app_code,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/wrong",
                    "code_verifier": verifier,
                    "resource": "http://localhost:8787",
                },
            )
            assert wrong_redirect_token.status_code == 400
            assert wrong_redirect_token.json()["error"] == "invalid_grant"

            wrong_resource_token = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": app_code,
                    "redirect_uri": "https://chatgpt.com/connector/oauth/allowed",
                    "code_verifier": verifier,
                    "resource": "https://other.example",
                },
            )
            assert wrong_resource_token.status_code == 400
            assert wrong_resource_token.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_google_access_token_refresh_is_used_for_sync(tmp_path, monkeypatch) -> None:
    bundle = make_bundle(tmp_path)
    fake_health = FakeGoogleHealth()
    bundle.health_store.google = fake_health
    user_id = bundle.auth_service._create_user_from_google(
        {
            "access_token": "expired-google-access",
            "refresh_token": "fake-google-refresh",
            "expires_in": -30,
            "scope": " ".join(bundle.settings.google_scopes),
        },
        {"email": "tester@example.com", "sub": "google-subject"},
    )

    class FakeRefreshResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"access_token": "fake-google-access", "expires_in": 3600}

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, data: dict[str, Any]) -> FakeRefreshResponse:
            assert url == "https://oauth2.googleapis.com/token"
            assert data["refresh_token"] == "fake-google-refresh"
            assert data["grant_type"] == "refresh_token"
            return FakeRefreshResponse()

    monkeypatch.setattr("app.auth.httpx.AsyncClient", FakeAsyncClient)

    result = await bundle.health_store.sync_latest(user_id)

    assert result["status"] == "ok"
    assert result["records_upserted"] >= 10
    assert result["partial_sync"] is False
    assert result["metrics_deferred"] == []
    assert bundle.auth_service.current_user_google_token(user_id) == "fake-google-access"


@pytest.mark.asyncio
async def test_multi_user_data_isolation_and_no_startup_sync(tmp_path) -> None:
    bundle = make_bundle(tmp_path)
    user_a = bundle.auth_service._create_user_from_google(
        {
            "access_token": "fake-google-access",
            "refresh_token": "fake-google-refresh-a",
            "expires_in": 3600,
            "scope": " ".join(bundle.settings.google_scopes),
        },
        {"email": "a@example.com", "sub": "google-subject-a"},
    )
    user_b = bundle.auth_service._create_user_from_google(
        {
            "access_token": "fake-google-access",
            "refresh_token": "fake-google-refresh-b",
            "expires_in": 3600,
            "scope": " ".join(bundle.settings.google_scopes),
        },
        {"email": "b@example.com", "sub": "google-subject-b"},
    )
    client_a = "client-a"
    client_b = "client-b"
    now = iso_now()
    with bundle.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO oauth_clients (client_id, client_secret, metadata_json, created_at)
            VALUES (?, NULL, ?, ?), (?, NULL, ?, ?)
            """,
            (
                client_a,
                dumps({"token_endpoint_auth_method": "none"}),
                now,
                client_b,
                dumps({"token_endpoint_auth_method": "none"}),
                now,
            ),
        )

    assert bundle.health_store.connection_status(user_a)["records"] == 0
    assert bundle.health_store.connection_status(user_b)["records"] == 0

    today = datetime.now(UTC).date().isoformat()
    bundle.health_store.upsert_records(
        user_a,
        "steps",
        [
            {
                "name": "user-a-steps",
                "steps": {"count": 11111},
                "interval": {"startTime": f"{today}T10:00:00Z", "endTime": f"{today}T11:00:00Z"},
            }
        ],
    )
    token_a = json.loads(bundle.auth_service._issue_app_tokens(user_a, client_a, ["health.read"]).body)[
        "access_token"
    ]
    token_b = json.loads(bundle.auth_service._issue_app_tokens(user_b, client_b, ["health.read"]).body)[
        "access_token"
    ]
    transport = httpx.ASGITransport(app=bundle.app)

    async with bundle.app.router.lifespan_context(bundle.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8787") as client:
            context_a = tool_content(
                await mcp_request(
                    client,
                    token_a,
                    "tools/call",
                    {"name": "get_today_context", "arguments": {}},
                    1,
                )
            )
            context_b = tool_content(
                await mcp_request(
                    client,
                    token_b,
                    "tools/call",
                    {"name": "get_today_context", "arguments": {}},
                    2,
                )
            )

    assert context_a["status"] == "ok"
    assert context_a["today"]["steps"] == 11111
    assert context_b["status"] == "empty"


@pytest.mark.asyncio
async def test_mcp_rejects_unauthenticated_calls_with_oauth_challenge(tmp_path) -> None:
    bundle = make_bundle(tmp_path)
    transport = httpx.ASGITransport(app=bundle.app)

    async with bundle.app.router.lifespan_context(bundle.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8787") as client:
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers={"Accept": "application/json, text/event-stream"},
            )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"
    assert "resource_metadata" in response.headers["www-authenticate"]


class FailingGoogleHealth:
    async def list_data_points(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        request = httpx.Request("GET", "https://health.googleapis.com/v4/fake")
        response = httpx.Response(503, request=request, json={"error": "temporarily unavailable"})
        raise httpx.HTTPStatusError("temporarily unavailable", request=request, response=response)

    async def daily_rollup(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class PartiallyFailingGoogleHealth:
    async def list_data_points(
        self,
        access_token: str,
        spec: DataTypeSpec,
        start_time: str,
        end_time: str,
        timeout_seconds: int = 8,
        max_pages: int = 8,
    ) -> list[dict[str, Any]]:
        if spec.id == "sleep":
            today = datetime.now(UTC).date().isoformat()
            return [
                {
                    "name": "partial-sleep",
                    "sleep": {
                        "interval": {
                            "startTime": f"{today}T00:00:00Z",
                            "endTime": f"{today}T07:00:00Z",
                        }
                    },
                }
            ]
        raise TimeoutError("simulated slow Google Health metric")

    async def daily_rollup(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise TimeoutError("simulated slow Google Health rollup")


@pytest.mark.asyncio
async def test_partial_sync_preserves_records_and_reports_metric_diagnostics(tmp_path) -> None:
    bundle = make_bundle(tmp_path)
    bundle.health_store.google = PartiallyFailingGoogleHealth()
    user_id = bundle.auth_service._create_user_from_google(
        {
            "access_token": "fake-google-access",
            "refresh_token": "fake-google-refresh",
            "expires_in": 3600,
            "scope": " ".join(bundle.settings.google_scopes),
        },
        {"email": "tester@example.com", "sub": "google-subject"},
    )

    result = await bundle.health_store.sync_latest(user_id)

    assert result["status"] == "ok"
    assert result["partial_sync"] is True
    assert result["records_upserted"] == 1
    assert result["metrics_synced"] == ["sleep"]
    assert result["metric_errors"][0]["category"] == "timeout"
    assert "timed out" in result["metric_errors"][0]["error"]
    assert result["sync_diagnostics"]["metric_error_count"] >= 1

    sync_run = bundle.db.one("SELECT status, records_upserted, message FROM sync_runs WHERE user_id = ?", (user_id,))
    assert sync_run is not None
    assert sync_run["status"] == "partial"
    assert sync_run["records_upserted"] == 1
    assert "errors=" in sync_run["message"]


@pytest.mark.asyncio
async def test_sync_failure_is_reported_without_fabricated_context(tmp_path) -> None:
    bundle = make_bundle(tmp_path)
    bundle.health_store.google = FailingGoogleHealth()
    user_id = bundle.auth_service._create_user_from_google(
        {
            "access_token": "fake-google-access",
            "refresh_token": "fake-google-refresh",
            "expires_in": 3600,
            "scope": " ".join(bundle.settings.google_scopes),
        },
        {"email": "tester@example.com", "sub": "google-subject"},
    )
    bundle.db.one("SELECT id FROM users WHERE id = ?", (user_id,))
    client_id = "failure-client"
    with bundle.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO oauth_clients (client_id, client_secret, metadata_json, created_at)
            VALUES (?, NULL, ?, ?)
            """,
            (client_id, json.dumps({"token_endpoint_auth_method": "none"}), datetime.now(UTC).isoformat()),
        )
    token = json.loads(bundle.auth_service._issue_app_tokens(user_id, client_id, ["health.read"]).body)[
        "access_token"
    ]
    transport = httpx.ASGITransport(app=bundle.app)

    async with bundle.app.router.lifespan_context(bundle.app):
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8787") as client:
            sync = tool_content(
                await mcp_request(
                    client,
                    token,
                    "tools/call",
                    {"name": "sync_latest_fitbit_data", "arguments": {}},
                    1,
                )
            )
            today = tool_content(
                await mcp_request(
                    client,
                    token,
                    "tools/call",
                    {"name": "get_today_context", "arguments": {}},
                    2,
                )
            )

    assert sync["status"] == "error"
    assert sync["message"] == "Google Health sync failed."
    assert sync["metric_errors"][0]["category"] == "google_http_503"
    assert "Google Health HTTP 503" in sync["detail"]
    assert sync["records_upserted"] == 0
    assert today["status"] == "empty"

    sync_run = bundle.db.one(
        "SELECT status, records_upserted, message FROM sync_runs WHERE user_id = ?",
        (user_id,),
    )
    assert sync_run is not None
    assert sync_run["status"] == "error"
    assert sync_run["records_upserted"] == 0
    assert "google_http_503" in sync_run["message"]
