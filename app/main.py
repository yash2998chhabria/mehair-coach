from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon, ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from .auth import AppTokenVerifier, AuthError, AuthService
from .db import Database
from .health_store import HealthStore, model_signal_context, setup_required
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
    "mehair coach provides read-only Google Health/Fitbit context for a connected user. "
    "Treat tool descriptions and response contracts as routing and answer-shape guidance, not scripts: "
    "let the user's wording, current situation, and returned signals decide the final coaching answer. "
    "Everyday prompts like 'should I run today', 'I want to get fitter but not feel wrecked', "
    "'what should I do today?', or 'I only have 30 minutes' are coaching requests, not requests "
    "for a metric dump. "
    "Use plain English before statistics. Keep metric labels such as HRV, RPE, AZM, and resting "
    "heart rate, but briefly explain what they mean when they appear in user-facing advice. "
    "When mentioning steps or other movement totals, include the date/window and explain why that "
    "total does or does not matter for the decision. If a step average is based on recorded days, "
    "say recorded step days instead of implying it is averaged across every day in the lookback. "
    "When a tool returns coach_response, use it as the answer skeleton: direct human answer first, "
    "then the session_blueprint or what_to_do, then the explained metric labels, then stop conditions "
    "or caveats. Shape the answer as decision, do now, why the data matters, and what would change "
    "the call. Also use training_decision, model_signal_context, and available_signal_snapshot as "
    "response contract fields: summarize the relevant parts, do not recite every field. For vague, "
    "novel, or all-data questions, use decision_frame.model_decision_policy or "
    "model_signal_context.decision_policy to select signals by safety, recovery, load, capacity, "
    "and user-context axes instead of relying on exact words in the prompt. Avoid leading "
    "with raw tables or unexplained evidence logs. Do not say a tool was "
    "blocked unless the tool result itself has an error or setup-required status. "
    "Actual mehair coach cards are rendered by card tools with an Apps SDK outputTemplate. If the "
    "user asks to show, render, update, or rerun the workout card, make a current card-rendering "
    "tool call; do not say the workout card UI is unavailable when recommend_workout_today, "
    "plan_workout_with_health_context, or guide_active_workout is available. "
    "If get_health_question_clues returns suggested_card, treat suggested_card as the current "
    "card-ready coaching result for that turn; answer from it or make the next recommended tool "
    "call, but do not stop at a generic signals card when the user asked for a workout card. "
    "Match the user's actual situation: do not default to 'I feel off', fatigue, soreness, or recovery "
    "framing unless the user says it or the synced/check-in signals support it. For neutral or positive "
    "questions, give normal training permission with clear guardrails and the data that would change the call. "
    "If connection or synced data is missing, call status/freshness tools and explain setup; "
    "never invent health data. Use already-synced local data for normal current/latest/today questions, "
    "because every overview includes freshness metadata. Already-synced local data means data in the "
    "user's private mehair coach store, not data already visible in the conversation. For current, latest, "
    "today, use-tools, or card requests, make a current connector read or card tool call before answering. "
    "Fresh means synced in the last 15 minutes, "
    "aging means 15-60 minutes, and stale means more than 60 minutes or not observed today. "
    "Treat phrases like check my Fitbit context, "
    "look at my data, use my data, or what should I do today as already-synced reads unless the user "
    "literally asks to sync, refresh, pull, or update Fitbit/Google Health data now. Sync only when "
    "the user explicitly asks for a fresh sync/refresh/pull/update, or when a freshness result says "
    "needs_sync_before_time_sensitive_advice, including aging or stale data for a hard, risky, or "
    "time-sensitive call. For explicit requests to sync or refresh and then "
    "summarize freshness, show a card, analyze all available metrics, explain changes, or give an overview, call "
    "sync_and_get_health_overview directly; this is a non-destructive, idempotent pull of the user's "
    "cloud-synced Fitbit data into their private store, so do not describe it as blocked, dangerous, "
    "or unsafe when the user requested it. Sync tools are preparatory for workout/run/lift/card "
    "requests: after syncing, the final card-rendering call for day-of workout advice must be "
    "recommend_workout_today, plan_workout_with_health_context, or guide_active_workout. Do not answer "
    "a workout-card request from a sync or overview result alone. For broad "
    "health, fitness, recovery, current/latest/today, or 'use all my data' overview questions that "
    "do not explicitly request sync/refresh, call get_health_overview before answering. Use the "
    "available_signal_snapshot returned by overview/clue/comparison tools for broad, oxygen, breathing, "
    "temperature, VO2, and 'what other data matters?' questions; explain why normal secondary signals "
    "do or do not change the workout call instead of silently ignoring them. "
    "If a user says their oxygen looked lower, breathing felt different, temperature changed, or VO2 "
    "max changed, use recovery/comparison or clue tools to put those signals next to sleep, HRV, "
    "resting heart rate, load, symptoms, and freshness; do not diagnose or treat normal oxygen/VO2 "
    "as automatic permission for hard training. "
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
    "free text. For plan_workout_with_health_context, use planned_activity and target_areas only "
    "for the workout the user actually wants to do; keep constraints like 'don't want tired legs' "
    "or 'hike tomorrow' in constraints, not as leg target_areas. Label prior conversation facts as user-stated context, not synced Fitbit evidence, "
    "and do not treat earlier symptoms as current unless the user says they are still present. "
    "In long threads, do not answer from an old visible card or prior tool result when the user asks "
    "to use tools, check my data again, update the card, rerun, refresh, or show a card. Make a fresh "
    "relevant tool call and base the answer on the newest tool result. Treat older cards as historical "
    "context only because they may not include the user's new constraint, especially time limits, "
    "class/meeting/work/travel obligations, pain, symptoms, or in-workout reports. "
    "During an active workout, call guide_active_workout when the user reports live RPE, heart rate, "
    "pain, symptoms, elapsed time, or asks whether to keep going, push, hold steady, back off, slow "
    "down, or stop. Call guide_active_workout directly for these in-session questions because it "
    "already reads the latest synced readiness/load context and renders the active workout card. Do "
    "not substitute get_health_overview for live workout decisions. Prefer one card-rendering tool per "
    "answer unless the user explicitly asks for multiple cards."
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
SYNC = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
WIDGET_META = {
    "ui": {"resourceUri": WIDGET_URI},
    "openai/outputTemplate": WIDGET_URI,
}
APP_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-label="mehair coach">
  <rect width="96" height="96" rx="24" fill="#d63384"/>
  <path d="M22 64V31h9l17 20 17-20h9v33h-9V44L50 62h-4L31 44v20h-9Z" fill="white"/>
  <circle cx="73" cy="24" r="8" fill="#fff0f6"/>
