from __future__ import annotations

import httpx
import pytest

from app.main import app, mcp
from app.widget import WIDGET_URI


@pytest.mark.asyncio
async def test_mcp_tool_list_matches_private_beta_plan() -> None:
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}

    assert names == {
        "connect_google_health_status",
        "sync_latest_fitbit_data",
        "get_data_freshness",
        "get_today_context",
        "get_recovery_readiness",
        "recommend_workout_today",
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
    assert protected.json()["resource"].rstrip("/") == "http://localhost:8787"
