from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from .auth import AppTokenVerifier, AuthError, AuthService
from .db import Database
from .health_store import HealthStore, setup_required
from .settings import Settings, get_settings
from .widget import TODAY_WIDGET_HTML, WIDGET_MIME_TYPE, WIDGET_URI


SERVER_INSTRUCTIONS = (
    "Mehair Coach provides read-only Google Health/Fitbit context for a connected user. "
    "If connection or synced data is missing, call status/freshness tools and explain setup; "
    "never invent health data. Sync only when the user asks for fresh Fitbit data."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
SYNC = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
WIDGET_META = {
    "ui": {"resourceUri": WIDGET_URI},
    "openai/outputTemplate": WIDGET_URI,
}


@dataclass(frozen=True)
class ServerBundle:
    settings: Settings
    db: Database
    auth_service: AuthService
    health_store: HealthStore
    mcp: FastMCP
    app: Starlette


def create_server(settings_override: Settings | None = None) -> ServerBundle:
    settings = settings_override or get_settings()
    db = Database(settings.sqlite_path)
    db.init()
    auth_service = AuthService(db, settings)
    health_store = HealthStore(db, auth_service, settings)

    mcp = FastMCP(
        name="Mehair Coach",
        instructions=SERVER_INSTRUCTIONS,
        token_verifier=AppTokenVerifier(auth_service),
        auth=AuthSettings(
            issuer_url=settings.base_url,
            resource_server_url=settings.base_url,
            service_documentation_url=f"{settings.base_url}/docs/setup",
            required_scopes=[settings.app_scope],
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.mcp_allowed_hosts,
            allowed_origins=settings.mcp_allowed_origins,
        ),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @mcp.resource(
        WIDGET_URI,
        name="mehair-today-card",
        title="Mehair Coach Today Card",
        description="Inline readiness, sleep, activity, and evidence card for synced Fitbit context.",
        mime_type=WIDGET_MIME_TYPE,
        meta={
            "ui": {
                "prefersBorder": True,
                "csp": {"connectDomains": [], "resourceDomains": []},
            }
        },
    )
    def today_card() -> str:
        return TODAY_WIDGET_HTML

    def current_user_id() -> str | None:
        token = get_access_token()
        return token.subject if token else None

    @mcp.tool(
        title="Google Health connection status",
        description="Check whether this ChatGPT user has connected Google Health/Fitbit data and whether records exist.",
        annotations=READ_ONLY,
    )
    def connect_google_health_status() -> dict[str, Any]:
        return health_store.connection_status(current_user_id())

    @mcp.tool(
        title="List available health metrics",
        description="List every device-first Google Health/Fitbit metric this app can sync and query, with per-user record counts when available.",
        annotations=READ_ONLY,
    )
    def list_available_health_metrics() -> dict[str, Any]:
        return health_store.available_metrics(current_user_id())

    @mcp.tool(
        title="Query health metrics",
        description="Query one or more synced Google Health/Fitbit metrics from the local store over a bounded date range.",
        annotations=READ_ONLY,
    )
    def query_health_metrics(
        metrics: list[str] | None = None,
        days: int = 7,
        start_date: str | None = None,
        end_date: str | None = None,
        include_records: bool = False,
        limit_per_metric: int = 25,
    ) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.query_metrics(
            user_id,
            metrics=metrics,
            days=max(1, min(days, 30)),
            start_date=start_date,
            end_date=end_date,
            include_records=include_records,
            limit_per_metric=max(1, min(limit_per_metric, 200)),
        )

    @mcp.tool(
        title="Sync latest Fitbit data",
        description="Pull the latest available cloud-synced Fitbit data from Google Health into the local user store.",
        annotations=SYNC,
        meta=WIDGET_META,
    )
    async def sync_latest_fitbit_data() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return await health_store.sync_latest(user_id)

    @mcp.tool(
        title="Data freshness",
        description="Report how fresh the synced Fitbit/Google Health records are for this user.",
        annotations=READ_ONLY,
    )
    def get_data_freshness() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.freshness(user_id)

    @mcp.tool(
        title="Today context",
        description="Return latest daily fitness context: activity, sleep, heart metrics, readiness, and evidence.",
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_today_context() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.latest_context(user_id)

    @mcp.tool(
        title="Recovery readiness",
        description="Return a readiness score with evidence from sleep, HRV, resting heart rate, and activity load.",
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_recovery_readiness() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        context = health_store.latest_context(user_id)
        if context.get("status") != "ok":
            return context
        return {
            "status": "ok",
            "latest_date": context["latest_date"],
            "activity_date": context["activity_date"],
            "recovery_date": context["recovery_date"],
            "readiness": context["readiness"],
            "today": context["today"],
            "evidence": context["evidence"],
        }

    @mcp.tool(
        title="Recommend workout today",
        description="Recommend how hard to work out today using synced Fitbit context and logged goals/check-ins.",
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def recommend_workout_today() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return workout_recommendation(health_store.latest_context(user_id))

    @mcp.tool(
        title="Sleep analysis",
        description="Analyze recent synced Fitbit sleep records and return stages and latest duration.",
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_sleep_analysis(days: int = 7) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.sleep_analysis(user_id, max(1, min(days, 30)))

    @mcp.tool(
        title="Activity load",
        description="Summarize recent steps, active minutes, zone minutes, and distance.",
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_activity_load(days: int = 7) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.activity_load(user_id, max(1, min(days, 30)))

    @mcp.tool(
        title="Heart trends",
        description="Summarize recent heart rate, resting heart rate, and HRV from synced Fitbit records.",
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_heart_trends(days: int = 7) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.heart_trends(user_id, max(1, min(days, 30)))

    @mcp.tool(
        title="Workout history",
        description="List recent Fitbit exercise sessions and workout-level metrics.",
        annotations=READ_ONLY,
    )
    def get_workout_history(days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.workout_history(user_id, max(1, min(days, 90)))

    @mcp.tool(
        title="Set coaching goal",
        description="Store a user-provided fitness goal for future recommendations. Writes only to local Mehair Coach storage.",
        annotations=WRITE_LOCAL,
    )
    def set_goal(
        goal_type: str,
        target: str,
        days_per_week: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.save_goal(
            user_id,
            {
                "goal_type": goal_type,
                "target": target,
                "days_per_week": days_per_week,
                "notes": notes,
            },
        )

    @mcp.tool(
        title="Log check-in",
        description="Store a subjective energy, soreness, stress, or notes check-in for future coaching.",
        annotations=WRITE_LOCAL,
    )
    def log_checkin(
        energy: int | None = None,
        soreness: int | None = None,
        stress: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        checkin = {
            "energy": _bounded_rating(energy),
            "soreness": _bounded_rating(soreness),
            "stress": _bounded_rating(stress),
            "notes": notes,
        }
        return health_store.save_checkin(user_id, checkin)

    app = mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "name": "Mehair Coach",
                "mcp_endpoint": f"{settings.base_url}/mcp",
                "google_oauth_configured": bool(
                    settings.google_client_id
                    and settings.google_client_secret
                    and settings.token_encryption_key
                ),
            }
        )

    async def home(_: Request) -> PlainTextResponse:
        return PlainTextResponse("Mehair Coach MCP server. Connect ChatGPT to /mcp.")

    async def oauth_metadata(_: Request) -> JSONResponse:
        return JSONResponse(auth_service.oauth_metadata())

    async def register_client(request: Request) -> JSONResponse:
        return await auth_service.register_client(request)

    async def authorize(request: Request) -> Response:
        return await auth_service.authorize(request)

    async def token(request: Request) -> JSONResponse:
        try:
            return await auth_service.token(request)
        except AuthError as exc:
            return JSONResponse(
                {"error": "invalid_client", "error_description": str(exc)},
                status_code=401,
            )

    async def google_callback(request: Request) -> Response:
        return await auth_service.google_callback(request)

    async def setup_doc(_: Request) -> HTMLResponse:
        return HTMLResponse(
            """
            <!doctype html>
            <html lang="en">
              <meta charset="utf-8" />
              <title>Mehair Coach setup</title>
              <body style="font-family: system-ui; max-width: 760px; margin: 40px auto; line-height: 1.5">
                <h1>Mehair Coach setup</h1>
                <p>Expose this server over HTTPS, set PUBLIC_BASE_URL and GOOGLE_REDIRECT_URI to that origin, then create a ChatGPT developer-mode connector pointing at <code>/mcp</code>.</p>
                <p>Google Health OAuth must be configured with read-only Health scopes and each beta tester must be added as a Google OAuth test user.</p>
              </body>
            </html>
            """.strip()
        )

    app.add_route("/", home, methods=["GET"])
    app.add_route("/health", health, methods=["GET"])
    app.add_route("/.well-known/oauth-authorization-server", oauth_metadata, methods=["GET"])
    app.add_route("/.well-known/openid-configuration", oauth_metadata, methods=["GET"])
    app.add_route("/oauth/register", register_client, methods=["POST"])
    app.add_route("/oauth/authorize", authorize, methods=["GET"])
    app.add_route("/oauth/token", token, methods=["POST"])
    app.add_route("/oauth/callback/google", google_callback, methods=["GET"])
    app.add_route("/docs/setup", setup_doc, methods=["GET"])

    return ServerBundle(
        settings=settings,
        db=db,
        auth_service=auth_service,
        health_store=health_store,
        mcp=mcp,
        app=app,
    )


def workout_recommendation(context: dict[str, Any]) -> dict[str, Any]:
    if context.get("status") != "ok":
        return context
    readiness = context["readiness"]
    label = readiness.get("label")
    today = context.get("today", {})
    sleep = today.get("sleep", {})
    if label == "green":
        plan = "Train normally: strength, intervals, or a full session are reasonable if your body agrees."
        intensity = "moderate-to-hard"
    elif label == "yellow":
        plan = "Keep it controlled: zone 2 cardio, technique work, or submax strength."
        intensity = "moderate"
    else:
        plan = "Make today recovery-biased: walking, mobility, breath work, and an earlier bedtime."
        intensity = "easy"
    if today.get("active_zone_minutes", 0) > 45:
        plan += " You already have a high zone-minute load today, so avoid stacking another hard effort."
    if sleep.get("asleep_hours") and sleep["asleep_hours"] < 5:
        plan += " Keep impact low because the latest sleep block was short."
    return {
        "status": "ok",
        "intensity": intensity,
        "recommendation": plan,
        "latest_date": context.get("latest_date"),
        "activity_date": context.get("activity_date"),
        "recovery_date": context.get("recovery_date"),
        "today": today,
        "why": readiness.get("evidence", []),
        "evidence": readiness.get("evidence", []),
        "data_used": {
            "activity_date": context.get("activity_date"),
            "recovery_date": context.get("recovery_date"),
            "steps_today": today.get("steps", 0),
            "active_minutes_today": today.get("active_minutes", 0),
            "active_zone_minutes_today": today.get("active_zone_minutes", 0),
            "latest_sleep_hours": sleep.get("asleep_hours") or sleep.get("duration_hours"),
            "resting_heart_rate": today.get("resting_heart_rate"),
            "hrv_ms": today.get("hrv_ms"),
        },
        "readiness": readiness,
        "context": context,
        "safety_note": "This is fitness coaching context, not medical advice.",
    }


def _bounded_rating(value: int | None) -> int | None:
    if value is None:
        return None
    return max(1, min(10, int(value)))


bundle = create_server()
settings = bundle.settings
db = bundle.db
auth_service = bundle.auth_service
health_store = bundle.health_store
mcp = bundle.mcp
app = bundle.app


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
