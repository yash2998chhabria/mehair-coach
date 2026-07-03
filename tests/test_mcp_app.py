from __future__ import annotations

import httpx
import pytest

from app.main import app, mcp, settings as app_settings
from app.settings import Settings
from app.widget import WIDGET_PREVIEW_STATES, WIDGET_URI


@pytest.mark.asyncio
async def test_mcp_tool_list_matches_private_beta_plan() -> None:
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}

    assert names == {
        "connect_google_health_status",
        "list_available_health_metrics",
        "query_health_metrics",
        "sync_latest_fitbit_data",
        "get_data_freshness",
        "get_today_context",
        "get_health_overview",
        "get_recovery_readiness",
        "get_health_question_clues",
        "get_recovery_signal_comparison",
        "recommend_workout_today",
        "plan_workout_with_health_context",
        "get_sleep_analysis",
        "get_activity_load",
        "get_heart_trends",
        "get_workout_history",
        "set_goal",
        "log_checkin",
    }
    assert "food" not in " ".join(names)


@pytest.mark.asyncio
async def test_widget_resource_is_registered() -> None:
    resources = await mcp.list_resources()

    assert str(resources[0].uri) == WIDGET_URI
    assert resources[0].mimeType == "text/html;profile=mcp-app"


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
        safety = await client.get("/docs/widget-preview?state=heart-safety")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "I feel cooked today" in response.text
    assert "state.data =" in response.text
    assert "initialize();" not in response.text
    assert "Health Clues" in response.text
    assert "Latest energy check-in is 3/10." in response.text
    assert "Goal progress in this window: 1/4 workout sessions logged." in response.text
    assert safety.status_code == 200
    assert "Should I worry about my high heart rate and dizziness?" in safety.text
    assert "Health Check" in safety.text
    assert "Safety Context" in safety.text


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
