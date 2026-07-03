from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from .auth import AppTokenVerifier, AuthError, AuthService
from .db import Database
from .health_store import HealthStore, setup_required
from .settings import Settings, get_settings
from .widget import (
    TODAY_WIDGET_HTML,
    WIDGET_MIME_TYPE,
    WIDGET_PREVIEW_STATES,
    WIDGET_RESOURCE_URIS,
    WIDGET_URI,
    widget_preview_html,
)


SERVER_INSTRUCTIONS = (
    "Mehair Coach provides read-only Google Health/Fitbit context for a connected user. "
    "Use plain English before statistics. Keep metric labels such as HRV, RPE, AZM, and resting "
    "heart rate, but briefly explain what they mean when they appear in user-facing advice. "
    "When a tool returns coach_response, use it as the answer skeleton: direct human answer first, "
    "then the session_blueprint or what_to_do, then the explained metric labels, then stop conditions "
    "or caveats. Avoid leading with raw tables or unexplained evidence logs. "
    "If connection or synced data is missing, call status/freshness tools and explain setup; "
    "never invent health data. Use already-synced local data for normal current/latest/today questions, "
    "because every overview includes freshness metadata. Treat phrases like check my Fitbit context, "
    "look at my data, use my data, or what should I do today as already-synced reads unless the user "
    "literally asks to sync, refresh, pull, or update Fitbit/Google Health data now. Sync only when "
    "the user explicitly asks for a fresh sync/refresh/pull/update, or when a freshness result says "
    "the data is stale for time-sensitive advice. For explicit requests to sync or refresh and then "
    "summarize, analyze all available metrics, explain changes, or give an overview, call "
    "sync_and_get_health_overview so the answer is based on one fresh overview result. For broad "
    "health, fitness, recovery, current/latest/today, or 'use all my data' overview questions that "
    "do not explicitly request sync/refresh, call get_health_overview before answering. "
    "For exploratory or unusual questions, use list_available_health_metrics to inspect the per-user "
    "metric catalog and query_health_metrics to fetch the specific signals you choose; let the user's "
    "question decide the metric mix instead of following a fixed recipe. "
    "For everyday coaching questions like 'I feel off, what should I do today?' or 'how hard should "
    "I train?', call recommend_workout_today directly and pass the user's plain-language feeling into "
    "current_feeling. Use get_health_question_clues for exploratory or diagnostic-sounding questions "
    "where the user asks which metrics matter, why they may feel tired, or what signals to inspect "
    "before choosing follow-up tools. "
    "For sleep/HRV/resting-heart-rate/load comparisons, call get_recovery_signal_comparison. "
    "For any specific workout, sport, muscle-group, soreness, or recovery decision, call "
    "plan_workout_with_health_context or recommend_workout_today before answering; do not infer "
    "readiness, HRV, sleep, or load from conversation memory. Pass user-stated current feelings, "
    "symptoms, soreness, time limits, or pain into the tool arguments instead of leaving them in "
    "free text. Label prior conversation facts as user-stated context, not synced Fitbit evidence, "
    "and do not treat earlier symptoms as current unless the user says they are still present. "
    "During an active workout, call guide_active_workout when the user reports live RPE, heart rate, "
    "pain, symptoms, elapsed time, or asks whether to keep going, push, hold steady, back off, slow "
    "down, or stop. Call guide_active_workout directly for these in-session questions because it "
    "already reads the latest synced readiness/load context and renders the active workout card. Do "
    "not substitute get_health_overview for live workout decisions. Prefer one card-rendering tool per "
    "answer unless the user explicitly asks for multiple cards."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
SYNC = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
WIDGET_META = {
    "ui": {"resourceUri": WIDGET_URI},
    "openai/outputTemplate": WIDGET_URI,
}
ILLNESS_PHRASES = (
    "fever",
    "flu",
    "covid",
    "infection",
    "vomit",
    "vomiting",
    "nausea",
    "chills",
    "sore throat",
    "head cold",
    "cold symptoms",
    "feel sick",
    "feeling sick",
    "sick today",
    "illness",
    "body aches",
)

METRIC_LABEL_EXPLANATIONS = {
    "Readiness": "a quick recovery score built from sleep, heart, and recent load signals",
    "RPE": "rate of perceived exertion: how hard it feels from 1 easy to 10 max",
    "HR": "heart rate right now: current beats per minute during movement or rest",
    "HRV": "heart-rate variability: a recovery stress signal compared with your usual",
    "Resting HR": "resting heart rate: heart stress at rest, best judged against your usual",
    "AZM": "Active Zone Minutes: Fitbit's hard-work minutes from elevated heart-rate zones",
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
    db = Database.from_url(settings.database_url, settings.libsql_auth_token)
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

    def register_today_card(widget_uri: str) -> None:
        widget_version = widget_uri.rsplit("/", 1)[-1].replace(".html", "")

        @mcp.resource(
            widget_uri,
            name=f"mehair-today-card-{widget_version}",
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

    for widget_uri in WIDGET_RESOURCE_URIS:
        register_today_card(widget_uri)

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
        description=(
            "List every device-first Google Health/Fitbit metric this app can sync and query, with "
            "per-user record counts plus model-facing guidance for choosing which metrics to inspect."
        ),
        annotations=READ_ONLY,
    )
    def list_available_health_metrics() -> dict[str, Any]:
        return health_store.available_metrics(current_user_id())

    @mcp.tool(
        title="Query health metrics",
        description=(
            "Generic model-selected metric query. Use after list_available_health_metrics or "
            "get_health_question_clues when a question needs specific synced Google Health/Fitbit signals "
            "over a bounded date range."
        ),
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
        description=(
            "Pull the latest available cloud-synced Fitbit data from Google Health into the local user store. "
            "By default, skips redundant network syncs when data was already synced very recently; set force "
            "true only when the user explicitly asks to force a refresh now."
        ),
        annotations=SYNC,
    )
    async def sync_latest_fitbit_data(force: bool = False) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return await health_store.sync_latest(user_id, force=force)

    @mcp.tool(
        title="Sync and get health overview",
        description=(
            "Use only when the user explicitly asks to sync, refresh, pull, or update Fitbit/Google "
            "Health data now and then summarize, analyze all available health metrics, explain what "
            "changed, or recommend today's intensity. Runs one sync, then returns a card-ready "
            "all-data overview with sync freshness. For normal current/latest/today questions, use "
            "get_health_overview instead because it is faster and includes freshness metadata. Leave force "
            "false unless the user explicitly asks to force a refresh."
        ),
        annotations=SYNC,
        meta=WIDGET_META,
    )
    async def sync_and_get_health_overview(days: int = 14, force: bool = False) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()

        sync = await health_store.sync_latest(user_id, force=force)
        if sync.get("status") != "ok":
            return sync

        overview = health_store.health_overview(user_id, max(1, min(days, 30)))
        if overview.get("status") != "ok":
            return overview

        overview["fresh_sync"] = {
            "status": sync.get("status"),
            "message": sync.get("message"),
            "sync_skipped": sync.get("sync_skipped", False),
            "skip_reason": sync.get("skip_reason"),
            "records_upserted": sync.get("records_upserted"),
            "total_records": sync.get("total_records"),
            "partial_sync": sync.get("partial_sync", False),
            "time_budget_exhausted": sync.get("time_budget_exhausted", False),
            "metrics_synced": sync.get("metrics_synced", []),
            "metrics_fetched": sync.get("metrics_fetched", []),
            "metrics_considered": sync.get("metrics_considered", []),
            "metrics_deferred": sync.get("metrics_deferred", []),
            "metric_errors": sync.get("metric_errors", []),
            "elapsed_seconds": sync.get("elapsed_seconds"),
            "sync_diagnostics": sync.get("sync_diagnostics", {}),
            "lookback_days": sync.get("lookback_days"),
            "sync_window": sync.get("sync_window"),
            "freshness": sync.get("freshness"),
        }
        return overview

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
    )
    def get_today_context() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.latest_context(user_id)

    @mcp.tool(
        title="Health overview",
        description=(
            "Fast path for current/latest/today health and fitness questions using already-synced "
            "local Google Health/Fitbit data. Returns an all-data coaching overview across readiness, "
            "activity, sleep, heart, recovery, workouts, goals, check-ins, data coverage, freshness, "
            "and concrete next actions without starting a sync."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_health_overview(days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.health_overview(user_id, max(1, min(days, 30)))

    @mcp.tool(
        title="Recovery readiness",
        description="Return a readiness score with evidence from sleep, HRV, resting heart rate, and activity load.",
        annotations=READ_ONLY,
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
        title="Health question clues",
        description=(
            "For a user's natural-language health, recovery, sleep, heart, soreness, or workout question, "
            "identify likely intents, the best synced Fitbit metrics to inspect, clues already visible "
            "from overview data, and recommended follow-up tools."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_health_question_clues(question: str, days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.health_question_clues(user_id, question, max(1, min(days, 30)))

    @mcp.tool(
        title="Recovery signal comparison",
        description=(
            "Compare recent sleep, HRV, resting heart rate, respiratory/SpO2 context, and activity load "
            "against baseline to explain recovery patterns."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_recovery_signal_comparison(days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.recovery_signal_comparison(user_id, max(1, min(days, 30)))

    @mcp.tool(
        title="Recommend workout today",
        description=(
            "Fast, card-ready answer for normal day-of coaching questions like 'I feel off, should I "
            "work out?', 'how hard should I train today?', or 'what should I do today?'. Uses already-"
            "synced Fitbit context, goals, check-ins, recent workouts, and the optional current_feeling "
            "text. Does not start a sync."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def recommend_workout_today(
        current_feeling: Annotated[
            str | None,
            Field(
                description=(
                    "The user's current plain-language feeling, symptoms, soreness, energy, time limit, "
                    "or concern, for example 'I feel a little off but want to work out'."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return workout_recommendation(
            context=health_store.latest_context(user_id),
            goal=health_store.latest_goal(user_id),
            checkins=health_store.recent_checkins(user_id),
            workout_history=health_store.workout_history(user_id, 7),
            current_feeling=current_feeling,
        )

    @mcp.tool(
        title="Plan workout with health context",
        description=(
            "Plan a specific upcoming workout, sport session, or muscle-group day using synced "
            "sleep, HRV, resting heart rate, activity load, goals, check-ins, and user-stated constraints."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def plan_workout_with_health_context(
        planned_activity: str,
        target_areas: list[str] | None = None,
        planned_date: str | None = None,
        constraints: str | None = None,
        duration_minutes: int | None = None,
    ) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        context = health_store.health_overview(user_id, 14)
        if context.get("status") != "ok":
            return context
        return workout_plan_for_activity(
            context=context,
            planned_activity=planned_activity,
            target_areas=target_areas or [],
            planned_date=planned_date,
            constraints=constraints,
            duration_minutes=duration_minutes,
            goal=health_store.latest_goal(user_id),
            checkins=health_store.recent_checkins(user_id),
        )

    @mcp.tool(
        title="Guide active workout",
        description=(
            "Give in-session continue/hold-steady/downshift/stop guidance using live user-reported "
            "heart rate, RPE, pain, symptoms, elapsed time, and the latest synced Fitbit "
            "readiness/load context. Use this for during-workout prompts like 'HR 150, RPE 7, "
            "pain 0/10, should I push or back off?'; it returns the active workout card."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def guide_active_workout(
        planned_activity: str,
        current_heart_rate_bpm: int | None = None,
        current_rpe: int | None = None,
        pain_level: int | None = None,
        symptoms: str | None = None,
        elapsed_minutes: int | None = None,
        planned_duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        context = health_store.latest_context(user_id)
        if context.get("status") != "ok":
            return context
        return active_workout_guidance(
            context=context,
            planned_activity=planned_activity,
            current_heart_rate_bpm=current_heart_rate_bpm,
            current_rpe=current_rpe,
            pain_level=pain_level,
            symptoms=symptoms,
            elapsed_minutes=elapsed_minutes,
            planned_duration_minutes=planned_duration_minutes,
            notes=notes,
            goal=health_store.latest_goal(user_id),
            checkins=health_store.recent_checkins(user_id),
        )

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
        connected_user_id: str | None = None

        def capture_connected_user(user_id: str) -> None:
            nonlocal connected_user_id
            connected_user_id = user_id

        response = await auth_service.google_callback(
            request,
            on_connected=capture_connected_user,
        )
        if connected_user_id and settings.sync_on_connect and 300 <= response.status_code < 400:
            response.background = BackgroundTask(
                health_store.sync_latest,
                connected_user_id,
                force=False,
            )
        return response

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

    async def widget_preview(request: Request) -> Response:
        state = request.query_params.get("state", "health-clues")
        if state not in WIDGET_PREVIEW_STATES:
            return JSONResponse(
                {
                    "status": "not_found",
                    "message": "Unknown widget preview state.",
                    "available_states": sorted(WIDGET_PREVIEW_STATES),
                },
                status_code=404,
            )
        return HTMLResponse(widget_preview_html(state))

    app.add_route("/", home, methods=["GET"])
    app.add_route("/health", health, methods=["GET"])
    app.add_route("/.well-known/oauth-authorization-server", oauth_metadata, methods=["GET"])
    app.add_route("/.well-known/openid-configuration", oauth_metadata, methods=["GET"])
    app.add_route("/oauth/register", register_client, methods=["POST"])
    app.add_route("/oauth/authorize", authorize, methods=["GET"])
    app.add_route("/oauth/token", token, methods=["POST"])
    app.add_route("/oauth/callback/google", google_callback, methods=["GET"])
    app.add_route("/docs/setup", setup_doc, methods=["GET"])
    app.add_route("/docs/widget-preview", widget_preview, methods=["GET"])

    return ServerBundle(
        settings=settings,
        db=db,
        auth_service=auth_service,
        health_store=health_store,
        mcp=mcp,
        app=app,
    )


def workout_recommendation(
    context: dict[str, Any],
    goal: dict[str, Any] | None = None,
    checkins: list[dict[str, Any]] | None = None,
    workout_history: dict[str, Any] | None = None,
    current_feeling: str | None = None,
) -> dict[str, Any]:
    if context.get("status") != "ok":
        return context
    readiness = context["readiness"]
    label = readiness.get("label")
    today = context.get("today", {})
    sleep_hours = _sleep_hours_from_context(context)
    hrv_ms = _hrv_ms_from_context(context)
    resting_heart_rate = _resting_heart_rate_from_context(context)
    activity_date, recovery_date = _context_dates(context)
    freshness = context.get("data_freshness", {})
    current_feeling_text = (current_feeling or "").strip()
    current_feeling_lower = current_feeling_text.lower()
    stated_energy = _rating_from_text(current_feeling_lower, ("energy", "energy level"))
    stated_soreness = _rating_from_text(current_feeling_lower, ("soreness", "sore", "tightness", "tight"))
    stated_pain = _rating_from_text(current_feeling_lower, ("pain", "ache", "tightness", "tight"))
    subjective_limiter = _subjective_limiter_from_text(current_feeling_lower)
    soreness_rating = _first_present(stated_soreness, stated_pain, _latest_rating(checkins or [], "soreness"))
    energy_rating = _first_present(stated_energy, _latest_rating(checkins or [], "energy"))
    stress_rating = _latest_rating(checkins or [], "stress")
    illness_flags = _dedupe(_illness_flags_from_text(current_feeling_lower) + _illness_flags_from_checkins(checkins or []))
    workout_summary = (workout_history or {}).get("summary", {}) if (workout_history or {}).get("status") == "ok" else {}
    workout_count = int(workout_summary.get("workout_count") or 0)
    goal_payload = (goal or {}).get("goal") or {}
    goal_status = _goal_status(goal_payload, workout_count)
    context_gaps = _workout_context_gaps(checkins or [], goal_status, has_current_feeling=bool(current_feeling_text))

    if label == "green":
        plan = "Train normally: strength, intervals, or a full session are reasonable if your body agrees."
        intensity = "moderate-to-hard"
        rpe_cap = 8
    elif label == "yellow":
        plan = "Keep it controlled: zone 2 cardio, technique work, or submax strength."
        intensity = "moderate"
        rpe_cap = 7
    else:
        plan = "Make today recovery-biased: walking, mobility, breath work, and an earlier bedtime."
        intensity = "easy"
        rpe_cap = 6

    next_actions = []
    avoid = []
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        next_actions.append("Sync latest Fitbit data before making a time-sensitive hard training decision.")
        plan = f"{freshness.get('recommendation', 'Sync latest Fitbit data first')} Based on stored data only: {plan}"
    if subjective_limiter:
        if label == "green":
            plan = (
                "Do a controlled, useful session today. Your recovery signals support training, "
                "but because you do not feel fully right, do enough to feel better, not something "
                "you have to survive. Let the first 10-15 minutes decide whether to continue."
            )
        else:
            plan += (
                " Since you do not feel fully right, do enough to feel better, not something you "
                "have to survive. Let the warm-up decide whether to continue."
            )
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
        next_actions.append("Use the first 10-15 minutes as a pass/fail readiness screen before doing any hard work.")
        avoid.append("Turning a not-100% day into a max-effort or high-volume session")
    if today.get("active_zone_minutes", 0) > 45:
        plan += " You already have a high zone-minute load today, so avoid stacking another hard effort."
        avoid.append("Another hard conditioning block today")
        rpe_cap = min(rpe_cap, 7)
    if sleep_hours is not None and sleep_hours < 5:
        plan += " Keep impact low because the latest sleep block was short."
        avoid.append("High-impact or max-effort work on short sleep")
        rpe_cap = min(rpe_cap, 6)
    if soreness_rating and soreness_rating >= 7:
        plan += f" Your soreness check-in is high at {soreness_rating}/10, so bias toward recovery or pain-free technique."
        intensity = "easy"
        rpe_cap = min(rpe_cap, 6)
        avoid.append("Loading sore areas aggressively")
    elif soreness_rating and soreness_rating >= 5:
        plan += f" Your soreness check-in is moderate at {soreness_rating}/10, so keep 2-3 reps in reserve."
        intensity = "moderate" if intensity == "moderate-to-hard" else intensity
        rpe_cap = min(rpe_cap, 7)
    if energy_rating and energy_rating <= 4:
        plan += f" Energy is low at {energy_rating}/10, so use the first 10 minutes as a readiness check."
        rpe_cap = min(rpe_cap, 6)
    if stress_rating and stress_rating >= 7:
        plan += f" Stress is high at {stress_rating}/10, so keep the session predictable and avoid all-out work."
        rpe_cap = min(rpe_cap, 7)
    if illness_flags:
        plan += " Illness signs override normal training pressure: skip hard work and use rest or only very easy movement if symptoms are mild."
        intensity = "easy"
        rpe_cap = min(rpe_cap, 4)
        avoid.append("High-intensity training while sick, feverish, or flu-like symptoms are present")

    if goal_status.get("remaining_sessions") is not None:
        if goal_status["remaining_sessions"] > 0 and intensity != "easy":
            next_actions.append(
                f"Count today toward your weekly goal with a controlled session; {goal_status['remaining_sessions']} session(s) remain."
            )
        elif goal_status["remaining_sessions"] > 0:
            next_actions.append(
                f"You are {goal_status['remaining_sessions']} session(s) from the weekly target, but recovery signals make an easy day smarter."
            )
        else:
            next_actions.append("Weekly workout target is already covered; prioritize quality and recovery.")
    if context_gaps and intensity in {"moderate", "moderate-to-hard"}:
        next_actions.append("Before hard work, tell me your energy, soreness, stress, and pain right now.")

    if intensity == "moderate-to-hard":
        primary_action = "Train normally, but stop before form or breathing feels unusual."
    elif intensity == "moderate":
        primary_action = "Do a controlled session: zone 2, technique, or submax strength."
    else:
        primary_action = "Make today recovery-biased: walk, mobility, easy cardio, or rest."
    if illness_flags:
        primary_action = "Rest today, or keep movement to a short easy walk if symptoms are mild and improving."
    next_actions.insert(1 if freshness.get("needs_sync_before_time_sensitive_advice") else 0, primary_action)
    evidence = _workout_evidence(
        context=context,
        readiness=readiness,
        today=today,
        freshness=freshness,
        soreness_rating=soreness_rating,
        energy_rating=energy_rating,
        stress_rating=stress_rating,
        illness_flags=illness_flags,
        current_feeling=current_feeling_text,
        subjective_limiter=subjective_limiter,
        goal_status=goal_status,
        workout_summary=workout_summary,
    )
    stop_conditions = _workout_stop_conditions(
        rpe_cap,
        subjective_limiter=subjective_limiter,
        illness_flags=illness_flags,
    )
    deduped_next_actions = _dedupe(next_actions)
    deduped_avoid = _dedupe(avoid)
    coach_response = _today_workout_coach_response(
        intensity=intensity,
        rpe_cap=rpe_cap,
        readiness=readiness,
        next_actions=deduped_next_actions,
        evidence=evidence,
        avoid=deduped_avoid,
        stop_conditions=stop_conditions,
        subjective_limiter=subjective_limiter,
        illness_flags=illness_flags,
    )

    return {
        "status": "ok",
        "intensity": intensity,
        "rpe_cap": rpe_cap,
        "recommendation": plan,
        "next_actions": deduped_next_actions,
        "stop_conditions": stop_conditions,
        "avoid": deduped_avoid,
        "latest_date": context.get("latest_date"),
        "activity_date": activity_date,
        "recovery_date": recovery_date,
        "today": today,
        "why": evidence,
        "evidence": evidence,
        "context_gaps": context_gaps,
        "goal_context": goal_status,
        "subjective_context": {
            "energy": energy_rating,
            "soreness": soreness_rating,
            "stress": stress_rating,
            "illness_flags": illness_flags,
            "current_feeling": current_feeling_text or None,
            "subjective_limiter": subjective_limiter,
            "latest_checkins": checkins or [],
        },
        "workout_history_summary": workout_summary or None,
        "data_freshness": freshness,
        "data_used": {
            "activity_date": activity_date,
            "recovery_date": recovery_date,
            "steps_today": today.get("steps", 0),
            "active_minutes_today": today.get("active_minutes", 0),
            "active_zone_minutes_today": today.get("active_zone_minutes", 0),
            "latest_sleep_hours": sleep_hours,
            "resting_heart_rate": resting_heart_rate,
            "hrv_ms": hrv_ms,
            "energy_checkin": energy_rating,
            "soreness_checkin": soreness_rating,
            "stress_checkin": stress_rating,
            "current_feeling": current_feeling_text or None,
            "subjective_limiter": subjective_limiter,
            "stated_energy": stated_energy,
            "stated_soreness": stated_soreness,
            "stated_pain": stated_pain,
            "illness_flags": illness_flags,
            "goal": goal,
            "recent_workouts": workout_count,
            "freshness_level": freshness.get("freshness_level"),
        },
        "readiness": readiness,
        "coach_response": coach_response,
        "context": context,
        "safety_note": "This is fitness coaching context, not medical advice.",
    }


def workout_plan_for_activity(
    context: dict[str, Any],
    planned_activity: str,
    target_areas: list[str],
    planned_date: str | None = None,
    constraints: str | None = None,
    duration_minutes: int | None = None,
    goal: dict[str, Any] | None = None,
    checkins: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if context.get("status") != "ok":
        return context

    readiness = context["readiness"]
    today = context.get("today", {})
    latest_load = today.get("latest_training_load", {})
    sleep_hours = _sleep_hours_from_context(context)
    sleep_sessions = _sleep_sessions_from_context(context)
    hrv_ms = _hrv_ms_from_context(context)
    resting_heart_rate = _resting_heart_rate_from_context(context)
    activity_date, recovery_date = _context_dates(context)
    planned = " ".join([planned_activity or "", " ".join(target_areas or [])]).lower()
    constraint_text = (constraints or "").lower()
    all_context_text = " ".join([planned, constraint_text])
    readiness_label = readiness.get("label", "pending")
    readiness_score = int(readiness.get("score", 0))
    stated_energy = _rating_from_text(constraint_text, ("energy", "energy level"))
    stated_soreness = _rating_from_text(constraint_text, ("soreness", "sore", "tightness", "tight"))
    stated_pain = _rating_from_text(constraint_text, ("pain", "ache", "tightness", "tight"))
    subjective_limiter = _subjective_limiter_from_text(constraint_text)
    soreness_rating = _first_present(stated_soreness, stated_pain, _latest_rating(checkins or [], "soreness"))
    energy_rating = _first_present(stated_energy, _latest_rating(checkins or [], "energy"))
    illness_flags = _dedupe(_illness_flags_from_text(all_context_text) + _illness_flags_from_checkins(checkins or []))
    has_soreness_constraint = _has_training_pain_constraint(constraint_text)
    spinal_constraint = _mentions(
        constraint_text,
        (
            "low back",
            "lower back",
            "back pain",
            "back sore",
            "back soreness",
            "back ache",
            "back tight",
            "hip pain",
            "hip sore",
            "hip ache",
        ),
    )
    preserving_next_session = _mentions_upcoming_session(constraint_text)

    intensity = _base_intensity(readiness_label)
    rpe_cap = {"easy": 6, "moderate": 7, "moderate-to-hard": 8}.get(intensity, 6)
    limiting_factors = _normalized_readiness_evidence(context)
    if soreness_rating and soreness_rating >= 7:
        intensity = "easy"
        rpe_cap = min(rpe_cap, 6)
        limiting_factors.append(f"Latest soreness check-in is high at {soreness_rating}/10.")
    elif soreness_rating and soreness_rating >= 5:
        intensity = "moderate" if intensity == "moderate-to-hard" else intensity
        rpe_cap = min(rpe_cap, 7)
        limiting_factors.append(f"Latest soreness check-in is moderate at {soreness_rating}/10.")
    if has_soreness_constraint:
        rpe_cap = min(rpe_cap, 7)
        limiting_factors.append("User-stated soreness or pain should cap loading and volume.")
    if stated_pain is not None:
        limiting_factors.append(f"User-stated pain or tightness is {stated_pain}/10.")
    if spinal_constraint:
        rpe_cap = min(rpe_cap, 7)
        limiting_factors.append("User-stated lower-back or hip constraint should cap spinal loading.")
    if energy_rating is not None:
        if energy_rating <= 4:
            if intensity == "moderate-to-hard":
                intensity = "moderate"
            elif intensity == "moderate":
                intensity = "easy"
            rpe_cap = min(rpe_cap, 6)
            limiting_factors.append(f"User-stated energy is low at {energy_rating}/10.")
        elif energy_rating >= 7:
            limiting_factors.append(f"User-stated energy is strong at {energy_rating}/10.")
    if subjective_limiter:
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
        limiting_factors.append("User-stated they do not feel 100%, so the session should be useful but conservative.")
    if preserving_next_session:
        rpe_cap = min(rpe_cap, 6)
        limiting_factors.append("User wants to preserve readiness for another sport or workout soon.")
    if latest_load.get("active_zone_minutes", 0) > 45:
        rpe_cap = min(rpe_cap, 7)
    if illness_flags:
        intensity = "easy"
        rpe_cap = min(rpe_cap, 4)
        limiting_factors.extend(illness_flags)

    focus, avoid, warmup, session = _activity_guidance(all_context_text, rpe_cap, intensity)
    exercise_blocks, substitutions = _exercise_prescription(
        all_context_text,
        rpe_cap,
        readiness_label,
        spinal_constraint,
    )
    if duration_minutes:
        session.append(f"Keep the session near {max(15, min(duration_minutes, 120))} minutes including warm-up.")
    if subjective_limiter:
        focus.insert(0, "Make this a minimum useful session, not a proving-ground session.")
        session.insert(0, "Use the first 10-15 minutes as a pass/fail readiness screen before adding intensity.")
        avoid.append("Chasing PRs, extra finishers, or high-volume work on a not-100% day")
    if preserving_next_session:
        session.append("Leave the session feeling fresher than you started so tomorrow's sport session stays available.")
        avoid.append("Extra finishers that steal from tomorrow's squash or sport session")
    if readiness_label == "red":
        session.insert(0, "Do not chase PRs; keep every compound lift 3-4 reps in reserve.")
    elif readiness_label == "yellow":
        session.insert(0, "Use a controlled session and stop 2-3 reps before failure.")
    else:
        session.insert(0, "A normal session is reasonable if warm-up movement feels good.")
    if illness_flags:
        session.insert(
            0,
            "Do not train hard while illness signs are present; choose rest, fluids, and only easy movement if symptoms are mild.",
        )
        focus.insert(0, "Treat symptoms as the limiter even if wearable readiness is not red.")
        avoid.insert(0, "Sweat-it-out workouts, intervals, heavy sets, or long sessions while sick.")

    display_activity = _display_workout_activity(planned_activity, intensity)
    planned_date_text = planned_date or "next planned session"
    summary = (
        f"For {planned_date_text}, keep {display_activity} at {intensity} intensity "
        f"({_intensity_plain(intensity)}) with an RPE cap around {rpe_cap}/10 "
        f"({_rpe_plain(rpe_cap)})."
    )
    if readiness_label == "red":
        summary += " Treat this as a quality/recovery-biased session because recovery signals are red."
    if illness_flags:
        summary += " Illness signs should override the workout plan until symptoms are clearly improving."
    stop_conditions = _workout_stop_conditions(
        rpe_cap,
        subjective_limiter=subjective_limiter,
        illness_flags=illness_flags,
    )
    deduped_limiting_factors = _dedupe(limiting_factors)
    deduped_avoid = _dedupe(avoid)
    deduped_substitutions = _dedupe(substitutions)
    coach_response = _workout_plan_coach_response(
        display_activity=display_activity,
        summary=summary,
        intensity=intensity,
        rpe_cap=rpe_cap,
        readiness=readiness,
        focus=focus,
        warmup=warmup,
        session=session,
        exercise_blocks=exercise_blocks,
        limiting_factors=deduped_limiting_factors,
        avoid=deduped_avoid,
        substitutions=deduped_substitutions,
        subjective_limiter=subjective_limiter,
        preserving_next_session=preserving_next_session,
        illness_flags=illness_flags,
        stop_conditions=stop_conditions,
    )

    return {
        "status": "ok",
        "planned_activity": display_activity,
        "planned_activity_raw": planned_activity,
        "planned_date": planned_date,
        "target_areas": target_areas,
        "constraints": constraints,
        "summary": summary,
        "recommended_intensity": intensity,
        "rpe_cap": rpe_cap,
        "readiness": readiness,
        "focus": focus,
        "warmup": warmup,
        "exercise_blocks": exercise_blocks,
        "session_guidance": session,
        "avoid": deduped_avoid,
        "substitutions": deduped_substitutions,
        "progression_rules": [
            "If warm-up raises pain, heaviness, dizziness, or unusual breathlessness, downshift or stop.",
            "If HRV and resting heart rate rebound and sleep improves, progress load or volume next session.",
            "If recovery stays red for two straight days, bias toward zone 2, mobility, or a full rest day.",
        ],
        "stop_conditions": stop_conditions,
        "limiting_factors": deduped_limiting_factors,
        "data_used": {
            "activity_date": activity_date,
            "recovery_date": recovery_date,
            "readiness_score": readiness_score,
            "readiness_label": readiness_label,
            "sleep_asleep_hours": sleep_hours,
            "sleep_sessions": sleep_sessions,
            "hrv_ms": hrv_ms,
            "resting_heart_rate": resting_heart_rate,
            "steps": today.get("steps", 0),
            "active_minutes": today.get("active_minutes", 0),
            "active_zone_minutes": today.get("active_zone_minutes", 0),
            "latest_training_load": latest_load,
            "energy_checkin": energy_rating,
            "soreness_checkin": soreness_rating,
            "stated_energy": stated_energy,
            "stated_soreness": stated_soreness,
            "stated_pain": stated_pain,
            "subjective_limiter": subjective_limiter,
            "illness_flags": illness_flags,
            "preserving_next_session": preserving_next_session,
            "goal": goal,
        },
        "questions_to_ask_if_uncertain": [
            "Any pain above 3/10 during warm-up?",
            "Did sleep feel restorative despite the wearable score?",
            "Is the planned workout performance-focused, maintenance, or just keeping the habit?",
        ],
        "coach_response": coach_response,
        "safety_note": "This is fitness coaching context, not medical advice.",
        "context": context,
    }


def active_workout_guidance(
    context: dict[str, Any],
    planned_activity: str,
    current_heart_rate_bpm: int | None = None,
    current_rpe: int | None = None,
    pain_level: int | None = None,
    symptoms: str | None = None,
    elapsed_minutes: int | None = None,
    planned_duration_minutes: int | None = None,
    notes: str | None = None,
    goal: dict[str, Any] | None = None,
    checkins: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if context.get("status") != "ok":
        return context

    readiness = context["readiness"]
    today = context.get("today", {})
    latest_load = today.get("latest_training_load", {})
    hrv_ms = _hrv_ms_from_context(context)
    resting_heart_rate = _resting_heart_rate_from_context(context)
    activity_date, recovery_date = _context_dates(context)
    readiness_label = readiness.get("label", "pending")
    readiness_score = int(readiness.get("score", 0))
    rpe = _bounded_rating(current_rpe)
    pain = _bounded_rating(pain_level, minimum=0)
    symptoms_text = " ".join([symptoms or "", notes or ""]).lower()
    safety_flags = _active_workout_safety_flags(symptoms_text, current_heart_rate_bpm, pain)
    evidence = list(readiness.get("evidence", []))
    if current_heart_rate_bpm is not None:
        evidence.append(f"Live heart rate reported: {current_heart_rate_bpm} bpm (HR = current beats per minute).")
    if rpe is not None:
        evidence.append(f"Live effort reported: RPE {rpe}/10 (RPE = how hard it feels).")
    if pain is not None:
        evidence.append(f"Live pain reported: {pain}/10.")
    if latest_load.get("active_zone_minutes") is not None:
        evidence.append(
            "Latest synced load before/during this decision: "
            f"{latest_load['active_zone_minutes']} Active Zone Minutes on {latest_load.get('date')} "
            "(AZM, Fitbit hard-work minutes)."
        )

    decision = "continue_controlled"
    headline = "Keep going only if form, breathing, and symptoms stay normal."
    immediate_actions = [
        "Keep the next block controlled and reassess in 5-10 minutes.",
        "Stay below the point where form, breathing, or coordination changes.",
    ]
    modifications = [
        "Hold intensity steady instead of chasing a new peak.",
        "Extend rest periods if heart rate or RPE is not settling.",
    ]
    avoid = ["Adding surprise max-effort work", "Ignoring new pain or unusual symptoms"]

    if safety_flags:
        decision = "stop_and_assess"
        headline = "Stop the hard work now and treat this as a safety check, not a training decision."
        immediate_actions = [
            "Stop the set or interval now and move to a safe seated or standing position.",
            "Do not resume hard training while these symptoms are present.",
            "Seek urgent medical care for chest pain, fainting, severe shortness of breath, or symptoms that are new, severe, or worsening.",
        ]
        modifications = ["If symptoms fully resolve and are mild, switch only to an easy cooldown or end the session."]
        avoid = ["Continuing intervals or heavy sets", "Trying to push through symptoms", "Driving yourself if you feel faint"]
    elif pain is not None and pain >= 7:
        decision = "stop_session"
        headline = "End the working session because pain is high."
        immediate_actions = [
            "Stop loading the painful area now.",
            "Switch to easy walking, gentle mobility, or end the workout.",
            "Consider clinical advice if pain is sharp, worsening, or changes how you move.",
        ]
        modifications = ["Do not test heavy variations today."]
        avoid = ["Loading through pain", "Ballistic movements", "More volume for the painful area"]
    elif "fever" in symptoms_text or "vomit" in symptoms_text or "flu" in symptoms_text:
        decision = "stop_session"
        headline = "End the workout; illness signs make training riskier today."
        immediate_actions = [
            "Stop the workout and prioritize fluids, food as tolerated, and rest.",
            "Resume training only after symptoms improve and normal daily movement feels okay.",
        ]
        modifications = ["Use rest or very easy mobility instead of conditioning."]
        avoid = ["High intensity while sick", "Sweat-it-out workouts"]
    elif (rpe is not None and rpe >= 9) or (current_heart_rate_bpm is not None and current_heart_rate_bpm >= 190):
        decision = "downshift_now"
        headline = "Downshift now; the session is running near the ceiling."
        immediate_actions = [
            "Take 3-5 minutes easy and wait for breathing and heart rate to settle.",
            "Resume only at a lower intensity if coordination and symptoms feel normal.",
        ]
        modifications = ["Cut the next block by 25-50% or switch to zone 2."]
        avoid = ["Another all-out interval", "Heavy work before heart rate settles"]
    elif pain is not None and pain >= 4:
        decision = "modify"
        headline = "Modify the workout around pain before it escalates."
        immediate_actions = [
            "Reduce load, range of motion, speed, or impact now.",
            "Keep pain at or below 3/10 or stop that movement.",
        ]
        modifications = ["Choose a pain-free variation or switch muscle groups."]
        avoid = ["Repeated reps that increase pain", "Testing max range under load"]
    elif readiness_label == "red" or latest_load.get("active_zone_minutes", 0) > 45:
        decision = "downshift_now"
        headline = "Keep this session recovery-biased because synced recovery/load context is constrained."
        immediate_actions = [
            "Keep the rest of the session easy to moderate.",
            "Skip finishers and leave the session with energy in reserve.",
        ]
        modifications = ["Reduce volume or intensity by 25-50%."]
        avoid = ["Hard finishers", "PR attempts", "Extra conditioning"]

    if planned_duration_minutes and elapsed_minutes and elapsed_minutes >= planned_duration_minutes:
        immediate_actions.append("You have reached the planned duration; cool down instead of extending the session.")
        avoid.append("Extending the workout just because momentum feels good")
    deduped_immediate_actions = _dedupe(immediate_actions)
    deduped_modifications = _dedupe(modifications)
    deduped_avoid = _dedupe(avoid)
    deduped_evidence = _dedupe(evidence)
    coach_response = _active_workout_coach_response(
        decision=decision,
        headline=headline,
        immediate_actions=deduped_immediate_actions,
        modifications=deduped_modifications,
        avoid=deduped_avoid,
        safety_flags=safety_flags,
        evidence=deduped_evidence,
        readiness=readiness,
        rpe=rpe,
        current_heart_rate_bpm=current_heart_rate_bpm,
        pain=pain,
    )

    return {
        "status": "ok",
        "guidance_type": "active_workout_guidance",
        "planned_activity": planned_activity,
        "decision": decision,
        "headline": headline,
        "immediate_actions": deduped_immediate_actions,
        "modifications": deduped_modifications,
        "avoid": deduped_avoid,
        "safety_flags": safety_flags,
        "evidence": deduped_evidence,
        "readiness": readiness,
        "goal_context": (goal or {}).get("goal"),
        "recent_checkins": checkins or [],
        "live_inputs": {
            "current_heart_rate_bpm": current_heart_rate_bpm,
            "current_rpe": rpe,
            "pain_level": pain,
            "symptoms": symptoms,
            "elapsed_minutes": elapsed_minutes,
            "planned_duration_minutes": planned_duration_minutes,
            "notes": notes,
        },
        "data_used": {
            "activity_date": activity_date,
            "recovery_date": recovery_date,
            "readiness_score": readiness_score,
            "readiness_label": readiness_label,
            "latest_training_load": latest_load,
            "resting_heart_rate": resting_heart_rate,
            "hrv_ms": hrv_ms,
        },
        "questions_to_ask_if_uncertain": [
            "Are symptoms new, severe, or getting worse?",
            "Is pain sharp, localized, or changing your movement?",
            "Does heart rate settle after 3-5 minutes easy?",
        ],
        "coach_response": coach_response,
        "safety_note": "This is in-session fitness guidance, not medical diagnosis or emergency care.",
        "context": context,
    }


def _base_intensity(label: str) -> str:
    if label == "green":
        return "moderate-to-hard"
    if label == "yellow":
        return "moderate"
    return "easy"


def _goal_status(goal_payload: dict[str, Any], workout_count: int) -> dict[str, Any]:
    days_per_week = goal_payload.get("days_per_week")
    remaining = None
    if days_per_week is not None:
        try:
            target = max(0, int(days_per_week))
            remaining = max(0, target - workout_count)
        except (TypeError, ValueError):
            target = None
    else:
        target = None
    return {
        "goal_type": goal_payload.get("goal_type"),
        "target": goal_payload.get("target"),
        "days_per_week": target,
        "recent_workouts": workout_count,
        "remaining_sessions": remaining,
        "notes": goal_payload.get("notes"),
    }


def _coach_metric_glossary(labels: list[str] | tuple[str, ...] | None = None) -> list[dict[str, str]]:
    selected = labels or ("Readiness", "RPE", "HRV", "Resting HR", "AZM")
    return [
        {"label": label, "meaning": METRIC_LABEL_EXPLANATIONS[label]}
        for label in selected
        if label in METRIC_LABEL_EXPLANATIONS
    ]


def _coach_data_story(readiness: dict[str, Any], evidence: list[str]) -> str:
    label = readiness.get("label")
    evidence_items = [str(item).lower() for item in evidence]
    constraints: list[str] = []
    supports: list[str] = []

    sleep_items = [item for item in evidence_items if "sleep" in item]
    hrv_items = [item for item in evidence_items if "hrv" in item]
    resting_items = [item for item in evidence_items if "resting" in item or "rhr" in item]
    load_items = [
        item
        for item in evidence_items
        if "active zone minutes" in item or "training load" in item or "zone minutes" in item
    ]
    freshness_items = [item for item in evidence_items if "data freshness" in item or "sync latest" in item]
    checkin_items = [item for item in evidence_items if "check-in" in item]
    safety_items = [
        item
        for item in evidence_items
        if "medical caution" in item
        or "urgent care" in item
        or "reported symptoms" in item
        or "dizzy" in item
        or "dizziness" in item
    ]
    illness_items = [
        item
        for item in evidence_items
        if item.startswith("illness symptoms")
        or (
            item.startswith("current user-stated feeling")
            and any(term in item for term in ("fever", "chills", "flu", "sore throat", "vomit", "nausea"))
        )
    ]
    subjective_items = [
        item
        for item in evidence_items
        if "do not feel fully right" in item or "not feel 100" in item or "current user-stated feeling" in item
    ]
    preserve_items = [
        item
        for item in evidence_items
        if "preserve readiness" in item or "preserve" in item or "another sport" in item or "tomorrow" in item
    ]

    if safety_items:
        constraints.append("live symptoms override the workout plan")
    if illness_items:
        constraints.append("symptoms override the wearable score")
    if any("stale" in item or "sync latest" in item for item in freshness_items):
        constraints.append("data needs a fresh sync before a hard call")

    if any("short" in item or "below" in item for item in sleep_items):
        constraints.append("sleep is limiting recovery")
    elif any("strong" in item or "supportive" in item or "above" in item for item in sleep_items):
        supports.append("sleep supports training")

    if any("below" in item or "suppressed" in item or "lagging" in item for item in hrv_items):
        constraints.append("HRV is lower than usual")
    elif any("above" in item for item in hrv_items):
        supports.append("HRV is above usual")

    if any("elevated" in item or "above recent average" in item for item in resting_items):
        constraints.append("Resting HR is elevated")
    elif any("steady" in item or "below recent average" in item or "not elevated" in item for item in resting_items):
        supports.append("Resting HR is calm")

    if load_items:
        load_values: list[int] = []
        for item in load_items:
            for match in re.finditer(r"(\d+)\s+(?:active zone minutes|zone minutes)", item):
                load_values.append(int(match.group(1)))
        if any(value >= 45 for value in load_values) or any("high" in item for item in load_items):
            constraints.append("recent training load matters today")
        else:
            supports.append("recent load is manageable")

    limiting_checkins = any(
        "soreness check-in is high" in item
        or "soreness check-in is moderate" in item
        or "energy check-in is low" in item
        or "stress check-in is high" in item
        or re.search(r"energy check-in is [0-4]/10", item)
        or re.search(r"soreness check-in is [5-9]/10", item)
        or re.search(r"stress check-in is [7-9]/10", item)
        for item in checkin_items
    )
    if limiting_checkins:
        constraints.append("your check-in changes the plan")
    elif checkin_items:
        supports.append("your check-in supports training")
    if subjective_items:
        constraints.append("your current body feel caps the ceiling")
    if preserve_items:
        constraints.append("tomorrow's session is the priority")

    if constraints:
        return "The useful read: " + "; ".join(_dedupe(constraints)[:4]) + "."
    if supports:
        return "The useful read: " + "; ".join(_dedupe(supports)[:4]) + "."
    if label == "green":
        return "The useful read: recovery signals are supportive, so the warm-up decides how hard to go."
    if label == "yellow":
        return "The useful read: recovery is mixed, so useful controlled work beats max effort."
    return "The useful read: recovery signals are constrained, so the best workout is the one you recover from."


def _today_session_blueprint(
    *,
    intensity: str,
    rpe_cap: int,
    subjective_limiter: bool,
    illness_flags: list[str],
) -> list[str]:
    if illness_flags:
        return [
            "Today: skip hard training.",
            "If symptoms are mild and improving, do 10-20 minutes of easy walking or mobility only.",
            "End the session if symptoms worsen, breathing feels unusual, or energy drops.",
        ]

    if intensity == "easy":
        blueprint = [
            "Start with 10 minutes easy walking, cycling, or mobility to see if you feel better.",
            f"Then do 10-25 minutes easy movement at RPE <= {rpe_cap}/10; stop before it feels like work.",
            "Finish while you feel better than when you started.",
        ]
    elif intensity == "moderate":
        blueprint = [
            "Start with a 10-15 minute gradual warm-up.",
            f"Main work: 20-40 minutes of zone 2, technique, or submax strength at RPE <= {rpe_cap}/10.",
            "Cool down for 5 minutes and leave 2-3 reps or one more interval in reserve.",
        ]
    else:
        blueprint = [
            "Start with a 10-15 minute warm-up and check breathing, form, and pain.",
            f"Main work can be challenging, but keep the ceiling at RPE <= {rpe_cap}/10.",
            "Skip max attempts if the warm-up feels off; cool down before you feel cooked.",
        ]

    if subjective_limiter:
        blueprint.insert(
            1,
            "At 10-15 minutes, continue only if energy improves and pain, breathing, and heart rate feel normal.",
        )
    return _dedupe(blueprint)


def _workout_session_blueprint(
    *,
    warmup: list[str],
    session: list[str],
    focus: list[str],
    exercise_blocks: list[dict[str, Any]],
    rpe_cap: int,
    subjective_limiter: bool,
    illness_flags: list[str],
) -> list[str]:
    if illness_flags:
        return [
            "Do not do the planned workout hard today.",
            "Use rest, fluids, and at most very easy walking or mobility while symptoms are present.",
            "Come back to the plan after symptoms improve and normal daily movement feels okay.",
        ]

    blueprint: list[str] = []
    if warmup:
        blueprint.append(f"Warm-up: {warmup[0]}")
    else:
        blueprint.append("Warm-up: 10 minutes easy and only continue if movement feels better.")

    if subjective_limiter:
        blueprint.append("Readiness screen: after 10-15 minutes, continue only if you feel better, not worse.")

    block_names = _representative_exercise_names(exercise_blocks)
    if block_names:
        blueprint.append(f"Main work: {', '.join(block_names[:3])}; keep every set at RPE <= {rpe_cap}/10.")
    elif session:
        blueprint.append(session[0])
    elif focus:
        blueprint.append(focus[0])

    if len(session) > 1:
        blueprint.append(session[1])
    else:
        blueprint.append(f"Stop with energy in reserve; RPE stays <= {rpe_cap}/10.")

    if focus:
        blueprint.append(f"Main coaching cue: {focus[0]}")

    return _dedupe(blueprint)[:5]


def _representative_exercise_names(exercise_blocks: list[dict[str, Any]]) -> list[str]:
    names = [
        str(block.get("exercise"))
        for block in exercise_blocks
        if isinstance(block, dict) and block.get("exercise")
    ]
    if len(names) <= 3:
        return names

    lower_names = [(name, name.lower()) for name in names]

    def first_with(*terms: str) -> str | None:
        for name, lower in lower_names:
            if any(term in lower for term in terms):
                return name
        return None

    selected = [
        first_with("press", "chest"),
        first_with("row"),
        first_with("pulldown", "pull-up", "pullup"),
    ]
    selected = [name for name in selected if name]
    if len(selected) >= 2:
        return _dedupe(selected + names)
    return names


def _active_workout_next_check(
    *,
    decision: str,
    rpe: int | None,
    current_heart_rate_bpm: int | None,
    pain: int | None,
) -> list[str]:
    if decision in {"stop_and_assess", "stop_session"}:
        return [
            "Next 3-5 minutes: stop hard work, breathe normally, and let heart rate and symptoms settle.",
            "Do not restart hard training today if symptoms are new, severe, or return.",
            "Seek urgent help for chest pain, fainting, severe shortness of breath, or worsening symptoms.",
        ]
    if decision == "downshift_now":
        return [
            "Next 3-5 minutes: go easy until breathing and heart rate clearly settle.",
            "Resume only one level easier, and stop the hard work if RPE climbs back near the ceiling.",
            "Cut the next block by 25-50% or switch to zone 2.",
        ]
    if decision == "modify":
        return [
            "Next set: reduce load, range, speed, or impact before pain changes your form.",
            "Continue only if pain stays at 3/10 or lower.",
            "Switch movements if the same pain repeats.",
        ]

    checks = ["Next 5-10 minutes: hold steady instead of chasing a harder effort."]
    if rpe is not None:
        checks.append(f"Keep RPE at or below {min(max(rpe, 6), 8)}/10 unless the plan intentionally calls for more.")
    if current_heart_rate_bpm is not None:
        checks.append("Heart rate should rise and settle predictably for the work you are doing.")
    if pain is not None:
        checks.append("Pain stays 3/10 or lower and does not change your form.")
    return _dedupe(checks)


def _today_workout_coach_response(
    *,
    intensity: str,
    rpe_cap: int,
    readiness: dict[str, Any],
    next_actions: list[str],
    evidence: list[str],
    avoid: list[str],
    stop_conditions: list[str],
    subjective_limiter: bool,
    illness_flags: list[str],
) -> dict[str, Any]:
    evidence_text = " ".join(evidence).lower()
    has_stale_data = "data freshness is stale" in evidence_text or "sync latest fitbit data" in evidence_text
    if has_stale_data:
        short_answer = "Sync latest Fitbit data before a time-sensitive hard workout decision. If you train before syncing, keep it controlled."
    elif illness_flags:
        short_answer = "Skip hard training today. If symptoms are mild and improving, keep it to a short easy walk or mobility."
    elif intensity == "easy":
        short_answer = "Make today recovery-biased: useful movement is fine, but do not chase fitness today."
    elif intensity == "moderate":
        short_answer = "Do a controlled session that helps you feel better, not a workout you have to survive."
    else:
        short_answer = "Training is available today if the warm-up feels normal and your breathing, form, and pain stay calm."

    if subjective_limiter and not illness_flags:
        short_answer += " Because you do not feel fully right, let the first 10-15 minutes decide whether to continue."

    what_to_do = list(next_actions[:3])
    rpe_line = f"Keep RPE (how hard it feels) at or below {rpe_cap}/10, which means {_rpe_plain(rpe_cap)}."
    what_to_do.insert(1 if what_to_do else 0, rpe_line)
    session_blueprint = _today_session_blueprint(
        intensity=intensity,
        rpe_cap=rpe_cap,
        subjective_limiter=subjective_limiter,
        illness_flags=illness_flags,
    )

    return {
        "short_answer": short_answer,
        "data_story": _coach_data_story(readiness, evidence),
        "session_blueprint": session_blueprint,
        "what_to_do": _dedupe(what_to_do)[:5],
        "why": _humanized_evidence(evidence)[:6],
        "labels_explained": _coach_metric_glossary(),
        "stop_if": stop_conditions[:5],
        "avoid": avoid[:5],
        "answer_style": "Answer like a personal coach: direct recommendation first, then explain the kept metric labels in one short why section.",
        "realistic_follow_ups": [
            "I feel a little off today but still want to move. What is the safest useful session?",
            "Can I train hard today, or should I keep it controlled?",
            "What would make you tell me to stop during the workout?",
        ],
    }


def _workout_plan_coach_response(
    *,
    display_activity: str,
    summary: str,
    intensity: str,
    rpe_cap: int,
    readiness: dict[str, Any],
    focus: list[str],
    warmup: list[str],
    session: list[str],
    exercise_blocks: list[dict[str, Any]],
    limiting_factors: list[str],
    avoid: list[str],
    substitutions: list[str],
    subjective_limiter: bool,
    preserving_next_session: bool,
    illness_flags: list[str],
    stop_conditions: list[str],
) -> dict[str, Any]:
    if illness_flags:
        short_answer = f"For {display_activity}, keep this as rest or very easy movement until symptoms improve."
    elif preserving_next_session:
        short_answer = f"For {display_activity}, train controlled enough that tomorrow still stays available."
    elif intensity == "easy":
        short_answer = f"For {display_activity}, make the win leaving better than you started."
    elif intensity == "moderate":
        short_answer = f"For {display_activity}, do useful work, but keep the session controlled."
    else:
        short_answer = f"For {display_activity}, a normal session is reasonable if the warm-up feels good."

    if subjective_limiter and not illness_flags:
        short_answer += " This is a not-100% day, so treat the warm-up as the test."

    what_to_do = [
        summary,
        f"RPE (how hard it feels) cap: {rpe_cap}/10, which means {_rpe_plain(rpe_cap)}.",
        *session[:2],
        *focus[:2],
    ]
    session_blueprint = _workout_session_blueprint(
        warmup=warmup,
        session=session,
        focus=focus,
        exercise_blocks=exercise_blocks,
        rpe_cap=rpe_cap,
        subjective_limiter=subjective_limiter,
        illness_flags=illness_flags,
    )
    return {
        "short_answer": short_answer,
        "data_story": _coach_data_story(readiness, limiting_factors),
        "session_blueprint": session_blueprint,
        "what_to_do": _dedupe(what_to_do)[:5],
        "why": _humanized_evidence(limiting_factors)[:6],
        "labels_explained": _coach_metric_glossary(),
        "stop_if": stop_conditions[:5],
        "avoid": avoid[:5],
        "substitutions": substitutions[:5],
        "answer_style": "Keep the workout name and labels, but translate each label in simple words before giving the plan.",
        "realistic_follow_ups": [
            "I only have 30 minutes. What should I actually do?",
            "My legs feel heavy but I want to run. How should I adjust?",
            "Which part of this plan changes if my warm-up feels bad?",
        ],
    }


def _active_workout_coach_response(
    *,
    decision: str,
    headline: str,
    immediate_actions: list[str],
    modifications: list[str],
    avoid: list[str],
    safety_flags: list[str],
    evidence: list[str],
    readiness: dict[str, Any],
    rpe: int | None,
    current_heart_rate_bpm: int | None,
    pain: int | None,
) -> dict[str, Any]:
    if decision in {"stop_and_assess", "stop_session"}:
        short_answer = "Stop the hard part now. Treat this as a safety decision, not a toughness decision."
    elif decision == "downshift_now":
        short_answer = "Back off now. You can still get a useful session by lowering intensity and reassessing."
    elif decision == "modify":
        short_answer = "Modify the movement before it becomes a problem. Pain and form decide the workout now."
    else:
        short_answer = "Keep going only if breathing, form, pain, and symptoms stay normal."

    live_labels = ["RPE", "AZM", "Readiness"]
    if current_heart_rate_bpm is not None:
        live_labels.insert(0, "HR")
    if any("HRV" in item for item in evidence):
        live_labels.append("HRV")

    live_context = []
    if current_heart_rate_bpm is not None:
        live_context.append(f"HR (heart rate right now): {current_heart_rate_bpm} bpm.")
    if rpe is not None:
        live_context.append(f"RPE (how hard it feels): {rpe}/10, which means {_rpe_plain(rpe)}.")
    if pain is not None:
        live_context.append(f"Pain: {pain}/10. Keep it 3/10 or lower, or stop that movement.")

    return {
        "short_answer": short_answer,
        "data_story": _coach_data_story(readiness, safety_flags or evidence),
        "next_check": _active_workout_next_check(
            decision=decision,
            rpe=rpe,
            current_heart_rate_bpm=current_heart_rate_bpm,
            pain=pain,
        ),
        "what_to_do": _dedupe([headline, *immediate_actions, *modifications])[:5],
        "live_context": live_context,
        "why": _humanized_evidence(safety_flags or evidence)[:6],
        "labels_explained": _coach_metric_glossary(_dedupe(live_labels)),
        "stop_if": safety_flags[:5] or [
            "Stop if symptoms are new, severe, or worsening.",
            "Stop if heart rate or breathing does not settle after 3-5 easy minutes.",
            "Stop if pain rises above 3/10 or changes your form.",
        ],
        "avoid": avoid[:5],
        "answer_style": "Use urgent, plain language first; explain HR, RPE, AZM, and readiness only after the action is clear.",
    }


def _humanized_evidence(items: list[str]) -> list[str]:
    return _dedupe([_humanize_evidence_item(item) for item in items if item])


def _humanize_evidence_item(item: str) -> str:
    text = str(item)
    lower = text.lower()
    if "hrv" in lower:
        expanded = text if "recovery stress signal" in lower else text.replace("HRV", "HRV (recovery stress signal)")
        if "that supports" in lower or "recovery caution" in lower or "neutral-to-supportive" in lower:
            return expanded
        if "below" in lower or "suppressed" in lower or "lagging" in lower:
            return f"{expanded} Lower HRV than usual is a caution signal, so cap intensity."
        if "above" in lower:
            return f"{expanded} Higher HRV than usual supports training room if the warm-up feels good."
        return f"{expanded} Use it as recovery context, not as a standalone rule."
    if "resting heart rate" in lower or "resting hr" in lower or "rhr" in lower:
        expanded = text
        if "heart stress" not in lower:
            expanded = re.sub(
                r"\bResting heart rate\b",
                "Resting HR (resting heart rate; heart stress at rest)",
                expanded,
                flags=re.IGNORECASE,
            )
            expanded = re.sub(r"\bRHR\b", "RHR (resting heart rate)", expanded)
        if "can point" in lower or "supportive" in lower or "neutral recovery" in lower:
            return expanded
        if "elevated" in lower or "above" in lower:
            return f"{expanded} Elevated versus your usual can point to stress, illness, fatigue, or under-recovery."
        if not any(term in lower for term in ("below", "near", "steady")):
            return f"{expanded} Use it as heart-recovery context, not as a standalone rule."
        return f"{expanded} Not elevated versus your usual is a supportive recovery sign."
    if "active zone minutes" in lower:
        expanded = text if "hard-work minutes" in lower else text.replace(
            "Active Zone Minutes",
            "Active Zone Minutes (AZM, Fitbit hard-work minutes)",
        )
        if "high" in lower or "latest training load" in lower:
            return f"{expanded} More AZM means more recent training stress to account for."
        return expanded
    if "rpe" in lower:
        return text.replace("RPE", "RPE (how hard it feels)")
    if "sleep" in lower and ("short" in lower or "below" in lower):
        return f"{text} Short sleep should lower the ceiling for hard work."
    if "sleep" in lower and ("strong" in lower or "support" in lower or "above" in lower):
        return f"{text} Good sleep gives more room to train, as long as the warm-up agrees."
    if "check-in" in lower:
        return f"{text} Your own body report can override a good wearable score."
    return text


def _workout_evidence(
    *,
    context: dict[str, Any],
    readiness: dict[str, Any],
    today: dict[str, Any],
    freshness: dict[str, Any],
    soreness_rating: int | None,
    energy_rating: int | None,
    stress_rating: int | None,
    illness_flags: list[str],
    current_feeling: str | None,
    subjective_limiter: bool,
    goal_status: dict[str, Any],
    workout_summary: dict[str, Any],
) -> list[str]:
    evidence = _normalized_readiness_evidence(context)

    freshness_level = freshness.get("freshness_level")
    if freshness.get("needs_sync_before_time_sensitive_advice") or freshness_level in {"aging", "stale", "empty"}:
        level = freshness_level or freshness.get("freshness_label") or "not fresh"
        if freshness.get("freshness_label") and freshness.get("freshness_label") != level:
            level = f"{level} ({freshness['freshness_label']})"
        recommendation = freshness.get("recommendation") or "Sync latest Fitbit data before a time-sensitive decision."
        evidence.append(f"Data freshness is {level}: {recommendation}")

    latest_load = today.get("latest_training_load") or {}
    latest_load_minutes = latest_load.get("active_zone_minutes")
    if latest_load_minutes is not None:
        when = f" on {latest_load['date']}" if latest_load.get("date") else ""
        evidence.append(
            f"Latest training load: {latest_load_minutes} Active Zone Minutes{when} "
            "(AZM, Fitbit hard-work minutes)."
        )

    active_zone_minutes = today.get("active_zone_minutes")
    if active_zone_minutes is not None:
        evidence.append(
            f"Today has {active_zone_minutes} Active Zone Minutes so far "
            "(AZM, Fitbit hard-work minutes)."
        )

    sleep = today.get("sleep") or {}
    sleep_hours = sleep.get("asleep_hours") or sleep.get("duration_hours")
    if sleep_hours is not None:
        evidence.append(
            f"Latest sleep used for recommendation: {float(sleep_hours):.1f}h "
            "(sleep is the main recovery input)."
        )

    if today.get("hrv_ms") is not None:
        evidence.append(
            f"Latest HRV used for recommendation: {float(today['hrv_ms']):.1f} ms "
            "(HRV is a recovery stress signal)."
        )
    if today.get("resting_heart_rate") is not None:
        evidence.append(
            "Latest Resting HR used for recommendation: "
            f"{today['resting_heart_rate']} bpm "
            "(resting heart rate is heart stress at rest)."
        )

    if energy_rating is not None:
        evidence.append(f"Latest energy check-in is {energy_rating}/10.")
    if soreness_rating is not None:
        evidence.append(f"Latest soreness check-in is {soreness_rating}/10.")
    if stress_rating is not None:
        evidence.append(f"Latest stress check-in is {stress_rating}/10.")
    if current_feeling:
        evidence.append(f"Current user-stated feeling: {current_feeling}.")
    if subjective_limiter:
        evidence.append("User-stated they do not feel fully right, so subjective readiness caps the session.")
    for flag in illness_flags:
        evidence.append(flag)

    if goal_status.get("target"):
        evidence.append(f"Current goal: {goal_status['target']}.")
    if goal_status.get("days_per_week") is not None and goal_status.get("remaining_sessions") is not None:
        evidence.append(
            "Goal progress: "
            f"{goal_status.get('recent_workouts', 0)}/{goal_status['days_per_week']} sessions logged; "
            f"{goal_status['remaining_sessions']} remaining."
        )

    if workout_summary.get("workout_count"):
        evidence.append(f"Recent workout history: {workout_summary['workout_count']} workout(s) in the lookback window.")
    hardest = workout_summary.get("hardest_workout") or {}
    if hardest.get("display_name") or hardest.get("name") or hardest.get("active_zone_minutes") is not None:
        name = hardest.get("display_name") or hardest.get("name") or "hardest recent workout"
        minutes = hardest.get("active_zone_minutes")
        date = hardest.get("date")
        details = []
        if minutes is not None:
            details.append(f"{minutes} Active Zone Minutes")
        if date:
            details.append(str(date))
        suffix = f" ({', '.join(details)})" if details else ""
        evidence.append(f"Hardest recent workout: {name}{suffix}.")

    return _dedupe(evidence)


def _workout_context_gaps(
    checkins: list[dict[str, Any]],
    goal_status: dict[str, Any],
    *,
    has_current_feeling: bool = False,
) -> list[str]:
    gaps: list[str] = []
    if not checkins:
        if has_current_feeling:
            gaps.append(
                "No structured check-in is logged; the current free-text feeling was used, but energy, soreness, stress, pain, or illness ratings would sharpen the plan."
            )
        else:
            gaps.append(
                "No recent subjective check-in is logged; energy, soreness, stress, pain, or illness could change the training call."
            )
    else:
        missing = [
            label
            for label, value in (
                ("energy", _latest_rating(checkins, "energy")),
                ("soreness", _latest_rating(checkins, "soreness")),
                ("stress", _latest_rating(checkins, "stress")),
            )
            if value is None
        ]
        if missing:
            gaps.append(f"Recent check-ins are missing {', '.join(missing)}.")
    if not goal_status.get("target") and goal_status.get("days_per_week") is None:
        gaps.append("No coaching goal is set, so the recommendation cannot optimize toward a weekly target.")
    return _dedupe(gaps)


def _subjective_limiter_from_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    not_right_patterns = (
        r"\b(?:do not|don't|dont|not)\s+feel(?:ing)?\s+(?:my\s+)?(?:100|one hundred|great|right|normal|fresh)\b",
        r"\b(?:feel|feeling)\s+(?:a\s+little\s+|kind\s+of\s+|sort\s+of\s+)?(?:off|not fresh|run down|rundown|under[- ]?recovered|cooked|drained|fatigued|heavy)\b",
        r"\b(?:low energy|heavy legs|not recovered|not fully recovered)\b",
    )
    if any(re.search(pattern, lower) for pattern in not_right_patterns):
        return True
    return any(
        _has_unnegated_phrase(lower, term)
        for term in (
            "tired",
            "fatigue",
            "fatigued",
            "drained",
            "cooked",
            "run down",
            "low energy",
            "heavy legs",
        )
    )


def _workout_stop_conditions(
    rpe_cap: int,
    *,
    subjective_limiter: bool = False,
    illness_flags: list[str] | None = None,
) -> list[str]:
    conditions = [
        "Stop or downshift for dizziness, chest pain/tightness, faintness, severe shortness of breath, or symptoms that are new or worsening.",
        "Stop the movement if pain rises above 3/10, becomes sharp, or changes your form.",
        f"Cap effort if RPE (how hard it feels from 1 easy to 10 max) drifts above {rpe_cap}/10 or breathing/heart rate does not settle after easy minutes.",
    ]
    if subjective_limiter:
        conditions.append("End early if the warm-up does not make you feel better within 10-15 minutes.")
    if illness_flags:
        conditions.append("Skip hard training while fever, flu-like symptoms, vomiting, or worsening illness signs are present.")
    return _dedupe(conditions)


def _rpe_plain(rpe_cap: int) -> str:
    if rpe_cap <= 4:
        return "easy effort"
    if rpe_cap <= 6:
        return "comfortable, should not feel like a grind"
    if rpe_cap <= 7:
        return "hard but controlled"
    if rpe_cap <= 8:
        return "challenging, but not a max attempt"
    return "very hard"


def _intensity_plain(intensity: str) -> str:
    if intensity == "easy":
        return "recovery pace"
    if intensity == "moderate":
        return "useful work, not all-out"
    if intensity == "moderate-to-hard":
        return "challenging work if the warm-up feels good"
    return "adjust based on the warm-up"


def _active_workout_safety_flags(
    symptoms_text: str,
    current_heart_rate_bpm: int | None,
    pain_level: int | None,
) -> list[str]:
    flags: list[str] = []
    urgent_terms = (
        "chest pain",
        "chest tight",
        "chest tightness",
        "chest pressure",
        "shortness of breath",
        "trouble breathing",
        "faint",
        "fainting",
        "dizzy",
        "dizziness",
        "palpitation",
        "palpitations",
        "irregular heartbeat",
        "passing out",
    )
    if any(_has_unnegated_phrase(symptoms_text, term) for term in urgent_terms):
        flags.append(
            "Reported symptoms may need medical caution; stop hard training and seek urgent care for chest pain, fainting, severe shortness of breath, or new/worsening symptoms."
        )
    if current_heart_rate_bpm is not None and current_heart_rate_bpm >= 190:
        flags.append(
            f"Live heart rate is very high at {current_heart_rate_bpm} bpm; downshift immediately and do not resume hard work unless it settles and symptoms are absent."
        )
    if pain_level is not None and pain_level >= 8:
        flags.append(f"Pain is severe at {pain_level}/10; stop loading that area.")
    return _dedupe(flags)


def _has_unnegated_phrase(text: str, phrase: str) -> bool:
    for match in re.finditer(rf"\b{re.escape(phrase)}\b", text):
        prefix = text[max(0, match.start() - 28) : match.start()]
        if re.search(r"\b(no|not|without|denies|deny|none)\b[\s,;:.-]{0,12}$", prefix):
            continue
        return True
    return False


def _activity_guidance(planned: str, rpe_cap: int, intensity: str) -> tuple[list[str], list[str], list[str], list[str]]:
    warmup = [
        "5-8 minutes easy cardio to check readiness.",
        "Dynamic hips, thoracic rotations, and shoulder/scapular activation.",
        "Two ramp sets before the first working set.",
    ]
    focus = ["Move well first, then add load only if the warm-up feels better than expected."]
    avoid = ["Max-effort attempts", "Adding extra hard conditioning after the session"]
    session = [f"Keep working sets at or below RPE {rpe_cap}/10 ({_rpe_plain(rpe_cap)})."]

    if _mentions(planned, ("chest", "bench", "press", "push")):
        focus.extend(
            [
                "Use chest-supported or machine options if bracing feels off.",
                "Prioritize controlled pressing, stable feet, and shoulder-blade position.",
                "Choose dumbbell or machine press before barbell PR attempts when recovery is red.",
            ]
        )
        session.extend(["Main press: 2-4 working sets.", "Accessories: incline press, cable fly, and light triceps."])
        avoid.extend(["Aggressive bench arch if low back feels sensitive", "Forced reps on pressing"])
    if _mentions(planned, ("back", "row", "pull", "deadlift", "hinge")):
        focus.extend(["Prefer chest-supported rows, pulldowns, and cable work.", "Keep bracing neutral and pain-free."])
        session.extend(["Pulling volume should be smooth and submaximal.", "Pair rows with face pulls or rear delts."])
        avoid.extend(["Heavy deadlifts", "Heavy bent-over rows", "Loaded spinal flexion"])
    if _mentions(planned, ("squash", "tennis", "court", "run", "interval", "hiit")):
        focus.extend(["Bias skill, footwork quality, and easy aerobic work over all-out intervals."])
        session.extend(["Keep change-of-direction volume low if recovery is red.", "Stop before movement gets sloppy."])
        avoid.extend(["Repeated max sprints", "Hard cutting if knee, hip, or back feels unstable"])
    if _mentions(planned, ("leg", "squat", "lower", "quad", "hamstring")):
        focus.extend(["Use controlled range and stable unilateral work only if joints feel calm."])
        session.extend(["Keep lower-body compounds submaximal.", "Use machines or tempo work before heavy free-weight loading."])
        avoid.extend(["Max squats", "High-volume plyometrics", "Hard lateral work after high zone-minute days"])
    if intensity == "easy":
        focus.append("A productive session today means leaving the gym feeling better, not crushed.")

    return _dedupe(focus), _dedupe(avoid), _dedupe(warmup), _dedupe(session)


def _exercise_prescription(
    planned: str,
    rpe_cap: int,
    readiness_label: str,
    spinal_constraint: bool,
) -> tuple[list[dict[str, str]], list[str]]:
    blocks: list[dict[str, str]] = []
    substitutions: list[str] = []
    easy_volume = readiness_label == "red"

    def add(name: str, sets: str, reps: str, note: str, alternative: str | None = None) -> None:
        blocks.append(
            {
                "exercise": name,
                "sets": sets,
                "reps": reps,
                "intensity": f"RPE <= {rpe_cap}",
                "note": note,
                "alternative": alternative or "",
            }
        )

    if _mentions(planned, ("chest", "bench", "press", "push")):
        add(
            "Machine chest press",
            "2-3" if easy_volume else "3-4",
            "8-10",
            "Stable torso; leave 3-4 reps in reserve if recovery is red.",
            "Flat dumbbell press with a neutral, pain-free arch.",
        )
        add(
            "Incline dumbbell press",
            "2" if easy_volume else "3",
            "10-12",
            "Moderate load, controlled lowering, no grinding.",
            "Incline machine press.",
        )
        add(
            "Cable fly",
            "2",
            "12-15",
            "Pump work only; stop before shoulder or back compensation.",
            "Pec deck.",
        )
        substitutions.append("Barbell bench with a big arch -> machine or dumbbell press.")

    if _mentions(planned, ("back", "row", "pull", "deadlift", "hinge")):
        add(
            "Chest-supported row",
            "2-3" if easy_volume else "3-4",
            "10-12",
            "Keep the lower back quiet; squeeze without yanking.",
            "Seated cable row with chest support.",
        )
        add(
            "Neutral-grip lat pulldown",
            "3",
            "10-12",
            "Stay tall and avoid leaning far back.",
            "Assisted pull-up if smooth and controlled.",
        )
        add(
            "Face pull",
            "2-3",
            "15-20",
            "Shoulder-blade control and upper-back blood flow.",
            "Rear-delt cable fly.",
        )
        substitutions.extend(
            [
                "Bent-over row -> chest-supported row.",
                "Heavy deadlift or hinge -> pulldown, supported row, or skip the hinge pattern today.",
            ]
        )

    if _mentions(planned, ("squash", "tennis", "court", "run", "interval", "hiit")):
        add(
            "Easy aerobic warm-up",
            "1",
            "8-12 min",
            "Nasal/easy breathing; use this as the readiness check.",
            "Brisk walk or bike.",
        )
        add(
            "Technique block",
            "4-6",
            "2 min",
            "Skill or footwork quality at conversational intensity.",
            "Zone 2 cardio if cutting feels off.",
        )
        add(
            "Short controlled pickup",
            "3-5",
            "20-30 sec",
            "Only if symptoms are absent and movement feels snappy.",
            "Skip pickups and cool down.",
        )

    if _mentions(planned, ("leg", "squat", "lower", "quad", "hamstring")):
        add(
            "Leg press or goblet squat",
            "2-3" if easy_volume else "3-4",
            "8-12",
            "Controlled range and no bracing strain.",
            "Split squat to a comfortable depth.",
        )
        add(
            "Hamstring curl",
            "2-3",
            "10-15",
            "Machine-based posterior-chain work without heavy hinging.",
            "Glute bridge if pain-free.",
        )
        add(
            "Calf raise",
            "2-3",
            "12-15",
            "Smooth tempo, no bouncing.",
            "Seated calf raise.",
        )

    if not blocks:
        add(
            "Easy warm-up",
            "1",
            "8-10 min",
            "Use breathing, coordination, and pain as the readiness screen.",
            "Walk, bike, or mobility flow.",
        )
        add(
            "Main movement",
            "2-3",
            "8-12",
            "Pick a familiar exercise and keep it below the intensity cap.",
            "Machine or supported variation.",
        )
        add(
            "Accessory circuit",
            "2",
            "10-15",
            "Quality reps only; end before fatigue changes form.",
            "Mobility or zone 2 if recovery feels poor.",
        )

    if spinal_constraint:
        substitutions.extend(
            [
                "Standing cable row -> seated cable row with chest support.",
                "Loaded spinal flexion or twisting -> supported machine work or mobility only.",
            ]
        )

    return blocks[:6], _dedupe(substitutions)


def _latest_rating(checkins: list[dict[str, Any]], key: str) -> int | None:
    for item in checkins:
        value = item.get("checkin", {}).get(key)
        if value is not None:
            return _bounded_rating(value)
    return None


def _illness_flags_from_checkins(checkins: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    for item in checkins:
        checkin = item.get("checkin", {})
        text = " ".join(
            str(checkin.get(key) or "")
            for key in ("notes", "symptoms", "illness")
        )
        flags.extend(_illness_flags_from_text(text))
        if flags:
            break
    return _dedupe(flags)


def _illness_flags_from_text(text: str) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    if any(_has_unnegated_phrase(lower, phrase) for phrase in ILLNESS_PHRASES):
        return [
            "Illness symptoms are present in the latest user context, so hard training should be avoided."
        ]
    return []


def _has_training_pain_constraint(text: str) -> bool:
    if not text:
        return False
    musculoskeletal_text = re.sub(r"\b(no\s+)?sore throat\b", "", text.lower())
    return any(
        _has_unnegated_phrase(musculoskeletal_text, term)
        for term in ("sore", "soreness", "pain", "ache", "tight", "tweak", "injury", "complains")
    )


def _rating_from_text(text: str, labels: tuple[str, ...]) -> int | None:
    if not text:
        return None
    label_pattern = "|".join(re.escape(label) for label in labels)
    patterns = (
        rf"(?:{label_pattern})\D{{0,20}}(\d{{1,2}})\s*/\s*10",
        rf"(\d{{1,2}})\s*/\s*10\D{{0,20}}(?:{label_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _bounded_rating(int(match.group(1)), minimum=0)
    return None


def _mentions(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _mentions_upcoming_session(text: str) -> bool:
    if not text:
        return False
    future_terms = (
        "tomorrow",
        "next day",
        "later today",
        "tonight",
        "this evening",
        "upcoming",
        "next session",
    )
    sport_terms = (
        "squash",
        "tennis",
        "pickleball",
        "basketball",
        "soccer",
        "run",
        "race",
        "match",
        "game",
        "tournament",
        "practice",
        "sport",
        "workout",
    )
    intent_terms = (
        "want to play",
        "need to play",
        "planning to play",
        "plan to play",
        "have to play",
        "have a match",
        "have a game",
        "have practice",
        "compete",
    )
    return (
        any(term in text for term in future_terms)
        and any(term in text for term in sport_terms)
        and (
            any(term in text for term in intent_terms)
            or "tomorrow" in text
            or "upcoming" in text
        )
    )


def _normalized_readiness_evidence(context: dict[str, Any]) -> list[str]:
    evidence = list((context.get("readiness") or {}).get("evidence", []))
    hrv_line = _hrv_average_evidence(context)
    resting_line = _resting_heart_rate_average_evidence(context)
    normalized: list[str] = []
    used_hrv = False
    used_resting = False

    for item in evidence:
        lower = item.lower()
        if "hrv" in lower and hrv_line:
            if not used_hrv:
                normalized.append(hrv_line)
                used_hrv = True
            continue
        if "resting heart" in lower and resting_line:
            if not used_resting:
                normalized.append(resting_line)
                used_resting = True
            continue
        normalized.append(item)

    return _dedupe(normalized)


def _hrv_average_evidence(context: dict[str, Any]) -> str | None:
    heart = (context.get("sections") or {}).get("heart") or {}
    latest = _number_or_none(_first_present(heart.get("latest_hrv_ms"), _hrv_ms_from_context(context)))
    average = _number_or_none(heart.get("average_hrv_ms"))
    if latest is None or average in (None, 0):
        return None
    delta = ((latest - average) / average) * 100
    label = "HRV (recovery stress signal)"
    if abs(delta) < 5:
        return (
            f"{label} is near recent average: {_fmt_num(latest)} ms vs {_fmt_num(average)} ms. "
            "That is neutral-to-supportive for training if warm-up feels good."
        )
    direction = "above" if delta > 0 else "below"
    meaning = (
        "That supports more training room if the warm-up feels good."
        if delta > 0
        else "That is a recovery caution, so keep intensity capped."
    )
    return (
        f"{label} is {abs(round(delta))}% {direction} recent average: "
        f"{_fmt_num(latest)} ms vs {_fmt_num(average)} ms. {meaning}"
    )


def _resting_heart_rate_average_evidence(context: dict[str, Any]) -> str | None:
    heart = (context.get("sections") or {}).get("heart") or {}
    latest = _number_or_none(
        _first_present(heart.get("latest_resting_heart_rate"), _resting_heart_rate_from_context(context))
    )
    average = _number_or_none(heart.get("average_resting_heart_rate"))
    if latest is None or average is None:
        return None
    delta = latest - average
    label = "Resting HR (resting heart rate; heart stress at rest)"
    if abs(delta) < 1:
        return (
            f"{label} is near recent average: {_fmt_num(latest, 0)} bpm vs {_fmt_num(average)} bpm. "
            "That is a neutral recovery sign."
        )
    direction = "elevated above" if delta > 0 else "below"
    meaning = (
        "Elevated Resting HR can point to stress, illness, fatigue, or under-recovery."
        if delta > 0
        else "Below-average Resting HR is usually supportive if symptoms feel normal."
    )
    return (
        f"{label} is {direction} recent average: "
        f"{_fmt_num(latest, 0)} bpm vs {_fmt_num(average)} bpm. {meaning}"
    )


def _number_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _fmt_num(value: float, digits: int = 1) -> str:
    if digits <= 0:
        return f"{value:.0f}"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def _display_workout_activity(planned_activity: str, intensity: str) -> str:
    normalized = (planned_activity or "").strip().lower()
    if normalized in {"", "general workout", "workout", "workout plan"}:
        if "easy" in intensity:
            return "Recovery Workout"
        return "Useful Controlled Workout"
    return planned_activity


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _context_dates(context: dict[str, Any]) -> tuple[str | None, str | None]:
    data_used = context.get("data_used", {})
    return (
        context.get("activity_date") or data_used.get("activity_date"),
        context.get("recovery_date") or data_used.get("recovery_date"),
    )


def _sleep_hours_from_context(context: dict[str, Any]) -> float | int | None:
    today = context.get("today", {})
    sleep = today.get("sleep", {})
    overview_sleep = context.get("sections", {}).get("sleep", {})
    return _first_present(
        sleep.get("asleep_hours"),
        sleep.get("duration_hours"),
        overview_sleep.get("latest_asleep_hours"),
    )


def _sleep_sessions_from_context(context: dict[str, Any]) -> int | None:
    today = context.get("today", {})
    sleep = today.get("sleep", {})
    return sleep.get("sessions_count")


def _hrv_ms_from_context(context: dict[str, Any]) -> float | int | None:
    today = context.get("today", {})
    overview_heart = context.get("sections", {}).get("heart", {})
    return _first_present(today.get("hrv_ms"), overview_heart.get("latest_hrv_ms"))


def _resting_heart_rate_from_context(context: dict[str, Any]) -> float | int | None:
    today = context.get("today", {})
    overview_heart = context.get("sections", {}).get("heart", {})
    return _first_present(
        today.get("resting_heart_rate"),
        overview_heart.get("latest_resting_heart_rate"),
    )


def _bounded_rating(value: int | None, minimum: int = 1) -> int | None:
    if value is None:
        return None
    return max(minimum, min(10, int(value)))


bundle = create_server()
settings = bundle.settings
db = bundle.db
auth_service = bundle.auth_service
health_store = bundle.health_store
mcp = bundle.mcp
app = bundle.app


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
