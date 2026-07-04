from __future__ import annotations

import httpx
import pytest
from starlette.responses import Response

from app.crypto import generate_key
from app.main import SERVER_INSTRUCTIONS, app, create_server, mcp, settings as app_settings
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
        "sync_and_get_workout_card",
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
    assert by_name["sync_and_get_health_overview"].meta is None
    assert by_name["sync_and_get_workout_card"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["get_health_question_clues"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["get_recovery_signal_comparison"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["guide_active_workout"].meta["openai/outputTemplate"] == WIDGET_URI
    assert by_name["sync_latest_fitbit_data"].meta is None
    assert by_name["sync_latest_fitbit_data"].annotations.idempotentHint is True
    assert by_name["sync_and_get_health_overview"].annotations.idempotentHint is True
    assert by_name["sync_and_get_workout_card"].annotations.idempotentHint is True
    assert by_name["get_today_context"].meta is None
    assert by_name["get_recovery_readiness"].meta is None
    assert "what data you can see" in by_name["list_available_health_metrics"].description
    assert "ChatGPT can choose metrics intelligently" in by_name[
        "list_available_health_metrics"
    ].description
    assert "metric-selection requests" in by_name["list_available_health_metrics"].description
    assert "Do not use a fixed recipe" in by_name["query_health_metrics"].description
    assert "normal wearable context, not a symptom report" in by_name[
        "query_health_metrics"
    ].description
    query_schema = by_name["query_health_metrics"].inputSchema["properties"]
    assert "Metric ids to fetch" in query_schema["metrics"]["description"]
    assert "7-14 for coaching" in query_schema["days"]["description"]
    assert "Fast all-context path" in by_name["get_health_overview"].description
    assert "give me my health overview today" in by_name["get_health_overview"].description
    assert "what health signals do you see" in by_name["get_health_overview"].description
    assert "broad context card, not the final workout-card tool" in by_name[
        "get_health_overview"
    ].description
    assert "create a new current overview card in long threads" in by_name[
        "get_health_overview"
    ].description
    assert "preparatory sync tool" in by_name["sync_latest_fitbit_data"].description
    assert "Do not use this as the visible final card" in by_name[
        "sync_and_get_health_overview"
    ].description
    assert by_name["sync_and_get_health_overview"].title == "Sync broad health overview, not workout cards"
    sync_overview_description = by_name["sync_and_get_health_overview"].description
    assert "Do not use for prompts that ask to show, update, render, or rerun an actual workout card" in sync_overview_description
    assert (
        "call sync_latest_fitbit_data first" in sync_overview_description
        or "sync_and_get_workout_card instead" in sync_overview_description
    )
    assert by_name["sync_and_get_workout_card"].title == "Sync and render actual workout card"
    assert "Best single tool" in by_name["sync_and_get_workout_card"].description
    assert "force refresh Fitbit now, then show the actual workout card" in by_name[
        "sync_and_get_workout_card"
    ].description
    assert "actual workout card" in by_name["sync_and_get_workout_card"].description
    assert "Do not call get_health_overview after this" in by_name[
        "sync_and_get_workout_card"
    ].description
    assert "Prefer get_health_overview for broad everyday coaching prompts" in by_name[
        "get_today_context"
    ].description
    assert "Narrow readiness score" in by_name["get_recovery_readiness"].description
    assert "what other signals are relevant" in by_name["get_health_question_clues"].description
    assert "suggested_card" in by_name["get_health_question_clues"].description
    assert "without forcing a brittle script" in by_name["get_health_question_clues"].description
    assert "metric-selection instruction" in by_name["get_health_question_clues"].description
    assert "oxygen/breathing signals can be named as background" in by_name[
        "get_recovery_signal_comparison"
    ].description
    assert "my oxygen looked lower" in by_name["get_recovery_signal_comparison"].description
    assert "I want to get fitter but not feel wrecked" in by_name[
        "recommend_workout_today"
    ].description
    assert "actual Apps SDK workout card renderer" in by_name[
        "recommend_workout_today"
    ].description
    assert "Do not say the card UI is unavailable" in by_name[
        "recommend_workout_today"
    ].description
    assert "call this tool again rather than answering from an older card" in by_name[
        "recommend_workout_today"
    ].description
    assert "SpO2" in by_name["recommend_workout_today"].description
    assert "metric list as symptoms" in by_name["recommend_workout_today"].description
    assert "Pass only current user-stated context" in by_name["recommend_workout_today"].inputSchema[
        "properties"
    ]["current_feeling"]["description"]
    assert "metric-selection instructions" in by_name["recommend_workout_today"].inputSchema[
        "properties"
    ]["current_feeling"]["description"]
    assert "upper body but save my legs for a hike" in by_name[
        "plan_workout_with_health_context"
    ].description
    assert "actual Apps SDK workout-plan card renderer" in by_name[
        "plan_workout_with_health_context"
    ].description
    assert "sleep temperature" in by_name["plan_workout_with_health_context"].description
    assert "data-use preference, not a symptom report" in by_name[
        "plan_workout_with_health_context"
    ].description
    assert "copy metric-selection instructions" in by_name["plan_workout_with_health_context"].inputSchema[
        "properties"
    ]["constraints"]["description"]
    assert "Live inputs are user-reported" in by_name["guide_active_workout"].description
    assert "not direct band telemetry" in by_name["guide_active_workout"].description
    assert "actual Apps SDK active workout card renderer" in by_name[
        "guide_active_workout"
    ].description
    assert "do not reuse earlier active-workout guidance" in by_name["guide_active_workout"].description
    planned_activity = by_name["guide_active_workout"].inputSchema["properties"]["planned_activity"]
    assert planned_activity["default"] == "current workout"
    assert "Use 'current workout'" in planned_activity["description"]
    assert "explicitly negates symptoms" in by_name["guide_active_workout"].inputSchema["properties"][
        "symptoms"
    ]["description"]


def test_server_instructions_keep_normal_latest_questions_fast() -> None:
    assert "Use plain English before statistics" in SERVER_INSTRUCTIONS
    assert "Treat tool descriptions and response contracts as routing" in SERVER_INSTRUCTIONS
    assert "Everyday prompts like 'should I run today'" in SERVER_INSTRUCTIONS
    assert "'I want to get fitter but not feel wrecked'" in SERVER_INSTRUCTIONS
    assert "Keep metric labels such as HRV, RPE, AZM" in SERVER_INSTRUCTIONS
    assert "metric-selection and answer-shaping instructions" in SERVER_INSTRUCTIONS
    assert "Do not put those metric-selection phrases into current_feeling" in SERVER_INSTRUCTIONS
    assert "Do not narrate internal failed or blocked tool attempts" in SERVER_INSTRUCTIONS
    assert "Keep source boundaries clear" in SERVER_INSTRUCTIONS
    assert "synced Fitbit/Google Health signals are wearable evidence" in SERVER_INSTRUCTIONS
    assert "conversation memory or prior chat context" in SERVER_INSTRUCTIONS
    assert "do not imply the band measured it" in SERVER_INSTRUCTIONS
    assert "include the date/window" in SERVER_INSTRUCTIONS
    assert "recorded step days" in SERVER_INSTRUCTIONS
    assert "When a tool returns coach_response" in SERVER_INSTRUCTIONS
    assert "If get_health_question_clues returns suggested_card" in SERVER_INSTRUCTIONS
    assert "training_decision, readiness_attribution, model_signal_context" in SERVER_INSTRUCTIONS
    assert "which signals actually moved" in SERVER_INSTRUCTIONS
    assert "readiness score as a summary, not an independent reason" in SERVER_INSTRUCTIONS
    assert "decision_frame.model_decision_policy" in SERVER_INSTRUCTIONS
    assert "safety, recovery, load, capacity" in SERVER_INSTRUCTIONS
    assert "Do not say a tool was blocked unless the tool result itself has an error" in SERVER_INSTRUCTIONS
    assert "Actual mehair coach cards are rendered by card tools" in SERVER_INSTRUCTIONS
    assert "call sync_and_get_workout_card as the single current card-rendering path" in SERVER_INSTRUCTIONS
    assert "do not say the workout card UI is unavailable" in SERVER_INSTRUCTIONS
    assert "decision, do now, why the data matters" in SERVER_INSTRUCTIONS
    assert "do not default to 'I feel off'" in SERVER_INSTRUCTIONS
    assert "Use already-synced local data for normal current/latest/today questions" in SERVER_INSTRUCTIONS
    assert "data in the user's private mehair coach store" in SERVER_INSTRUCTIONS
    assert "not data already visible in the conversation" in SERVER_INSTRUCTIONS
    assert "Fresh means synced in the last 15 minutes" in SERVER_INSTRUCTIONS
    assert "Sync only when the user explicitly asks for a fresh sync" in SERVER_INSTRUCTIONS
    assert "non-destructive, idempotent pull" in SERVER_INSTRUCTIONS
    assert "do not describe it as blocked" in SERVER_INSTRUCTIONS
    assert "Sync tools are preparatory for workout/run/lift/card" in SERVER_INSTRUCTIONS
    assert "final card-rendering call for day-of workout advice" in SERVER_INSTRUCTIONS
    assert "Do not answer a workout-card request from a sync or overview result alone" in SERVER_INSTRUCTIONS
    assert "Treat phrases like check my Fitbit context" in SERVER_INSTRUCTIONS
    assert "call recommend_workout_today directly" in SERVER_INSTRUCTIONS
    assert "use planned_activity and target_areas only for the workout the user actually wants to do" in SERVER_INSTRUCTIONS
    assert "not as leg target_areas" in SERVER_INSTRUCTIONS
    assert "do not answer from an old visible card" in SERVER_INSTRUCTIONS
    assert "Treat older cards as historical context only" in SERVER_INSTRUCTIONS
    assert "use list_available_health_metrics to inspect the per-user metric catalog" in SERVER_INSTRUCTIONS
    assert "query_health_metrics to fetch the specific signals you choose" in SERVER_INSTRUCTIONS
    assert "call get_health_overview" in SERVER_INSTRUCTIONS
    assert "available_signal_snapshot" in SERVER_INSTRUCTIONS
    assert "oxygen, breathing" in SERVER_INSTRUCTIONS
    assert "oxygen looked lower" in SERVER_INSTRUCTIONS
    assert "do not diagnose" in SERVER_INSTRUCTIONS
    assert "Do not substitute get_health_overview for live workout decisions" in SERVER_INSTRUCTIONS


@pytest.mark.asyncio
async def test_widget_resource_is_registered() -> None:
    resources = await mcp.list_resources()
    resource = await mcp.read_resource(WIDGET_URI)
    html = resource[0].content

    assert str(resources[0].uri) == WIDGET_URI
    assert resources[0].mimeType == "text/html;profile=mcp-app"
    assert WIDGET_URI == "ui://mehair/today-v28.html"
    assert "ui://mehair/today-v27.html" in LEGACY_WIDGET_URIS
    assert "Preparing card" in html
    assert 'appInfo: { name: "mehair coach", version: "0.7.9" }' in html
    assert "mehair-coach-widget" not in html
    assert 'renderEmpty("Preparing the health card from the latest tool result.", "waiting")' in html
    assert "window.openai?.toolOutput" in html
    assert "openai:set_globals" in html
    assert "function hasCardData(data)" in html
    assert "function withDataWindow(model, data)" in html
    assert "data?.suggested_card" in html
    assert "Latest Fitbit data pull was" in html
    assert "formatDateTime(freshness.last_sync)} (${ageMinutesText(minutes)})" in html
    assert "not fresh; sync recommended" in html
    assert "using Fitbit data through" in html
    assert "data-window" in html
    assert "--sync-dot" in html
    assert "function todayWorkoutTitle(data, reserveEnergy, deadlineMinutes)" in html
    assert "Minimum Useful Movement" in html
    assert "Before Class Movement" in html
    assert "Before Dinner Movement" in html
    assert "Before Plans Movement" in html
    assert "Before Travel Movement" in html
    assert "Tomorrow-Friendly Workout" in html
    assert 'text.includes("work")' not in html
    assert "function renderLabelKey(labels)" in html
    assert "function inferredLabelKey(model)" in html
    assert "label-key" in html
    assert "Metric labels, translated" in html
    assert "score-state::before" in html
    assert "const showScore = model.showScore !== false" in html
    assert 'class="hero ${showScore ? "" : "no-score"}"' in html
    assert "showScore: !safety.length" in html
    assert "band-green" in html
    assert "training available" not in html
    assert "Train available" not in html
    assert "more training room" in html
    assert "More training room (75+)" in html
    assert "function renderPrescriptionPills(block)" in html
    assert "workout-prescription" in html
    assert "rx-pill" in html
    assert 'join(" | ")' not in html
    assert 'root.style.setProperty("--state", "#d63384")' in html
    assert 'root.style.setProperty("--state", accent)' not in html
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
        icon = await client.get("/assets/mehair-coach-icon.svg")
        oauth = await client.get("/.well-known/oauth-authorization-server")
        protected = await client.get("/.well-known/oauth-protected-resource")

    assert health.status_code == 200
    assert health.json()["name"] == "mehair coach"
    assert health.json()["mcp_endpoint"].endswith("/mcp")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")
    assert "#d63384" in icon.text
    assert oauth.status_code == 200
    assert oauth.json()["client_name"] == "mehair coach"
    assert oauth.json()["logo_uri"].endswith("/assets/mehair-coach-icon.svg")
    assert oauth.json()["authorization_endpoint"].endswith("/oauth/authorize")
    assert protected.status_code == 200
    assert protected.json()["resource"].rstrip("/") == app_settings.base_url


@pytest.mark.asyncio
async def test_google_callback_background_sync_skips_context_payload(tmp_path) -> None:
    bundle = create_server(
        Settings(
            public_base_url="http://localhost:8787",
            database_url=f"sqlite:///{tmp_path / 'callback.sqlite3'}",
            token_encryption_key=generate_key(),
            google_client_id="fake-google-client",
            google_client_secret="fake-google-secret",
            google_redirect_uri="http://localhost:8787/oauth/callback/google",
        )
    )
    sync_calls = []

    async def fake_google_callback(request, on_connected=None):
        if on_connected:
            on_connected("user-with-google-health")
        return Response(status_code=302, headers={"location": "https://chatgpt.com"})

    async def fake_sync_latest(user_id, force=False, *, include_context=True):
        sync_calls.append(
            {
                "user_id": user_id,
                "force": force,
                "include_context": include_context,
            }
        )
        return {"status": "ok"}

    bundle.auth_service.google_callback = fake_google_callback
    bundle.health_store.sync_latest = fake_sync_latest

    transport = httpx.ASGITransport(app=bundle.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8787") as client:
        response = await client.get("/oauth/callback/google", follow_redirects=False)

    assert response.status_code == 302
    assert sync_calls == [
        {
            "user_id": "user-with-google-health",
            "force": False,
            "include_context": False,
        }
    ]


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
        active_workout_hold = await client.get("/docs/widget-preview?state=active-workout-hold")
        recovery_comparison = await client.get("/docs/widget-preview?state=recovery-comparison")

    for preview in [
        response,
        overview,
        safety,
        today_workout,
        workout_plan,
        active_workout,
        active_workout_hold,
        recovery_comparison,
    ]:
        assert preview.status_code == 200
        assert "data-window" in preview.text
        assert "Latest Fitbit data pull was" in preview.text
        assert "using Fitbit data through" in preview.text

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "I feel cooked today" in response.text
    assert "state.data =" in response.text
    assert "initialize();" not in response.text
    assert "Signals That Matter" in response.text
    assert "Why I Checked These" in response.text
    assert "Latest energy check-in is 3/10." in response.text
    assert "Goal progress in this window: 1/4 workout sessions logged." in response.text
    assert overview.status_code == 200
    assert "Health Overview" in overview.text
    assert "Movement load context; mostly useful for leg fatigue and total day load." in overview.text
    assert "steps_per_day" in overview.text
    assert "today so far\", stepAverageLabel, stepRecordedLabel" in overview.text
    assert "/day avg on recorded step days" in overview.text
    assert "Movement load context; mostly useful for leg fatigue and total day load." in overview.text
    assert "Training Load" in overview.text
    assert "AZM over ${rangeLabel}" in overview.text
    assert "HRV vs usual" in overview.text
    assert "Resting HR vs usual" in overview.text
    assert "HRV = recovery stress signal" in overview.text
    assert "AZM = Fitbit hard-work minutes" in overview.text
    assert "Signals checked" in overview.text
    assert "Other signals checked for this answer" in overview.text
    assert "Fitbit data timing" in overview.text
    assert "Fresh data" in overview.text
    assert "Latest Fitbit data pull was" in overview.text
    assert "using Fitbit data through" in overview.text
    assert "signal-strip" in overview.text
    assert "green 75+" in overview.text
    assert "yellow 55-74" in overview.text
    assert "red &lt;55" in overview.text
    assert "Vitals" in overview.text
    assert "recovery-first" in overview.text
    assert "Priority Signals" in overview.text
    assert "1/4 workout sessions logged; 3 remaining." in overview.text
    assert "Pain location is not logged" in overview.text
    assert safety.status_code == 200
    assert "Should I worry about my high heart rate and dizziness?" in safety.text
    assert "Health Check" in safety.text
    assert "mehair coach" in safety.text
    assert active_workout.status_code == 200
    assert "Active Workout" in active_workout.text
    assert "stop_and_assess" in active_workout.text
    assert "Stop + Assess" in active_workout.text
    assert "Stop Hard Work Now" in active_workout.text
    assert "Do Now" not in active_workout.text
    assert recovery_comparison.status_code == 200
    assert "Recovery Signals" in recovery_comparison.text
    assert "What This Means For Training" in recovery_comparison.text
    assert "Latest recovery comparison" in recovery_comparison.text
    assert "Metric label explanations" in recovery_comparison.text
    assert "HRV = recovery stress signal" in recovery_comparison.text
    assert "SpO2 = oxygen saturation" in recovery_comparison.text
    assert "dizzy during the interval" in active_workout.text
    assert "yellow today (55-74); green is 75+, red is <55" in active_workout.text
    assert "AZM = Fitbit hard-work minutes" in active_workout.text
    assert active_workout_hold.status_code == 200
    assert "Active Workout" in active_workout_hold.text
    assert "continue_controlled" in active_workout_hold.text
    assert "Hold This Effort" in active_workout_hold.text
    assert "Do Now" not in active_workout_hold.text
    assert "Next 5-10 minutes: hold steady" in active_workout_hold.text
    assert "RPE = how hard it feels" in active_workout_hold.text
    assert "aging 15-60m" in active_workout_hold.text
    assert "SpO2 / oxygen saturation" in overview.text
    assert "Readiness thresholds: green 75+, yellow 55-74, red <55" in overview.text
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
    assert "Exercise prescription" in workout_plan.text
    assert "Effort" in workout_plan.text
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