</svg>
""".strip()

POST_SYNC_ROUTING_GUIDANCE = {
    "role": "preparatory_sync_result",
    "use_this_result_for": [
        "freshness status",
        "latest synced dates",
        "overview context",
        "available Fitbit/Google Health signals",
    ],
    "do_not_use_as_final_for": [
        "workout card",
        "run/lift/go-hard decision",
        "active in-session guidance",
    ],
    "next_tool_for_workout_card": (
        "If the user asked for a workout card, day-of training decision, run/lift advice, "
        "or enough movement before an obligation, call recommend_workout_today next and pass "
        "the user's current plain-language context in current_feeling."
    ),
    "next_tool_for_specific_activity": (
        "If the user named a specific activity, sport, muscle group, or constraints, call "
        "plan_workout_with_health_context next."
    ),
    "next_tool_for_active_workout": (
        "If the user is mid-workout and reports live heart rate, RPE, pain, symptoms, or elapsed time, "
        "call guide_active_workout next."
    ),
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
    "Readiness": "a quick recovery score built from sleep, heart, and recent load signals; green is 75+, yellow is 55-74, red is below 55",
    "RPE": "rate of perceived exertion: how hard it feels from 1 easy to 10 max; use it to decide whether to hold, back off, or stop",
    "HR": "heart rate right now: current beats per minute during movement or rest",
    "HRV": "heart-rate variability: a recovery stress signal compared with your usual",
    "Resting HR": "resting heart rate: heart stress at rest, best judged against your usual",
    "AZM": "Active Zone Minutes: Fitbit's hard-work minutes from elevated heart-rate zones; recent AZM is load you need to recover from",
    "SpO2": "oxygen saturation context from Fitbit; useful with breathing, symptoms, and heart signals, not a standalone green light",
    "Respiratory rate": "overnight breaths per minute; compare it with your usual before using it as a caution signal",
    "Sleep temperature": "temperature deviation during sleep; can be a stress or illness clue, but is not diagnostic",
    "VO2 max": "longer-term cardio capacity context, not same-day recovery readiness",
}

CARDIO_SPORT_TERMS = (
    "squash",
    "tennis",
    "pickleball",
    "basketball",
    "soccer",
    "court",
    "run",
    "race",
    "interval",
    "hiit",
    "cardio",
    "bike",
    "cycling",
    "swim",
    "walk",
)

LOWER_BODY_TRAINING_TERMS = (
    "leg",
    "legs",
    "lower",
    "squat",
    "squats",
    "lunge",
    "lunges",
    "quad",
    "quads",
    "hamstring",
    "hamstrings",
    "calf",
    "calves",
    "glute",
    "glutes",
    "deadlift",
    "hinge",
)

UPPER_BODY_TRAINING_TERMS = (
    "upper",
    "upper body",
    "chest",
    "back",
    "shoulder",
    "shoulders",
    "arm",
    "arms",
    "bicep",
    "biceps",
    "tricep",
    "triceps",
    "press",
    "bench",
    "row",
    "pull",
    "push",
)


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
        name="mehair coach",
        instructions=SERVER_INSTRUCTIONS,
        icons=[
            Icon(
                src=f"{settings.base_url}/assets/mehair-coach-icon.svg",
                mimeType="image/svg+xml",
                sizes=["96x96"],
            )
        ],
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
            title="mehair coach today card",
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
        description=(
            "Check whether this ChatGPT user has connected Google Health/Fitbit data and whether "
            "any synced records exist. Use for setup, empty-state, or 'can you see my data?' "
            "questions before coaching from wearable context."
        ),
        annotations=READ_ONLY,
    )
    def connect_google_health_status() -> dict[str, Any]:
        return health_store.connection_status(current_user_id())

    @mcp.tool(
        title="List available health metrics",
        description=(
            "Metric discovery for flexible questions. Use when the user asks what data you can see, "
            "what other signals matter, or an unusual question does not fit a canned coaching path. "
            "Returns every device-first Google Health/Fitbit metric this app can sync/query, per-user "
            "record counts, and model-facing guidance so ChatGPT can choose metrics intelligently."
        ),
        annotations=READ_ONLY,
    )
    def list_available_health_metrics() -> dict[str, Any]:
        return health_store.available_metrics(current_user_id())

    @mcp.tool(
        title="Query health metrics",
        description=(
            "Generic model-selected metric query for the exact synced Google Health/Fitbit signals "
            "ChatGPT decides are relevant. Use after list_available_health_metrics or "
            "get_health_question_clues when the answer needs details beyond an overview, such as "
            "oxygen plus respiratory rate, HRV plus resting HR, heart-rate zones, steps, or workout "
            "records over a bounded date range. Do not use a fixed recipe; choose metrics from the "
            "user's question. For in-session HR/RPE/pain decisions, use guide_active_workout instead."
        ),
        annotations=READ_ONLY,
    )
    def query_health_metrics(
        metrics: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Metric ids to fetch, chosen from list_available_health_metrics or clue suggestions. "
                    "Leave empty only when the user asks for a broad metric sample."
                )
            ),
        ] = None,
        days: Annotated[
            int,
            Field(description="Lookback window in days, usually 7-14 for coaching and up to 30 for trends."),
        ] = 7,
        start_date: Annotated[
            str | None,
            Field(description="Optional ISO date lower bound when the user gives a specific date range."),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(description="Optional ISO date upper bound when the user gives a specific date range."),
        ] = None,
        include_records: Annotated[
            bool,
            Field(
                description=(
                    "Set true only when raw record examples are needed; summaries are usually better "
                    "for normal ChatGPT coaching answers."
                )
            ),
        ] = False,
        limit_per_metric: Annotated[
            int,
            Field(description="Maximum raw records per metric when include_records is true."),
        ] = 25,
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
            "true only when the user explicitly asks to force a refresh now. This is a preparatory sync "
            "tool, not the final workout-card tool. If the user asked for a workout card, run/lift advice, "
            "or enough movement today, call recommend_workout_today or plan_workout_with_health_context "
            "after this sync completes."
        ),
        annotations=SYNC,
    )
    async def sync_latest_fitbit_data(force: bool = False) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        result = await health_store.sync_latest(user_id, force=force, include_context=False)
        if result.get("status") == "ok":
            result["post_sync_routing_guidance"] = POST_SYNC_ROUTING_GUIDANCE
        return result

    @mcp.tool(
        title="Sync and get health overview",
        description=(
            "Use only when the user explicitly asks to sync, refresh, pull, or update Fitbit/Google "
            "Health data now and then summarize, analyze all available health metrics, or explain what "
            "changed. Runs one sync, then returns a card-ready all-data overview with sync freshness "
            "to prepare for a later intensity recommendation. For normal current/latest/today questions, use "
            "get_health_overview instead because it is faster and includes freshness metadata. Leave force "
            "false unless the user explicitly asks to force a refresh. Use this to create a new current "
            "overview card in long threads when the user explicitly asks to sync/refresh/pull/update and "
            "show a broad card. This is not the final workout-card tool. If the user asked for a workout "
            "card, run/lift advice, or enough movement today, call recommend_workout_today or "
            "plan_workout_with_health_context after this sync/overview completes."
        ),
        annotations=SYNC,
        meta=WIDGET_META,
    )
    async def sync_and_get_health_overview(days: int = 14, force: bool = False) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()

        sync = await health_store.sync_latest(user_id, force=force, include_context=False)
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
            "total_records": sync.get("total_records")
            or overview.get("data_freshness", {}).get("records"),
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
            "freshness": sync.get("freshness") or overview.get("data_freshness"),
        }
        overview["post_sync_routing_guidance"] = POST_SYNC_ROUTING_GUIDANCE
        return overview

    @mcp.tool(
        title="Data freshness",
        description=(
            "Report how fresh the synced Fitbit/Google Health records are. Use before hard, risky, "
            "or time-sensitive advice when freshness is uncertain; broad overview tools already include "
            "freshness metadata."
        ),
        annotations=READ_ONLY,
    )
    def get_data_freshness() -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.freshness(user_id)

    @mcp.tool(
        title="Today context",
        description=(
            "Compact latest daily fitness context: activity, sleep, heart metrics, readiness, and evidence. "
            "Use for narrow current-data checks. Prefer get_health_overview for broad everyday coaching "
            "prompts because it includes more context and a card contract."
        ),
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
            "Fast all-context path for everyday current/latest/today health and fitness questions using "
            "already-synced local Google Health/Fitbit data. Use for prompts like 'give me my health "
            "overview today', 'show the whole picture', 'how do I get fitter without feeling wrecked?', "
            "'use all my data', or 'what other signals matter?'. Returns a card-ready overview across readiness, "
            "activity, sleep, heart, oxygen/breathing/temperature/capacity context when available, "
            "workouts, goals, check-ins, data coverage, freshness, and concrete next actions without "
            "starting a sync. This is the broad context card, not the final workout-card tool: if the "
            "user asks what to do, how hard to train, whether to run/lift/work out, or wants a workout "
            "card, call recommend_workout_today or plan_workout_with_health_context as the final card "
            "tool. Use this to create a new current overview card in long threads when the user asks "
            "to use tools, check latest data again, rerun analysis, or show a broad context card, but "
            "does not explicitly ask to sync."
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
        description=(
            "Narrow readiness score with evidence from sleep, HRV, resting heart rate, and activity load. "
            "Use when the user asks specifically for readiness; for actual workout advice prefer "
            "recommend_workout_today or plan_workout_with_health_context."
        ),
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
            "Natural-language routing helper for realistic health, recovery, sleep, heart, soreness, "
            "oxygen, or workout questions. Use it when the prompt is informal, broad, diagnostic-sounding, "
            "or asks 'what data matters?' / 'what other signals are relevant?'. For direct workout-card "
            "requests, prefer recommend_workout_today or plan_workout_with_health_context first. If this "
            "tool is called first for an obvious workout-card request, use its suggested_card field as the "
            "current card instead of stopping at a generic clues card. It identifies likely "
            "intents, the best synced Fitbit metrics to inspect, visible clues, recommended follow-up "
            "tools, and conversation flow options without forcing a brittle script."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def get_health_question_clues(question: str, days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        safe_days = max(1, min(days, 30))
        clues = health_store.health_question_clues(user_id, question, safe_days)
        return _augment_health_question_clues_for_card(
            clues=clues,
            question=question,
            user_id=user_id,
            health_store=health_store,
            days=safe_days,
        )

    @mcp.tool(
        title="Recovery signal comparison",
        description=(
            "Compare recent sleep, HRV, resting heart rate, respiratory/SpO2 context, sleep temperature, "
            "and activity load against baseline to explain recovery patterns. Use for questions like "
            "'why am I tired?', 'my oxygen looked lower', 'is my breathing data weird?', or 'how did "
            "sleep and heart numbers affect today's plan?'. Includes available signal context so normal "
            "oxygen/breathing signals can be named as background instead of ignored; it is not a diagnosis."
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
            "Fast, card-ready answer for normal day-of coaching questions like 'should I run today?', "
            "'I feel off, should I work out?', 'how hard should I train today?', 'what should I do "
            "today?', or 'I want to get fitter but not feel wrecked'. Uses already-synced Fitbit "
            "context, goals, check-ins, recent workouts, and optional current_feeling text to produce "
            "a direct decision, session blueprint, RPE cap, evidence, labels explained, and stop "
            "conditions. This is the actual Apps SDK workout card renderer for general day-of "
            "workout advice; call it when the user asks to show, render, update, or rerun the card. "
            "Do not say the card UI is unavailable if this tool is available. Does not start a sync."
            " If the user asks to use tools, show the card, or asks the same day-of question again with "
            "new context, call this tool again rather than answering from an older card in the thread."
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
                    "or concern, for example 'I have 30 minutes after work', 'I feel good and want to run', "
                    "or 'I feel a little off but want to work out'. Pass only current user-stated context; "
                    "do not revive old conversation symptoms unless the user says they still apply."
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
            "sleep, HRV, resting heart rate, oxygen/breathing context, activity load, goals, check-ins, "
            "the available signal snapshot, and user-stated constraints. Use for concrete plans like "
            "'upper body but save my legs for a hike', '30-minute run after work', or 'chest day with "
            "back soreness'. Put near-term class, meeting, work, travel, social plans, and 'I need energy "
            "after this' context in constraints so the plan preserves energy. It returns a card-ready plan with exercises, substitutions, avoid-list, "
            "RPE cap, label explanations, and a plain-English coaching contract."
            " This is the actual Apps SDK workout-plan card renderer for specific activities and constraints; "
            "do not say the card UI is unavailable if this tool is available."
            " If the user says to use tools or show a workout card, call this tool for the current turn "
            "instead of reusing an older visible card."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def plan_workout_with_health_context(
        planned_activity: Annotated[
            str,
            Field(
                description=(
                    "The workout the user actually wants to do today or soon, such as 'upper-body lift', "
                    "'20-minute mobility', 'run', or 'general workout'. Do not put protective constraints "
                    "here; for example, 'don't want tired legs' is a constraint, not a leg workout."
                )
            ),
        ],
        target_areas: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Only the body areas the user explicitly wants to train in the planned workout. "
                    "Do not infer 'legs' from phrases like 'protect my legs', 'hike tomorrow', or "
                    "'don't want tired legs'."
                )
            ),
        ] = None,
        planned_date: Annotated[
            str | None,
            Field(description="When the planned workout is meant to happen, if the user says it."),
        ] = None,
        constraints: Annotated[
            str | None,
            Field(
                description=(
                    "User-stated guardrails, context, and preferences: time limits, soreness, pain, "
                    "symptoms, upcoming hikes/sports/walks, energy, and what they want to avoid."
                )
            ),
        ] = None,
        duration_minutes: Annotated[
            int | None,
            Field(description="Requested total session length in minutes, if the user gives one."),
        ] = None,
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
            "pain 0/10, should I push or back off?', 'my chest feels tight', or 'keep going?'. "
            "Live inputs are user-reported, not direct band telemetry. Do not substitute "
            "get_health_overview for active in-session decisions; this is the actual Apps SDK active "
            "workout card renderer. "
            "Always call this again for each new in-session update; do not reuse earlier active-workout guidance."
        ),
        annotations=READ_ONLY,
        meta=WIDGET_META,
    )
    def guide_active_workout(
        planned_activity: Annotated[
            str,
            Field(
                description=(
                    "The workout currently happening. Use 'current workout' if the user reports live "
                    "HR/RPE/pain but does not name the activity."
                )
            ),
        ] = "current workout",
        current_heart_rate_bpm: Annotated[
            int | None,
            Field(description="The user's current live heart rate in bpm, if they report it."),
        ] = None,
        current_rpe: Annotated[
            int | None,
            Field(description="The user's current effort from 1 easy to 10 max, if they report RPE."),
        ] = None,
        pain_level: Annotated[
            int | None,
            Field(description="Current pain from 0 to 10, where 0 means no pain."),
        ] = None,
        symptoms: Annotated[
            str | None,
            Field(
                description=(
                    "Any live symptoms, breathing changes, dizziness, chest tightness, nausea, or "
                    "'none' if the user explicitly negates symptoms."
                )
            ),
        ] = None,
        elapsed_minutes: Annotated[
            int | None,
            Field(description="How many minutes into the workout the user is."),
        ] = None,
        planned_duration_minutes: Annotated[
            int | None,
            Field(description="Planned total workout duration in minutes, if known."),
        ] = None,
        notes: Annotated[
            str | None,
            Field(description="Other live context such as legs heavy, form changing, heat, pace, or interval number."),
        ] = None,
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
        description=(
            "Narrow sleep report from recent synced Fitbit records: duration, stages, and latest sleep. "
            "Use as supporting detail for sleep-specific questions; for workout decisions pair with "
            "readiness/recovery tools."
        ),
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
        description=(
            "Narrow activity-load report: recent steps, active minutes, zone minutes, and distance. "
            "Use to explain load stacking, leg fatigue, or weekly movement context with a stated window."
        ),
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
        description=(
            "Narrow heart report from synced Fitbit records: heart rate samples, resting heart rate, "
            "and HRV. Use for heart-specific trend questions; for symptoms use safety-first language "
            "and avoid diagnosis."
        ),
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
        description=(
            "List recent Fitbit exercise sessions and workout-level metrics. Use for weekly consistency, "
            "recent hard-session context, or when a workout plan needs prior-load detail."
        ),
        annotations=READ_ONLY,
    )
    def get_workout_history(days: int = 14) -> dict[str, Any]:
        user_id = current_user_id()
        if not user_id:
            return setup_required()
        return health_store.workout_history(user_id, max(1, min(days, 90)))

    @mcp.tool(
        title="Set coaching goal",
        description="Store a user-provided fitness goal for future recommendations. Writes only to local mehair coach storage.",
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
                "name": "mehair coach",
                "mcp_endpoint": f"{settings.base_url}/mcp",
                "google_oauth_configured": bool(
                    settings.google_client_id
                    and settings.google_client_secret
                    and settings.token_encryption_key
                ),
            }
        )

    async def home(_: Request) -> PlainTextResponse:
        return PlainTextResponse("mehair coach MCP server. Connect ChatGPT to /mcp.")

    async def oauth_metadata(_: Request) -> JSONResponse:
        return JSONResponse(auth_service.oauth_metadata())

    async def app_icon(_: Request) -> Response:
        return Response(APP_ICON_SVG, media_type="image/svg+xml")

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
              <title>mehair coach setup</title>
              <body style="font-family: system-ui; max-width: 760px; margin: 40px auto; line-height: 1.5">
                <h1>mehair coach setup</h1>
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
    app.add_route("/assets/mehair-coach-icon.svg", app_icon, methods=["GET"])
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


def _augment_health_question_clues_for_card(
    *,
    clues: dict[str, Any],
    question: str,
    user_id: str,
    health_store: HealthStore,
    days: int,
) -> dict[str, Any]:
    if clues.get("status") != "ok" or not _question_clues_should_attach_card(clues, question):
        return clues

    context = health_store.health_overview(user_id, days)
    if context.get("status") != "ok":
        return clues

    question_text = str(question or "").strip()
    if _question_prefers_specific_workout_card(question_text, clues):
        planned_activity, target_areas = _workout_activity_from_question(question_text)
        suggested_card = workout_plan_for_activity(
            context=context,
            planned_activity=planned_activity,
            target_areas=target_areas,
            constraints=question_text,
            goal=health_store.latest_goal(user_id),
            checkins=health_store.recent_checkins(user_id),
        )
        card_tool = "plan_workout_with_health_context"
    else:
        suggested_card = workout_recommendation(
            context=context,
            goal=health_store.latest_goal(user_id),
            checkins=health_store.recent_checkins(user_id),
            workout_history=health_store.workout_history(user_id, days),
            current_feeling=question_text,
        )
        card_tool = "recommend_workout_today"

    if suggested_card.get("status") != "ok":
        return clues

    guidance = list(clues.get("answering_guidance") or [])
    guidance.insert(
        0,
        "This result includes suggested_card because the prompt asked for workout coaching. If a final workout card has not rendered, call suggested_card_tool next; do not write a markdown replacement from old context. If this tool result already rendered the widget, answer from suggested_card.",
    )
    guidance.insert(
        1,
        "Do not say sync is unavailable. sync_latest_fitbit_data and sync_and_get_health_overview are available when a fresh cloud pull is actually needed.",
    )

    recommended_sequence = _dedupe([card_tool, *clues.get("recommended_tool_sequence", [])])
    return {
        **clues,
        "recommended_tool_sequence": recommended_sequence,
        "suggested_card": suggested_card,
        "suggested_card_type": "workout_plan"
        if card_tool == "plan_workout_with_health_context"
        else "today_workout",
        "suggested_card_tool": card_tool,
        "answering_guidance": _dedupe(guidance),
        "sync_tool_available": True,
        "sync_guidance": (
            "Use latest available synced data for normal coaching. If the user explicitly asks to sync, "
            "refresh, pull, or update, call sync_latest_fitbit_data or sync_and_get_health_overview; "
            "do not describe syncing as unavailable."
        ),
    }


def _question_clues_should_attach_card(clues: dict[str, Any], question: str) -> bool:
    intents = set(clues.get("intent_hints") or [])
    if "active_workout" in intents:
        return False
    if not ({"workout_decision", "daily_plan"} & intents):
        return False
    text = str(question or "").lower()
    return _mentions(
        text,
        (
            "card",
            "workout",
            "work out",
            "train",
            "run",
            "lift",
            "gym",
            "movement",
            "session",
            "what should i do",
            "how hard",
            "enough",
        ),
    )


def _question_prefers_specific_workout_card(question: str, clues: dict[str, Any]) -> bool:
    text = question.lower()
    context_cues = clues.get("decision_frame", {}).get("user_context_cues", [])
    if any(
        item.get("cue") in {"time_budget", "reserve_energy_or_future_event", "load_stacking"}
        for item in context_cues
    ):
        return True
    return _mentions(
        text,
        (
            "card",
            "run",
            "jog",
            "lift",
            "gym",
            "upper",
            "lower",
            "chest",
            "back",
            "legs",
            "mobility",
            "stretch",
            "class",
            "meeting",
            "work",
        ),
    )


def _workout_activity_from_question(question: str) -> tuple[str, list[str]]:
    text = question.lower()
    target_areas: list[str] = []
    if _mentions(text, ("upper", "upper body", "arms", "shoulders")):
        target_areas.append("upper body")
    if _mentions(text, ("chest",)):
        target_areas.append("chest")
    if _mentions(text, ("back",)):
        target_areas.append("back")
    if _mentions(text, ("core", "abs")):
        target_areas.append("core")
    if _mentions(text, ("legs", "leg day", "lower body")) and not _protect_lower_body_from_text(text):
        target_areas.append("legs")

    if _mentions(text, ("run", "running", "jog", "jogging")):
        return "run", target_areas
    if _mentions(text, ("walk", "walking")):
        return "walk", target_areas
    if _mentions(text, ("bike", "cycling", "cycle")):
        return "bike", target_areas
    if _mentions(text, ("mobility", "stretch", "stretching")):
        return "mobility", target_areas
    if target_areas:
        return f"{' and '.join(target_areas)} lift", target_areas
    return "general workout", target_areas


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
    time_limit_minutes = _time_limit_minutes_from_text(current_feeling_lower)
    stated_energy = _rating_from_text(current_feeling_lower, ("energy", "energy level"))
    stated_soreness = _rating_from_text(current_feeling_lower, ("soreness", "sore", "tightness", "tight"))
    stated_pain = _rating_from_text(current_feeling_lower, ("pain", "ache", "tightness", "tight"))
    subjective_limiter = _subjective_limiter_from_text(current_feeling_lower)
    stated_high_movement = _high_movement_from_text(current_feeling_lower)
    reserve_energy_obligation = _reserve_energy_obligation_from_text(current_feeling_lower)
    deadline_movement_minutes = _movement_minutes_before_obligation(current_feeling_lower)
    if deadline_movement_minutes is not None:
        time_limit_minutes = deadline_movement_minutes
    soreness_rating = _first_present(stated_soreness, stated_pain, _latest_rating(checkins or [], "soreness"))
    energy_rating = _first_present(stated_energy, _latest_rating(checkins or [], "energy"))
    stress_rating = _latest_rating(checkins or [], "stress")
    current_illness_flags = _illness_flags_from_text(current_feeling_lower)
    checkin_illness_flags = _illness_flags_from_checkins(checkins or [])
    illness_flags = _current_or_checkin_illness_flags(
        current_illness_flags=current_illness_flags,
        checkin_illness_flags=checkin_illness_flags,
        current_text=current_feeling_lower,
    )
    workout_summary = (workout_history or {}).get("summary", {}) if (workout_history or {}).get("status") == "ok" else {}
    workout_count = int(workout_summary.get("workout_count") or 0)
    goal_payload = (goal or {}).get("goal") or {}
    goal_status = _goal_status(goal_payload, workout_count)
    context_gaps = _workout_context_gaps(checkins or [], goal_status, has_current_feeling=bool(current_feeling_text))
    signal_snapshot = context.get("available_signal_snapshot", {}) or {}

    if label == "green":
        plan = "Train normally: strength, intervals, or a full session are reasonable if your body agrees."
        intensity = "moderate-to-hard"
        rpe_cap = 8
    elif label == "yellow":
        plan = "Keep it controlled: use one clear aerobic or submax strength block, then stop with energy in reserve."
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
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
        avoid.append("All-out intervals, max attempts, or PR work before a fresh sync")
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
    steps_today = _safe_int(today.get("steps"))
    high_step_load = steps_today is not None and steps_today >= 15000
    if stated_high_movement or high_step_load:
        plan += (
            " Treat today's walking/step volume as leg-load context: keep lower-body intensity controlled "
            "and avoid stacking hard conditioning on top of it."
        )
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
        next_actions.append(
            "Because movement volume is already high, choose upper body, technique, mobility, or short controlled intervals before adding lower-body volume."
        )
        avoid.append("Stacking hard lower-body work on top of a high-step or high-walking day")
    if reserve_energy_obligation:
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 6)
        plan += (
            " Because you have something else soon, make this the smallest useful dose: leave energy, "
            "attention, and calm breathing for the rest of the day."
        )
        next_actions.append("Keep this to a minimum useful dose and finish feeling clearer than when you started.")
        if deadline_movement_minutes is not None:
            next_actions.append(
                f"Use about {deadline_movement_minutes} minutes for movement, then leave time to cool down, hydrate, and switch contexts."
            )
        avoid.append("A workout that leaves you rushed, sweaty, drained, or mentally foggy for the next obligation")
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
    if time_limit_minutes is not None and intensity != "easy":
        next_actions.append(
            f"Use the {time_limit_minutes} minutes for one focused block: warm-up, main work, then a short cooldown."
        )
    if context_gaps and intensity in {"moderate", "moderate-to-hard"}:
        next_actions.append("Before hard work, tell me your energy, soreness, stress, and pain right now.")

    if intensity == "moderate-to-hard":
        primary_action = "Train normally, but stop before form or breathing feels unusual."
    elif intensity == "moderate":
        if reserve_energy_obligation:
            primary_action = "Do enough useful movement to feel better, then stop before it feels like a workout you have to recover from."
        else:
            primary_action = "Do one controlled main block: easy zone 2 if no plan, or submax planned training with reps in reserve."
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
        current_feeling=current_feeling_text,
        time_limit_minutes=time_limit_minutes,
        reserve_energy_obligation=reserve_energy_obligation,
        high_movement_context=stated_high_movement or high_step_load,
    )
    training_decision = _training_decision_frame(
        intensity=intensity,
        rpe_cap=rpe_cap,
        readiness=readiness,
        evidence=evidence,
        avoid=deduped_avoid,
        stop_conditions=stop_conditions,
        next_actions=deduped_next_actions,
        freshness=freshness,
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
            "time_limit_minutes": time_limit_minutes,
            "deadline_movement_minutes": deadline_movement_minutes,
            "subjective_limiter": subjective_limiter,
            "reserve_energy_obligation": reserve_energy_obligation,
            "latest_checkins": checkins or [],
        },
        "workout_history_summary": workout_summary or None,
        "data_freshness": freshness,
        "training_decision": training_decision,
        "model_signal_context": model_signal_context(signal_snapshot),
        "data_used": {
            "activity_date": activity_date,
            "recovery_date": recovery_date,
            "steps_today": today.get("steps"),
            "active_minutes_today": today.get("active_minutes"),
            "active_zone_minutes_today": today.get("active_zone_minutes"),
            "latest_sleep_hours": sleep_hours,
            "resting_heart_rate": resting_heart_rate,
            "hrv_ms": hrv_ms,
            "energy_checkin": energy_rating,
            "soreness_checkin": soreness_rating,
            "stress_checkin": stress_rating,
            "current_feeling": current_feeling_text or None,
            "time_limit_minutes": time_limit_minutes,
            "deadline_movement_minutes": deadline_movement_minutes,
            "subjective_limiter": subjective_limiter,
            "reserve_energy_obligation": reserve_energy_obligation,
            "stated_energy": stated_energy,
            "stated_soreness": stated_soreness,
            "stated_pain": stated_pain,
            "stated_high_movement": stated_high_movement,
            "illness_flags": illness_flags,
            "current_illness_flags": current_illness_flags,
            "checkin_illness_flags_used": bool(illness_flags and not current_illness_flags),
            "goal": goal,
            "recent_workouts": workout_count,
            "freshness_level": freshness.get("freshness_level"),
            "available_signal_count": len(signal_snapshot.get("signals", [])),
            "available_signal_ids": signal_snapshot.get("available_signal_ids", []),
        },
        "available_signal_snapshot": signal_snapshot,
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
    requested_duration_minutes = duration_minutes or _time_limit_minutes_from_text(all_context_text)
    deadline_movement_minutes = _movement_minutes_before_obligation(all_context_text)
    if deadline_movement_minutes is not None:
        requested_duration_minutes = min(
            requested_duration_minutes or deadline_movement_minutes,
            deadline_movement_minutes,
        )
    readiness_label = readiness.get("label", "pending")
    readiness_score = int(readiness.get("score", 0))
    stated_energy = _rating_from_text(constraint_text, ("energy", "energy level"))
    stated_soreness = _rating_from_text(constraint_text, ("soreness", "sore", "tightness", "tight"))
    stated_pain = _rating_from_text(constraint_text, ("pain", "ache", "tightness", "tight"))
    subjective_limiter = _subjective_limiter_from_text(constraint_text)
    stated_high_movement = _high_movement_from_text(constraint_text)
    reserve_energy_obligation = _reserve_energy_obligation_from_text(all_context_text)
    soreness_rating = _first_present(stated_soreness, stated_pain, _latest_rating(checkins or [], "soreness"))
    energy_rating = _first_present(stated_energy, _latest_rating(checkins or [], "energy"))
    current_illness_flags = _illness_flags_from_text(all_context_text)
    checkin_illness_flags = _illness_flags_from_checkins(checkins or [])
    illness_flags = _current_or_checkin_illness_flags(
        current_illness_flags=current_illness_flags,
        checkin_illness_flags=checkin_illness_flags,
        current_text=constraint_text,
    )
    has_soreness_constraint = _has_training_pain_constraint(constraint_text)
    localized_soreness_away_from_target = _localized_soreness_away_from_activity(constraint_text, planned)
    if localized_soreness_away_from_target:
        subjective_limiter = False
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
    protect_lower_body = _protect_lower_body_from_text(constraint_text)
    exercise_context_text = _workout_activity_selection_text(
        planned=planned,
        constraint_text=constraint_text,
        protect_lower_body=protect_lower_body,
    )
    signal_snapshot = context.get("available_signal_snapshot", {}) or {}

    intensity = _base_intensity(readiness_label)
    rpe_cap = {"easy": 6, "moderate": 7, "moderate-to-hard": 8}.get(intensity, 6)
    limiting_factors = _normalized_readiness_evidence(context)
    limiting_factors.extend(_signal_snapshot_evidence(signal_snapshot, limit=5))
    steps_today = _safe_int(today.get("steps"))
    high_step_load = steps_today is not None and steps_today >= 15000
    short_constrained_session = _short_constrained_session(
        all_context_text,
        requested_duration_minutes,
    )
    explicit_high_intensity_request = _explicit_high_intensity_request(all_context_text)
    if localized_soreness_away_from_target and intensity == "moderate-to-hard":
        intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
    if short_constrained_session and not explicit_high_intensity_request:
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
        limiting_factors.append(
            "Short time box: cap intensity so the session helps the rest of the day instead of taking over it."
        )
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
        if localized_soreness_away_from_target:
            limiting_factors.append(
                "User-stated soreness is localized away from the planned workout, so it should shape exercise choice without forcing a rest day."
            )
        else:
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
    if stated_high_movement or high_step_load:
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 7)
        if high_step_load and steps_today is not None:
            limiting_factors.append(
                f"High-step movement context: {steps_today:,} steps on {activity_date} so far. "
                "Treat steps as leg/load context, not a standalone recovery score."
            )
        else:
            limiting_factors.append("User-stated high walking or step volume today should count as leg/load context.")
    if preserving_next_session:
        rpe_cap = min(rpe_cap, 6)
        limiting_factors.append("User wants to preserve readiness for another sport or workout soon.")
    if reserve_energy_obligation:
        if intensity == "moderate-to-hard":
            intensity = "moderate"
        rpe_cap = min(rpe_cap, 6)
        limiting_factors.append(
            "User has a near-term class, meeting, work, travel, or social obligation, so the session should leave energy and focus available."
        )
        if deadline_movement_minutes is not None:
            limiting_factors.append(
                f"Near-term obligation timing means the useful movement dose should be about {deadline_movement_minutes} minutes, not the full countdown window."
            )
    if protect_lower_body:
        rpe_cap = min(rpe_cap, 6)
        limiting_factors.append(
            "User wants fresh legs for an upcoming walk, hike, sport, or long day; today's card should avoid leg-fatiguing work."
        )
    if latest_load.get("active_zone_minutes", 0) > 45:
        rpe_cap = min(rpe_cap, 7)
    if illness_flags:
        intensity = "easy"
        rpe_cap = min(rpe_cap, 4)
        limiting_factors.extend(illness_flags)

    focus, avoid, warmup, session = _activity_guidance(exercise_context_text, rpe_cap, intensity)
    exercise_blocks, substitutions = _exercise_prescription(
        exercise_context_text,
        rpe_cap,
        readiness_label,
        spinal_constraint,
    )
    if reserve_energy_obligation and _generic_workout_text(planned_activity):
        exercise_blocks = []
        substitutions.append("Generic workout -> easy zone 2, mobility, or light technique that does not need recovery.")
    if deadline_movement_minutes is not None:
        session.append(
            f"Keep the movement dose around {deadline_movement_minutes} minutes, then stop with time to cool down, hydrate, and switch contexts."
        )
    elif requested_duration_minutes:
        session.append(f"Keep the session near {max(15, min(requested_duration_minutes, 120))} minutes including warm-up.")
    if short_constrained_session and not explicit_high_intensity_request:
        focus.insert(0, "Make the workout compact enough that you can return to the day clearer, not wrecked.")
        session.insert(
            0,
            "Treat this as a useful maintenance block: warm up, do the best work, and leave one gear unused.",
        )
        avoid.append("Turning a short between-meetings window into an all-out workout")
    if subjective_limiter:
        focus.insert(0, "Make this a minimum useful session, not a proving-ground session.")
        session.insert(0, "Use the first 10-15 minutes as a pass/fail readiness screen before adding intensity.")
        avoid.append("Chasing PRs, extra finishers, or high-volume work on a not-100% day")
    if stated_high_movement or high_step_load:
        focus.insert(0, "Account for today's walking or step volume as leg load before choosing the workout.")
        session.insert(0, "If legs feel heavy in the warm-up, bias toward upper-body, technique, mobility, or easy zone 2.")
        avoid.append("Stacking hard lower-body work, HIIT, or long conditioning on top of a high-step day")
        substitutions.append("Leg-heavy lift or intervals -> upper-body lift, technique work, mobility, or easy zone 2.")
    if localized_soreness_away_from_target:
        focus.insert(0, "Train the planned upper-body work, but keep sore legs out of the job.")
        session.insert(0, "Use seated, machine, or chest-supported options so leg soreness can recover while you still train.")
        avoid.extend(
            [
                "Leg drive, jump rope, sled work, sprints, or finishers that turn this into lower-body work",
                "Standing lifts that make sore legs or your lower back compensate",
            ]
        )
        substitutions.extend(
            [
                "Standing press -> seated machine or dumbbell press.",
                "Bent-over row -> chest-supported row.",
                "Conditioning finisher -> easy walk or mobility cooldown.",
            ]
        )
    if preserving_next_session:
        session.append("Leave the session feeling fresher than you started so tomorrow's sport session stays available.")
        avoid.append("Extra finishers that steal from tomorrow's sport or workout session")
    if reserve_energy_obligation:
        focus.insert(0, "Make this the smallest useful dose before the rest of the day.")
        session.insert(0, "Use easy movement, mobility, or submax work that leaves breathing calm and focus intact.")
        avoid.append("Turning a before-class or before-work window into a workout you need to recover from")
    if protect_lower_body:
        focus.insert(0, "Protect your legs for the upcoming hike, walk, sport, or long day.")
        warmup.insert(0, "5-8 minutes of very easy mobility plus light upper-body activation; your legs should feel lighter, not worked.")
        session.insert(0, "Use upper-body, core, and mobility work; skip lower-body strength and hard conditioning.")
        avoid.extend(
            [
                "Squats, lunges, leg press, hamstring curls, calf raises, hill sprints, intervals, plyometrics, or hard bike work",
                "Any finisher that makes tomorrow's legs feel heavy",
            ]
        )
        substitutions.append("Leg-heavy plan -> upper-body lift, core, mobility, or very easy recovery movement.")
    if reserve_energy_obligation:
        session.insert(
            0,
            "This is not a full normal-session window; treat it as minimum useful movement before your next obligation.",
        )
    elif readiness_label == "red":
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
    if reserve_energy_obligation and _generic_workout_text(planned_activity):
        display_activity = "Minimum Useful Movement"
    if protect_lower_body and _generic_workout_text(planned_activity):
        display_activity = "Upper Body + Mobility"
    intent_context = _workout_intent_context(
        planned_activity=planned_activity,
        target_areas=target_areas,
        constraints=constraints,
        exercise_context_text=exercise_context_text,
        protect_lower_body=protect_lower_body,
        preserving_next_session=preserving_next_session,
        stated_high_movement=stated_high_movement,
        high_step_load=high_step_load,
        localized_soreness_away_from_target=localized_soreness_away_from_target,
        subjective_limiter=subjective_limiter,
        reserve_energy_obligation=reserve_energy_obligation,
        requested_duration_minutes=requested_duration_minutes,
    )
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
    if stated_high_movement or high_step_load:
        summary += " Today's walking or step volume should count as leg/load context, so avoid stacking extra hard lower-body work."
    if reserve_energy_obligation:
        summary += " Keep it useful but leave enough energy and attention for the next obligation."
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
    training_decision = _training_decision_frame(
        intensity=intensity,
        rpe_cap=rpe_cap,
        readiness=readiness,
        evidence=deduped_limiting_factors,
        avoid=deduped_avoid,
        stop_conditions=stop_conditions,
        next_actions=session,
        freshness=context.get("data_freshness", {}),
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
        "intent_context": intent_context,
        "progression_rules": [
            "If warm-up raises pain, heaviness, dizziness, or unusual breathlessness, downshift or stop.",
            "If HRV and resting heart rate rebound and sleep improves, progress load or volume next session.",
            "If recovery stays red for two straight days, bias toward zone 2, mobility, or a full rest day.",
        ],
        "stop_conditions": stop_conditions,
        "limiting_factors": deduped_limiting_factors,
        "training_decision": training_decision,
        "model_signal_context": model_signal_context(signal_snapshot),
        "data_freshness": context.get("data_freshness", {}),
        "data_used": {
            "activity_date": activity_date,
            "recovery_date": recovery_date,
            "readiness_score": readiness_score,
            "readiness_label": readiness_label,
            "sleep_asleep_hours": sleep_hours,
            "sleep_sessions": sleep_sessions,
            "hrv_ms": hrv_ms,
            "resting_heart_rate": resting_heart_rate,
            "steps": today.get("steps"),
            "active_minutes": today.get("active_minutes"),
            "active_zone_minutes": today.get("active_zone_minutes"),
            "latest_training_load": latest_load,
            "energy_checkin": energy_rating,
            "soreness_checkin": soreness_rating,
            "stated_energy": stated_energy,
            "stated_soreness": stated_soreness,
            "stated_pain": stated_pain,
            "subjective_limiter": subjective_limiter,
            "reserve_energy_obligation": reserve_energy_obligation,
            "stated_high_movement": stated_high_movement,
            "illness_flags": illness_flags,
            "current_illness_flags": current_illness_flags,
            "checkin_illness_flags_used": bool(illness_flags and not current_illness_flags),
            "localized_soreness_away_from_target": localized_soreness_away_from_target,
            "preserving_next_session": preserving_next_session,
            "protect_lower_body": protect_lower_body,
            "short_constrained_session": short_constrained_session,
            "explicit_high_intensity_request": explicit_high_intensity_request,
            "requested_duration_minutes": requested_duration_minutes,
            "deadline_movement_minutes": deadline_movement_minutes,
            "goal": goal,
            "available_signal_count": len(signal_snapshot.get("signals", [])),
            "available_signal_ids": signal_snapshot.get("available_signal_ids", []),
        },
        "available_signal_snapshot": signal_snapshot,
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
    freshness = context.get("data_freshness", {})
    readiness_label = readiness.get("label", "pending")
    readiness_score = int(readiness.get("score", 0))
    rpe = _bounded_rating(current_rpe)
    pain = _bounded_rating(pain_level, minimum=0)
    symptoms_text = " ".join([symptoms or "", notes or ""]).lower()
    safety_flags = _active_workout_safety_flags(symptoms_text, current_heart_rate_bpm, pain)
    signal_snapshot = _active_workout_signal_snapshot(
        context,
        current_heart_rate_bpm=current_heart_rate_bpm,
        hrv_ms=hrv_ms,
        resting_heart_rate=resting_heart_rate,
    )
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
    if freshness.get("freshness_label"):
        evidence.append(
            "Synced Fitbit context freshness: "
            f"{freshness.get('freshness_label')}. Live HR/RPE/pain come from what the user reports during the workout."
        )

    next_check_window = _active_workout_check_window(elapsed_minutes)
    rpe_cap = _active_workout_rpe_cap(rpe, readiness_label)
    decision = "continue_controlled"
    headline = f"Hold steady until {next_check_window}; do not make the workout harder yet."
    immediate_actions = [
        f"Stay at or below RPE {rpe_cap}/10 until {next_check_window}.",
        "Keep the exact same pace, load, or resistance; no sprint, PR, or surprise finisher.",
        "Stay below the point where form, breathing, or coordination changes.",
    ]
    modifications = [
        "If heart rate climbs while the pace feels the same, back off for 3-5 easy minutes.",
        "If RPE rises by 1 point or breathing stops feeling controlled, reduce speed, load, or impact one notch.",
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
    elif rpe is not None and rpe >= 8:
        decision = "continue_controlled"
        headline = f"You can keep the session useful, but RPE {rpe}/10 means no harder from here."
        immediate_actions = [
            "Hold this effort for only the next 3-5 minutes, then reassess honestly.",
            "If this was supposed to be easy or moderate, back off one notch now.",
            "Keep pain at 0-3/10 and breathing controlled; stop hard work if either changes.",
        ]
        modifications = [
            "Turn the next interval into steady controlled work instead of chasing a peak.",
            "Add recovery time until heart rate and breathing clearly settle.",
        ]
        avoid = ["Trying to prove fitness after RPE reaches 8/10", "Adding a hard finish without a clear plan"]
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
        elapsed_minutes=elapsed_minutes,
        planned_duration_minutes=planned_duration_minutes,
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
        "data_freshness": freshness,
        "model_signal_context": model_signal_context(signal_snapshot),
        "live_data_note": "In-session guidance uses user-reported live HR/RPE/pain plus the latest cloud-synced Fitbit context; it is not direct band telemetry.",
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
            "freshness_level": freshness.get("freshness_level"),
            "freshness_label": freshness.get("freshness_label"),
            "live_inputs_are_user_reported": True,
            "available_signal_count": len(signal_snapshot.get("signals", [])),
            "available_signal_ids": signal_snapshot.get("available_signal_ids", []),
        },
        "available_signal_snapshot": signal_snapshot,
        "questions_to_ask_if_uncertain": [
            "Are symptoms new, severe, or getting worse?",
            "Is pain sharp, localized, or changing your movement?",
            "Does heart rate settle after 3-5 minutes easy?",
        ],
        "coach_response": coach_response,
        "safety_note": "This is in-session fitness guidance, not medical diagnosis or emergency care.",
        "context": context,
    }


def _active_workout_signal_snapshot(
    context: dict[str, Any],
    *,
    current_heart_rate_bpm: int | None,
    hrv_ms: float | int | None,
    resting_heart_rate: float | int | None,
) -> dict[str, Any]:
    existing = context.get("available_signal_snapshot", {}) or {}
    if existing.get("status") == "ok" and existing.get("signals"):
        return existing

    today = context.get("today", {}) or {}
    sleep = today.get("sleep", {}) or {}
    latest_load = today.get("latest_training_load", {}) or {}
    latest_date = (
        context.get("latest_date")
        or context.get("activity_date")
        or context.get("recovery_date")
        or latest_load.get("date")
    )
    signals: list[dict[str, Any]] = []

    def add_signal(
        *,
        signal_id: str,
        label: str,
        category: str,
        value: Any,
        display: str,
        unit: str = "",
        latest_date_override: str | None = None,
        why_it_matters: str,
        coaching_use: str,
        use_when: list[str],
        confidence: str,
        window_summary: dict[str, Any] | None = None,
    ) -> None:
        if value is None:
            return
        signals.append(
            {
                "id": signal_id,
                "label": label,
                "category": category,
                "latest_value": value,
                "unit": unit,
                "display": display,
                "latest_date": latest_date_override or latest_date,
                "why_it_matters": why_it_matters,
                "coaching_use": coaching_use,
                "use_when": use_when,
                "confidence": confidence,
                "window_summary": window_summary or {},
            }
        )

    add_signal(
        signal_id="heart_rate_samples",
        label="Heart rate",
        category="in_session_context",
        value=current_heart_rate_bpm,
        unit="bpm",
        display=f"{current_heart_rate_bpm} bpm",
        why_it_matters="Current HR helps pace the session when interpreted with symptoms, effort, and recovery context.",
        coaching_use="Use for in-session pacing only; this value is user-reported, not direct band telemetry.",
        use_when=["active_workout", "pacing", "symptoms", "high_effort"],
        confidence="user_reported_live",
        window_summary={"source": "user_reported_live_input"},
    )
    add_signal(
        signal_id="active_zone_minutes",
        label="Active Zone Minutes",
        category="activity_load",
        value=latest_load.get("active_zone_minutes") or today.get("active_zone_minutes"),
        unit="AZM",
        display=f"{latest_load.get('active_zone_minutes') or today.get('active_zone_minutes')} AZM",
        latest_date_override=latest_load.get("date") or latest_date,
        why_it_matters="AZM is Fitbit's hard-work-minute load signal; high recent load can cap intensity.",
        coaching_use="Use as latest synced load context, and state the date/window when it matters.",
        use_when=["active_workout", "daily_load", "training_decision"],
        confidence="synced_context",
    )
    add_signal(
        signal_id="hrv",
        label="HRV",
        category="recovery",
        value=hrv_ms,
        unit="ms",
        display=f"{_fmt_num(float(hrv_ms))} ms" if hrv_ms is not None else "",
        why_it_matters="HRV can reflect recovery and stress trends, especially compared with the user's baseline.",
        coaching_use="Use as recovery context; do not let it override live pain, symptoms, or very high effort.",
        use_when=["active_workout", "recovery", "training_decision"],
        confidence="synced_context",
    )
    add_signal(
        signal_id="resting_heart_rate",
        label="Resting HR",
        category="recovery",
        value=resting_heart_rate,
        unit="bpm",
        display=f"{_fmt_num(float(resting_heart_rate), 0)} bpm" if resting_heart_rate is not None else "",
        why_it_matters="Resting HR can rise with stress, illness, poor sleep, or fatigue.",
        coaching_use="Use as recovery context alongside HRV, sleep, load, and symptoms.",
        use_when=["active_workout", "recovery", "illness_context"],
        confidence="synced_context",
    )
    add_signal(
        signal_id="sleep_duration",
        label="Sleep",
        category="sleep_recovery",
        value=sleep.get("asleep_hours") or sleep.get("duration_hours"),
        unit="h",
        display=f"{_fmt_num(float(sleep.get('asleep_hours') or sleep.get('duration_hours')))}h asleep"
        if sleep.get("asleep_hours") or sleep.get("duration_hours")
        else "",
        why_it_matters="Sleep is a major recovery input for how hard to train today.",
        coaching_use="Use as primary recovery context, but still let live symptoms and pain override the plan.",
        use_when=["active_workout", "recovery", "training_decision"],
        confidence="synced_context",
    )

    return {
        "status": "ok" if signals else "missing",
        "window_days": 1 if latest_date else 0,
        "date_range": {"latest": latest_date} if latest_date else {},
        "available_signal_ids": [signal["id"] for signal in signals],
        "available_categories": sorted({signal["category"] for signal in signals}),
        "signals": signals,
        "source": "active_workout_context_fallback",
        "question_guidance": [
            "This compact snapshot was built from active-workout context already available to the tool.",
            "Live HR is user-reported; synced recovery/load values are background context.",
        ],
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


SUBJECTIVE_LIMITER_PHRASES = (
    "feel off",
    "off today",
    "not fresh",
    "run down",
    "rundown",
    "under-recovered",
    "under recovered",
    "not recovered",
    "not fully recovered",
    "fatigue",
    "fatigued",
    "tired",
    "drained",
    "cooked",
    "heavy",
    "heavy legs",
    "low energy",
    "sore",
    "soreness",
    "pain",
    "ache",
    "tight",
)


def _evidence_item_has_subjective_limiter(item: str) -> bool:
    if "do not feel fully right" in item or "not feel 100" in item:
        return True
    if not item.startswith("current user-stated feeling"):
        return False
    _, _, feeling = item.partition(":")
    return _subjective_limiter_from_text(feeling.strip())


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
    movement_items = [
        item
        for item in evidence_items
        if "high movement" in item or "high-step" in item or "high walking" in item
    ]
    steps_window_items = [
        item
        for item in evidence_items
        if "recorded step days" in item or "steps across" in item
    ]
    breathing_items = [
        item
        for item in evidence_items
        if "spo2" in item or "oxygen" in item or "respiratory rate" in item
    ]
    temperature_items = [item for item in evidence_items if "sleep temperature" in item]
    capacity_items = [item for item in evidence_items if "vo2 max" in item]
    localized_soreness_items = [
        item
        for item in evidence_items
        if "localized away from the planned workout" in item
        or "sore legs out of the job" in item
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
    subjective_items = [item for item in evidence_items if _evidence_item_has_subjective_limiter(item)]
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

    if movement_items:
        constraints.append("the movement-load window may affect legs")
    elif steps_window_items:
        supports.append("steps are useful background load context, with the recorded-day window stated")
    if localized_soreness_items:
        constraints.append("sore areas should shape exercise choice, not automatically cancel training")
    if any(
        " is elevated" in item
        or "below recent baseline" in item
        or "training caution signal" in item
        or "treat oxygen context as a training caution" in item
        for item in breathing_items
    ):
        constraints.append("breathing or oxygen context should cap intensity if symptoms agree")
    elif breathing_items:
        supports.append("breathing and oxygen signals are background context, not a standalone green light")
    if any("meaningfully different" in item or "temperature is high" in item for item in temperature_items):
        constraints.append("sleep temperature adds a caution clue")
    elif temperature_items:
        supports.append("sleep temperature is checked as secondary context")
    if capacity_items:
        supports.append("VO2 max informs capacity, not today's readiness")

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
    time_limit_minutes: int | None = None,
    reserve_energy_obligation: bool = False,
) -> list[str]:
    if illness_flags:
        return [
            "Today: skip hard training.",
            "If symptoms are mild and improving, do 10-20 minutes of easy walking or mobility only.",
            "End the session if symptoms worsen, breathing feels unusual, or energy drops.",
        ]

    if reserve_energy_obligation and not illness_flags:
        if time_limit_minutes is not None:
            usable_minutes = max(10, min(time_limit_minutes - 10, 30))
            return [
                "Start with 3-5 minutes easy movement and check breathing.",
                f"Do {usable_minutes} minutes of easy zone 2, mobility, or light technique at RPE <= {rpe_cap}/10.",
                "Stop while breathing is calm; leave time to cool down, hydrate, and switch contexts.",
            ]
        return [
            "Start with 5 minutes easy movement and check breathing.",
            f"Do 15-25 minutes easy zone 2, mobility, or light technique at RPE <= {rpe_cap}/10.",
            "Stop while you still feel clear and ready for the rest of the day.",
        ]

    if intensity == "easy":
        if time_limit_minutes is not None and time_limit_minutes <= 25:
            blueprint = [
                "Start with 3-5 minutes easy walking, cycling, or mobility.",
                f"Then use the remaining minutes for easy movement at RPE <= {rpe_cap}/10; stop before it feels like work.",
                "Finish with energy in reserve.",
            ]
        else:
            blueprint = [
                "Start with 10 minutes easy walking, cycling, or mobility to see how your body responds.",
                f"Then do 10-25 minutes easy movement at RPE <= {rpe_cap}/10; stop before it feels like work.",
                "Finish with energy in reserve.",
            ]
    elif intensity == "moderate":
        if time_limit_minutes is not None and time_limit_minutes <= 25:
            blueprint = [
                "Start with a 3-5 minute gradual warm-up.",
                f"Default main block: 12-18 minutes easy zone 2 cardio at RPE <= {rpe_cap}/10.",
                "Swap only if you already had a planned lift: keep it submax and stop 2-3 reps before failure.",
                "Use the final 2-3 minutes to cool down; leave one more set or interval in reserve.",
            ]
        elif time_limit_minutes is not None and time_limit_minutes <= 35:
            blueprint = [
                "Start with a 5-8 minute gradual warm-up.",
                f"Default main block: 18-25 minutes easy zone 2 cardio at RPE <= {rpe_cap}/10.",
                "Swap only if you already had a planned lift: keep it submax and stop 2-3 reps before failure.",
                "Cool down briefly and leave 2-3 reps or one more interval in reserve.",
            ]
        else:
            blueprint = [
                "Start with a 10-15 minute gradual warm-up.",
                f"Default main block: 20-30 minutes easy zone 2 cardio at RPE <= {rpe_cap}/10, then 5-8 minutes mobility or core.",
                "Swap only if you already had a planned lift: keep it submax and stop 2-3 reps before failure.",
                "Cool down for 5 minutes and leave 2-3 reps or one more interval in reserve.",
            ]
    else:
        if time_limit_minutes is not None and time_limit_minutes <= 25:
            blueprint = [
                "Start with a 3-5 minute warm-up and check breathing, form, and pain.",
                f"Default main block: 12-18 minutes of your planned training at RPE <= {rpe_cap}/10; if no plan, do easy zone 2 plus 2 short pickups.",
                "Skip max attempts; finish before form or breathing changes.",
            ]
        elif time_limit_minutes is not None and time_limit_minutes <= 35:
            blueprint = [
                "Start with a 5-8 minute warm-up and check breathing, form, and pain.",
                f"Default main block: 18-25 minutes of your planned training at RPE <= {rpe_cap}/10; if no plan, do controlled zone 2 plus 2 short pickups.",
                "Skip max attempts if the warm-up feels off; cool down before form fades.",
            ]
        else:
            blueprint = [
                "Start with a 10-15 minute warm-up and check breathing, form, and pain.",
                f"Default main block: 25-35 minutes of your planned training at RPE <= {rpe_cap}/10; if no plan, do controlled zone 2 plus 2 short pickups.",
                "Skip max attempts if the warm-up feels off; cool down before form fades.",
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

    priority_session = _priority_session_line(session)
    block_names = _representative_exercise_names(exercise_blocks)
    if block_names:
        if _exercise_blocks_are_aerobic(exercise_blocks):
            blueprint.append(f"Main block: {', '.join(block_names[:3])}; keep effort at RPE <= {rpe_cap}/10.")
        else:
            blueprint.append(f"Main work: {', '.join(block_names[:3])}; keep every set at RPE <= {rpe_cap}/10.")
    elif session:
        blueprint.append(session[0])
    elif focus:
        blueprint.append(focus[0])

    if priority_session and priority_session not in blueprint:
        blueprint.append(priority_session)
    elif len(session) > 1:
        blueprint.append(session[1])
    else:
        blueprint.append(f"Stop with energy in reserve; RPE stays <= {rpe_cap}/10.")

    if focus:
        blueprint.append(f"Main coaching cue: {focus[0]}")

    return _dedupe(blueprint)[:5]


def _priority_session_line(session: list[str]) -> str | None:
    for item in session:
        lower = item.lower()
        if "movement dose" in lower or "switch contexts" in lower or "cool down" in lower:
            return item
    return None


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


def _exercise_blocks_are_aerobic(exercise_blocks: list[dict[str, Any]]) -> bool:
    names = " ".join(
        str(block.get("exercise", ""))
        for block in exercise_blocks
        if isinstance(block, dict)
    ).lower()
    return bool(names) and any(
        term in names
        for term in ("aerobic", "pickup", "technique", "stride", "cardio", "run", "walk", "bike")
    )


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


def _active_workout_check_window(elapsed_minutes: int | None) -> str:
    if elapsed_minutes is None:
        return "the next 5-10 minutes"
    start = elapsed_minutes + 5
    end = elapsed_minutes + 10
    return f"{start}-{end} minutes elapsed"


def _active_workout_rpe_cap(rpe: int | None, readiness_label: str) -> int:
    if rpe is not None:
        return min(max(rpe, 6), 8)
    if readiness_label == "red":
        return 6
    if readiness_label == "yellow":
        return 7
    return 8


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
    current_feeling: str | None = None,
    time_limit_minutes: int | None = None,
    reserve_energy_obligation: bool = False,
    high_movement_context: bool = False,
) -> dict[str, Any]:
    evidence_text = " ".join(evidence).lower()
    has_stale_data = "data freshness is stale" in evidence_text or "sync latest fitbit data" in evidence_text
    has_high_movement = high_movement_context
    if has_stale_data:
        short_answer = "Sync latest Fitbit data before a time-sensitive hard workout decision. If you train before syncing, keep it controlled."
    elif illness_flags:
        short_answer = "Skip hard training today. If symptoms are mild and improving, keep it to a short easy walk or mobility."
    elif intensity == "easy":
        short_answer = "Make today recovery-biased: useful movement is fine, but keep it easy and finish with energy in reserve."
    elif reserve_energy_obligation:
        short_answer = "Do the smallest useful dose today: move enough to feel better, then leave energy for what comes next."
    elif has_high_movement:
        short_answer = (
            "Train, but keep lower-body work and hard conditioning controlled because the movement-load "
            "window already adds leg stress."
        )
    elif intensity == "moderate":
        short_answer = "Do a focused controlled session today: useful work, not all-out intensity."
    else:
        if _positive_or_neutral_feeling_from_text(current_feeling or ""):
            short_answer = "Training is available today; if the warm-up matches how good or normal you feel, you can make it challenging."
        else:
            short_answer = "Training is available today if the warm-up feels normal and your breathing, form, and pain stay calm."

    if subjective_limiter and not illness_flags:
        short_answer += " Because you do not feel fully right, let the first 10-15 minutes decide whether to continue."
    if time_limit_minutes is not None and time_limit_minutes <= 35 and not has_stale_data:
        short_answer += f" Since you have {time_limit_minutes} minutes, make the plan compact instead of adding extra volume."
    elif reserve_energy_obligation and time_limit_minutes is not None and not has_stale_data:
        short_answer += f" Since the next thing is in about {time_limit_minutes} minutes, stop early enough to cool down and reset."

    what_to_do = list(next_actions[:3])
    rpe_line = f"Keep RPE (how hard it feels) at or below {rpe_cap}/10, which means {_rpe_plain(rpe_cap)}."
    what_to_do.insert(1 if what_to_do else 0, rpe_line)
    session_blueprint = _today_session_blueprint(
        intensity=intensity,
        rpe_cap=rpe_cap,
        subjective_limiter=subjective_limiter,
        illness_flags=illness_flags,
        time_limit_minutes=time_limit_minutes,
        reserve_energy_obligation=reserve_energy_obligation,
    )

    return {
        "short_answer": short_answer,
        "data_story": _coach_data_story(readiness, evidence),
        "session_blueprint": session_blueprint,
        "what_to_do": _dedupe(what_to_do)[:5],
        "why": _humanized_evidence(_prioritize_coach_evidence(evidence))[:10],
        "labels_explained": _coach_metric_glossary(_metric_labels_from_evidence(evidence)),
        "stop_if": stop_conditions[:5],
        "avoid": avoid[:5],
        "answer_style": (
            "Use this as a flexible coaching contract, not wording to copy. Answer like a personal "
            "coach: direct recommendation first, concrete next move second, then explain the kept "
            "metric labels in one short why section. Match the current user-stated situation exactly."
        ),
        "realistic_follow_ups": _today_realistic_followups(subjective_limiter, illness_flags),
    }


def _training_decision_frame(
    *,
    intensity: str,
    rpe_cap: int,
    readiness: dict[str, Any],
    evidence: list[str],
    avoid: list[str],
    stop_conditions: list[str],
    next_actions: list[str],
    freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    freshness = freshness or {}
    evidence_text = " ".join(str(item).lower() for item in evidence)
    has_sync_limit = bool(freshness.get("needs_sync_before_time_sensitive_advice")) or "data freshness" in evidence_text
    has_symptom_limit = any(
        term in evidence_text
        for term in (
            "illness symptoms",
            "reported symptoms",
            "urgent care",
            "chest pain",
            "chest tightness",
            "dizzy",
            "dizziness",
            "fever",
            "user-stated pain",
            "live pain reported",
            "soreness check-in is high",
        )
    )
    has_load_limit = any(term in evidence_text for term in ("high-step", "high walking", "high zone", "high recent load"))
    if intensity == "moderate-to-hard" and not has_sync_limit and not has_symptom_limit:
        hard_training = "yes_if_warmup_agrees"
    elif intensity == "easy" or has_symptom_limit:
        hard_training = "no"
    else:
        hard_training = "conditional"

    if intensity == "easy":
        best_session_type = "recovery movement, mobility, walking, or rest"
    elif intensity == "moderate":
        best_session_type = "controlled strength, zone 2, technique, or submax intervals"
    else:
        best_session_type = "normal training with a warm-up check and no blind max effort"

    reasons_for, reasons_against = _split_training_reasons(evidence)
    if has_sync_limit and not any("fresh" in item.lower() or "sync" in item.lower() for item in reasons_against):
        reasons_against.insert(0, freshness.get("recommendation") or "Data should be synced before hard time-sensitive training.")
    if has_load_limit and not any("load" in item.lower() or "step" in item.lower() for item in reasons_against):
        reasons_against.append("Recent movement or zone load should cap added intensity.")

    return {
        "hard_training": hard_training,
        "best_session_type": best_session_type,
        "rpe_cap": rpe_cap,
        "readiness_score": readiness.get("score"),
        "readiness_band": readiness.get("label"),
        "freshness_level": freshness.get("freshness_level"),
        "reasons_for": reasons_for[:5],
        "reasons_against": reasons_against[:5],
        "do_now": next_actions[:5],
        "avoid": avoid[:5],
        "stop_or_downshift_triggers": stop_conditions[:6],
        "model_guidance": (
            "Use this as the compact decision frame, not a script. Explain the human action first, "
            "then use only the relevant reasons for/against to show how the data changed the "
            "recommendation. Do not recite fields the user does not need."
        ),
    }


def _split_training_reasons(evidence: list[str]) -> tuple[list[str], list[str]]:
    positive_terms = (
        "strong",
        "support",
        "above recent",
        "steady",
        "not elevated",
        "normal",
        "green",
        "available",
        "useful context",
    )
    caution_terms = (
        "short",
        "below",
        "elevated",
        "high",
        "stale",
        "aging",
        "sync",
        "training caution",
        "pain",
        "illness",
        "symptom",
        "not feel",
        "soreness",
        "stress",
        "near-term",
        "obligation",
        "drain",
    )
    reasons_for: list[str] = []
    reasons_against: list[str] = []
    for item in _humanized_evidence(_prioritize_coach_evidence(evidence)):
        lower = item.lower()
        if (
            ("spo2" in lower or "oxygen saturation" in lower or "respiratory rate" in lower)
            and " is elevated" not in lower
            and "below recent baseline" not in lower
            and "training caution" not in lower
        ):
            reasons_for.append(item)
            continue
        if "sleep temperature" in lower and "meaningfully different" not in lower and "temperature is high" not in lower:
            reasons_for.append(item)
            continue
        if any(term in lower for term in caution_terms):
            reasons_against.append(item)
        elif any(term in lower for term in positive_terms):
            reasons_for.append(item)
    if not reasons_for:
        reasons_for.append("Enough synced context exists to make a data-guided coaching call.")
    if not reasons_against:
        reasons_against.append("No major synced red flag was detected; warm-up, pain, breathing, and symptoms still decide the ceiling.")
    return _dedupe(reasons_for), _dedupe(reasons_against)


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
    has_short_time_box = any("short time box" in item.lower() for item in limiting_factors)
    has_reserve_obligation = any("near-term" in item.lower() and "obligation" in item.lower() for item in limiting_factors)
    if illness_flags:
        short_answer = f"For {display_activity}, keep this as rest or very easy movement until symptoms improve."
    elif preserving_next_session:
        short_answer = f"For {display_activity}, train controlled enough that tomorrow still stays available."
    elif has_reserve_obligation:
        short_answer = f"For {display_activity}, do the smallest useful dose and leave energy for what comes next."
    elif has_short_time_box:
        short_answer = f"For {display_activity}, make this compact and useful so it supports the rest of your day."
    elif intensity == "easy":
        short_answer = f"For {display_activity}, make the win leaving better than you started."
    elif intensity == "moderate":
        short_answer = f"For {display_activity}, do useful work, but keep the session controlled."
    else:
        short_answer = f"For {display_activity}, a normal session is reasonable if the warm-up feels good."

    if subjective_limiter and not illness_flags and not preserving_next_session:
        short_answer += " This is a not-100% day, so treat the warm-up as the test."
    elif subjective_limiter and preserving_next_session and not illness_flags:
        short_answer += " If the warm-up feels bad, downshift immediately so tomorrow stays protected."

    priority_session = _priority_session_line(session)
    what_to_do = [
        summary,
        f"RPE (how hard it feels) cap: {rpe_cap}/10, which means {_rpe_plain(rpe_cap)}.",
        priority_session,
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
        "labels_explained": _coach_metric_glossary(_metric_labels_from_evidence(limiting_factors)),
        "stop_if": stop_conditions[:5],
        "avoid": avoid[:5],
        "substitutions": substitutions[:5],
        "answer_style": (
            "Use this as a flexible workout-plan contract. Keep the workout name and metric labels, "
            "translate each label in simple words, and match the user's stated situation instead of "
            "assuming they feel off. Prefer a usable session blueprint over a stats recap."
            + (
                " This result supersedes any older visible card in the thread: because the user has a "
                "near-term obligation, do not present this as a normal RPE 8 workout, and do not suggest "
                "main/accessory strength blocks unless the returned exercise blocks include them."
                if has_reserve_obligation
                else ""
            )
        ),
        "realistic_follow_ups": [
            "I only have 30 minutes. What should I actually do?",
            "Can I make this harder if the warm-up feels great?",
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
    elapsed_minutes: int | None,
    planned_duration_minutes: int | None,
) -> dict[str, Any]:
    if decision in {"stop_and_assess", "stop_session"}:
        short_answer = "Stop the hard part now. Treat this as a safety decision, not a toughness decision."
    elif decision == "downshift_now":
        short_answer = "Back off now. You can still get a useful session by lowering intensity and reassessing."
    elif decision == "modify":
        short_answer = "Modify the movement before it becomes a problem. Pain and form decide the workout now."
    else:
        if rpe is not None and rpe >= 8:
            short_answer = f"Keep it useful, not harder: RPE {rpe}/10 is already challenging."
        else:
            short_answer = "Keep going, but hold the effort steady and reassess before you add intensity."

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
    if elapsed_minutes is not None and planned_duration_minutes:
        remaining = max(0, planned_duration_minutes - elapsed_minutes)
        live_context.append(f"Time: {elapsed_minutes} minutes done, about {remaining} planned minutes left.")
    elif elapsed_minutes is not None:
        live_context.append(f"Time: {elapsed_minutes} minutes into the session.")

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
        "answer_style": (
            "Use urgent, plain language first; explain HR, RPE, AZM, and readiness only after the "
            "action is clear. Say that live HR/RPE/pain are user-reported inputs, and never imply "
            "this tool is streaming live band telemetry."
        ),
    }


def _today_realistic_followups(subjective_limiter: bool, illness_flags: list[str]) -> list[str]:
    prompts = [
        "Can I train hard today, or should I keep it controlled?",
        "I only have 30 minutes. What is the best use of it?",
        "What would make you change the plan during my warm-up?",
        "How should I adjust if my heart rate or breathing feels unusual?",
    ]
    if subjective_limiter:
        prompts.append("If I still feel off after the warm-up, what should I switch to?")
    if illness_flags:
        prompts.insert(0, "What easy movement is okay while I have symptoms?")
    return _dedupe(prompts)[:5]


def _humanized_evidence(items: list[str]) -> list[str]:
    return _dedupe([_humanize_evidence_item(item) for item in items if item])


def _prioritize_coach_evidence(evidence: list[str]) -> list[str]:
    core: list[str] = []
    secondary: list[str] = []
    rest: list[str] = []
    secondary_needles = (
        "spo2",
        "oxygen saturation",
        "respiratory rate",
        "sleep temperature",
        "vo2 max",
        "steps across",
        "recorded step days",
        "heart-rate zones",
        "activity levels",
    )
    core_needles = (
        "data freshness",
        "sleep",
        "hrv",
        "resting heart",
        "resting hr",
        "active zone minutes",
        "current user-stated feeling",
        "check-in",
    )
    for item in evidence:
        lower = str(item).lower()
        if any(needle in lower for needle in secondary_needles):
            secondary.append(item)
        elif any(needle in lower for needle in core_needles):
            core.append(item)
        else:
            rest.append(item)
    return _dedupe(core[:4] + secondary[:5] + core[4:] + rest)


def _humanize_evidence_item(item: str) -> str:
    text = str(item)
    lower = text.lower()
    if "spo2" in lower or "oxygen saturation" in lower:
        return f"{text} Oxygen is useful context with breathing, symptoms, and heart signals; it is not a standalone green light."
    if "respiratory rate" in lower:
        return f"{text} Breathing rate matters most when it is unusual for you or paired with symptoms."
    if "sleep temperature" in lower:
        return f"{text} Temperature can add a stress or illness clue, but it does not diagnose anything by itself."
    if "vo2 max" in lower:
        return f"{text} VO2 max helps plan endurance work and progress, not today's recovery ceiling."
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
    if "steps across" in lower or "recorded step days" in lower:
        return f"{text} This is movement-load context, and the recorded-day window keeps the average honest."
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

    steps_today = _safe_int(today.get("steps"))
    activity_date = context.get("activity_date") or context.get("latest_date") or "today"
    if steps_today is not None and steps_today >= 15000:
        evidence.append(
            f"High-step movement context: {steps_today:,} steps on {activity_date} so far. "
            "Steps are leg/load context, not a standalone recovery score."
        )
    if current_feeling and _high_movement_from_text(current_feeling.lower()):
        evidence.append(
            "User-stated high walking or step volume today; treat this as leg fatigue/load context."
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

    evidence.extend(_signal_snapshot_evidence(context.get("available_signal_snapshot", {}), limit=7))

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


def _signal_snapshot_evidence(snapshot: dict[str, Any], *, limit: int = 6) -> list[str]:
    if snapshot.get("status") != "ok":
        return []
    priority = {
        "spo2": 0,
        "respiratory_rate": 1,
        "sleep_temperature": 2,
        "heart_rate_zones": 3,
        "steps": 4,
        "heart_rate_samples": 5,
        "vo2_max": 6,
        "activity_levels": 7,
        "sedentary_minutes": 8,
        "distance": 9,
        "floors": 10,
    }
    signals = sorted(
        snapshot.get("signals") or [],
        key=lambda signal: priority.get(str(signal.get("id") or ""), 99),
    )
    lines: list[str] = []
    for signal in signals:
        signal_id = str(signal.get("id") or "")
        if signal_id not in priority:
            continue
        display = signal.get("display")
        if not display:
            continue
        label = signal.get("label") or signal_id
        coaching_use = signal.get("coaching_use") or signal.get("why_it_matters") or ""
        if signal_id == "steps":
            window = signal.get("window_summary") or {}
            display = window.get("display") or display
            average = window.get("average_display")
            if average:
                display = f"{display}; {average}"
        lines.append(f"{label}: {display}. {coaching_use}".strip())
        if len(lines) >= limit:
            break
    return lines


def _metric_labels_from_evidence(evidence: list[str]) -> list[str]:
    labels = ["Readiness", "RPE", "HRV", "Resting HR", "AZM"]
    evidence_text = " ".join(str(item) for item in evidence).lower()
    additions = (
        ("SpO2", ("spo2", "oxygen saturation")),
        ("Respiratory rate", ("respiratory rate", "breaths/min")),
        ("Sleep temperature", ("sleep temperature", "temperature deviation")),
        ("VO2 max", ("vo2 max", "cardio capacity")),
        ("HR", ("heart-rate samples", "heart rate samples", "live heart rate")),
    )
    for label, needles in additions:
        if any(needle in evidence_text for needle in needles):
            labels.append(label)
    return _dedupe(labels)


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
    )
    if any(re.search(pattern, lower) for pattern in not_right_patterns):
        return True
    return any(
        _has_unnegated_phrase(lower, term)
        for term in SUBJECTIVE_LIMITER_PHRASES
    )


def _positive_or_neutral_feeling_from_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    phrases = (
        "feel good",
        "feeling good",
        "feel great",
        "feeling great",
        "feel normal",
        "feeling normal",
        "feel fresh",
        "feeling fresh",
        "feel strong",
        "feeling strong",
        "slept great",
        "slept well",
    )
    return any(_has_unnegated_phrase(lower, phrase) for phrase in phrases)


def _time_limit_minutes_from_text(text: str) -> int | None:
    if not text:
        return None
    matches = re.findall(
        r"\b(?:only\s+have|have|got|with|for|about|around|approximately|under)?\s*(\d{1,3})\s*(?:min|mins|minute|minutes)\b",
        text.lower(),
    )
    if not matches:
        return None
    minutes = int(matches[0])
    return max(5, min(minutes, 180))


def _movement_minutes_before_obligation(text: str) -> int | None:
    lower = (text or "").lower()
    if not lower:
        return None
    obligation_terms = (
        "class",
        "meeting",
        "work",
        "shift",
        "call",
        "appointment",
        "travel",
        "flight",
        "commute",
        "dinner",
        "date",
        "social",
        "plans",
        "reservation",
        "event",
    )
    if not _mentions(lower, obligation_terms):
        return None
    obligation_pattern = (
        "class|meeting|work|shift|call|appointment|travel|flight|commute|dinner|"
        "date|social|plans|reservation|event"
    )
    match = re.search(
        rf"\b(?:{obligation_pattern})\b.{{0,32}}?\b(?:in|within|starts in|begins in)\s+(\d{{1,3}})\s*(?:min|mins|minute|minutes)\b",
        lower,
    )
    if not match:
        match = re.search(
            rf"\b(?:in|within)\s+(\d{{1,3}})\s*(?:min|mins|minute|minutes)\b.{{0,32}}?\b(?:{obligation_pattern})\b",
            lower,
        )
    if not match:
        return None
    countdown = max(5, min(int(match.group(1)), 180))
    if countdown <= 20:
        return max(5, countdown - 10)
    if countdown <= 45:
        return 20
    if countdown <= 75:
        return 25
    if countdown <= 120:
        return 35
    return None


def _short_constrained_session(text: str, minutes: int | None) -> bool:
    lower = (text or "").lower()
    if minutes is not None and minutes <= 25:
        return True
    return _mentions(
        lower,
        (
            "between meetings",
            "in between meetings",
            "lunch break",
            "coffee break",
            "quick workout",
            "quick session",
            "quick lift",
            "short on time",
            "time crunch",
            "limited time",
            "busy day",
            "squeeze it in",
            "squeezed in",
            "fit it in",
            "only have",
            "only got",
        ),
    )


def _reserve_energy_obligation_from_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    after_only = (
        "after work" in lower
        or "after class" in lower
        or "after school" in lower
        or "after my shift" in lower
        or "after shift" in lower
    )
    obligation_terms = (
        "class",
        "school",
        "lecture",
        "meeting",
        "call",
        "appointment",
        "work shift",
        "shift",
        "office",
        "presentation",
        "exam",
        "interview",
        "dinner",
        "date",
        "event",
        "party",
        "travel",
        "flight",
        "drive",
        "commute",
        "errand",
        "errands",
    )
    has_obligation = any(_has_unnegated_phrase(lower, term) for term in obligation_terms)
    if not has_obligation:
        return False

    direct_preserve = (
        "do not want to be drained",
        "don't want to be drained",
        "dont want to be drained",
        "don't want to feel drained",
        "dont want to feel drained",
        "not feel drained",
        "not be drained",
        "still need energy",
        "need energy for",
        "save energy",
        "preserve energy",
        "leave energy",
        "not be cooked",
        "not feel cooked",
    )
    if any(phrase in lower for phrase in direct_preserve):
        return True

    timing_cues = (
        "before",
        "soon",
        "later",
        "later today",
        "tonight",
        "this evening",
        "right after",
        "after this",
        "then",
        "next",
        "heading to",
        "need to go",
        "have to go",
        "got to go",
        "gotta go",
    )
    has_timing_cue = any(phrase in lower for phrase in timing_cues)
    has_in_window = re.search(r"\bin\s+\d{1,3}\s*(?:min|mins|minute|minutes|hr|hrs|hour|hours)\b", lower) is not None
    if after_only and not (has_in_window or any(phrase in lower for phrase in ("before", "later", "soon", "then", "next"))):
        return False
    return has_in_window or has_timing_cue


def _explicit_high_intensity_request(text: str) -> bool:
    lower = (text or "").lower()
    phrases = (
        "hard workout",
        "hard session",
        "hard intervals",
        "push hard",
        "go hard",
        "train hard",
        "intense workout",
        "intense session",
        "high intensity",
        "hiit",
        "sprint workout",
        "sprints",
        "threshold run",
        "tempo run",
        "race pace",
        "all-out",
        "all out",
        "max effort",
        "heavy singles",
        "heavy set",
        "heavy lift",
        "one rep max",
        "1rm",
        "metcon",
    )
    return any(_has_unnegated_phrase(lower, phrase) for phrase in phrases)


def _high_movement_from_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    phrases = (
        "walked a ton",
        "walked a lot",
        "walked so much",
        "lots of walking",
        "lot of walking",
        "ton of walking",
        "high steps",
        "lots of steps",
        "lot of steps",
        "many steps",
        "step count is high",
        "on my feet all day",
        "been on my feet",
        "standing all day",
        "long walk",
        "long hike",
        "hiked a lot",
    )
    return any(_has_unnegated_phrase(lower, phrase) for phrase in phrases)


def _protect_lower_body_from_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    explicit_phrases = (
        "don't want tired legs",
        "dont want tired legs",
        "do not want tired legs",
        "don't want my legs tired",
        "dont want my legs tired",
        "do not want my legs tired",
        "keep legs fresh",
        "keep my legs fresh",
        "keep legs useful",
        "keep my legs useful",
        "keep legs usable",
        "keep my legs usable",
        "useful legs",
        "usable legs",
        "fresh legs",
        "save my legs",
        "save legs",
        "preserve legs",
        "preserve my legs",
        "protect legs",
        "protect my legs",
        "leg fatigue",
        "legs fatigued",
        "tired legs",
        "heavy legs tomorrow",
        "legs heavy tomorrow",
        "cook my legs",
        "cook myself for tomorrow",
        "drained legs",
    )
    if any(phrase in lower for phrase in explicit_phrases):
        return True

    future_terms = ("tomorrow", "later today", "tonight", "this evening", "next day", "upcoming")
    lower_body_events = (
        "long hike",
        "hike",
        "hiking",
        "long walk",
        "walk",
        "run",
        "race",
        "soccer",
        "basketball",
        "tennis",
        "squash",
        "pickleball",
    )
    preserve_intents = (
        "don't want",
        "dont want",
        "do not want",
        "avoid",
        "protect",
        "preserve",
        "save",
        "fresh",
        "ready for",
        "not tired",
        "not drained",
        "useful",
        "usable",
    )
    return (
        any(term in lower for term in future_terms)
        and any(term in lower for term in lower_body_events)
        and any(term in lower for term in preserve_intents)
    )


def _workout_activity_selection_text(
    *,
    planned: str,
    constraint_text: str,
    protect_lower_body: bool,
) -> str:
    if not protect_lower_body:
        return " ".join([planned, constraint_text])

    combined = " ".join([planned, constraint_text])
    parts: list[str] = []
    planned_is_generic = _generic_workout_text(planned)
    planned_mentions_cardio = _mentions(planned, CARDIO_SPORT_TERMS)
    planned_mentions_lower_strength = _mentions(planned, LOWER_BODY_TRAINING_TERMS)
    if planned and not planned_is_generic and (planned_mentions_cardio or not planned_mentions_lower_strength):
        parts.append(planned)
    if _mentions(combined, UPPER_BODY_TRAINING_TERMS):
        parts.append("upper body chest back shoulders arms press row pull push")
    if _mentions(combined, ("core", "abs", "mobility", "stretch", "stretching")):
        parts.append("core mobility")
    if not parts:
        parts.append("upper body chest back press row pull push core mobility")
    return " ".join(_dedupe(parts))


def _generic_workout_text(text: str) -> bool:
    normalized = " ".join((text or "").split()).strip().lower()
    if normalized in {"", "workout", "general workout", "workout plan", "train", "training", "train today"}:
        return True
    return normalized in {
        "fitness",
        "exercise",
        "movement",
        "useful controlled workout",
        "recovery workout",
    }


def _workout_intent_context(
    *,
    planned_activity: str,
    target_areas: list[str],
    constraints: str | None,
    exercise_context_text: str,
    protect_lower_body: bool,
    preserving_next_session: bool,
    stated_high_movement: bool,
    high_step_load: bool,
    localized_soreness_away_from_target: bool,
    subjective_limiter: bool,
    reserve_energy_obligation: bool,
    requested_duration_minutes: int | None,
) -> dict[str, Any]:
    constraint_roles: list[str] = []
    exercise_bias: list[str] = []
    guardrails: list[str] = []
    do_not_treat_as_targets: list[str] = []

    if protect_lower_body:
        primary_job = "train today while preserving fresh legs for an upcoming walk, hike, sport, or long day"
        exercise_bias.extend(["upper_body", "core", "mobility", "easy_recovery_movement"])
        constraint_roles.append("lower_body_protection")
        guardrails.extend(
            [
                "avoid leg-fatiguing strength, intervals, plyometrics, hill work, or finishers",
                "keep the session useful enough to train, but easy enough that tomorrow still feels available",
            ]
        )
        do_not_treat_as_targets.extend(["legs", "hike", "walk", "future sport"])
    elif preserving_next_session:
        primary_job = "train today without stealing readiness from the next session"
        exercise_bias.extend(["controlled_volume", "submaximal_strength", "technique"])
        constraint_roles.append("future_session_priority")
        guardrails.append("leave clear energy in reserve")
    elif reserve_energy_obligation:
        primary_job = "get useful movement without draining energy, focus, or calm breathing before the next obligation"
        exercise_bias.extend(["minimum_effective_dose", "easy_zone_2", "mobility", "light_technique"])
        constraint_roles.append("reserve_energy_obligation")
        guardrails.append("finish early enough to cool down, hydrate, and switch contexts")
    elif localized_soreness_away_from_target:
        primary_job = "train the requested area while keeping the sore area out of the job"
        exercise_bias.extend(["supported_exercises", "machine_options", "reduced_compensation"])
        constraint_roles.append("localized_soreness_guardrail")
        guardrails.append("choose exercise variations that do not make the sore area compensate")
    elif subjective_limiter:
        primary_job = "make the session useful but conservative because current body feel is the limiter"
        exercise_bias.extend(["readiness_screen", "lower_rpe_cap", "minimum_effective_dose"])
        constraint_roles.append("current_body_feel_limiter")
        guardrails.append("let the first 10-15 minutes decide whether to continue")
    else:
        primary_job = "match the requested workout to today's recovery and load context"
        exercise_bias.extend(["requested_session", "warmup_check", "data_guided_intensity"])

    if stated_high_movement or high_step_load:
        constraint_roles.append("movement_volume_counts_as_leg_load")
        guardrails.append("count walking and steps as leg/load context before adding conditioning")
    if requested_duration_minutes:
        constraint_roles.append("time_box")
        guardrails.append(f"fit the plan inside about {requested_duration_minutes} minutes including warm-up")

    return {
        "primary_job": primary_job,
        "planned_activity_user_wants": planned_activity,
        "target_areas_user_requested": target_areas,
        "user_constraints": constraints,
        "exercise_selection_basis": exercise_context_text,
        "constraint_roles": _dedupe(constraint_roles),
        "exercise_bias": _dedupe(exercise_bias),
        "guardrails": _dedupe(guardrails),
        "do_not_treat_as_targets": _dedupe(do_not_treat_as_targets),
        "model_instruction": (
            "Use this intent context to explain the plan. Do not turn a protective constraint into the "
            "exercise target; use it to choose safer variations, intensity, and avoid-list items."
        ),
    }


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
        "feel faint",
        "felt faint",
        "lightheaded",
        "light headed",
        "light-headed",
        "woozy",
        "seeing stars",
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
        prefix = text[max(0, match.start() - 64) : match.start()]
        local_prefix = re.split(r"[.!?;]", prefix)[-1]
        if re.search(r"\b(no|not|without|denies|deny|none)\b[\s,;:.-]{0,12}$", prefix):
            continue
        if re.search(
            r"\b(?:not|never)\s+"
            r"(?:saying|claiming|reporting|telling(?:\s+you)?|indicating|mentioning)\b",
            local_prefix,
        ):
            continue
        if re.search(r"\b(?:do not|don't|dont)\s+(?:feel|have)\b", local_prefix) and re.search(
            r"\b(?:or|and|,)\s*$", local_prefix
        ):
            continue
        if re.search(r"\b(?:do not|don't|dont)\s+(?:have\s+|feel\s+|feeling\s+)?$", prefix):
            continue
        return True
    return False


def _activity_guidance(planned: str, rpe_cap: int, intensity: str) -> tuple[list[str], list[str], list[str], list[str]]:
    is_cardio_sport = _mentions(planned, CARDIO_SPORT_TERMS)
    warmup = [
        "5-8 minutes easy cardio to check readiness.",
        "Dynamic hips, thoracic rotations, and shoulder/scapular activation.",
        "Two ramp sets before the first working set.",
    ]
    focus = ["Move well first, then add load only if the warm-up feels better than expected."]
    avoid = ["Max-effort attempts", "Adding extra hard conditioning after the session"]
    session = [f"Keep working sets at or below RPE {rpe_cap}/10 ({_rpe_plain(rpe_cap)})."]

    if is_cardio_sport:
        warmup = [
            "5-8 minutes very easy movement to check breathing, legs, and coordination.",
            "Add 2-3 short relaxed strides or technique reps only if the warm-up feels smooth.",
        ]
        focus = [
            "Use this as aerobic quality, not a proving-ground workout.",
            "Keep pace conversational unless the plan specifically calls for short controlled pickups.",
            "Stop before stride, footwork, or breathing gets sloppy.",
        ]
        avoid = ["All-out sprints", "Extra intervals", "Hard cutting if knee, hip, or back feels unstable"]
        session = [
            f"Keep the hard parts at or below RPE {rpe_cap}/10 ({_rpe_plain(rpe_cap)}).",
            "Use easy aerobic work as the default; add short pickups only if everything feels normal.",
        ]

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
    if is_cardio_sport:
        focus.extend(["Bias skill, footwork quality, and easy aerobic work over all-out intervals."])
        session.extend(["Keep change-of-direction volume low if recovery is red.", "Stop before movement gets sloppy."])
        avoid.extend(["Repeated max sprints", "Hard cutting if knee, hip, or back feels unstable"])
    if _mentions(planned, ("leg", "squat", "lower", "quad", "hamstring")) and not is_cardio_sport:
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
    is_cardio_sport = _mentions(planned, CARDIO_SPORT_TERMS)

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

    if _mentions(planned, ("core", "abs", "mobility")):
        add(
            "Dead bug + side plank",
            "2",
            "8 each side + 20-30 sec",
            "Core work that supports tomorrow without tiring your legs.",
            "Pallof press or easy breathing drill.",
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

    if is_cardio_sport:
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

    if _mentions(planned, ("leg", "squat", "lower", "quad", "hamstring")) and not is_cardio_sport:
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


def _current_or_checkin_illness_flags(
    *,
    current_illness_flags: list[str],
    checkin_illness_flags: list[str],
    current_text: str,
) -> list[str]:
    if current_illness_flags:
        return _dedupe(current_illness_flags)
    if checkin_illness_flags and _current_text_overrides_checkin_illness(current_text):
        return []
    return _dedupe(checkin_illness_flags)


def _current_text_overrides_checkin_illness(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if _positive_or_neutral_feeling_from_text(lower):
        return True
    if _has_training_pain_constraint(lower):
        return True
    return _mentions(
        lower,
        (
            "feel",
            "feeling",
            "energy",
            "pain",
            "sore",
            "soreness",
            "tight",
            "normal",
            "okay",
            "fine",
            "good",
        ),
    )


def _has_training_pain_constraint(text: str) -> bool:
    if not text:
        return False
    musculoskeletal_text = re.sub(r"\b(no\s+)?sore throat\b", "", text.lower())
    return any(
        _has_unnegated_phrase(musculoskeletal_text, term)
        for term in ("sore", "soreness", "pain", "ache", "tight", "tweak", "injury", "complains")
    )


def _localized_soreness_away_from_activity(text: str, planned: str) -> bool:
    if not text or not planned:
        return False
    lower_text = text.lower()
    lower_planned = planned.lower()
    if any(_has_unnegated_phrase(lower_text, term) for term in ("fatigue", "fatigued", "tired", "drained", "low energy")):
        return False
    lower_body_soreness = _mentions(
        lower_text,
        ("leg", "legs", "quad", "quads", "hamstring", "calf", "calves", "glute", "knee", "ankle", "foot", "feet"),
    ) and any(
        _has_unnegated_phrase(lower_text, term)
        for term in ("sore", "soreness", "pain", "ache", "tight", "heavy")
    )
    if not lower_body_soreness:
        return False
    upper_body_plan = _mentions(
        lower_planned,
        (
            "upper",
            "chest",
            "back",
            "shoulder",
            "arm",
            "bicep",
            "tricep",
            "press",
            "bench",
            "row",
            "pull",
            "push",
        ),
    )
    lower_body_or_sport_plan = _mentions(
        lower_planned,
        (
            "leg",
            "lower",
            "squat",
            "lunge",
            "deadlift",
            "hinge",
            "run",
            "sprint",
            "soccer",
            "basketball",
            "squash",
            "tennis",
            "pickleball",
            "cardio",
            "hiit",
            "interval",
        ),
    )
    return upper_body_plan and not lower_body_or_sport_plan


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
    if not text:
        return False
    return any(_contains_term(text, word) for word in words)


def _contains_term(text: str, term: str) -> bool:
    term = term.strip().lower()
    if not term:
        return False
    if " " in term:
        pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(part) for part in term.split()) + r"(?![a-z0-9])"
        return re.search(pattern, text) is not None

    suffix = r"(?:s|es|ed|ing)?"
    if term == "run":
        suffix = r"(?:s|ning|ner|ners)?"
    pattern = rf"(?<![a-z0-9]){re.escape(term)}{suffix}(?![a-z0-9])"
    return re.search(pattern, text) is not None


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
        "hike",
        "hiking",
        "walk",
        "long walk",
        "run",
        "race",
        "match",
        "game",
        "tournament",
        "practice",
        "sport",
        "workout",
        "training",
        "train",
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


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
