from __future__ import annotations

import httpx
import pytest

from app.main import SERVER_INSTRUCTIONS, app, mcp, settings as app_settings
from app.settings import Settings
from app.widget import LEGACY_WIDGET_URIS, WIDGET_PREVIEW_STATES, WIDGET_URI


@pytest.mark.asyncio
async def test_mcp_tool_list_matches_private_beta_plan() -> None:
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}

    assert names == {
        "connect_google_health_status",
        "list_available_health_metrics",
        "query_health_metrics",
        "sync_latest_fitbit_data",
        "sync_and_get_health_overview",
        "get_data_freshness",
        "get_today_context",
        "get_health_overview",
        "get_recovery_readiness",
        "get_health_question_clues",
        "get_recovery_signal_comparison",
        "recommend_workout_today",
        "plan_workout_with_health_context",
        "guide_active_workout",
        "get_sleep_analysis",
        "get_activity_load",
        "get_heart_trends",
        "get_workout_history",
        "set_goal",
        "log_checkin",
    }
    assert "food" not in " ".join(names)

    by_name = {tool.name: tool for tool in tools}
    assert by_name["get_health_overview"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["sync_and_get_health_overview"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["get_health_question_clues"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["get_recovery_signal_comparison"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["guide_active_workout"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["sync_latest_fitbit_data"].meta is None
    assert by_name["get_today_context"].meta is None
    assert by_name["get_recovery_readiness"].meta is None


def test_server_instructions_keep_normal_latest_questions_fast() -> None:
    assert "Use plain English before statistics" in SERVER_INSTRUCTIONS
    assert "Keep metric labels such as HRV, RPE, AZM" in SERVER_INSTRUCTIONS
    assert "include the date/window" in SERVER_INSTRUCTIONS
    assert "When a tool returns coach_response" in SERVER_INSTRUCTIONS
    assert "do not default to 'I feel off'" in SERVER_INSTRUCTIONS
    assert "Use already-synced local data for normal current/latest/today questions" in SERVER_INSTRUCTIONS
    assert "Sync only when the user explicitly asks for a fresh sync" in SERVER_INSTRUCTIONS
    assert "Treat phrases like check my Fitbit context" in SERVER_INSTRUCTIONS
    assert "call recommend_workout_today directly" in SERVER_INSTRUCTIONS
    assert "use list_available_health_metrics to inspect the per-user metric catalog" in SERVER_INSTRUCTIONS
    assert "query_health_metrics to fetch the specific signals you choose" in SERVER_INSTRUCTIONS
    assert "call get_health_overview" in SERVER_INSTRUCTIONS
    assert "Do not substitute get_health_overview for live workout decisions" in SERVER_INSTRUCTIONS


@pytest.mark.asyncio
async def test_widget_resource_is_registered() -> None:
    resources = await mcp.list_resources()
    resource = await mcp.read_resource(WIDGET_URI)
    html = resource[0].content

    assert str(resources[0].uri) == WIDGET_URI
    assert resources[0].mimeType == "text/html;profile=mcp-app"
    assert "Preparing card" in html
    assert 'renderEmpty("Preparing the health card from the latest tool result.", "waiting")' in html
    assert "function hasCardData(data)" in html
    assert "function renderLabelKey(labels)" in html
    assert "label-key" in html
    assert "dataUsed.sleep_asleep_hours != null" in html
    assert "dataUsed.hrv_ms != null" in html

    registered_uris = {str(item.uri) for item in resources}
    assert registered_uris.issuperset({WIDGET_URI, *LEGACY_WIDGET_URIS})
    for legacy_uri in LEGACY_WIDGET_URIS:
        legacy_resource = await mcp.read_resource(legacy_uri)
        assert legacy_resource[0].mime_type == "text/html;profile=mcp-app"
        assert "Preparing card" in legacy_resource[0].content


@pytest.mark.asyncio
async def test_http_metadata_routes() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        oauth = await client.get("/.well-known/oauth-authorization-server")
        protected = await client.get("/.well-known/oauth-protected-resource")

    assert health.status_code == 200
    assert health.json()["mcp_endpoint"].endswith("/mcp")
    assert oauth.status_code == 200
    assert oauth.json()["authorization_endpoint"].endswith("/oauth/authorize")
    assert protected.status_code == 200
    assert protected.json()["resource"].rstrip("/") == app_settings.base_url


@pytest.mark.asyncio
async def test_widget_preview_route_renders_real_card_state() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs/widget-preview?state=health-clues")
        overview = await client.get("/docs/widget-preview?state=health-overview")
        safety = await client.get("/docs/widget-preview?state=heart-safety")
        today_workout = await client.get("/docs/widget-preview?state=today-workout")
        workout_plan = await client.get("/docs/widget-preview?state=workout-plan")
        active_workout = await client.get("/docs/widget-preview?state=active-workout")
        recovery_comparison = await client.get("/docs/widget-preview?state=recovery-comparison")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "I feel cooked today" in response.text
    assert "state.data =" in response.text
    assert "initialize();" not in response.text
    assert "Health Clues" in response.text
    assert "Latest energy check-in is 3/10." in response.text
    assert "Goal progress in this window: 1/4 workout sessions logged." in response.text
    assert overview.status_code == 200
    assert "Health Overview" in overview.text
    assert "Movement load context; mostly useful for leg fatigue and total day load." in overview.text
    assert "steps_per_day" in overview.text
    assert "today so far; ${intText(stepAverage)}/day avg over ${rangeLabel}" in overview.text
    assert "Movement load context; mostly useful for leg fatigue and total day load." in overview.text
    assert "Training Load" in overview.text
    assert "AZM over ${rangeLabel}" in overview.text
    assert "HRV vs Avg" in overview.text
    assert "RHR vs Avg" in overview.text
    assert "HRV = recovery stress signal" in overview.text
    assert "AZM = Fitbit hard-work minutes" in overview.text
    assert "Vitals" in overview.text
    assert "recovery-first" in overview.text
    assert "Priority Signals" in overview.text
    assert "1/4 workout sessions logged; 3 remaining." in overview.text
    assert "Pain location is not logged" in overview.text
    assert safety.status_code == 200
    assert "Should I worry about my high heart rate and dizziness?" in safety.text
    assert "Health Check" in safety.text
    assert "Safety Context" in safety.text
    assert active_workout.status_code == 200
    assert "Active Workout" in active_workout.text
    assert "stop_and_assess" in active_workout.text
    assert "Stop + Assess" in active_workout.text
    assert recovery_comparison.status_code == 200
    assert "Recovery Comparison" in recovery_comparison.text
    assert "Latest recovery comparison" in recovery_comparison.text
    assert "dizzy during the interval" in active_workout.text
    assert today_workout.status_code == 200
    assert "Today's Workout" in today_workout.text
    assert "Next Session" in today_workout.text
    assert "The useful read: sleep is limiting recovery" in today_workout.text
    assert "Metric label explanations" in today_workout.text
    assert "Goal progress: 2/4 sessions logged; 2 remaining." in today_workout.text
    assert workout_plan.status_code == 200
    assert "Session Blueprint" in workout_plan.text
    assert "Machine chest press" in workout_plan.text
    assert "Chest-supported row" in workout_plan.text
    assert "RPE = how hard it feels" in workout_plan.text
    assert "hard but controlled" in workout_plan.text
    assert "Bent-over row -> chest-supported row." in workout_plan.text
    assert "sleep_asleep_hours" in workout_plan.text
    assert "31.3" in workout_plan.text
    assert "Latest energy check-in is 3/10." in today_workout.text


@pytest.mark.asyncio
async def test_widget_preview_route_lists_available_states_for_unknown_state() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs/widget-preview?state=missing")

    assert response.status_code == 404
    assert response.json()["available_states"] == sorted(WIDGET_PREVIEW_STATES)


def test_mcp_transport_security_allows_public_base_url_host() -> None:
    settings = Settings(public_base_url="https://example-tunnel.trycloudflare.com")

    assert "example-tunnel.trycloudflare.com" in settings.mcp_allowed_hosts
    assert "https://chatgpt.com" in settings.mcp_allowed_origins
