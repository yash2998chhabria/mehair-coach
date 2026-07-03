from __future__ import annotations

import re
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
from .widget import TODAY_WIDGET_HTML, WIDGET_MIME_TYPE, WIDGET_PREVIEW_STATES, WIDGET_URI, widget_preview_html


SERVER_INSTRUCTIONS = (
    "Mehair Coach provides read-only Google Health/Fitbit context for a connected user. "
    "If connection or synced data is missing, call status/freshness tools and explain setup; "
    "never invent health data. Use already-synced local data for normal current/latest/today questions, "
    "because every overview includes freshness metadata. Sync only when the user explicitly says sync, "
    "refresh, pull, or update Fitbit/Google Health data now, or when a freshness result says the data "
    "is stale for time-sensitive advice. For explicit requests to sync or refresh and then summarize, "
    "use all data, or give an overview, call sync_and_get_health_overview so the answer is based on "
    "one fresh overview result. For broad health, fitness, recovery, current/latest/today, or 'use all "
    "my data' overview questions that do not explicitly request sync/refresh, call get_health_overview "
    "before answering. "
    "For vague or diagnostic-sounding coaching questions like what the user should do today, "
    "why the user feels tired, how hard to train, whether heart signals look off, or which metrics matter, "
    "call get_health_question_clues "
    "first so the model can choose the right follow-up metrics. "
    "For sleep/HRV/resting-heart-rate/load comparisons, call get_recovery_signal_comparison. "
    "For any specific workout, sport, muscle-group, soreness, or recovery decision, call "
    "plan_workout_with_health_context or recommend_workout_today before answering; do not infer "
    "readiness, HRV, sleep, or load from conversation memory. "
    "During an active workout, call guide_active_workout when the user reports live RPE, heart rate, "
    "pain, symptoms, or asks whether to keep going. Call guide_active_workout directly for these "
    "in-session questions because it already reads the latest synced readiness/load context and "
    "renders the active workout card. Prefer one card-rendering tool per answer unless the user "
    "explicitly asks for multiple cards."
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
    )
    def get_recovery_signal_comparison(days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.recovery_signal_comparison(user_id, max(1, min(days, 30)))

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
        return workout_recommendation(
            context=health_store.latest_context(user_id),
            goal=health_store.latest_goal(user_id),
            checkins=health_store.recent_checkins(user_id),
            workout_history=health_store.workout_history(user_id, 7),
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
        context = health_store.latest_context(user_id)
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
            "Give in-session guidance using live user-reported heart rate, RPE, pain, symptoms, "
            "elapsed time, and the latest synced Fitbit readiness/load context."
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
) -> dict[str, Any]:
    if context.get("status") != "ok":
        return context
    readiness = context["readiness"]
    label = readiness.get("label")
    today = context.get("today", {})
    sleep = today.get("sleep", {})
    freshness = context.get("data_freshness", {})
    soreness_rating = _latest_rating(checkins or [], "soreness")
    energy_rating = _latest_rating(checkins or [], "energy")
    stress_rating = _latest_rating(checkins or [], "stress")
    workout_summary = (workout_history or {}).get("summary", {}) if (workout_history or {}).get("status") == "ok" else {}
    workout_count = int(workout_summary.get("workout_count") or 0)
    goal_payload = (goal or {}).get("goal") or {}
    goal_status = _goal_status(goal_payload, workout_count)
    context_gaps = _workout_context_gaps(checkins or [], goal_status)

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
    if today.get("active_zone_minutes", 0) > 45:
        plan += " You already have a high zone-minute load today, so avoid stacking another hard effort."
        avoid.append("Another hard conditioning block today")
        rpe_cap = min(rpe_cap, 7)
    if sleep.get("asleep_hours") and sleep["asleep_hours"] < 5:
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
        next_actions.append("Log a quick energy, soreness, stress, and pain check-in before committing to hard work.")

    if intensity == "moderate-to-hard":
        primary_action = "Train normally, but stop before form or breathing feels unusual."
    elif intensity == "moderate":
        primary_action = "Do a controlled session: zone 2, technique, or submax strength."
    else:
        primary_action = "Make today recovery-biased: walk, mobility, easy cardio, or rest."
    next_actions.insert(1 if freshness.get("needs_sync_before_time_sensitive_advice") else 0, primary_action)
    evidence = _workout_evidence(
        readiness=readiness,
        today=today,
        freshness=freshness,
        soreness_rating=soreness_rating,
        energy_rating=energy_rating,
        stress_rating=stress_rating,
        goal_status=goal_status,
        workout_summary=workout_summary,
    )

    return {
        "status": "ok",
        "intensity": intensity,
        "rpe_cap": rpe_cap,
        "recommendation": plan,
        "next_actions": _dedupe(next_actions),
        "avoid": _dedupe(avoid),
        "latest_date": context.get("latest_date"),
        "activity_date": context.get("activity_date"),
        "recovery_date": context.get("recovery_date"),
        "today": today,
        "why": evidence,
        "evidence": evidence,
        "context_gaps": context_gaps,
        "goal_context": goal_status,
        "subjective_context": {
            "energy": energy_rating,
            "soreness": soreness_rating,
            "stress": stress_rating,
            "latest_checkins": checkins or [],
        },
        "workout_history_summary": workout_summary or None,
        "data_freshness": freshness,
        "data_used": {
            "activity_date": context.get("activity_date"),
            "recovery_date": context.get("recovery_date"),
            "steps_today": today.get("steps", 0),
            "active_minutes_today": today.get("active_minutes", 0),
            "active_zone_minutes_today": today.get("active_zone_minutes", 0),
            "latest_sleep_hours": sleep.get("asleep_hours") or sleep.get("duration_hours"),
            "resting_heart_rate": today.get("resting_heart_rate"),
            "hrv_ms": today.get("hrv_ms"),
            "energy_checkin": energy_rating,
            "soreness_checkin": soreness_rating,
            "stress_checkin": stress_rating,
            "goal": goal,
            "recent_workouts": workout_count,
            "freshness_level": freshness.get("freshness_level"),
        },
        "readiness": readiness,
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
    sleep = today.get("sleep", {})
    latest_load = today.get("latest_training_load", {})
    planned = " ".join([planned_activity or "", " ".join(target_areas or [])]).lower()
    constraint_text = (constraints or "").lower()
    all_context_text = " ".join([planned, constraint_text])
    readiness_label = readiness.get("label", "pending")
    readiness_score = int(readiness.get("score", 0))
    soreness_rating = _latest_rating(checkins or [], "soreness")
    energy_rating = _latest_rating(checkins or [], "energy")
    has_soreness_constraint = _mentions(
        constraint_text,
        ("sore", "soreness", "pain", "ache", "tight", "tweak", "injury", "complains"),
    )
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

    intensity = _base_intensity(readiness_label)
    rpe_cap = {"easy": 6, "moderate": 7, "moderate-to-hard": 8}.get(intensity, 6)
    limiting_factors = list(readiness.get("evidence", []))
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
    if spinal_constraint:
        rpe_cap = min(rpe_cap, 7)
        limiting_factors.append("User-stated lower-back or hip constraint should cap spinal loading.")
    if latest_load.get("active_zone_minutes", 0) > 45:
        rpe_cap = min(rpe_cap, 7)

    focus, avoid, warmup, session = _activity_guidance(all_context_text, rpe_cap, intensity)
    exercise_blocks, substitutions = _exercise_prescription(
        all_context_text,
        rpe_cap,
        readiness_label,
        spinal_constraint,
    )
    if duration_minutes:
        session.append(f"Keep the session near {max(15, min(duration_minutes, 120))} minutes including warm-up.")
    if readiness_label == "red":
        session.insert(0, "Do not chase PRs; keep every compound lift 3-4 reps in reserve.")
    elif readiness_label == "yellow":
        session.insert(0, "Use a controlled session and stop 2-3 reps before failure.")
    else:
        session.insert(0, "A normal session is reasonable if warm-up movement feels good.")

    planned_date_text = planned_date or "next planned session"
    summary = (
        f"For {planned_date_text}, keep {planned_activity} at {intensity} intensity "
        f"with an RPE cap around {rpe_cap}/10."
    )
    if readiness_label == "red":
        summary += " Treat this as a quality/recovery-biased session because recovery signals are red."

    return {
        "status": "ok",
        "planned_activity": planned_activity,
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
        "avoid": avoid,
        "substitutions": substitutions,
        "progression_rules": [
            "If warm-up raises pain, heaviness, dizziness, or unusual breathlessness, downshift or stop.",
            "If HRV and resting heart rate rebound and sleep improves, progress load or volume next session.",
            "If recovery stays red for two straight days, bias toward zone 2, mobility, or a full rest day.",
        ],
        "limiting_factors": _dedupe(limiting_factors),
        "data_used": {
            "activity_date": context.get("activity_date"),
            "recovery_date": context.get("recovery_date"),
            "readiness_score": readiness_score,
            "readiness_label": readiness_label,
            "sleep_asleep_hours": sleep.get("asleep_hours") or sleep.get("duration_hours"),
            "sleep_sessions": sleep.get("sessions_count"),
            "hrv_ms": today.get("hrv_ms"),
            "resting_heart_rate": today.get("resting_heart_rate"),
            "steps": today.get("steps", 0),
            "active_minutes": today.get("active_minutes", 0),
            "active_zone_minutes": today.get("active_zone_minutes", 0),
            "latest_training_load": latest_load,
            "energy_checkin": energy_rating,
            "soreness_checkin": soreness_rating,
            "goal": goal,
        },
        "questions_to_ask_if_uncertain": [
            "Any pain above 3/10 during warm-up?",
            "Did sleep feel restorative despite the wearable score?",
            "Is the planned workout performance-focused, maintenance, or just keeping the habit?",
        ],
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
    readiness_label = readiness.get("label", "pending")
    readiness_score = int(readiness.get("score", 0))
    rpe = _bounded_rating(current_rpe)
    pain = _bounded_rating(pain_level)
    symptoms_text = " ".join([symptoms or "", notes or ""]).lower()
    safety_flags = _active_workout_safety_flags(symptoms_text, current_heart_rate_bpm, pain)
    evidence = list(readiness.get("evidence", []))
    if current_heart_rate_bpm is not None:
        evidence.append(f"Live heart rate reported: {current_heart_rate_bpm} bpm.")
    if rpe is not None:
        evidence.append(f"Live effort reported: RPE {rpe}/10.")
    if pain is not None:
        evidence.append(f"Live pain reported: {pain}/10.")
    if latest_load.get("active_zone_minutes") is not None:
        evidence.append(
            f"Latest synced load before/during this decision: {latest_load['active_zone_minutes']} Active Zone Minutes on {latest_load.get('date')}."
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

    return {
        "status": "ok",
        "guidance_type": "active_workout_guidance",
        "planned_activity": planned_activity,
        "decision": decision,
        "headline": headline,
        "immediate_actions": _dedupe(immediate_actions),
        "modifications": _dedupe(modifications),
        "avoid": _dedupe(avoid),
        "safety_flags": safety_flags,
        "evidence": _dedupe(evidence),
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
            "activity_date": context.get("activity_date"),
            "recovery_date": context.get("recovery_date"),
            "readiness_score": readiness_score,
            "readiness_label": readiness_label,
            "latest_training_load": latest_load,
            "resting_heart_rate": today.get("resting_heart_rate"),
            "hrv_ms": today.get("hrv_ms"),
        },
        "questions_to_ask_if_uncertain": [
            "Are symptoms new, severe, or getting worse?",
            "Is pain sharp, localized, or changing your movement?",
            "Does heart rate settle after 3-5 minutes easy?",
        ],
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


def _workout_evidence(
    *,
    readiness: dict[str, Any],
    today: dict[str, Any],
    freshness: dict[str, Any],
    soreness_rating: int | None,
    energy_rating: int | None,
    stress_rating: int | None,
    goal_status: dict[str, Any],
    workout_summary: dict[str, Any],
) -> list[str]:
    evidence = list(readiness.get("evidence", []))

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
        evidence.append(f"Latest training load: {latest_load_minutes} Active Zone Minutes{when}.")

    active_zone_minutes = today.get("active_zone_minutes")
    if active_zone_minutes is not None:
        evidence.append(f"Today has {active_zone_minutes} Active Zone Minutes so far.")

    sleep = today.get("sleep") or {}
    sleep_hours = sleep.get("asleep_hours") or sleep.get("duration_hours")
    if sleep_hours is not None:
        evidence.append(f"Latest sleep used for recommendation: {float(sleep_hours):.1f}h.")

    if today.get("hrv_ms") is not None:
        evidence.append(f"Latest HRV used for recommendation: {float(today['hrv_ms']):.1f} ms.")
    if today.get("resting_heart_rate") is not None:
        evidence.append(f"Latest resting heart rate used for recommendation: {today['resting_heart_rate']} bpm.")

    if energy_rating is not None:
        evidence.append(f"Latest energy check-in is {energy_rating}/10.")
    if soreness_rating is not None:
        evidence.append(f"Latest soreness check-in is {soreness_rating}/10.")
    if stress_rating is not None:
        evidence.append(f"Latest stress check-in is {stress_rating}/10.")

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


def _workout_context_gaps(checkins: list[dict[str, Any]], goal_status: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not checkins:
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
    session = [f"Keep working sets at or below RPE {rpe_cap}/10."]

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


def _mentions(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


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
