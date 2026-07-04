from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from typing import Any

import httpx

from .auth import AuthService
from .db import Database, dumps, loads
from .google_health import GoogleHealthClient, SYNC_DATA_TYPE_IDS, SYNC_DATA_TYPES, metric_catalog
from .settings import Settings
from .time_utils import iso_now, utc_now

RECOVERY_KEYS = (
    "sleep",
    "hrv_ms",
    "hrv_sample_ms",
    "resting_heart_rate",
    "spo2_avg",
    "spo2_sample",
    "respiratory_rate",
    "respiratory_rate_sleep",
    "sleep_temperature",
)
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

INTENT_METRICS = {
    "daily_plan": [
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "activity-level",
        "active-minutes",
        "steps",
        "distance",
        "exercise",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    ],
    "workout_decision": [
        "exercise",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "calories-in-heart-rate-zone",
        "steps",
        "active-minutes",
        "activity-level",
        "distance",
        "floors",
        "sedentary-period",
        "heart-rate",
        "daily-resting-heart-rate",
        "daily-heart-rate-variability",
        "sleep",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "daily-oxygen-saturation",
        "oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    ],
    "active_workout": [
        "heart-rate",
        "time-in-heart-rate-zone",
        "active-zone-minutes",
        "exercise",
        "daily-resting-heart-rate",
        "daily-heart-rate-variability",
        "sleep",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
    ],
    "recovery": [
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "active-zone-minutes",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
    ],
    "sleep": [
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "daily-sleep-temperature-derivations",
        "daily-oxygen-saturation",
    ],
    "breathing_recovery": [
        "daily-oxygen-saturation",
        "oxygen-saturation",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "daily-sleep-temperature-derivations",
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
    ],
    "heart": [
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "heart-rate",
        "heart-rate-variability",
        "time-in-heart-rate-zone",
    ],
    "activity_load": [
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "calories-in-heart-rate-zone",
        "activity-level",
        "active-minutes",
        "steps",
        "distance",
        "floors",
        "sedentary-period",
        "active-energy-burned",
        "total-calories",
        "exercise",
    ],
    "subjective": [
        "sleep",
        "exercise",
        "active-zone-minutes",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
    ],
    "goal": [
        "exercise",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "active-minutes",
        "steps",
        "distance",
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "daily-vo2-max",
    ],
    "specific_activity": [
        "exercise",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "activity-level",
        "active-minutes",
        "steps",
        "distance",
        "floors",
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
    ],
    "multi_day_plan": [
        "exercise",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "activity-level",
        "active-minutes",
        "steps",
        "distance",
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    ],
    "symptom_safety": [
        "daily-resting-heart-rate",
        "heart-rate",
        "daily-heart-rate-variability",
        "sleep",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
    ],
    "general_overview": [
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "activity-level",
        "steps",
        "active-minutes",
        "distance",
        "exercise",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "daily-oxygen-saturation",
        "oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    ],
    "metric_discovery": [
        "sleep",
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "heart-rate",
        "heart-rate-variability",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "calories-in-heart-rate-zone",
        "activity-level",
        "active-minutes",
        "steps",
        "distance",
        "floors",
        "sedentary-period",
        "exercise",
        "daily-respiratory-rate",
        "respiratory-rate-sleep-summary",
        "daily-oxygen-saturation",
        "oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "daily-vo2-max",
    ],
}

METRIC_COACHING_REASONS = {
    "sleep": "Sleep duration, timing, and stages are primary recovery and fatigue context.",
    "daily-heart-rate-variability": "Daily HRV helps spot autonomic recovery changes versus baseline.",
    "heart-rate-variability": "HRV samples can add detail when daily HRV is sparse.",
    "daily-resting-heart-rate": "Resting heart rate often rises with stress, fatigue, illness, or under-recovery.",
    "heart-rate": "Heart-rate samples help explain intensity, unusual spikes, and workout effort.",
    "time-in-heart-rate-zone": "Time in zones shows how much cardiovascular stress was accumulated.",
    "active-zone-minutes": "Active Zone Minutes are a compact Fitbit load signal for workout decisions.",
    "active-minutes": "Active minutes show movement volume even when zone minutes are low.",
    "steps": "Steps are the simplest daily movement and load signal.",
    "distance": "Distance helps interpret walking or running volume.",
    "exercise": "Exercise sessions provide workout type, duration, calories, and session heart-rate context.",
    "daily-respiratory-rate": "Respiratory rate can support sleep and recovery interpretation.",
    "respiratory-rate-sleep-summary": "Sleep respiratory summaries can add overnight recovery context.",
    "daily-oxygen-saturation": "SpO2 can provide extra overnight recovery context when available.",
    "oxygen-saturation": "SpO2 samples can provide extra recovery context when daily summaries are sparse.",
    "daily-sleep-temperature-derivations": "Sleep temperature deviation can be a useful recovery clue when available.",
    "daily-vo2-max": "VO2 max is long-term cardio capacity context, not a same-day readiness signal.",
    "activity-level": "Activity levels show whether movement was light, moderate, vigorous, or sedentary.",
    "sedentary-period": "Sedentary time helps balance movement breaks and total daily load.",
    "calories-in-heart-rate-zone": "Calories by heart-rate zone add intensity context when zone minutes are present.",
    "active-energy-burned": "Active calories are rough movement workload context, not a precise fueling target.",
    "total-calories": "Total calories can provide broad energy-expenditure context when available.",
    "floors": "Floors can matter for leg load, hikes, and climbing-heavy days.",
}

SYNC_PRIORITY = (
    "sleep",
    "daily-resting-heart-rate",
    "daily-heart-rate-variability",
    "active-zone-minutes",
    "time-in-heart-rate-zone",
    "heart-rate",
    "active-minutes",
    "steps",
    "exercise",
    "daily-respiratory-rate",
    "daily-oxygen-saturation",
    "daily-sleep-temperature-derivations",
    "respiratory-rate-sleep-summary",
    "oxygen-saturation",
    "heart-rate-variability",
    "calories-in-heart-rate-zone",
    "total-calories",
    "active-energy-burned",
    "distance",
    "activity-level",
    "sedentary-period",
    "floors",
    "swim-lengths-data",
    "daily-vo2-max",
)

CORE_SYNC_METRICS = {
    "sleep",
    "daily-resting-heart-rate",
    "daily-heart-rate-variability",
    "active-zone-minutes",
    "time-in-heart-rate-zone",
    "active-minutes",
    "steps",
    "exercise",
    "daily-respiratory-rate",
    "daily-oxygen-saturation",
    "daily-sleep-temperature-derivations",
    "respiratory-rate-sleep-summary",
}
SYNC_METRIC_TIMEOUT_CAP_SECONDS = 4
SYNC_REQUEST_BUDGET_CAP_SECONDS = 16
SYNC_METRIC_PAGE_LIMIT_CAP = 4
SYNC_METRIC_CONCURRENCY_CAP = 8
LIVE_SECONDARY_RECORD_LIMIT = 50

logger = logging.getLogger(__name__)


class HealthStore:
    def __init__(self, db: Database, auth: AuthService, settings: Settings):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.google = GoogleHealthClient(settings.google_health_api_base)

    async def sync_latest(self, user_id: str, force: bool = False) -> dict[str, Any]:
        if not self.auth.refresh_token_available(user_id):
            return setup_required()

        abandoned = self._mark_abandoned_syncs(user_id)
        if not force:
            active = self._active_sync_result(user_id)
            if active:
                return active
            recent = self._recent_sync_result(user_id, abandoned_syncs=abandoned)
            if recent:
                return recent

        access_token = await self.auth.ensure_google_access_token(user_id)
        if not access_token:
            return setup_required("Google access token is unavailable. Reconnect Google Health.")

        started_at = iso_now()
        sync_id = self._start_sync(user_id, started_at)
        upserted = 0
        now = utc_now()
        start, sync_window = self._sync_window(user_id, now)
        start_time = start.isoformat().replace("+00:00", "Z")
        end_time = (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        start_date = start.date().isoformat()
        end_date = (now.date() + timedelta(days=1)).isoformat()
        sync_window.update(
            {
                "sync_mode": "parallel_bounded",
                "start_time": start_time,
                "end_time": end_time,
                "start_date": start_date,
                "end_date": end_date,
                "metric_priority": list(SYNC_PRIORITY),
            }
        )

        metric_errors: list[dict[str, str]] = []
        metrics_synced: list[str] = []
        metrics_fetched: list[str] = []
        metrics_deferred: list[str] = []
        metric_timings: list[dict[str, Any]] = []
        specs = self._sync_specs()
        metric_order = {spec.id: index for index, spec in enumerate(specs)}
        metrics_considered = [spec.id for spec in specs]
        time_budget_exhausted = False
        configured_budget = max(1, int(self.settings.sync_request_budget_seconds or 1))
        configured_metric_timeout = max(1, int(self.settings.sync_metric_timeout_seconds or 1))
        configured_page_limit = max(1, int(self.settings.sync_metric_page_limit or 1))
        configured_concurrency = max(1, int(self.settings.sync_metric_concurrency or 1))
        configured_record_limit = max(1, int(self.settings.sync_metric_record_limit or 1))
        budget_seconds = min(SYNC_REQUEST_BUDGET_CAP_SECONDS, configured_budget)
        metric_timeout = min(SYNC_METRIC_TIMEOUT_CAP_SECONDS, configured_metric_timeout)
        page_limit = min(SYNC_METRIC_PAGE_LIMIT_CAP, configured_page_limit)
        concurrency = min(SYNC_METRIC_CONCURRENCY_CAP, configured_concurrency)
        record_limit = configured_record_limit
        started_monotonic = monotonic()
        deadline = monotonic() + budget_seconds

        try:
            logger.info(
                "google_health_sync_start user=%s sync_id=%s mode=parallel_bounded budget=%ss metric_timeout=%ss page_limit=%s concurrency=%s metrics=%s",
                user_id,
                sync_id,
                budget_seconds,
                metric_timeout,
                page_limit,
                concurrency,
                len(specs),
            )
            semaphore = asyncio.Semaphore(concurrency)
            http_timeout = httpx.Timeout(
                metric_timeout + 1,
                connect=min(2.0, float(metric_timeout)),
                read=metric_timeout + 1,
                write=metric_timeout + 1,
                pool=min(2.0, float(metric_timeout)),
            )
            http_limits = httpx.Limits(
                max_connections=concurrency,
                max_keepalive_connections=concurrency,
            )

            async def fetch_one(spec: Any) -> dict[str, Any]:
                remaining = deadline - monotonic()
                if remaining <= 1:
                    return {
                        "status": "deferred",
                        "metric": spec.id,
                        "reason": "time_budget_exhausted_before_start",
                    }
                timeout = max(1, min(metric_timeout, int(remaining)))
                async with semaphore:
                    remaining = deadline - monotonic()
                    if remaining <= 1:
                        return {
                            "status": "deferred",
                            "metric": spec.id,
                            "reason": "time_budget_exhausted_before_fetch",
                        }
                    timeout = max(1, min(metric_timeout, int(remaining)))
                    metric_started = monotonic()
                    try:
                        records = await asyncio.wait_for(
                            self._fetch_metric_records(
                                access_token,
                                spec,
                                start_time=start_time,
                                end_time=end_time,
                                start_date=start_date,
                                end_date=end_date,
                                timeout_seconds=timeout,
                                page_limit=page_limit,
                                client=google_http,
                            ),
                            timeout=timeout + 1,
                        )
                    except Exception as exc:
                        elapsed = round(monotonic() - metric_started, 3)
                        logger.info(
                            "google_health_sync_metric_error user=%s sync_id=%s metric=%s category=%s metric_elapsed=%ss total_elapsed=%ss",
                            user_id,
                            sync_id,
                            spec.id,
                            _sync_error_category(exc),
                            elapsed,
                            round(monotonic() - started_monotonic, 3),
                        )
                        return {
                            "status": "error",
                            "metric": spec.id,
                            "category": _sync_error_category(exc),
                            "error": _sync_error_message(exc),
                            "elapsed_seconds": elapsed,
                        }
                    elapsed = round(monotonic() - metric_started, 3)
                    logger.info(
                        "google_health_sync_metric_done user=%s sync_id=%s metric=%s records=%s metric_elapsed=%ss total_elapsed=%ss",
                        user_id,
                        sync_id,
                        spec.id,
                        len(records),
                        elapsed,
                        round(monotonic() - started_monotonic, 3),
                    )
                    return {
                        "status": "ok",
                        "metric": spec.id,
                        "records": records,
                        "elapsed_seconds": elapsed,
                        "records_may_be_truncated": (
                            spec.operation != "dailyRollUp" and len(records) >= page_limit * 1000
                        ),
                    }

            async with httpx.AsyncClient(timeout=http_timeout, limits=http_limits) as google_http:
                pending_by_task = {asyncio.create_task(fetch_one(spec)): spec for spec in specs}
                completed_results: list[dict[str, Any]] = []
                pending = set(pending_by_task)
                while pending:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        time_budget_exhausted = True
                        break
                    done, pending = await asyncio.wait(
                        pending,
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        time_budget_exhausted = True
                        break
                    for task in done:
                        completed_results.append(task.result())

                if pending:
                    time_budget_exhausted = True
                    metrics_deferred.extend(pending_by_task[task].id for task in pending)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

            successful_results: list[dict[str, Any]] = []
            for result_item in completed_results:
                metric = result_item["metric"]
                if result_item["status"] == "ok":
                    storage_records = _prepare_records_for_sync(
                        metric,
                        result_item.get("records") or [],
                        record_limit,
                    )
                    result_item["storage_records"] = storage_records
                    successful_results.append(result_item)
                    metric_timings.append(
                        {
                            "metric": metric,
                            "status": "ok",
                            "seconds": result_item.get("elapsed_seconds"),
                            "records": len(result_item.get("records") or []),
                            "stored_records": len(storage_records),
                            "storage_strategy": _storage_strategy(metric),
                            "records_may_be_truncated": result_item.get(
                                "records_may_be_truncated",
                                False,
                            ),
                        }
                    )
                elif result_item["status"] == "deferred":
                    metrics_deferred.append(metric)
                    metric_timings.append(
                        {
                            "metric": metric,
                            "status": "deferred",
                            "reason": result_item.get("reason"),
                        }
                    )
                else:
                    metric_errors.append(
                        {
                            "metric": metric,
                            "category": result_item["category"],
                            "error": result_item["error"],
                        }
                    )
                    metric_timings.append(
                        {
                            "metric": metric,
                            "status": "error",
                            "seconds": result_item.get("elapsed_seconds"),
                            "category": result_item.get("category"),
                        }
                    )

            metrics_deferred = _ordered_unique(metrics_deferred, metric_order)
            metric_errors.sort(key=lambda item: metric_order.get(item["metric"], len(metric_order)))
            metric_timings.sort(key=lambda item: metric_order.get(item["metric"], len(metric_order)))
            prepared_results = sorted(
                successful_results,
                key=lambda item: metric_order.get(item["metric"], len(metric_order)),
            )
            metrics_fetched = _ordered_unique(
                [item["metric"] for item in prepared_results],
                metric_order,
            )
            live_results = [
                item
                for item in prepared_results
                if item["metric"] in CORE_SYNC_METRICS
                or 0 < len(item["storage_records"]) <= LIVE_SECONDARY_RECORD_LIMIT
            ]
            no_record_results = [
                item
                for item in prepared_results
                if item["metric"] not in CORE_SYNC_METRICS and not item["storage_records"]
            ]
            heavy_secondary_results = [
                item
                for item in prepared_results
                if item["metric"] not in CORE_SYNC_METRICS
                and len(item["storage_records"]) > LIVE_SECONDARY_RECORD_LIMIT
            ]

            write_started = monotonic()
            live_written = self.upsert_metric_records(user_id, live_results)
            upserted += live_written
            metrics_synced.extend(item["metric"] for item in live_results if item["storage_records"])
            live_write_seconds = round(monotonic() - write_started, 3)
            _annotate_write_timings(metric_timings, live_results, live_write_seconds)

            if heavy_secondary_results:
                metrics_deferred.extend(item["metric"] for item in heavy_secondary_results)
                _annotate_secondary_timings(metric_timings, heavy_secondary_results)
            _annotate_no_record_timings(metric_timings, no_record_results)

            metrics_synced = _ordered_unique(metrics_synced, metric_order)
            metrics_deferred = _ordered_unique(metrics_deferred, metric_order)

            partial = bool(metric_errors or time_budget_exhausted or metrics_deferred)
            elapsed_seconds = round(monotonic() - started_monotonic, 3)
            if upserted == 0 and metric_errors:
                message = (
                    "Google Health sync failed before any records were saved. "
                    f"elapsed={elapsed_seconds}s first_metric={metric_errors[0]['metric']} "
                    f"first_error={metric_errors[0]['category']}: {metric_errors[0]['error']}"
                )
                self._finish_sync(sync_id, "error", upserted, message)
                return {
                    "status": "error",
                    "message": "Google Health sync failed.",
                    "detail": metric_errors[0]["error"],
                    "records_upserted": upserted,
                    "elapsed_seconds": elapsed_seconds,
                    "metrics_synced": metrics_synced,
                    "metrics_fetched": metrics_fetched,
                    "metrics_considered": metrics_considered,
                    "metrics_deferred": metrics_deferred,
                    "sync_diagnostics": {
                        "metric_timeout_seconds": metric_timeout,
                        "configured_metric_timeout_seconds": configured_metric_timeout,
                        "request_budget_seconds": budget_seconds,
                        "configured_request_budget_seconds": configured_budget,
                        "time_budget_exhausted": time_budget_exhausted,
                        "metrics_synced": metrics_synced,
                        "metrics_fetched": metrics_fetched,
                        "metrics_considered": metrics_considered,
                        "metrics_deferred": metrics_deferred,
                        "metric_timings": metric_timings,
                        "page_limit": page_limit,
                        "configured_page_limit": configured_page_limit,
                        "concurrency": concurrency,
                        "configured_concurrency": configured_concurrency,
                        "record_limit": record_limit,
                        "configured_record_limit": configured_record_limit,
                    },
                    "metric_errors": metric_errors[:10],
                }

            finish_status = "partial" if partial else "ok"
            finish_message = (
                (
                    "Google Health sync saved core answer-ready records; secondary persistence deferred. "
                    f"elapsed={elapsed_seconds}s metrics_synced={len(metrics_synced)} "
                    f"errors={len(metric_errors)} deferred={len(metrics_deferred)} "
                    f"time_budget_exhausted={time_budget_exhausted}"
                )
                if partial
                else f"Sync complete. elapsed={elapsed_seconds}s metrics_synced={len(metrics_synced)}"
            )
            self._finish_sync(sync_id, finish_status, upserted, finish_message)
            logger.info(
                "google_health_sync_finish user=%s sync_id=%s status=%s upserted=%s elapsed=%ss errors=%s deferred=%s",
                user_id,
                sync_id,
                finish_status,
                upserted,
                elapsed_seconds,
                len(metric_errors),
                len(metrics_deferred),
            )
        except Exception as exc:
            elapsed_seconds = round(monotonic() - started_monotonic, 3)
            detail = _sync_error_message(exc)
            self._finish_sync(sync_id, "error", upserted, detail)
            return {
                "status": "error",
                "message": "Google Health sync failed.",
                "detail": detail,
                "records_upserted": upserted,
                "elapsed_seconds": elapsed_seconds,
                "sync_diagnostics": {
                    "error_category": _sync_error_category(exc),
                    "metric_timeout_seconds": metric_timeout,
                    "configured_metric_timeout_seconds": configured_metric_timeout,
                    "request_budget_seconds": budget_seconds,
                    "configured_request_budget_seconds": configured_budget,
                    "time_budget_exhausted": time_budget_exhausted,
                    "metrics_synced": metrics_synced,
                    "metrics_fetched": metrics_fetched,
                    "metrics_considered": metrics_considered,
                    "metrics_deferred": metrics_deferred,
                    "metric_timings": metric_timings,
                    "page_limit": page_limit,
                    "configured_page_limit": configured_page_limit,
                    "concurrency": concurrency,
                    "configured_concurrency": configured_concurrency,
                    "record_limit": record_limit,
                    "configured_record_limit": configured_record_limit,
                },
            }

        elapsed_seconds = round(monotonic() - started_monotonic, 3)
        result = {
            "status": "ok",
            "message": (
                "Google Health sync saved fresh core records; some secondary metric persistence was deferred."
                if metric_errors or time_budget_exhausted or metrics_deferred
                else "Google Health sync complete."
            ),
            "records_upserted": upserted,
            "partial_sync": bool(metric_errors or time_budget_exhausted or metrics_deferred),
            "time_budget_exhausted": time_budget_exhausted,
            "metrics_synced": metrics_synced,
            "metrics_fetched": metrics_fetched,
            "metrics_considered": metrics_considered,
            "metrics_deferred": metrics_deferred,
            "elapsed_seconds": elapsed_seconds,
            "sync_diagnostics": {
                "metric_timeout_seconds": metric_timeout,
                "configured_metric_timeout_seconds": configured_metric_timeout,
                "request_budget_seconds": budget_seconds,
                "configured_request_budget_seconds": configured_budget,
                "time_budget_exhausted": time_budget_exhausted,
                "metric_error_count": len(metric_errors),
                "metrics_fetched": metrics_fetched,
                "metrics_considered": metrics_considered,
                "metrics_deferred": metrics_deferred,
                "metric_timings": metric_timings,
                "page_limit": page_limit,
                "configured_page_limit": configured_page_limit,
                "concurrency": concurrency,
                "configured_concurrency": configured_concurrency,
                "record_limit": record_limit,
                "configured_record_limit": configured_record_limit,
                "coverage_summary": _sync_coverage_summary(metrics_synced, metrics_deferred, metric_errors),
            },
            "metric_errors": metric_errors[:10],
            "lookback_days": sync_window["lookback_days"],
            "sync_window": sync_window,
        }
        context = self.latest_context(user_id)
        if context.get("status") == "ok":
            result.update(
                {
                    "context": context,
                    "latest_date": context.get("latest_date"),
                    "readiness": context.get("readiness"),
                    "today": context.get("today"),
                    "evidence": context.get("evidence"),
                    "freshness": context.get("data_freshness"),
                    "total_records": context.get("data_freshness", {}).get("records"),
                }
            )
        return result

    async def _fetch_metric_records(
        self,
        access_token: str,
        spec: Any,
        *,
        start_time: str,
        end_time: str,
        start_date: str,
        end_date: str,
        timeout_seconds: int,
        page_limit: int,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        client_kwargs = {"client": client} if client is not None and isinstance(self.google, GoogleHealthClient) else {}
        if spec.operation == "dailyRollUp":
            return await self.google.daily_rollup(
                access_token,
                spec,
                start_date,
                end_date,
                timeout_seconds=timeout_seconds,
                **client_kwargs,
            )
        return await self.google.list_data_points(
            access_token,
            spec,
            start_time,
            end_time,
            timeout_seconds=timeout_seconds,
            max_pages=page_limit,
            **client_kwargs,
        )

    def _sync_specs(self) -> list[Any]:
        priority = {metric: index for index, metric in enumerate(SYNC_PRIORITY)}
        return sorted(SYNC_DATA_TYPES, key=lambda spec: priority.get(spec.id, len(priority)))

    def _active_sync_result(self, user_id: str) -> dict[str, Any] | None:
        minutes = max(1, int(self.settings.sync_abandoned_after_minutes or 1))
        row = self.db.one(
            """
            SELECT id, started_at
            FROM sync_runs
            WHERE user_id = ? AND status = 'running' AND finished_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        if not row:
            return None
        try:
            started = datetime.fromisoformat(row["started_at"])
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None
        elapsed_minutes = (utc_now() - started).total_seconds() / 60
        if elapsed_minutes >= minutes:
            return None

        freshness = self.freshness(user_id)
        context = self.latest_context(user_id)
        result: dict[str, Any] = {
            "status": "sync_in_progress",
            "message": "Google Health sync is already running from the recent connection; retry shortly.",
            "sync_in_progress": True,
            "sync_skipped": True,
            "skip_reason": "active_sync_in_progress",
            "records_upserted": 0,
            "sync_window": {
                "mode": "active_sync_in_progress",
                "started_at": row["started_at"],
                "elapsed_minutes": round(elapsed_minutes, 2),
                "abandoned_after_minutes": minutes,
            },
            "freshness": freshness,
        }
        if context.get("status") == "ok":
            result.update(
                {
                    "status": "ok",
                    "message": "Google Health sync is still running; using the records already available.",
                    "context": context,
                    "latest_date": context.get("latest_date"),
                    "readiness": context.get("readiness"),
                    "today": context.get("today"),
                    "evidence": context.get("evidence"),
                    "total_records": context.get("data_freshness", {}).get("records"),
                }
            )
        return result

    def _mark_abandoned_syncs(self, user_id: str) -> int:
        minutes = max(1, int(self.settings.sync_abandoned_after_minutes or 1))
        cutoff = utc_now() - timedelta(minutes=minutes)
        rows = self.db.all(
            """
            SELECT id, started_at
            FROM sync_runs
            WHERE user_id = ? AND status = 'running' AND finished_at IS NULL
            """,
            (user_id,),
        )
        abandoned_ids: list[int] = []
        for row in rows:
            try:
                started = datetime.fromisoformat(row["started_at"])
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                started = datetime.min.replace(tzinfo=UTC)
            if started < cutoff:
                abandoned_ids.append(int(row["id"]))

        if not abandoned_ids:
            return 0

        message = (
            "Marked abandoned after connector request ended before sync completion "
            f"(timeout>{minutes}m)."
        )
        with self.db.connect() as conn:
            for sync_id in abandoned_ids:
                conn.execute(
                    """
                    UPDATE sync_runs
                    SET finished_at = ?, status = 'abandoned', message = ?
                    WHERE id = ? AND status = 'running'
                    """,
                    (iso_now(), message, sync_id),
                )
        return len(abandoned_ids)

    def _recent_sync_result(
        self,
        user_id: str,
        *,
        abandoned_syncs: int = 0,
    ) -> dict[str, Any] | None:
        min_interval = max(0, int(self.settings.sync_min_interval_minutes or 0))
        if min_interval <= 0:
            return None

        last_finished = self.db.one(
            """
            SELECT finished_at, status
            FROM sync_runs
            WHERE user_id = ?
              AND status IN ('ok', 'partial')
              AND finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        if not last_finished:
            return None
        try:
            finished_at = datetime.fromisoformat(last_finished["finished_at"])
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None
        if (utc_now() - finished_at).total_seconds() / 60 >= min_interval:
            return None

        freshness = self.freshness(user_id)
        if freshness.get("status") != "ok":
            return None
        sync_age = freshness.get("sync_age_minutes")
        if (
            freshness.get("freshness_level") != "fresh"
            or sync_age is None
            or sync_age >= min_interval
        ):
            return None

        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return None

        return {
            "status": "ok",
            "message": "Google Health data was already synced recently; skipped a redundant sync.",
            "sync_skipped": True,
            "skip_reason": "recent_fresh_sync",
            "records_upserted": 0,
            "total_records": freshness.get("records"),
            "lookback_days": 0,
            "sync_window": {
                "mode": "recent_skip",
                "min_interval_minutes": min_interval,
                "sync_age_minutes": sync_age,
                "latest_observed_date": freshness.get("latest_observed_date"),
                "last_sync": freshness.get("last_sync"),
                "previous_sync_status": last_finished["status"],
                "abandoned_syncs_cleaned": abandoned_syncs,
            },
            "freshness": freshness,
            "context": context,
            "latest_date": context.get("latest_date"),
            "readiness": context.get("readiness"),
            "today": context.get("today"),
            "evidence": context.get("evidence"),
        }

    def _sync_window(self, user_id: str, now: datetime) -> tuple[datetime, dict[str, Any]]:
        full_days = max(1, int(self.settings.sync_lookback_days or 7))
        incremental_days = max(
            1,
            min(int(self.settings.sync_incremental_lookback_days or 2), full_days),
        )
        overlap_hours = max(0, int(self.settings.sync_incremental_overlap_hours or 0))
        full_start = now - timedelta(days=full_days)
        row = self.db.one(
            """
            SELECT COUNT(*) AS records, MAX(observed_date) AS latest_observed
            FROM raw_health_records
            WHERE user_id = ?
            """,
            (user_id,),
        )
        if not row or not row["records"]:
            return full_start, {
                "mode": "initial",
                "lookback_days": full_days,
                "existing_records": 0,
                "latest_observed_date": None,
            }

        incremental_start = now - timedelta(days=incremental_days)
        latest_observed = row["latest_observed"]
        start = incremental_start
        if latest_observed:
            try:
                anchor = datetime.fromisoformat(latest_observed).replace(tzinfo=UTC) - timedelta(
                    hours=overlap_hours
                )
                start = max(incremental_start, anchor)
            except ValueError:
                start = incremental_start
        start = max(full_start, start)
        effective_days = max(1, math.ceil((now - start).total_seconds() / 86400))
        return start, {
            "mode": "incremental",
            "lookback_days": effective_days,
            "configured_incremental_days": incremental_days,
            "configured_overlap_hours": overlap_hours,
            "existing_records": int(row["records"]),
            "latest_observed_date": latest_observed,
        }

    def upsert_records(self, user_id: str, data_type: str, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        return self.upsert_metric_records(
            user_id,
            [{"metric": data_type, "storage_records": records}],
        )

    def upsert_metric_records(self, user_id: str, metric_results: list[dict[str, Any]]) -> int:
        if not metric_results:
            return 0
        synced_at = iso_now()
        rows: list[tuple[str, str, str, str | None, str, str]] = []
        replace_days_by_metric: dict[str, set[str]] = defaultdict(set)
        for result_item in metric_results:
            data_type = result_item["metric"]
            for record in result_item.get("storage_records") or []:
                day = observed_date(record)
                if _uses_compact_sync_storage(data_type) and _is_compact_sync_summary(record) and day:
                    replace_days_by_metric[data_type].add(day)
                rows.append(
                    (
                        user_id,
                        data_type,
                        record.get("name") or _stable_hash(record),
                        day,
                        dumps(record),
                        synced_at,
                    )
                )
        if not rows:
            return 0
        with self.db.connect() as conn:
            for data_type, days in sorted(replace_days_by_metric.items()):
                ordered_days = sorted(days)
                placeholders = ",".join("?" for _ in ordered_days)
                conn.execute(
                    f"""
                    DELETE FROM raw_health_records
                    WHERE user_id = ?
                      AND data_type = ?
                      AND observed_date IN ({placeholders})
                    """,
                    (user_id, data_type, *ordered_days),
                )
            for batch in _chunks(rows, 100):
                placeholders = ",".join("(?, ?, ?, ?, ?, ?)" for _ in batch)
                params = tuple(value for row in batch for value in row)
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO raw_health_records
                      (user_id, data_type, record_key, observed_date, payload_json, synced_at)
                    VALUES {placeholders}
                    """,
                    params,
                )
        return len(rows)

    def connection_status(self, user_id: str | None) -> dict[str, Any]:
        if not user_id:
            return setup_required()
        token_row = self.db.one(
            "SELECT updated_at FROM google_tokens WHERE user_id = ?",
            (user_id,),
        )
        if not token_row:
            return setup_required()
        count_row = self.db.one(
            "SELECT COUNT(*) AS count, MAX(synced_at) AS last_sync FROM raw_health_records WHERE user_id = ?",
            (user_id,),
        )
        return {
            "status": "connected",
            "google_connected": True,
            "records": count_row["count"] if count_row else 0,
            "last_sync": count_row["last_sync"] if count_row else None,
            "message": "Google Health is connected.",
        }

    def records_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = self.db.all(
            """
            SELECT data_type, observed_date, payload_json
            FROM raw_health_records
            WHERE user_id = ?
            ORDER BY observed_date DESC, id DESC
            """,
            (user_id,),
        )
        return [
            {
                "data_type": row["data_type"],
                "observed_date": row["observed_date"],
                "payload": loads(row["payload_json"], {}),
            }
            for row in rows
        ]

    def _records_summary_context(
        self,
        user_id: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        records = self.records_for_user(user_id)
        if not records:
            return records, {}, empty_data()
        summary = summarize_records(records)
        context = _context_from_summary(summary, self.freshness(user_id))
        return records, summary, context

    def available_metrics(self, user_id: str | None) -> dict[str, Any]:
        stats = {}
        if user_id:
            rows = self.db.all(
                """
                SELECT data_type, COUNT(*) AS records, MIN(observed_date) AS first_observed,
                       MAX(observed_date) AS latest_observed, MAX(synced_at) AS last_sync
                FROM raw_health_records
                WHERE user_id = ?
                GROUP BY data_type
                """,
                (user_id,),
            )
            stats = {row["data_type"]: dict(row) for row in rows}
        metrics = []
        for item in metric_catalog():
            metric_stats = stats.get(item["id"], {})
            metrics.append(
                {
                    **item,
                    "records": metric_stats.get("records", 0),
                    "first_observed_date": metric_stats.get("first_observed"),
                    "latest_observed_date": metric_stats.get("latest_observed"),
                    "last_sync": metric_stats.get("last_sync"),
                }
            )
        return {
            "status": "ok",
            "source": "local_synced_google_health_store",
            "metrics": metrics,
            "synced_metric_count": sum(1 for item in metrics if item["records"] > 0),
            "supported_metric_count": len(metrics),
            "excluded_categories": ["food", "nutrition", "ecg", "irregular-rhythm-notification"],
            "model_guidance": metric_catalog_model_guidance(metrics),
            "message": "These are the device-first Google Health/Fitbit metrics this app can sync and query.",
        }

    def query_metrics(
        self,
        user_id: str,
        metrics: list[str] | None = None,
        days: int = 7,
        start_date: str | None = None,
        end_date: str | None = None,
        include_records: bool = False,
        limit_per_metric: int = 25,
    ) -> dict[str, Any]:
        if not self.db.one("SELECT id FROM users WHERE id = ?", (user_id,)):
            return setup_required()

        stored_rows = self.db.all(
            """
            SELECT data_type, COUNT(*) AS records, MAX(observed_date) AS latest_observed,
                   MAX(synced_at) AS last_sync
            FROM raw_health_records
            WHERE user_id = ?
            GROUP BY data_type
            """,
            (user_id,),
        )
        stored_types = {row["data_type"] for row in stored_rows}
        latest_observed = max((row["latest_observed"] for row in stored_rows if row["latest_observed"]), default=None)
        last_sync = max((row["last_sync"] for row in stored_rows if row["last_sync"]), default=None)
        total_stored_records = sum(int(row["records"] or 0) for row in stored_rows)
        if not latest_observed:
            return empty_data()

        requested_metrics = _normalize_metric_request(metrics, stored_types)
        unknown_metrics = sorted(metric for metric in requested_metrics if metric not in SYNC_DATA_TYPE_IDS)
        requested_metrics = [metric for metric in requested_metrics if metric in SYNC_DATA_TYPE_IDS]
        if not requested_metrics:
            return {
                "status": "empty",
                "message": "None of the requested metrics are supported by this beta.",
                "unknown_metrics": unknown_metrics,
                "supported_metrics": sorted(SYNC_DATA_TYPE_IDS),
            }

        resolved_end = _coerce_date(end_date) or latest_observed
        resolved_start = _coerce_date(start_date)
        if not resolved_start:
            safe_days = max(1, min(int(days or 7), 30))
            resolved_start = (
                datetime.fromisoformat(resolved_end).date() - timedelta(days=safe_days - 1)
            ).isoformat()
        if resolved_start > resolved_end:
            resolved_start, resolved_end = resolved_end, resolved_start

        placeholders = ",".join("?" for _ in requested_metrics)
        rows = self.db.all(
            f"""
            SELECT data_type, observed_date, payload_json
            FROM raw_health_records
            WHERE user_id = ?
              AND data_type IN ({placeholders})
              AND observed_date >= ?
              AND observed_date <= ?
            ORDER BY data_type, observed_date DESC, id DESC
            """,
            (user_id, *requested_metrics, resolved_start, resolved_end),
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["data_type"]].append(
                {
                    "data_type": row["data_type"],
                    "observed_date": row["observed_date"],
                    "payload": loads(row["payload_json"], {}),
                }
            )

        catalog_by_id = {item["id"]: item for item in metric_catalog()}
        metric_results = {}
        limit = max(1, min(int(limit_per_metric or 25), 200))
        for metric_id in requested_metrics:
            records = grouped.get(metric_id, [])
            summary = summarize_records(records)
            daily = [
                {"date": day, **_public_daily_values(values)}
                for day, values in sorted(summary["daily"].items())
            ]
            observed_counts = Counter(record["observed_date"] for record in records)
            result = {
                "catalog": catalog_by_id[metric_id],
                "record_count": len(records),
                "first_observed_date": min(observed_counts) if observed_counts else None,
                "latest_observed_date": max(observed_counts) if observed_counts else None,
                "daily": daily,
                "observed_day_counts": [
                    {"date": day, "records": count} for day, count in sorted(observed_counts.items())
                ],
            }
            if include_records:
                result["records"] = [
                    {
                        "observed_date": record["observed_date"],
                        "payload": record["payload"],
                    }
                    for record in records[:limit]
                ]
                result["truncated"] = len(records) > limit
            metric_results[metric_id] = result

        missing_metrics = [metric for metric in requested_metrics if metric not in grouped]
        return {
            "status": "ok",
            "source": "local_synced_google_health_store",
            "data_freshness": {
                "status": "ok",
                "records": total_stored_records,
                "latest_observed_date": latest_observed,
                "last_sync": last_sync,
                **freshness_details(latest_observed, last_sync),
            },
            "start_date": resolved_start,
            "end_date": resolved_end,
            "requested_metrics": requested_metrics,
            "unknown_metrics": unknown_metrics,
            "missing_metrics": missing_metrics,
            "record_count": sum(len(records) for records in grouped.values()),
            "include_records": include_records,
            "metrics": metric_results,
            "next_actions": ["Run sync_latest_fitbit_data if you need fresher cloud-synced data."],
        }

    def freshness(self, user_id: str) -> dict[str, Any]:
        row = self.db.one(
            """
            SELECT COUNT(*) AS records, MAX(observed_date) AS latest_observed,
                   MAX(synced_at) AS last_sync
            FROM raw_health_records
            WHERE user_id = ?
            """,
            (user_id,),
        )
        if not row or row["records"] == 0:
            return empty_data()
        return {
            "status": "ok",
            "records": row["records"],
            "latest_observed_date": row["latest_observed"],
            "last_sync": row["last_sync"],
            **freshness_details(row["latest_observed"], row["last_sync"]),
        }

    def latest_context(self, user_id: str) -> dict[str, Any]:
        _, _, context = self._records_summary_context(user_id)
        return context

    def health_overview(
        self,
        user_id: str,
        days: int = 14,
        *,
        _records: list[dict[str, Any]] | None = None,
        _summary: dict[str, Any] | None = None,
        _context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        records = _records if _records is not None else self.records_for_user(user_id)
        if not records:
            return empty_data()

        safe_days = max(1, min(int(days or 14), 30))
        summary = _summary if _summary is not None else summarize_records(records)
        context = _context if _context is not None else _context_from_summary(summary, self.freshness(user_id))
        if context.get("status") != "ok":
            return context

        recent_items = sorted(summary["daily"].items())[-safe_days:]
        daily_rows = [{"date": day, **_public_daily_values(values)} for day, values in recent_items]
        metric_counts = Counter(item["data_type"] for item in records)
        catalog_by_id = {item["id"]: item for item in metric_catalog()}
        synced_metrics = [
            {
                "id": metric_id,
                "label": catalog_by_id.get(metric_id, {}).get("label", metric_id),
                "category": catalog_by_id.get(metric_id, {}).get("category", "Other"),
                "records": count,
            }
            for metric_id, count in sorted(metric_counts.items())
        ]
        missing_supported_metrics = sorted(SYNC_DATA_TYPE_IDS - set(metric_counts))
        activity = _overview_activity(daily_rows, lookback_days=safe_days)
        sleep = _overview_sleep(daily_rows)
        heart = _overview_heart(daily_rows)
        recovery = _overview_recovery(daily_rows)
        signal_snapshot = _available_signal_snapshot(daily_rows, lookback_days=safe_days)
        workouts = _overview_workouts(
            [
                item
                for item in records
                if item["data_type"] == "exercise"
                and (item["observed_date"] or "") >= (daily_rows[0]["date"] if daily_rows else "")
            ]
        )
        readiness = context["readiness"]
        goal = self.latest_goal(user_id)
        checkins = self.recent_checkins(user_id)
        freshness = context["data_freshness"]
        positives, watchouts, next_actions = _overview_coaching(
            context=context,
            activity=activity,
            sleep=sleep,
            heart=heart,
            recovery=recovery,
            workouts=workouts,
            goal=goal,
            checkins=checkins,
            freshness=freshness,
        )
        daily_brief = _daily_coaching_brief(
            context=context,
            activity=activity,
            sleep=sleep,
            heart=heart,
            recovery=recovery,
            workouts=workouts,
            goal=goal,
            checkins=checkins,
            freshness=freshness,
            positives=positives,
            watchouts=watchouts,
            next_actions=next_actions,
        )
        return {
            "status": "ok",
            "overview_type": "health_overview",
            "window_days": safe_days,
            "date_range": {
                "start": daily_rows[0]["date"] if daily_rows else None,
                "end": daily_rows[-1]["date"] if daily_rows else None,
            },
            "headline": _overview_headline(readiness, sleep, activity, heart),
            "readiness": readiness,
            "today": context["today"],
            "sections": {
                "activity": activity,
                "sleep": sleep,
                "heart": heart,
                "recovery": recovery,
                "workouts": workouts,
            },
            "daily_brief": daily_brief,
            "available_signal_snapshot": signal_snapshot,
            "model_signal_context": model_signal_context(signal_snapshot),
            "positives": positives,
            "watchouts": watchouts,
            "next_actions": next_actions,
            "personal_context": {
                "goal": goal,
                "recent_checkins": checkins,
            },
            "daily": daily_rows,
            "data_coverage": context["data_coverage"],
            "data_freshness": context["data_freshness"],
            "sync_state": {
                "freshness_level": freshness.get("freshness_level"),
                "freshness_label": freshness.get("freshness_label"),
                "needs_sync_before_time_sensitive_advice": freshness.get(
                    "needs_sync_before_time_sensitive_advice"
                ),
                "recommendation": freshness.get("recommendation"),
            },
            "data_used": {
                "synced_metric_count": len(synced_metrics),
                "synced_metrics": synced_metrics,
                "missing_supported_metrics": missing_supported_metrics,
                "available_signal_count": len(signal_snapshot.get("signals", [])),
                "available_signal_ids": signal_snapshot.get("available_signal_ids", []),
                "raw_record_count": len(records),
                "activity_date": context.get("activity_date"),
                "recovery_date": context.get("recovery_date"),
            },
            "message": "Overview generated from all currently synced local Google Health/Fitbit records.",
            "safety_note": "This is fitness coaching context, not medical advice.",
        }

    def sleep_analysis(self, user_id: str, days: int = 7) -> dict[str, Any]:
        _, summary, context = self._records_summary_context(user_id)
        if context.get("status") != "ok":
            return context
        sleep_days = [
            {"date": day, **values.get("sleep", {})}
            for day, values in sorted(summary["daily"].items())[-days:]
            if values.get("sleep")
        ]
        if not sleep_days:
            return empty_data("No sleep records have synced yet.")
        asleep_values = [
            value
            for item in sleep_days
            if (value := item.get("asleep_hours") or item.get("duration_hours")) is not None
        ]
        latest = sleep_days[-1]
        latest_hours = latest.get("asleep_hours") or latest.get("duration_hours")
        average_hours = round(sum(asleep_values) / len(asleep_values), 2) if asleep_values else None
        return {
            "status": "ok",
            "data_freshness": context["data_freshness"],
            "date_range": {
                "start": sleep_days[0]["date"],
                "end": sleep_days[-1]["date"],
            },
            "days": sleep_days,
            "latest": latest,
            "summary": {
                "average_asleep_hours": average_hours,
                "latest_asleep_hours": latest_hours,
                "latest_vs_average_hours": round(latest_hours - average_hours, 2)
                if latest_hours is not None and average_hours is not None
                else None,
            },
        }

    def activity_load(self, user_id: str, days: int = 7) -> dict[str, Any]:
        _, summary, context = self._records_summary_context(user_id)
        if context.get("status") != "ok":
            return context
        raw_days = sorted(summary["daily"].items())
        activity_days = [
            (day, values)
            for day, values in raw_days
            if any(
                values.get(key) is not None
                for key in ("steps", "active_zone_minutes", "active_minutes", "distance_mm")
            )
            or values.get("activity_levels_minutes")
            or values.get("time_in_hr_zones_minutes")
        ][-days:]
        if not activity_days:
            return empty_data("No activity records have synced yet.")
        days_out = []
        for day, values in activity_days:
            distance_mm = values.get("distance_mm")
            days_out.append(
                {
                    "date": day,
                    "steps": values.get("steps"),
                    "active_zone_minutes": values.get("active_zone_minutes"),
                    "active_minutes": values.get("active_minutes"),
                    "distance_km": round(distance_mm / 1_000_000, 2) if distance_mm is not None else None,
                }
            )
        totals = {
            "steps": sum(day["steps"] or 0 for day in days_out),
            "active_zone_minutes": sum(day["active_zone_minutes"] or 0 for day in days_out),
            "active_minutes": sum(day["active_minutes"] or 0 for day in days_out),
        }
        highest_load = max(days_out, key=lambda day: day["active_zone_minutes"] or 0, default=None)
        return {
            "status": "ok",
            "data_freshness": context["data_freshness"],
            "date_range": {
                "start": days_out[0]["date"] if days_out else None,
                "end": days_out[-1]["date"] if days_out else None,
            },
            "days": days_out,
            "coverage": {
                "days_requested": days,
                "days_with_activity": len(days_out),
                "missing_days_in_summary": max(0, min(days, len(raw_days)) - len(days_out)),
            },
            "totals": totals,
            "highest_load_day": highest_load,
        }

    def heart_trends(self, user_id: str, days: int = 7) -> dict[str, Any]:
        _, summary, context = self._records_summary_context(user_id)
        if context.get("status") != "ok":
            return context
        raw_days = sorted(summary["daily"].items())
        heart_days = [
            (day, values)
            for day, values in raw_days
            if values.get("heart")
            or values.get("resting_heart_rate") is not None
            or values.get("hrv_ms") is not None
            or values.get("hrv_sample_ms") is not None
        ][-days:]
        if not heart_days:
            return empty_data("No heart trend records have synced yet.")
        days_out = []
        for day, values in heart_days:
            heart = values.get("heart", {})
            days_out.append(
                {
                    "date": day,
                    "avg_bpm": heart.get("avg_bpm"),
                    "resting_bpm": values.get("resting_heart_rate"),
                    "hrv_ms": values.get("hrv_ms") or (values.get("hrv_sample_ms") or {}).get("avg_ms"),
                }
            )
        latest = days_out[-1] if days_out else None
        hrv_values = [day["hrv_ms"] for day in days_out if day.get("hrv_ms") is not None]
        rhr_values = [day["resting_bpm"] for day in days_out if day.get("resting_bpm") is not None]
        return {
            "status": "ok",
            "data_freshness": context["data_freshness"],
            "date_range": {
                "start": days_out[0]["date"] if days_out else None,
                "end": days_out[-1]["date"] if days_out else None,
            },
            "days": days_out,
            "latest": latest,
            "coverage": {
                "days_requested": days,
                "days_with_heart_data": len(days_out),
                "missing_days_in_summary": max(0, min(days, len(raw_days)) - len(days_out)),
            },
            "summary": {
                "average_hrv_ms": round(sum(hrv_values) / len(hrv_values), 1) if hrv_values else None,
                "average_resting_bpm": round(sum(rhr_values) / len(rhr_values), 1) if rhr_values else None,
            },
        }

    def recovery_signal_comparison(
        self,
        user_id: str,
        days: int = 14,
        *,
        _summary: dict[str, Any] | None = None,
        _context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if _summary is None or _context is None:
            _, summary, context = self._records_summary_context(user_id)
        else:
            summary = _summary
            context = _context
        if context.get("status") != "ok":
            return context
        safe_days = max(1, min(days, 30))
        recent_days = sorted(summary["daily"].items())[-safe_days:]
        daily_rows = [{"date": day, **_public_daily_values(values)} for day, values in recent_days]
        signal_snapshot = _available_signal_snapshot(daily_rows, lookback_days=safe_days)
        rows = [_recovery_row(day, values) for day, values in recent_days]
        rows = [row for row in rows if _has_recovery_comparison_signal(row)]
        if not rows:
            return empty_data("No comparable sleep or heart recovery records have synced yet.")

        latest = _latest_recovery_row(rows)
        baseline_rows = [row for row in rows if row["date"] < latest["date"]]
        baseline = {
            "sleep_hours": _average([row["sleep_hours"] for row in baseline_rows]),
            "hrv_ms": _average([row["hrv_ms"] for row in baseline_rows]),
            "resting_heart_rate": _average([row["resting_heart_rate"] for row in baseline_rows]),
            "active_zone_minutes": _average([row["active_zone_minutes"] for row in baseline_rows]),
            "respiratory_rate": _average([row["respiratory_rate"] for row in baseline_rows]),
            "spo2_avg": _average([row["spo2_avg"] for row in baseline_rows]),
            "sleep_temperature_delta_celsius": _average(
                [row["sleep_temperature_delta_celsius"] for row in baseline_rows]
            ),
        }
        current_vs_baseline = _current_vs_baseline(latest, baseline)
        insights, watchouts, positives, next_actions = _recovery_comparison_takeaways(
            latest,
            baseline,
            current_vs_baseline,
            context,
        )
        paired_sleep_hrv = [
            (row["sleep_hours"], row["hrv_ms"])
            for row in rows
            if row.get("sleep_hours") is not None and row.get("hrv_ms") is not None
        ]
        paired_sleep_rhr = [
            (row["sleep_hours"], row["resting_heart_rate"])
            for row in rows
            if row.get("sleep_hours") is not None and row.get("resting_heart_rate") is not None
        ]
        return {
            "status": "ok",
            "comparison_type": "sleep_heart_recovery",
            "window_days": max(1, min(days, 30)),
            "date_range": {
                "start": rows[0]["date"],
                "end": rows[-1]["date"],
            },
            "headline": _recovery_comparison_headline(latest, current_vs_baseline),
            "latest": latest,
            "baseline": baseline,
            "current_vs_baseline": current_vs_baseline,
            "correlations": {
                "sleep_vs_hrv": _pearson(paired_sleep_hrv),
                "sleep_vs_resting_heart_rate": _pearson(paired_sleep_rhr),
                "sample_size_sleep_hrv": len(paired_sleep_hrv),
                "sample_size_sleep_resting_hr": len(paired_sleep_rhr),
            },
            "insights": insights,
            "positives": positives,
            "watchouts": watchouts,
            "next_actions": next_actions,
            "readiness": context["readiness"],
            "data_freshness": context["data_freshness"],
            "daily": rows,
            "available_signal_snapshot": signal_snapshot,
            "data_used": {
                "activity_date": context.get("activity_date"),
                "recovery_date": context.get("recovery_date"),
                "days_compared": len(rows),
                "signals": _recovery_signal_ids(rows),
                "available_signal_ids": signal_snapshot.get("available_signal_ids", []),
            },
            "safety_note": "This is fitness coaching context, not medical advice.",
        }

    def health_question_clues(self, user_id: str, question: str, days: int = 14) -> dict[str, Any]:
        records, summary, context = self._records_summary_context(user_id)
        if context.get("status") != "ok":
            return context

        safe_days = max(1, min(int(days or 14), 30))
        question_text = str(question or "").strip()
        intents = _question_intents(question_text)
        overview = self.health_overview(
            user_id,
            safe_days,
            _records=records,
            _summary=summary,
            _context=context,
        )
        comparison = self.recovery_signal_comparison(
            user_id,
            safe_days,
            _summary=summary,
            _context=context,
        )
        personal_context = overview.get("personal_context", {}) if overview.get("status") == "ok" else {}
        workout_context = overview.get("sections", {}).get("workouts", {}) if overview.get("status") == "ok" else {}
        signal_snapshot = overview.get("available_signal_snapshot", {}) if overview.get("status") == "ok" else {}
        illness_flags = _question_illness_flags(question_text, personal_context)
        if illness_flags:
            intents = _dedupe(["symptom_safety", *intents])
        safety_flags = _dedupe(_question_safety_flags(question_text, context) + illness_flags)
        catalog = self.available_metrics(user_id)
        catalog_by_id = {item["id"]: item for item in catalog.get("metrics", [])}
        metric_ids = _metric_ids_for_intents(intents)
        relevant_metrics = _relevant_metric_cards(metric_ids, catalog_by_id, intents)
        clues, positives, watchouts, next_actions = _question_clue_takeaways(
            intents=intents,
            context=context,
            overview=overview,
            comparison=comparison,
        )
        watchouts = safety_flags + watchouts
        if context.get("data_freshness", {}).get("needs_sync_before_time_sensitive_advice"):
            next_actions.insert(0, "Run sync_latest_fitbit_data before answering time-sensitive training questions.")
        conversation_flows = _conversation_flow_options(context.get("data_freshness", {}))
        primary_flows = _primary_conversation_flows(intents, conversation_flows)

        return {
            "status": "ok",
            "clue_type": "health_question_clues",
            "question": question_text or "General health and fitness coaching question",
            "window_days": safe_days,
            "headline": _question_clue_headline(intents, context, comparison),
            "intent_hints": intents,
            "primary_conversation_flows": primary_flows,
            "recommended_tool_sequence": _recommended_tool_sequence(
                intents,
                context.get("data_freshness", {}),
                primary_flows=primary_flows,
            ),
            "conversation_flow_options": conversation_flows,
            "relevant_metrics": relevant_metrics,
            "available_metric_ids": [item["id"] for item in relevant_metrics if item["records"] > 0],
            "missing_metric_ids": [item["id"] for item in relevant_metrics if item["records"] == 0],
            "query_suggestions": _metric_query_suggestions(intents, relevant_metrics, safe_days),
            "decision_frame": _decision_frame_for_question(
                question=question_text,
                intents=intents,
                context=context,
                overview=overview,
                comparison=comparison,
            ),
            "clues": _dedupe(clues),
            "positives": _dedupe(positives),
            "watchouts": _dedupe(watchouts),
            "next_actions": _dedupe(next_actions),
            "safety_flags": safety_flags,
            "readiness": context["readiness"],
            "today": _compact_today_context(context["today"]),
            "overview_context": _compact_overview_context(overview),
            "available_signal_snapshot": signal_snapshot,
            "model_signal_context": model_signal_context(signal_snapshot),
            "personal_context": personal_context,
            "recovery_comparison": _compact_recovery_comparison(comparison),
            "data_freshness": context["data_freshness"],
            "answering_guidance": [
                "Use the relevant_metrics list to decide which synced signals to inspect next.",
                "Prefer primary_conversation_flows over raw intent_hints when choosing tools for a natural user question.",
                "Use conversation_flow_options when the user's wording is informal, broad, or not well captured by intent_hints.",
                "Use available_signal_snapshot for broad, all-data, oxygen, breathing, or unusual-pattern questions so secondary signals are not ignored.",
                "Use decision_frame.model_decision_policy to choose data by safety, recovery, load, capacity, and user-context axes rather than by brittle wording alone.",
                "Mention normal secondary signals briefly as context when they do not change the workout call.",
                "Treat missing metrics as absent, not zero.",
                "For workout decisions, combine readiness, sleep, HRV, resting HR, oxygen/breathing/temperature context, load, recent workouts, goals, and check-ins.",
                "For symptom, pain, illness, or abnormal-heart-rate concerns, recommend appropriate clinical care instead of diagnosing.",
            ],
            "answer_rubric": _answer_rubric_for_intents(intents),
            "data_used": {
                "activity_date": context.get("activity_date"),
                "recovery_date": context.get("recovery_date"),
                "synced_metric_count": catalog.get("synced_metric_count", 0),
                "supported_metric_count": catalog.get("supported_metric_count", 0),
                "comparison_available": comparison.get("status") == "ok",
                "available_signal_count": len(signal_snapshot.get("signals", [])),
                "available_signal_ids": signal_snapshot.get("available_signal_ids", []),
                "goal_present": bool((personal_context.get("goal") or {}).get("goal")),
                "recent_checkins_count": len(personal_context.get("recent_checkins") or []),
                "recent_workout_count": workout_context.get("workout_count", 0),
            },
            "safety_note": "This is fitness coaching context, not medical advice.",
        }

    def workout_history(self, user_id: str, days: int = 14) -> dict[str, Any]:
        freshness = self.freshness(user_id)
        cutoff = (utc_now() - timedelta(days=days)).date().isoformat()
        rows = self.db.all(
            """
            SELECT data_type, observed_date, payload_json
            FROM raw_health_records
            WHERE user_id = ?
              AND data_type = 'exercise'
              AND observed_date >= ?
            ORDER BY observed_date DESC, id DESC
            """,
            (user_id, cutoff),
        )
        records = [
            {
                "data_type": row["data_type"],
                "observed_date": row["observed_date"],
                "payload": loads(row["payload_json"], {}),
            }
            for row in rows
        ]
        if not records:
            return empty_data("No workout records have synced yet.")
        workouts = []
        ignored_short_workouts = 0
        for item in records:
            exercise = item["payload"].get("exercise", {})
            interval = exercise.get("interval", {})
            duration_minutes = _duration_minutes(exercise.get("activeDuration"))
            workout = (
                {
                    "date": item["observed_date"],
                    "type": exercise.get("exerciseType"),
                    "display_name": exercise.get("displayName"),
                    "start_time": interval.get("startTime"),
                    "end_time": interval.get("endTime"),
                    "active_duration": exercise.get("activeDuration"),
                    "duration_minutes": duration_minutes,
                    "active_zone_minutes": _int(exercise.get("metricsSummary", {}), ["activeZoneMinutes"]),
                    "calories_kcal": _float(exercise.get("metricsSummary", {}), ["caloriesKcal"]),
                    "average_heart_rate": exercise.get("metricsSummary", {}).get(
                        "averageHeartRateBeatsPerMinute"
                    ),
                }
            )
            if duration_minutes is not None and duration_minutes < 2:
                ignored_short_workouts += 1
                continue
            workouts.append(workout)
        hardest = max(
            workouts,
            key=lambda item: (item.get("active_zone_minutes") or 0, _float({"value": item.get("average_heart_rate")}, ["value"])),
            default=None,
        )
        return {
            "status": "ok",
            "data_freshness": freshness,
            "date_range": {
                "start": min((item["date"] for item in workouts if item.get("date")), default=None),
                "end": max((item["date"] for item in workouts if item.get("date")), default=None),
            },
            "workouts": workouts,
            "summary": {
                "workout_count": len(workouts),
                "ignored_short_workouts": ignored_short_workouts,
                "hardest_workout": hardest,
            },
        }

    def save_goal(self, user_id: str, goal: dict[str, Any]) -> dict[str, Any]:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO goals (user_id, goal_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (user_id, dumps(goal), iso_now()),
            )
        return {"status": "ok", "goal": goal}

    def save_checkin(self, user_id: str, checkin: dict[str, Any]) -> dict[str, Any]:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO checkins (user_id, payload_json, created_at) VALUES (?, ?, ?)",
                (user_id, dumps(checkin), iso_now()),
            )
        return {"status": "ok", "checkin": checkin}

    def latest_goal(self, user_id: str) -> dict[str, Any] | None:
        row = self.db.one(
            "SELECT goal_json, updated_at FROM goals WHERE user_id = ?",
            (user_id,),
        )
        if not row:
            return None
        return {"goal": loads(row["goal_json"], {}), "updated_at": row["updated_at"]}

    def recent_checkins(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.db.all(
            """
            SELECT payload_json, created_at
            FROM checkins
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, max(1, min(limit, 20))),
        )
        return [
            {"checkin": loads(row["payload_json"], {}), "created_at": row["created_at"]}
            for row in rows
        ]

    def _start_sync(self, user_id: str, started_at: str) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (user_id, started_at, status)
                VALUES (?, ?, 'running')
                """,
                (user_id, started_at),
            )
            return int(cursor.lastrowid)

    def _finish_sync(self, sync_id: int, status: str, count: int, message: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?, records_upserted = ?, message = ?
                WHERE id = ?
                """,
                (iso_now(), status, count, message, sync_id),
            )


def setup_required(message: str = "Connect Google Health before using health tools.") -> dict[str, Any]:
    return {
        "status": "setup_required",
        "google_connected": False,
        "message": message,
        "plain_english_state": "I cannot see Fitbit or Google Health data until this ChatGPT user connects Google Health.",
        "next_actions": ["Connect Google Health from the ChatGPT app OAuth prompt."],
        "what_to_expect": [
            "After Google Health is connected, run sync_latest_fitbit_data to pull the user's private cloud-synced Fitbit data.",
            "Until then, answer only with setup guidance and do not infer health stats.",
        ],
        "conversation_flow_options": _conversation_flow_options(setup_state=True),
    }


def empty_data(message: str = "No Fitbit data has synced yet.") -> dict[str, Any]:
    return {
        "status": "empty",
        "message": message,
        "plain_english_state": "Google Health may be connected, but this private store has no synced Fitbit records yet.",
        "next_actions": ["Run sync_latest_fitbit_data after connecting Google Health."],
        "what_to_expect": [
            "The first sync starts the user's personal data history for this app.",
            "If sync returns no records, explain that the app has no wearable context yet instead of fabricating a plan.",
        ],
        "conversation_flow_options": _conversation_flow_options(empty_state=True),
    }


def _sync_error_category(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "timeout"
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return f"google_http_{status_code}"
    if exc.__class__.__module__.startswith("httpx"):
        return exc.__class__.__name__
    return exc.__class__.__name__


def _sync_error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        body = ""
        try:
            body = response.text[:500]
        except Exception:
            body = ""
        return f"Google Health HTTP {status_code}: {body or str(exc)}"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "Google Health metric request timed out."
    return str(exc) or exc.__class__.__name__


def freshness_details(latest_observed_date: str | None, last_sync: str | None) -> dict[str, Any]:
    now = utc_now()
    fresh_window_minutes = 15
    aging_window_minutes = 60
    observed_date = _date_from_iso(latest_observed_date)
    observed_days_ago = None
    if observed_date:
        observed_days_ago = max(0, (now.date() - observed_date).days)

    sync_age_minutes = None
    synced_at = _datetime_from_iso(last_sync)
    if synced_at:
        sync_age_minutes = max(0, round((now - synced_at).total_seconds() / 60))

    if observed_days_ago is None:
        level = "unknown"
        label = "unknown freshness"
        recommendation = "Run sync_latest_fitbit_data before using health data."
    elif observed_days_ago == 0 and sync_age_minutes is not None and sync_age_minutes <= fresh_window_minutes:
        level = "fresh"
        label = "fresh <15 min"
        recommendation = "Synced in the last 15 minutes; fresh enough for time-sensitive coaching."
    elif observed_days_ago == 0 and (sync_age_minutes is None or sync_age_minutes <= aging_window_minutes):
        level = "aging"
        label = "aging 15-60 min" if sync_age_minutes is not None else "sync age unknown"
        recommendation = "Usable for context, but sync before hard or time-sensitive workout decisions."
    else:
        level = "stale"
        label = "stale >1 hour" if observed_days_ago == 0 else "sync recommended"
        recommendation = "Run sync_latest_fitbit_data before time-sensitive workout decisions."

    return {
        "freshness_level": level,
        "freshness_label": label,
        "fresh_window_minutes": fresh_window_minutes,
        "aging_window_minutes": aging_window_minutes,
        "observed_days_ago": observed_days_ago,
        "sync_age_minutes": sync_age_minutes,
        "is_observed_today": observed_days_ago == 0,
        "needs_sync_before_time_sensitive_advice": level in {"aging", "stale", "unknown"},
        "recommendation": recommendation,
    }


def _overview_activity(
    daily_rows: list[dict[str, Any]],
    *,
    lookback_days: int | None = None,
) -> dict[str, Any]:
    step_days = [day for day in daily_rows if day.get("steps") is not None]
    active_days = [
        day
        for day in daily_rows
        if any(day.get(key) is not None for key in ("active_minutes", "active_zone_minutes", "distance_mm"))
    ]
    total_steps = sum(_float({"value": day.get("steps")}, ["value"]) for day in daily_rows)
    total_active = sum(_float({"value": day.get("active_minutes")}, ["value"]) for day in daily_rows)
    total_zone = sum(_float({"value": day.get("active_zone_minutes")}, ["value"]) for day in daily_rows)
    total_distance_km = sum(_float({"value": day.get("distance_mm")}, ["value"]) for day in daily_rows) / 1_000_000
    step_average = round(total_steps / len(step_days)) if step_days else None
    active_average = round(total_active / len(active_days), 1) if active_days else None
    zone_average = round(total_zone / len(active_days), 1) if active_days else None
    step_count = len(step_days)
    lookback_count = lookback_days or len(daily_rows) or step_count
    step_day_word = "day" if step_count == 1 else "days"
    step_window_text = (
        f"{round(total_steps):,} steps across {step_count} recorded {step_day_word} "
        f"in the {lookback_count}-day lookback"
        if step_count
        else None
    )
    step_average_text = (
        f"{step_average:,}/day average across recorded step days"
        if step_average is not None
        else None
    )
    highest_load = max(
        daily_rows,
        key=lambda day: _float({"value": day.get("active_zone_minutes")}, ["value"]),
        default={},
    )
    levels: dict[str, float] = defaultdict(float)
    zones: dict[str, float] = defaultdict(float)
    for day in daily_rows:
        for name, minutes in (day.get("activity_levels_minutes") or {}).items():
            levels[name] += _float({"value": minutes}, ["value"])
        for name, minutes in (day.get("time_in_hr_zones_minutes") or {}).items():
            zones[name] += _float({"value": minutes}, ["value"])
    return {
        "status": "ok" if active_days or step_days else "missing",
        "days_with_activity": len(active_days or step_days),
        "lookback_days": lookback_count,
        "latest": _last_with(daily_rows, ("steps", "active_minutes", "active_zone_minutes", "distance_mm")) or {},
        "totals": {
            "steps": round(total_steps),
            "active_minutes": round(total_active, 1),
            "active_zone_minutes": round(total_zone, 1),
            "distance_km": round(total_distance_km, 2),
        },
        "averages": {
            "steps_per_day": step_average,
            "active_minutes_per_day": active_average,
            "active_zone_minutes_per_day": zone_average,
        },
        "average_denominators": {
            "steps_per_day": "recorded_step_days",
            "active_minutes_per_day": "recorded_activity_days",
            "active_zone_minutes_per_day": "recorded_activity_days",
        },
        "coverage": {
            "days_in_lookback": lookback_count,
            "days_with_steps": step_count,
            "days_with_activity": len(active_days),
            "step_average_is_over_recorded_days": True,
        },
        "step_window_summary": {
            "display": step_window_text,
            "average_display": step_average_text,
            "total_steps": round(total_steps),
            "days_with_steps": step_count,
            "lookback_days": lookback_count,
            "average_steps_per_recorded_day": step_average,
        },
        "highest_load_day": {
            "date": highest_load.get("date"),
            "active_zone_minutes": highest_load.get("active_zone_minutes", 0),
            "steps": highest_load.get("steps", 0),
        }
        if highest_load
        else None,
        "activity_levels_minutes": {name: round(value, 1) for name, value in sorted(levels.items())},
        "time_in_heart_rate_zones_minutes": {
            name: round(value, 1) for name, value in sorted(zones.items())
        },
        "sedentary_minutes_average": _average(
            [_float({"value": day.get("sedentary_minutes")}, ["value"]) for day in daily_rows]
        ),
        "calories": {
            "active_kcal_total": round(
                sum(_float({"value": day.get("active_kcal")}, ["value"]) for day in daily_rows), 1
            ),
            "total_kcal_latest": _latest_number(daily_rows, "total_kcal"),
        },
    }


def _overview_sleep(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    sleep_days = [day for day in daily_rows if day.get("sleep")]
    latest = sleep_days[-1].get("sleep", {}) if sleep_days else {}
    hours = [
        value
        for day in sleep_days
        if (value := day.get("sleep", {}).get("asleep_hours") or day.get("sleep", {}).get("duration_hours"))
        is not None
    ]
    latest_hours = latest.get("asleep_hours") or latest.get("duration_hours")
    average_hours = _average(hours)
    return {
        "status": "ok" if sleep_days else "missing",
        "days_with_sleep": len(sleep_days),
        "latest": {"date": sleep_days[-1]["date"], **latest} if sleep_days else None,
        "average_asleep_hours": average_hours,
        "latest_asleep_hours": latest_hours,
        "latest_vs_average_hours": round(latest_hours - average_hours, 2)
        if latest_hours is not None and average_hours is not None
        else None,
        "total_sleep_sessions": sum(_int(day.get("sleep", {}), ["sessions_count"]) or 1 for day in sleep_days),
        "stage_averages_minutes": _stage_averages(sleep_days),
    }


def _overview_heart(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    hrv_values = [_float({"value": day.get("hrv_ms")}, ["value"]) for day in daily_rows if day.get("hrv_ms")]
    rhr_values = [
        _float({"value": day.get("resting_heart_rate")}, ["value"])
        for day in daily_rows
        if day.get("resting_heart_rate")
    ]
    avg_bpm_values = [
        _float({"value": day.get("heart", {}).get("avg_bpm")}, ["value"])
        for day in daily_rows
        if day.get("heart", {}).get("avg_bpm")
    ]
    latest_hrv_day = _last_with(daily_rows, ("hrv_ms",))
    latest_rhr_day = _last_with(daily_rows, ("resting_heart_rate",))
    latest_heart_day = _last_with(daily_rows, ("heart",))
    return {
        "status": "ok" if hrv_values or rhr_values or avg_bpm_values else "missing",
        "latest_hrv_ms": latest_hrv_day.get("hrv_ms") if latest_hrv_day else None,
        "latest_hrv_date": latest_hrv_day.get("date") if latest_hrv_day else None,
        "average_hrv_ms": _average(hrv_values),
        "latest_resting_heart_rate": latest_rhr_day.get("resting_heart_rate") if latest_rhr_day else None,
        "latest_resting_heart_rate_date": latest_rhr_day.get("date") if latest_rhr_day else None,
        "average_resting_heart_rate": _average(rhr_values),
        "latest_heart_sample_summary": latest_heart_day.get("heart") if latest_heart_day else None,
        "average_sampled_bpm": _average(avg_bpm_values),
    }


def _overview_recovery(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    spo2_day = _last_with(daily_rows, ("spo2_avg", "spo2_sample"))
    resp_day = _last_with(daily_rows, ("respiratory_rate",))
    resp_sleep_day = _last_with(daily_rows, ("respiratory_rate_sleep",))
    temp_day = _last_with(daily_rows, ("sleep_temperature",))
    vo2_day = _last_with(daily_rows, ("vo2_max",))
    latest_spo2 = None
    if spo2_day:
        latest_spo2 = spo2_day.get("spo2_avg") or spo2_day.get("spo2_sample", {}).get("avg")
    latest_resp_sleep = None
    if resp_sleep_day:
        latest_resp_sleep = resp_sleep_day.get("respiratory_rate_sleep", {}).get("full_sleep_breaths_per_minute")
    return {
        "status": "ok" if spo2_day or resp_day or resp_sleep_day or temp_day or vo2_day else "missing",
        "latest_spo2": latest_spo2,
        "latest_spo2_date": spo2_day.get("date") if spo2_day else None,
        "latest_respiratory_rate": resp_day.get("respiratory_rate") if resp_day else None,
        "latest_respiratory_rate_date": resp_day.get("date") if resp_day else None,
        "latest_respiratory_rate_sleep": latest_resp_sleep,
        "latest_respiratory_rate_sleep_date": resp_sleep_day.get("date") if resp_sleep_day else None,
        "latest_sleep_temperature": temp_day.get("sleep_temperature") if temp_day else None,
        "latest_sleep_temperature_date": temp_day.get("date") if temp_day else None,
        "latest_vo2_max": vo2_day.get("vo2_max") if vo2_day else None,
        "latest_vo2_max_date": vo2_day.get("date") if vo2_day else None,
    }


def _available_signal_snapshot(
    daily_rows: list[dict[str, Any]],
    *,
    lookback_days: int | None = None,
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    date_range = {
        "start": daily_rows[0]["date"] if daily_rows else None,
        "end": daily_rows[-1]["date"] if daily_rows else None,
    }

    def add_signal(
        *,
        signal_id: str,
        label: str,
        category: str,
        latest_value: Any | None = None,
        unit: str = "",
        latest_date: str | None = None,
        value_display: str | None = None,
        window_summary: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        why_it_matters: str,
        coaching_use: str,
        use_when: list[str],
        confidence: str = "context",
    ) -> None:
        if latest_value is None and not value_display and not window_summary and not details:
            return
        signals.append(
            {
                "id": signal_id,
                "label": label,
                "category": category,
                "latest": latest_value,
                "unit": unit,
                "latest_date": latest_date,
                "display": value_display or _format_signal_value(latest_value, unit),
                "window_summary": window_summary or {},
                "details": details or {},
                "why_it_matters": why_it_matters,
                "coaching_use": coaching_use,
                "use_when": use_when,
                "confidence": confidence,
            }
        )

    sleep_day = _last_with(daily_rows, ("sleep",))
    if sleep_day:
        sleep = sleep_day.get("sleep", {})
        sleep_hours = sleep.get("asleep_hours") or sleep.get("duration_hours")
        sleep_values = [
            value
            for day in daily_rows
            if (value := (day.get("sleep") or {}).get("asleep_hours") or (day.get("sleep") or {}).get("duration_hours"))
            is not None
        ]
        add_signal(
            signal_id="sleep_duration",
            label="Sleep",
            category="sleep",
            latest_value=_round_optional(sleep_hours, 1),
            unit="h",
            latest_date=sleep_day.get("date"),
            window_summary={
                "average_hours": _average(sleep_values),
                "days_with_sleep": len(sleep_values),
            },
            details={"stages_minutes": sleep.get("stages_minutes") or {}},
            why_it_matters="Sleep is the biggest recovery budget signal for hard training.",
            coaching_use="Use short or fragmented sleep to cap intensity; use supportive sleep as room to train, not permission for max effort.",
            use_when=["workout_intensity", "fatigue", "recovery", "daily_plan"],
            confidence="strong" if len(sleep_values) >= 3 else "low_baseline",
        )

    hrv_day = _last_with(daily_rows, ("hrv_ms", "hrv_sample_ms"))
    if hrv_day:
        hrv = hrv_day.get("hrv_ms") or (hrv_day.get("hrv_sample_ms") or {}).get("avg")
        hrv_values = [
            value
            for day in daily_rows
            if (value := day.get("hrv_ms") or (day.get("hrv_sample_ms") or {}).get("avg")) is not None
        ]
        add_signal(
            signal_id="hrv",
            label="HRV",
            category="heart",
            latest_value=_round_optional(hrv, 1),
            unit="ms",
            latest_date=hrv_day.get("date"),
            window_summary={"average_ms": _average(hrv_values), "days": len(hrv_values)},
            why_it_matters="HRV is a recovery-stress clue that only becomes meaningful against your usual pattern.",
            coaching_use="Lower-than-usual HRV should reduce intensity; normal or high HRV supports training only when sleep, symptoms, and load agree.",
            use_when=["recovery", "hard_training", "fatigue", "stress"],
            confidence="strong" if len(hrv_values) >= 3 else "low_baseline",
        )

    rhr_day = _last_with(daily_rows, ("resting_heart_rate",))
    if rhr_day:
        rhr_values = [day.get("resting_heart_rate") for day in daily_rows if day.get("resting_heart_rate") is not None]
        add_signal(
            signal_id="resting_heart_rate",
            label="Resting HR",
            category="heart",
            latest_value=rhr_day.get("resting_heart_rate"),
            unit="bpm",
            latest_date=rhr_day.get("date"),
            window_summary={"average_bpm": _average(rhr_values), "days": len(rhr_values)},
            why_it_matters="Resting heart rate can rise with stress, poor recovery, illness, or dehydration.",
            coaching_use="Elevated resting HR should make hard training harder to justify, especially with poor sleep or symptoms.",
            use_when=["recovery", "illness_clues", "fatigue", "hard_training"],
            confidence="strong" if len(rhr_values) >= 3 else "low_baseline",
        )

    heart_day = _last_with(daily_rows, ("heart",))
    if heart_day:
        heart = heart_day.get("heart") or {}
        add_signal(
            signal_id="heart_rate_samples",
            label="Heart rate samples",
            category="heart",
            latest_value=heart.get("avg_bpm"),
            unit="bpm avg",
            latest_date=heart_day.get("date"),
            details={
                "min_bpm": heart.get("min_bpm"),
                "max_bpm": heart.get("max_bpm"),
                "samples": heart.get("samples"),
            },
            why_it_matters="Heart-rate samples explain intensity and unusual spikes better than steps alone.",
            coaching_use="Use sample heart rate for recent effort context; use live user-reported HR for in-session decisions.",
            use_when=["active_workout", "cardio", "intensity", "heart_questions"],
        )

    spo2_day = _last_with(daily_rows, ("spo2_avg", "spo2_sample"))
    if spo2_day:
        spo2 = spo2_day.get("spo2_avg") or (spo2_day.get("spo2_sample") or {}).get("avg")
        add_signal(
            signal_id="spo2",
            label="SpO2 / oxygen saturation",
            category="breathing_recovery",
            latest_value=_round_optional(spo2, 1),
            unit="%",
            latest_date=spo2_day.get("date"),
            details=spo2_day.get("spo2_sample") or {},
            why_it_matters="SpO2 is an oxygen-context signal; normal values are reassuring background but not a green light by themselves.",
            coaching_use="Use low or unusual SpO2 with respiratory rate, resting HR, sleep, and symptoms to lower intensity or recommend caution.",
            use_when=["oxygen_questions", "breathing", "illness_clues", "recovery"],
            confidence="context_not_standalone",
        )

    resp_day = _last_with(daily_rows, ("respiratory_rate", "respiratory_rate_sleep"))
    if resp_day:
        resp_sleep = resp_day.get("respiratory_rate_sleep") or {}
        resp = resp_day.get("respiratory_rate") or resp_sleep.get("full_sleep_breaths_per_minute")
        resp_values = [
            value
            for day in daily_rows
            if (
                value := day.get("respiratory_rate")
                or (day.get("respiratory_rate_sleep") or {}).get("full_sleep_breaths_per_minute")
            )
            is not None
        ]
        add_signal(
            signal_id="respiratory_rate",
            label="Respiratory rate",
            category="breathing_recovery",
            latest_value=_round_optional(resp, 1),
            unit="breaths/min",
            latest_date=resp_day.get("date"),
            window_summary={"average_breaths_per_minute": _average(resp_values), "days": len(resp_values)},
            details=resp_sleep,
            why_it_matters="Overnight breathing rate can add recovery, illness, or stress context when it moves away from baseline.",
            coaching_use="Use elevated or unusual respiratory rate as a reason to cap intensity, especially with symptoms or low sleep.",
            use_when=["breathing", "illness_clues", "recovery", "sleep_quality"],
            confidence="strong" if len(resp_values) >= 3 else "low_baseline",
        )

    temp_day = _last_with(daily_rows, ("sleep_temperature",))
    if temp_day:
        temp = temp_day.get("sleep_temperature") or {}
        add_signal(
            signal_id="sleep_temperature",
            label="Sleep temperature",
            category="breathing_recovery",
            latest_value=temp.get("delta_celsius")
            if temp.get("delta_celsius") is not None
            else temp.get("nightly_celsius"),
            unit="C",
            latest_date=temp_day.get("date"),
            value_display=_sleep_temperature_display(temp),
            details=temp,
            why_it_matters="Sleep temperature deviation can be an early stress or illness clue when it is unusual for you.",
            coaching_use="Use an elevated deviation as context to keep training controlled; do not diagnose from it.",
            use_when=["illness_clues", "sleep_quality", "recovery", "fatigue"],
            confidence="context_not_standalone",
        )

    vo2_day = _last_with(daily_rows, ("vo2_max", "vo2_max_detail"))
    if vo2_day:
        vo2_detail = vo2_day.get("vo2_max_detail") or {}
        add_signal(
            signal_id="vo2_max",
            label="VO2 max",
            category="capacity",
            latest_value=_round_optional(vo2_day.get("vo2_max") or vo2_detail.get("vo2_max"), 1),
            unit="ml/kg/min",
            latest_date=vo2_day.get("date"),
            details=vo2_detail,
            why_it_matters="VO2 max estimates long-term cardio capacity, not how recovered you are today.",
            coaching_use="Use it for endurance planning and progress, not as the main same-day train-or-rest signal.",
            use_when=["endurance", "cardio_capacity", "progress", "running"],
            confidence="capacity_not_readiness",
        )

    latest_load = _last_with(daily_rows, ("active_zone_minutes",))
    if latest_load:
        azm_values = [day.get("active_zone_minutes") for day in daily_rows if day.get("active_zone_minutes") is not None]
        add_signal(
            signal_id="active_zone_minutes",
            label="Active Zone Minutes (AZM)",
            category="activity_load",
            latest_value=latest_load.get("active_zone_minutes"),
            unit="min",
            latest_date=latest_load.get("date"),
            window_summary={"total_minutes": round(sum(azm_values), 1), "average_minutes": _average(azm_values)},
            why_it_matters="AZM are Fitbit's compact hard-work minutes from elevated heart-rate zones.",
            coaching_use="High recent AZM means recovery cost is already present; avoid stacking another hard conditioning block.",
            use_when=["workout_intensity", "load_stacking", "cardio", "recovery"],
        )

    zones = _sum_daily_mapping(daily_rows, "time_in_hr_zones_minutes")
    if zones:
        add_signal(
            signal_id="heart_rate_zones",
            label="Heart-rate zones",
            category="activity_load",
            value_display=_format_minutes_mapping(zones),
            window_summary={"minutes_by_zone": zones},
            why_it_matters="Zone split shows whether recent load was easy, moderate, or hard.",
            coaching_use="More peak/cardio zone time should push the next session toward easy volume, technique, or strength away from fatigue.",
            use_when=["cardio", "intervals", "load_stacking", "active_workout"],
        )

    latest_steps = _last_with(daily_rows, ("steps",))
    if latest_steps:
        step_values = [day.get("steps") for day in daily_rows if day.get("steps") is not None]
        step_days = len(step_values)
        step_total = round(sum(step_values))
        step_average = round(sum(step_values) / step_days) if step_days else None
        step_day_word = "day" if step_days == 1 else "days"
        lookback_count = lookback_days or len(daily_rows) or step_days
        add_signal(
            signal_id="steps",
            label="Steps",
            category="activity_load",
            latest_value=latest_steps.get("steps"),
            unit="steps",
            latest_date=latest_steps.get("date"),
            window_summary={
                "total_steps": step_total,
                "days_with_steps": step_days,
                "lookback_days": lookback_count,
                "average_steps_per_recorded_day": step_average,
                "average_denominator": "recorded_step_days",
                "display": (
                    f"{step_total:,} steps across {step_days} recorded {step_day_word} "
                    f"in the {lookback_count}-day lookback"
                ),
                "average_display": (
                    f"{step_average:,}/day across recorded step days"
                    if step_average is not None
                    else None
                ),
            },
            why_it_matters="Steps show movement volume and leg load, especially before runs, hikes, or lower-body work.",
            coaching_use="Use high step volume as fatigue context; low steps alone do not mean the user needs hard training.",
            use_when=["walking", "running", "hiking", "leg_fatigue", "daily_load"],
        )

    latest_active = _last_with(daily_rows, ("active_minutes",))
    if latest_active:
        active_values = [day.get("active_minutes") for day in daily_rows if day.get("active_minutes") is not None]
        add_signal(
            signal_id="active_minutes",
            label="Active minutes",
            category="activity_load",
            latest_value=latest_active.get("active_minutes"),
            unit="min",
            latest_date=latest_active.get("date"),
            window_summary={"total_minutes": round(sum(active_values), 1), "average_minutes": _average(active_values)},
            why_it_matters="Active minutes capture movement that may not be intense enough to count as AZM.",
            coaching_use="Use this for total day load and consistency, especially when heart-zone data is sparse.",
            use_when=["daily_load", "consistency", "light_activity"],
        )

    latest_distance = _last_with(daily_rows, ("distance_mm",))
    if latest_distance:
        distance_values = [day.get("distance_mm") / 1_000_000 for day in daily_rows if day.get("distance_mm") is not None]
        latest_km = latest_distance.get("distance_mm") / 1_000_000 if latest_distance.get("distance_mm") is not None else None
        add_signal(
            signal_id="distance",
            label="Distance",
            category="activity_load",
            latest_value=_round_optional(latest_km, 2),
            unit="km",
            latest_date=latest_distance.get("date"),
            window_summary={"total_km": round(sum(distance_values), 2), "average_km": _average(distance_values)},
            why_it_matters="Distance matters when the question involves running, walking, hiking, or leg fatigue.",
            coaching_use="Use distance with steps and zones to protect legs before long walks, hikes, or runs.",
            use_when=["running", "walking", "hiking", "leg_fatigue"],
        )

    levels = _sum_daily_mapping(daily_rows, "activity_levels_minutes")
    if levels:
        add_signal(
            signal_id="activity_levels",
            label="Activity levels",
            category="activity_load",
            value_display=_format_minutes_mapping(levels),
            window_summary={"minutes_by_level": levels},
            why_it_matters="Activity levels separate light movement from moderate or vigorous work.",
            coaching_use="Use vigorous minutes as load; use light movement as recovery-supporting background.",
            use_when=["daily_load", "fatigue", "movement_breaks"],
        )

    latest_sedentary = _last_with(daily_rows, ("sedentary_minutes",))
    if latest_sedentary:
        sedentary_values = [day.get("sedentary_minutes") for day in daily_rows if day.get("sedentary_minutes") is not None]
        add_signal(
            signal_id="sedentary_minutes",
            label="Sedentary time",
            category="activity_load",
            latest_value=_round_optional(latest_sedentary.get("sedentary_minutes"), 0),
            unit="min",
            latest_date=latest_sedentary.get("date"),
            window_summary={"average_minutes": _average(sedentary_values)},
            why_it_matters="Sedentary time helps decide whether easy movement breaks may be more useful than a hard workout.",
            coaching_use="Use high sedentary time to suggest walking, mobility, or movement snacks when recovery does not support intensity.",
            use_when=["daily_plan", "movement_breaks", "recovery_day"],
        )

    latest_floors = _last_with(daily_rows, ("floors",))
    if latest_floors:
        add_signal(
            signal_id="floors",
            label="Floors",
            category="activity_load",
            latest_value=latest_floors.get("floors"),
            unit="floors",
            latest_date=latest_floors.get("date"),
            window_summary={"total_floors": round(sum(day.get("floors") for day in daily_rows if day.get("floors") is not None))},
            why_it_matters="Floors can add hidden calf, quad, and hiking/climbing load.",
            coaching_use="Use floors when planning hikes, stairs, runs, or lower-body sessions.",
            use_when=["hiking", "stairs", "leg_fatigue"],
        )

    latest_active_kcal = _last_with(daily_rows, ("active_kcal",))
    if latest_active_kcal:
        kcal_values = [day.get("active_kcal") for day in daily_rows if day.get("active_kcal") is not None]
        add_signal(
            signal_id="active_energy",
            label="Active energy",
            category="activity_load",
            latest_value=_round_optional(latest_active_kcal.get("active_kcal"), 0),
            unit="kcal",
            latest_date=latest_active_kcal.get("date"),
            window_summary={"total_kcal": round(sum(kcal_values), 1)},
            why_it_matters="Active calories are a rough workload clue; wearable calorie estimates are imperfect.",
            coaching_use="Use as secondary load context, not as the main reason to train or rest.",
            use_when=["daily_load", "fueling_context", "long_activity"],
            confidence="rough_estimate",
        )

    return {
        "status": "ok" if signals else "missing",
        "window_days": len(daily_rows),
        "date_range": date_range,
        "available_signal_ids": [signal["id"] for signal in signals],
        "available_categories": sorted({signal["category"] for signal in signals}),
        "signals": signals,
        "question_guidance": [
            "For broad questions, inspect this snapshot first so normal context signals are not silently ignored.",
            "Explain why a signal changes the workout call, or why it is only background context.",
            "SpO2, respiratory rate, and sleep temperature are context or caution signals; do not use them alone as permission to train hard or as a diagnosis.",
            "VO2 max is capacity/progress context, not same-day readiness.",
        ],
    }


def _model_decision_policy(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = snapshot or {}
    available = set(snapshot.get("available_signal_ids") or [])

    def present(signal_ids: list[str]) -> list[str]:
        return [signal_id for signal_id in signal_ids if signal_id in available]

    axes = [
        {
            "axis": "safety_override",
            "plain_language_question": "Is there anything that should stop or downshift training regardless of good-looking stats?",
            "signals_to_check": [
                "user-reported symptoms",
                "pain",
                "dizziness",
                "chest symptoms",
                "resting_heart_rate",
                "heart_rate_samples",
                "respiratory_rate",
                "spo2",
                "sleep_temperature",
            ],
            "available_signal_ids": present(
                ["resting_heart_rate", "heart_rate_samples", "respiratory_rate", "spo2", "sleep_temperature"]
            ),
            "decision_effect": "Symptoms, pain, unusual breathing/oxygen/temperature, or unusual heart signals cap intensity before recovery scoring matters.",
            "missing_data_behavior": "Ask about symptoms or current feeling when needed; do not assume the wearable can diagnose safety.",
        },
        {
            "axis": "freshness_confidence",
            "plain_language_question": "Is the synced context current enough for a time-sensitive decision?",
            "signals_to_check": ["data_freshness", "last_sync", "latest_observed_date"],
            "available_signal_ids": [],
            "decision_effect": "Fresh data supports normal coaching. Aging data can guide controlled choices. Stale data should sync before hard or risky calls.",
            "missing_data_behavior": "If no data exists, return setup or empty-state guidance instead of inventing context.",
        },
        {
            "axis": "recovery_capacity",
            "plain_language_question": "How much training room does the body appear to have today?",
            "signals_to_check": ["sleep_duration", "hrv", "resting_heart_rate", "active_zone_minutes"],
            "available_signal_ids": present(["sleep_duration", "hrv", "resting_heart_rate", "active_zone_minutes"]),
            "decision_effect": "Good alignment supports normal training; short sleep, low HRV, elevated resting HR, or high recent load lowers volume/RPE.",
            "missing_data_behavior": "Use the available recovery signals and label low-confidence baselines clearly.",
        },
        {
            "axis": "breathing_oxygen_temperature_caution",
            "plain_language_question": "Do overnight breathing, oxygen, or temperature signals add a caution clue?",
            "signals_to_check": ["spo2", "respiratory_rate", "sleep_temperature"],
            "available_signal_ids": present(["spo2", "respiratory_rate", "sleep_temperature"]),
            "decision_effect": "Normal values are reassuring background. Low/unusual oxygen, elevated breathing rate, or changed sleep temperature should bias toward controlled work, especially with symptoms.",
            "missing_data_behavior": "Say the signal is not available; do not treat missing SpO2, respiratory rate, or temperature as normal.",
        },
        {
            "axis": "activity_load_window",
            "plain_language_question": "What load has already accumulated, and over what window?",
            "signals_to_check": [
                "active_zone_minutes",
                "heart_rate_zones",
                "exercise",
                "steps",
                "distance",
                "floors",
                "active_minutes",
                "activity_levels",
                "sedentary_minutes",
                "active_energy",
            ],
            "available_signal_ids": present(
                [
                    "active_zone_minutes",
                    "heart_rate_zones",
                    "steps",
                    "distance",
                    "floors",
                    "active_minutes",
                    "activity_levels",
                    "sedentary_minutes",
                    "active_energy",
                ]
            ),
            "decision_effect": "High zone minutes, hard workouts, high movement volume, hills/floors, or leg-heavy days reduce the next hard effort; low load may support training if recovery agrees.",
            "missing_data_behavior": "When using load, name the date/window and avoid treating steps as useful without explaining why they matter for this decision.",
        },
        {
            "axis": "capacity_progress",
            "plain_language_question": "What does longer-term fitness capacity suggest, without overusing it for today's readiness?",
            "signals_to_check": ["vo2_max", "exercise_history", "heart_rate_zones"],
            "available_signal_ids": present(["vo2_max", "heart_rate_zones"]),
            "decision_effect": "Use VO2 max and workout history for endurance planning and progress, not as a same-day green light for max intensity.",
            "missing_data_behavior": "If VO2 max is absent, plan from sleep, heart, load, and goals instead.",
        },
        {
            "axis": "user_context_and_goal",
            "plain_language_question": "What does the person actually want to accomplish today, and what constraints matter?",
            "signals_to_check": ["goal", "checkins", "energy", "soreness", "stress", "time_budget", "future_plans"],
            "available_signal_ids": [],
            "decision_effect": "Goals and check-ins tune the plan: preserve energy for later, avoid sore areas, or choose the smallest useful session that keeps consistency.",
            "missing_data_behavior": "Ask one short follow-up only if the answer would materially change the recommendation.",
        },
        {
            "axis": "in_session_control",
            "plain_language_question": "If the user is already exercising, should they continue, hold, downshift, or stop?",
            "signals_to_check": ["user-reported current HR", "RPE", "pain", "symptoms", "elapsed time", "planned session purpose"],
            "available_signal_ids": present(["heart_rate_samples", "heart_rate_zones"]),
            "decision_effect": "Use live user-reported HR/RPE/pain/symptoms as the primary in-session data; synced Fitbit context is background only.",
            "missing_data_behavior": "Do not imply direct live band telemetry; ask the user for current HR/RPE/pain if missing.",
        },
    ]
    return {
        "purpose": "A compact, generalizable map for choosing health signals for any natural coaching question.",
        "question_parsing_steps": [
            "Identify the actual decision: train/rest, session plan, active-workout pacing, recovery explanation, trend/progress, or metric discovery.",
            "Identify constraints the user states: symptoms, pain, time, future plans, energy preservation, soreness, goals, or preferred activity.",
            "Select the smallest useful set of axes below, then use the matching available signals and tools.",
            "Convert the data into a plain-language action, intensity/RPE cap, duration or next block, avoid-list, and what would change the call.",
        ],
        "decision_axes": axes,
        "answer_style": [
            "Human answer first, stats second.",
            "Show labels like HRV, RPE, AZM, SpO2, and VO2 max when used, but explain them in one plain sentence.",
            "Say when a checked signal is normal background and did not change the recommendation.",
            "Avoid raw metric dumps unless the user asks for a data table.",
        ],
    }


def model_signal_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    signals = snapshot.get("signals") or []
    if snapshot.get("status") != "ok" or not signals:
        return {
            "status": "missing",
            "model_guidance": (
                "No synced signal snapshot is available. Answer with setup or empty-state guidance "
                "instead of inventing health data."
            ),
            "decision_policy": _model_decision_policy(snapshot),
        }

    by_id = {str(signal.get("id") or ""): signal for signal in signals}

    def pack(signal_ids: tuple[str, ...]) -> list[dict[str, Any]]:
        packed: list[dict[str, Any]] = []
        for signal_id in signal_ids:
            signal = by_id.get(signal_id)
            if not signal:
                continue
            packed.append(
                {
                    "id": signal_id,
                    "label": signal.get("label"),
                    "latest": signal.get("display"),
                    "latest_date": signal.get("latest_date"),
                    "confidence": signal.get("confidence"),
                    "why_it_matters": signal.get("why_it_matters"),
                    "coaching_use": signal.get("coaching_use"),
                    "use_when": signal.get("use_when") or [],
                    "window_summary": signal.get("window_summary") or {},
                }
            )
        return packed

    return {
        "status": "ok",
        "date_range": snapshot.get("date_range"),
        "all_available_signal_ids": snapshot.get("available_signal_ids", []),
        "decision_policy": _model_decision_policy(snapshot),
        "decision_order": [
            "Start from the user's actual goal, current feeling, symptoms, time budget, and future plans.",
            "Use readiness, sleep, HRV, resting heart rate, and recent load as the primary train-hard-or-control call.",
            "Use SpO2, respiratory rate, and sleep temperature as caution/context signals; normal values are reassuring background, not permission for max effort.",
            "Use AZM, heart-rate zones, steps, distance, floors, active minutes, and active energy as load-window signals; always include the date/window when they matter.",
            "Use VO2 max for cardio capacity, endurance planning, and progress context, not same-day recovery permission.",
            "Use live user-reported HR, RPE, pain, symptoms, and elapsed time for in-session decisions because the MCP is not direct band telemetry.",
        ],
        "signal_groups": {
            "primary_recovery": pack(
                ("sleep_duration", "hrv", "resting_heart_rate", "active_zone_minutes")
            ),
            "breathing_temperature_caution": pack(
                ("spo2", "respiratory_rate", "sleep_temperature")
            ),
            "activity_load_window": pack(
                (
                    "active_zone_minutes",
                    "heart_rate_zones",
                    "steps",
                    "active_minutes",
                    "distance",
                    "floors",
                    "activity_levels",
                    "sedentary_minutes",
                    "active_energy",
                )
            ),
            "capacity_progress": pack(("vo2_max",)),
            "in_session_context": pack(("heart_rate_samples", "heart_rate_zones")),
        },
        "answer_contract": [
            "Say the practical decision first, then explain the smallest set of signals that changed it.",
            "For every metric shown, say what it means in plain English and whether it is a primary driver, secondary clue, or background context.",
            "When a signal is normal but relevant, say it was checked and why it did not change the recommendation.",
            "Never turn a green readiness score, normal SpO2, or high VO2 max into automatic permission for all-out work.",
            "Do not treat missing values as zero; say they are not synced or not available.",
        ],
    }


def _recovery_row(day: str, values: dict[str, Any]) -> dict[str, Any]:
    sleep = values.get("sleep", {})
    hrv_sample = values.get("hrv_sample_ms") or {}
    respiratory_sleep = values.get("respiratory_rate_sleep") or {}
    sleep_temperature = values.get("sleep_temperature") or {}
    return {
        "date": day,
        "sleep_hours": sleep.get("asleep_hours") or sleep.get("duration_hours"),
        "sleep_sessions": sleep.get("sessions_count"),
        "hrv_ms": values.get("hrv_ms") or hrv_sample.get("avg"),
        "resting_heart_rate": values.get("resting_heart_rate"),
        "active_zone_minutes": values.get("active_zone_minutes", 0),
        "steps": values.get("steps", 0),
        "respiratory_rate": values.get("respiratory_rate")
        or respiratory_sleep.get("full_sleep_breaths_per_minute"),
        "respiratory_rate_sleep": respiratory_sleep or None,
        "spo2_avg": values.get("spo2_avg") or values.get("spo2_sample", {}).get("avg"),
        "sleep_temperature_delta_celsius": sleep_temperature.get("delta_celsius"),
        "sleep_temperature": sleep_temperature or None,
        "vo2_max": values.get("vo2_max"),
    }


def _has_recovery_comparison_signal(row: dict[str, Any]) -> bool:
    return any(
        row.get(key) is not None
        for key in (
            "sleep_hours",
            "hrv_ms",
            "resting_heart_rate",
            "respiratory_rate",
            "spo2_avg",
            "sleep_temperature_delta_celsius",
        )
    )


def _latest_recovery_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        if _has_recovery_comparison_signal(row):
            return row
    return rows[-1]


def _current_vs_baseline(latest: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "sleep_hours_delta": _delta(latest.get("sleep_hours"), baseline.get("sleep_hours")),
        "hrv_ms_delta": _delta(latest.get("hrv_ms"), baseline.get("hrv_ms")),
        "hrv_percent_delta": _percent_delta(latest.get("hrv_ms"), baseline.get("hrv_ms")),
        "resting_heart_rate_delta": _delta(
            latest.get("resting_heart_rate"), baseline.get("resting_heart_rate")
        ),
        "active_zone_minutes_delta": _delta(
            latest.get("active_zone_minutes"), baseline.get("active_zone_minutes")
        ),
        "respiratory_rate_delta": _delta(
            latest.get("respiratory_rate"), baseline.get("respiratory_rate")
        ),
        "spo2_delta": _delta(latest.get("spo2_avg"), baseline.get("spo2_avg")),
        "sleep_temperature_delta_change_celsius": _delta(
            latest.get("sleep_temperature_delta_celsius"),
            baseline.get("sleep_temperature_delta_celsius"),
        ),
    }


def _recovery_signal_ids(rows: list[dict[str, Any]]) -> list[str]:
    signal_keys = [
        ("sleep_hours", "sleep_hours"),
        ("hrv_ms", "hrv_ms"),
        ("resting_heart_rate", "resting_heart_rate"),
        ("active_zone_minutes", "active_zone_minutes"),
        ("respiratory_rate", "respiratory_rate"),
        ("spo2_avg", "spo2"),
        ("sleep_temperature_delta_celsius", "sleep_temperature"),
        ("vo2_max", "vo2_max"),
    ]
    return [
        signal_id
        for key, signal_id in signal_keys
        if any(row.get(key) is not None for row in rows)
    ]


def _recovery_comparison_takeaways(
    latest: dict[str, Any],
    baseline: dict[str, Any],
    current_vs_baseline: dict[str, Any],
    context: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    insights: list[str] = []
    watchouts: list[str] = []
    positives: list[str] = []
    next_actions: list[str] = []
    sleep = latest.get("sleep_hours")
    hrv = latest.get("hrv_ms")
    rhr = latest.get("resting_heart_rate")
    spo2 = latest.get("spo2_avg")
    respiratory_rate = latest.get("respiratory_rate")
    sleep_temp_delta = latest.get("sleep_temperature_delta_celsius")
    hrv_pct_delta = current_vs_baseline.get("hrv_percent_delta")
    rhr_delta = current_vs_baseline.get("resting_heart_rate_delta")
    sleep_delta = current_vs_baseline.get("sleep_hours_delta")
    resp_delta = current_vs_baseline.get("respiratory_rate_delta")
    spo2_delta = current_vs_baseline.get("spo2_delta")
    temp_delta_change = current_vs_baseline.get("sleep_temperature_delta_change_celsius")
    load = latest.get("active_zone_minutes") or 0

    if sleep is not None and sleep < 6 and ((hrv_pct_delta is not None and hrv_pct_delta <= -10) or (rhr_delta is not None and rhr_delta >= 4)):
        insights.append("Short sleep is lining up with weaker heart recovery signals.")
        watchouts.append("Sleep is short while HRV is suppressed or resting heart rate is elevated.")
        next_actions.append("Keep training easy until sleep and heart recovery rebound.")
    elif sleep is not None and sleep >= 7 and ((hrv_pct_delta is not None and hrv_pct_delta >= -5) or (rhr_delta is not None and rhr_delta <= 2)):
        insights.append("Sleep duration and heart recovery are broadly aligned.")
        positives.append("Sleep is supportive and heart signals are near baseline.")
        next_actions.append("A normal session can be reasonable if warm-up feels good.")
    elif sleep is not None and sleep >= 7 and (hrv_pct_delta is not None and hrv_pct_delta < -10):
        insights.append("Sleep duration looks fine, but HRV is still lagging.")
        watchouts.append("Good sleep hours are not fully translating into autonomic recovery yet.")
        next_actions.append("Use a controlled session and watch how quickly heart rate settles in warm-up.")
    elif sleep_delta is not None and sleep_delta < -0.75:
        insights.append("Sleep is meaningfully below your recent baseline.")
        watchouts.append("Lower sleep may be dragging down readiness even if other signals are incomplete.")
        next_actions.append("Protect sleep tonight and keep intensity capped today.")

    if load > 45:
        insights.append(f"Recent training load is high at {load} zone minutes.")
        watchouts.append("High zone-minute load can suppress HRV or elevate resting heart rate.")
        next_actions.append("Avoid stacking another hard conditioning session today.")
    if hrv is not None and hrv_pct_delta is not None:
        if hrv_pct_delta <= -15:
            watchouts.append(f"HRV is {abs(round(hrv_pct_delta))}% below baseline.")
        elif hrv_pct_delta >= 10:
            positives.append(f"HRV is {round(hrv_pct_delta)}% above baseline.")
    if rhr is not None and rhr_delta is not None:
        if rhr_delta >= 5:
            watchouts.append(f"Resting heart rate is {round(rhr_delta, 1)} bpm above baseline.")
        elif rhr_delta <= 2:
            positives.append("Resting heart rate is near baseline.")
    if respiratory_rate is not None:
        if resp_delta is not None and resp_delta >= 2:
            watchouts.append(
                f"Respiratory rate is {round(resp_delta, 1)} breaths/min above baseline."
            )
            next_actions.append("Treat breathing rate as a reason to keep intensity controlled today.")
        elif resp_delta is not None and resp_delta <= 1:
            positives.append("Respiratory rate is not elevated versus recent baseline.")
        else:
            insights.append(
                f"Respiratory rate is {respiratory_rate:.1f} breaths/min; use it as context with sleep and heart signals."
            )
    if spo2 is not None:
        if spo2 < 94:
            watchouts.append(
                f"SpO2 is {spo2:.1f}%, which should be treated as a caution signal with symptoms and breathing."
            )
            next_actions.append("Avoid hard training if oxygen, breathing, symptoms, or warm-up feel abnormal.")
        elif spo2_delta is not None and spo2_delta <= -2:
            watchouts.append(f"SpO2 is {abs(round(spo2_delta, 1))}% below recent baseline.")
        else:
            positives.append("SpO2 is available as reassuring background context, not a standalone reason to train hard.")
    if sleep_temp_delta is not None:
        if abs(sleep_temp_delta) >= 0.6 or (temp_delta_change is not None and temp_delta_change >= 0.5):
            watchouts.append("Sleep temperature is meaningfully different from baseline.")
            next_actions.append("Use sleep temperature as a caution clue and keep intensity predictable.")
        else:
            insights.append("Sleep temperature is available as a secondary recovery clue.")

    freshness = context.get("data_freshness", {})
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        watchouts.insert(0, "Data should be synced before making a time-sensitive recovery call.")
        next_actions.insert(0, "Run sync_latest_fitbit_data for the freshest recovery comparison.")

    if not insights:
        insights.append("Synced sleep and heart signals are available, but the pattern is not strong yet.")
    if not watchouts:
        watchouts.append("No major sleep-heart recovery mismatch was detected.")
    if not positives:
        positives.append("The comparison has enough data to ground the recovery discussion.")
    if not next_actions:
        next_actions.append("Use this comparison as context, then ask for a specific workout plan if needed.")
    return _dedupe(insights), _dedupe(watchouts), _dedupe(positives), _dedupe(next_actions)


def _recovery_comparison_headline(
    latest: dict[str, Any],
    current_vs_baseline: dict[str, Any],
) -> str:
    parts = []
    if latest.get("sleep_hours") is not None:
        delta = current_vs_baseline.get("sleep_hours_delta")
        parts.append(f"sleep {latest['sleep_hours']:.1f}h" + (f" ({delta:+.1f}h)" if delta is not None else ""))
    if latest.get("hrv_ms") is not None:
        pct = current_vs_baseline.get("hrv_percent_delta")
        parts.append(f"HRV {latest['hrv_ms']:.1f} ms" + (f" ({pct:+.0f}%)" if pct is not None else ""))
    if latest.get("resting_heart_rate") is not None:
        delta = current_vs_baseline.get("resting_heart_rate_delta")
        parts.append(
            f"RHR {latest['resting_heart_rate']} bpm" + (f" ({delta:+.1f})" if delta is not None else "")
        )
    if latest.get("respiratory_rate") is not None:
        delta = current_vs_baseline.get("respiratory_rate_delta")
        parts.append(
            f"resp {latest['respiratory_rate']:.1f}"
            + (f" ({delta:+.1f})" if delta is not None else "")
        )
    if latest.get("spo2_avg") is not None:
        parts.append(f"SpO2 {latest['spo2_avg']:.1f}%")
    return "Latest recovery comparison: " + "; ".join(parts) + "."


def _question_intents(question: str) -> list[str]:
    text = question.lower()
    intents: list[str] = []

    def has(*words: str) -> bool:
        return any(word in text for word in words)

    future_window_context = has(
        "next 2 days",
        "next two days",
        "next 3 days",
        "next three days",
        "next few days",
        "tomorrow",
        "this week",
        "weekend",
        "coming days",
        "next session",
        "one evening",
    ) or bool(re.search(r"\b(next|coming)\s+\d+\s+(day|days|week|weeks)\b", text))
    improvement_goal_context = has(
        "get fitter",
        "getting fitter",
        "build fitness",
        "improve fitness",
        "better shape",
        "cardio better",
        "increase endurance",
        "maintain my body",
        "stay consistent",
        "consistent",
        "not wrecked",
        "without feeling wrecked",
        "not feel wrecked",
        "not overdo",
        "overdo it",
        "too drained",
        "feel drained",
        "leave energy",
        "preserve energy",
        "stay fresh",
    )
    specific_activity_context = has(
        "hike",
        "walk",
        "long walk",
        "lift",
        "run",
        "upper body",
        "lower body",
        "legs",
        "leg day",
        "gym",
        "squash",
        "soccer",
        "sport",
        "dinner later",
        "later today",
        "tomorrow",
        "next session",
        "preserve",
        "keep my legs",
        "keeps my legs",
        "feel drained",
        "not drained",
        "run or",
        "or lift",
    )
    broad_data_context = has(
        "what data",
        "which data",
        "data points",
        "all data",
        "all my data",
        "all signals",
        "all metrics",
        "available data",
        "available metrics",
        "data are you using",
        "data you're using",
        "data you are using",
        "what are you ignoring",
        "what you are ignoring",
        "what you're ignoring",
        "whole picture",
        "full picture",
        "other stats",
        "other signals",
        "appropriate data",
        "necessary data",
        "everything",
    )
    exercise_context = has(
        "workout",
        "work out",
        "working out",
        "how hard",
        "train",
        "training",
        "exercise",
        "lift",
        "run",
        "cardio",
        "interval",
        "intervals",
        "push",
        "harder",
        "squash",
        "sport",
        "legs",
        "chest",
        "back",
        "shoulder",
        "gym",
        "easy miles",
        "quality session",
        "hard session",
        "big session",
        "talk me out",
        "send it",
        "green light",
    )

    asks_for_today_plan = any(
        phrase in text
        for phrase in (
            "what should i do",
            "what do i do",
            "what should my day",
            "what's the plan",
            "whats the plan",
            "today's plan",
            "todays plan",
            "today plan",
            "daily plan",
            "daily brief",
            "coach me today",
            "what should i focus on",
            "make the call",
            "make a call",
            "call for my body",
            "body can absorb",
            "build the day",
            "best use of it",
            "best use of my time",
            "best use of today",
            "quick useful",
            "useful move",
            "useful session",
            "smartest useful session",
        )
    ) or ("today" in text and any(word in text for word in ("recommend", "suggest", "plan", "focus", "best use")))
    if not asks_for_today_plan and has("minutes", "quick", "short on time", "only have"):
        asks_for_today_plan = has("today", "workout", "work out", "train", "training", "session", "exercise")
    if asks_for_today_plan:
        intents.extend(
            [
                "daily_plan",
                "general_overview",
                "workout_decision",
                "recovery",
                "activity_load",
                "heart",
                "sleep",
                "subjective",
                "goal",
            ]
        )

    if future_window_context:
        intents.extend(["multi_day_plan", "daily_plan", "general_overview", "workout_decision", "recovery", "activity_load", "heart", "sleep", "goal"])

    if improvement_goal_context:
        intents.extend(["daily_plan", "general_overview", "workout_decision", "recovery", "activity_load", "heart", "sleep", "goal"])

    if exercise_context:
        intents.extend(["workout_decision", "recovery", "activity_load", "heart", "sleep", "subjective", "goal"])
    if specific_activity_context and exercise_context:
        intents.extend(["specific_activity", "workout_decision", "activity_load", "recovery", "subjective"])
    live_workout_context = has(
        "during workout",
        "during my workout",
        "in-session",
        "in session",
        "mid-workout",
        "active workout",
        "keep going",
        "continue",
        "push",
        "hold steady",
        "back off",
        "slow down",
        "stop",
        "rpe",
        "elapsed",
    ) or (
        has("bpm", "heart rate", "hr ")
        and has("pain", "dizzy", "dizziness", "chest pain", "chest tightness", "breathing", "rpe")
    )
    if live_workout_context:
        intents.extend(["active_workout", "workout_decision", "heart", "activity_load", "recovery", "subjective"])
    if has("tired", "fatigue", "fatigued", "cooked", "drained", "recovery", "readiness", "ready", "rest", "rested", "why"):
        intents.extend(["recovery", "sleep", "heart", "activity_load", "subjective"])
    if has("sleep", "slept", "nap", "bed", "insomnia", "awake", "restless"):
        intents.extend(["sleep", "recovery", "heart"])
    if has("heart", "hrv", "bpm", "pulse", "resting", "cardio"):
        intents.extend(["heart", "recovery", "activity_load"])
    if has("oxygen", "spo2", "sp02", "breathing", "breath", "respiratory", "temperature", "temp"):
        intents.extend(["breathing_recovery", "recovery", "sleep", "heart", "workout_decision"])
    if has("vo2", "capacity", "endurance", "aerobic", "cardio fitness"):
        intents.extend(["general_overview", "activity_load", "heart", "goal"])
    if broad_data_context:
        intents.extend(["metric_discovery", "general_overview", "recovery", "heart", "sleep", "activity_load"])
    if has("sore", "soreness", "pain", "injury", "ache", "stress", "energy", "feel"):
        intents.extend(["subjective", "recovery", "activity_load", "sleep"])
    if has(
        "sick",
        "ill",
        "illness",
        "fever",
        "flu",
        "covid",
        "cold symptoms",
        "sore throat",
        "nausea",
        "chills",
        "vomit",
    ):
        intents.extend(["symptom_safety", "subjective", "recovery", "heart", "sleep"])
    if has("step", "steps", "calorie", "calories", "zone", "active", "load", "distance", "walk"):
        intents.extend(["activity_load", "workout_decision"])
    if has("goal", "goals", "progress", "week", "weekly"):
        intents.extend(["goal", "workout_decision", "activity_load", "daily_plan"])

    if not intents:
        intents = ["general_overview", "recovery", "heart", "sleep", "activity_load"]
    return _dedupe(intents)


def _metric_ids_for_intents(intents: list[str]) -> list[str]:
    metric_ids: list[str] = []
    for intent in intents:
        metric_ids.extend(INTENT_METRICS.get(intent, []))
    return _dedupe(metric_ids)


def metric_catalog_model_guidance(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    available = {item["id"] for item in metrics if int(item.get("records") or 0) > 0}

    def present(metric_ids: list[str]) -> list[str]:
        return [metric_id for metric_id in metric_ids if metric_id in available]

    groups = {
        "recovery_readiness": present(
            [
                "sleep",
                "daily-heart-rate-variability",
                "daily-resting-heart-rate",
                "daily-respiratory-rate",
                "daily-oxygen-saturation",
                "daily-sleep-temperature-derivations",
            ]
        ),
        "training_load": present(
            [
                "active-zone-minutes",
                "time-in-heart-rate-zone",
                "exercise",
                "active-minutes",
                "steps",
                "distance",
            ]
        ),
        "heart_context": present(
            [
                "heart-rate",
                "daily-resting-heart-rate",
                "heart-rate-variability",
                "daily-heart-rate-variability",
                "time-in-heart-rate-zone",
            ]
        ),
        "movement_volume": present(["steps", "distance", "active-minutes", "floors", "sedentary-period"]),
        "capacity": present(["daily-vo2-max", "exercise"]),
    }
    return {
        "principles": [
            "Choose metrics from the user's question, not from a fixed recipe.",
            "Check freshness before time-sensitive coaching and treat missing metrics as unknown, not zero.",
            "Use subjective goals/check-ins together with wearable data when available.",
            "For symptoms, pain, illness, or abnormal-heart-rate concerns, prioritize safety language and avoid diagnosis.",
            "Prefer compact summaries for answers; query raw records only when the user asks for detail or the summary is insufficient.",
        ],
        "general_tool_flow": [
            "connect_google_health_status",
            "get_data_freshness",
            "list_available_health_metrics",
            "get_health_question_clues for ambiguous questions",
            "query_health_metrics for model-selected metric details",
            "get_health_overview or a specific coaching tool for the final card-ready answer",
        ],
        "metric_groups": groups,
        "query_strategy": [
            "Start with 7-14 days for coaching decisions; expand to 30 days for baseline or trend questions.",
            "Pair sleep with HRV/resting heart rate for recovery questions.",
            "Pair oxygen saturation, respiratory rate, and sleep temperature with sleep/heart recovery instead of treating them as standalone train-or-rest signals.",
            "Pair activity-zone minutes, heart-rate zones, activity levels, exercises, steps, distance, and floors for training-load questions.",
            "Pair live user input with guide_active_workout for in-session decisions.",
        ],
    }


def _relevant_metric_cards(
    metric_ids: list[str],
    catalog_by_id: dict[str, dict[str, Any]],
    intents: list[str],
) -> list[dict[str, Any]]:
    cards = []
    for priority, metric_id in enumerate(metric_ids):
        item = catalog_by_id.get(metric_id)
        if not item:
            continue
        cards.append(
            {
                "id": metric_id,
                "label": item.get("label", metric_id),
                "category": item.get("category", "Other"),
                "records": int(item.get("records") or 0),
                "latest_observed_date": item.get("latest_observed_date"),
                "first_observed_date": item.get("first_observed_date"),
                "reason": _metric_reason(metric_id, intents, item),
                "priority": priority,
            }
        )
    return sorted(cards, key=lambda item: (item["records"] == 0, item["priority"]))


def _metric_reason(metric_id: str, intents: list[str], catalog_item: dict[str, Any]) -> str:
    reason = METRIC_COACHING_REASONS.get(metric_id) or catalog_item.get("description") or "Useful health context."
    if "workout_decision" in intents and metric_id in {"active-zone-minutes", "time-in-heart-rate-zone", "exercise"}:
        return f"{reason} This is especially useful for deciding today's intensity."
    if "recovery" in intents and metric_id in {"sleep", "daily-heart-rate-variability", "daily-resting-heart-rate"}:
        return f"{reason} This is a core recovery signal."
    if "sleep" in intents and metric_id.startswith("daily-sleep"):
        return f"{reason} This can explain sleep quality beyond duration."
    return reason


def _recommended_tool_sequence(
    intents: list[str],
    freshness: dict[str, Any],
    *,
    primary_flows: list[dict[str, Any]] | None = None,
) -> list[str]:
    tools: list[str] = ["get_health_question_clues"]
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        tools.extend(["get_data_freshness", "sync_latest_fitbit_data"])
    for flow in (primary_flows or [])[:3]:
        tools.extend(flow.get("primary_tools") or [])
        tools.extend(flow.get("supporting_tools") or [])
    if "metric_discovery" in intents:
        tools.extend(["list_available_health_metrics", "query_health_metrics"])
    if "general_overview" in intents or "daily_plan" in intents or "goal" in intents:
        tools.append("get_health_overview")
    if "active_workout" in intents:
        tools.append("guide_active_workout")
    if "workout_decision" in intents or "daily_plan" in intents:
        tools.extend(["recommend_workout_today", "plan_workout_with_health_context"])
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        tools.extend(["get_recovery_signal_comparison", "get_sleep_analysis", "get_heart_trends"])
    if "activity_load" in intents:
        tools.extend(["get_activity_load", "get_workout_history"])
    return _dedupe(tools)


def _conversation_flow_options(
    freshness: dict[str, Any] | None = None,
    *,
    setup_state: bool = False,
    empty_state: bool = False,
) -> list[dict[str, Any]]:
    freshness = freshness or {}
    sync_prefix = (
        ["get_data_freshness", "sync_latest_fitbit_data"]
        if freshness.get("needs_sync_before_time_sensitive_advice")
        else []
    )
    freshness_policy = (
        freshness.get("recommendation")
        or "Use already-synced data for normal coaching; sync only when the user asks or freshness is stale."
    )

    if setup_state:
        return [
            {
                "flow": "connect_first",
                "use_for": [
                    "new ChatGPT user",
                    "friend has not connected Google Health",
                    "OAuth required",
                ],
                "primary_tools": ["connect_google_health_status"],
                "model_instruction": "Explain that this app starts empty per user and cannot see Fitbit data until Google Health OAuth is completed.",
            }
        ]

    if empty_state:
        return [
            {
                "flow": "first_sync_after_connect",
                "use_for": [
                    "connected account with no synced records",
                    "first run after setup",
                    "friend or new user empty state",
                ],
                "primary_tools": ["connect_google_health_status", "sync_latest_fitbit_data"],
                "model_instruction": "Ask the user to sync before coaching from data; if sync is still empty, say there is not enough wearable context yet.",
            }
        ]

    return [
        {
            "flow": "daily_training_decision",
            "use_for": [
                "train hard today",
                "green light to push",
                "low energy but want to move",
                "run vs lift today",
                "what should I do today",
            ],
            "primary_tools": [*sync_prefix, "recommend_workout_today"],
            "supporting_tools": ["get_health_overview", "get_recovery_signal_comparison"],
            "data_surfaces_to_use": [
                "training_decision",
                "coach_response",
                "available_signal_snapshot",
                "data_freshness",
                "goal_context",
                "subjective_context",
            ],
            "model_instruction": (
                "Turn the data into a specific session type, duration, intensity, RPE cap, avoid-list, "
                "and the signals that would change the call."
            ),
            "freshness_policy": freshness_policy,
        },
        {
            "flow": "specific_activity_plan",
            "use_for": [
                "hike tomorrow",
                "legs sore but want to lift",
                "upper body or run",
                "specific sport or muscle group",
            ],
            "primary_tools": [*sync_prefix, "plan_workout_with_health_context"],
            "supporting_tools": ["recommend_workout_today", "get_activity_load"],
            "data_surfaces_to_use": [
                "training_decision",
                "coach_response",
                "available_signal_snapshot",
                "goal_context",
                "recent_checkins",
            ],
            "model_instruction": (
                "Put the actual workout in planned_activity and keep future events, soreness, pain, "
                "time limits, and energy preservation in constraints."
            ),
            "freshness_policy": freshness_policy,
        },
        {
            "flow": "active_workout_pacing",
            "use_for": [
                "during workout",
                "heart rate is high",
                "RPE or pain reported",
                "should I keep going or stop",
            ],
            "primary_tools": ["guide_active_workout"],
            "supporting_tools": ["get_data_freshness"],
            "data_surfaces_to_use": [
                "coach_response",
                "training_decision",
                "data_freshness",
                "available_signal_snapshot",
                "live_inputs_are_user_reported",
            ],
            "model_instruction": (
                "Use live user-reported HR, RPE, pain, symptoms, elapsed time, and synced readiness/load; "
                "do not describe synced Fitbit context as a live band stream."
            ),
            "freshness_policy": "Synced context can be background during a workout; live HR/RPE/pain must come from the user's report.",
        },
        {
            "flow": "sleep_breathing_recovery_question",
            "use_for": [
                "compare sleep and heart",
                "SpO2 or respiratory rate concern",
                "illness suspicion",
                "why do I feel tired",
            ],
            "primary_tools": [*sync_prefix, "get_recovery_signal_comparison"],
            "supporting_tools": ["query_health_metrics", "get_sleep_analysis", "get_heart_trends"],
            "data_surfaces_to_use": [
                "recovery_comparison",
                "available_signal_snapshot",
                "query_suggestions",
                "safety_flags",
            ],
            "model_instruction": (
                "Explain which signals agree or disagree. Treat oxygen, respiratory rate, and sleep "
                "temperature as context with symptoms and heart/sleep patterns, not as standalone diagnosis."
            ),
            "freshness_policy": freshness_policy,
        },
        {
            "flow": "weekly_training_planning",
            "use_for": [
                "weekly plan",
                "training consistency",
                "goal progress",
                "how much have I done",
            ],
            "primary_tools": ["get_health_overview", "get_activity_load", "get_workout_history"],
            "supporting_tools": ["recommend_workout_today"],
            "data_surfaces_to_use": [
                "overview_context",
                "goal_context",
                "activity_load",
                "workout_history",
                "available_signal_snapshot",
            ],
            "model_instruction": (
                "Separate past load from what to do next; name the window for steps/AZM/workouts and "
                "turn it into the smallest useful next move."
            ),
            "freshness_policy": freshness_policy,
        },
        {
            "flow": "metric_discovery_or_unusual_question",
            "use_for": [
                "what other data matters",
                "use all my data",
                "which metrics should you inspect",
                "unusual pattern",
            ],
            "primary_tools": ["list_available_health_metrics", "query_health_metrics"],
            "supporting_tools": ["get_health_question_clues", "get_health_overview"],
            "data_surfaces_to_use": [
                "metric_catalog_model_guidance",
                "query_suggestions",
                "available_signal_snapshot",
                "relevant_metrics",
            ],
            "model_instruction": "Let the user's question choose the metrics; use missing metrics as unknown, never as zero.",
            "freshness_policy": freshness_policy,
        },
    ]


def _primary_conversation_flows(
    intents: list[str],
    conversation_flows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flows_by_name = {flow["flow"]: flow for flow in conversation_flows}
    ranked_names: list[tuple[str, str]] = []

    def add(flow_name: str, reason: str) -> None:
        if flow_name in flows_by_name and all(name != flow_name for name, _ in ranked_names):
            ranked_names.append((flow_name, reason))

    if "active_workout" in intents:
        add("active_workout_pacing", "The user is asking for an in-session hold, push, downshift, or stop decision.")
    if "symptom_safety" in intents:
        add("sleep_breathing_recovery_question", "Symptoms or abnormal-heart-rate concerns should use recovery and safety surfaces first.")
    if "breathing_recovery" in intents:
        add("sleep_breathing_recovery_question", "Oxygen, respiratory-rate, or sleep-temperature questions need recovery comparison before training permission.")
    if "metric_discovery" in intents:
        add("metric_discovery_or_unusual_question", "The user is asking which data matters, what is available, or what is being ignored.")
    if "specific_activity" in intents:
        add("specific_activity_plan", "A named activity, future event, body area, or energy-preservation constraint should shape the session first.")
    if "multi_day_plan" in intents:
        add("weekly_training_planning", "A next-few-days or weekly question should start from recent load, workout history, goals, and recovery windows.")
    if "daily_plan" in intents or "workout_decision" in intents:
        add("daily_training_decision", "The user needs a concrete today/session decision, not only a metric explanation.")
    if "goal" in intents and ("daily_plan" in intents or "activity_load" in intents):
        add("weekly_training_planning", "Goal or consistency language needs load and workout-history context.")
    if "workout_decision" in intents and "subjective" in intents:
        add("specific_activity_plan", "The answer may need to adapt a named activity, body area, soreness, time limit, or constraint.")
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        add("sleep_breathing_recovery_question", "Sleep, heart, breathing, oxygen, or temperature signals need comparison context.")
    if "activity_load" in intents or "goal" in intents:
        add("weekly_training_planning", "Recent steps, AZM, workouts, and goals need a named data window.")
    if "general_overview" in intents:
        add("daily_training_decision", "A broad health question can still end with the smallest useful next move.")
        add("metric_discovery_or_unusual_question", "Broad wording may need the metric catalog and model-selected query path.")

    if not ranked_names:
        add("daily_training_decision", "Default to a practical health-coaching decision flow.")
        add("metric_discovery_or_unusual_question", "Use metric discovery if the question does not map cleanly to a known flow.")

    return [
        {
            "rank": rank,
            "flow": flow_name,
            "why_selected": reason,
            "primary_tools": flows_by_name[flow_name].get("primary_tools", []),
            "supporting_tools": flows_by_name[flow_name].get("supporting_tools", []),
            "data_surfaces_to_use": flows_by_name[flow_name].get("data_surfaces_to_use", []),
            "model_instruction": flows_by_name[flow_name].get("model_instruction", ""),
            "freshness_policy": flows_by_name[flow_name].get("freshness_policy", ""),
        }
        for rank, (flow_name, reason) in enumerate(ranked_names[:4], start=1)
    ]


def _metric_query_suggestions(
    intents: list[str],
    relevant_metrics: list[dict[str, Any]],
    days: int,
) -> list[dict[str, Any]]:
    available = {item["id"] for item in relevant_metrics if item.get("records", 0) > 0}
    groups = [
        (
            "recovery",
            "Compare sleep, HRV, resting heart rate, breathing/oxygen context, sleep temperature, and load.",
            [
                "sleep",
                "daily-heart-rate-variability",
                "daily-resting-heart-rate",
                "daily-respiratory-rate",
                "respiratory-rate-sleep-summary",
                "daily-oxygen-saturation",
                "oxygen-saturation",
                "daily-sleep-temperature-derivations",
                "active-zone-minutes",
            ],
        ),
        (
            "heart",
            "Inspect heart-rate and HRV details.",
            ["heart-rate", "heart-rate-variability", "daily-heart-rate-variability", "daily-resting-heart-rate"],
        ),
        (
            "load",
            "Inspect movement and workout load.",
            [
                "active-zone-minutes",
                "time-in-heart-rate-zone",
                "calories-in-heart-rate-zone",
                "activity-level",
                "active-minutes",
                "steps",
                "distance",
                "floors",
                "sedentary-period",
                "exercise",
            ],
        ),
        (
            "sleep",
            "Inspect sleep and overnight recovery context.",
            ["sleep", "daily-respiratory-rate", "daily-oxygen-saturation", "daily-sleep-temperature-derivations"],
        ),
        (
            "symptom_safety",
            "Inspect recovery and cardiopulmonary clues while keeping the answer non-diagnostic.",
            [
                "daily-resting-heart-rate",
                "heart-rate",
                "daily-heart-rate-variability",
                "sleep",
                "daily-respiratory-rate",
                "daily-oxygen-saturation",
            ],
        ),
    ]
    suggestions = []
    for purpose, description, metric_ids in groups:
        if purpose not in intents and purpose != "load":
            continue
        usable = [metric_id for metric_id in metric_ids if metric_id in available]
        if usable:
            suggestions.append(
                {
                    "purpose": purpose,
                    "description": description,
                    "metrics": usable,
                    "tool": "query_health_metrics",
                    "arguments": {
                        "metrics": usable,
                        "days": days,
                        "include_records": False,
                    },
                    "when_to_use": "Call this when the overview/clues are not enough detail for the user's question.",
                }
            )
    return suggestions


def _answer_rubric_for_intents(intents: list[str]) -> list[str]:
    rubric = [
        "Start with the direct answer, then name the strongest supporting signals.",
        "Keep metric labels visible, but explain every label you use in simple words the first time it appears.",
        "When steps or movement totals are used, name the date/window and explain why they matter or do not matter for this decision.",
        "Separate wearable evidence, user-reported context, and missing data.",
        "Mention freshness when the user asks about today, latest data, or real-time decisions.",
        "Match the user's situation; do not assume fatigue, soreness, or an off-day unless the user or data says so.",
    ]
    if "workout_decision" in intents or "daily_plan" in intents:
        rubric.append("For training advice, convert the signals into intensity, RPE cap, session type, and avoid-list.")
    if "active_workout" in intents:
        rubric.append("For in-session advice, prioritize stop/continue/downshift guidance from symptoms, RPE, pain, and heart rate.")
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        rubric.append(
            "For recovery explanations, compare latest sleep, HRV, resting heart rate, oxygen/breathing context, sleep temperature when available, and load against recent baseline."
        )
    if "symptom_safety" in intents:
        rubric.append("For symptoms or illness, avoid diagnosis, advise rest or easy movement, and suggest clinical care for severe or worsening symptoms.")
    if "goal" in intents:
        rubric.append("Tie the recommendation back to the user's stored goal without overriding recovery or safety signals.")
    return _dedupe(rubric)


def _decision_frame_for_question(
    question: str,
    intents: list[str],
    context: dict[str, Any],
    overview: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    freshness = context.get("data_freshness", {})
    signal_snapshot = overview.get("available_signal_snapshot") or {}
    return {
        "primary_decision": _primary_decision_for_intents(intents),
        "model_role": (
            "Use this as a reasoning scaffold, not a script. Match the user's actual situation, "
            "then turn the data into one practical coaching call."
        ),
        "user_context_cues": _question_context_cues(question),
        "model_decision_policy": _model_decision_policy(signal_snapshot),
        "signal_roles": _signal_roles_for_intents(intents, overview, comparison),
        "available_signal_ids": signal_snapshot.get("available_signal_ids", [])
        if overview.get("status") == "ok"
        else [],
        "output_contract": _output_contract_for_intents(intents, freshness),
        "plain_language_labels": [
            "Readiness = quick recovery score from sleep, heart, and load signals; green supports normal training, not max effort by itself.",
            "RPE = how hard it feels from 1 easy to 10 max; use it as the effort cap.",
            "AZM = Active Zone Minutes, Fitbit's harder-effort minutes from elevated heart-rate zones.",
            "HRV = recovery stress signal; compare it to the user's usual before treating it as meaningful.",
            "Resting HR = heart stress at rest; higher than usual can point to stress, illness, fatigue, or poor recovery.",
            "SpO2 = oxygen saturation context; normal is reassuring background, low or unusual should be interpreted with symptoms and breathing.",
            "Respiratory rate = overnight breaths per minute; compare to usual before treating it as meaningful.",
            "VO2 max = longer-term cardio capacity, not same-day recovery.",
        ],
        "do_not_do": [
            "Do not list stats without saying how each stat changes today's decision.",
            "Do not let a green readiness score override symptoms, pain, poor warm-up, or a user-stated need to preserve energy.",
            "Do not treat steps as automatically good or bad; explain the date/window and whether they add useful load context.",
            "Do not pretend missing or low-confidence baselines are strong evidence.",
        ],
    }


def _primary_decision_for_intents(intents: list[str]) -> str:
    if "symptom_safety" in intents:
        return "safety-first movement decision"
    if "active_workout" in intents:
        return "in-session continue, hold, downshift, or stop decision"
    if "daily_plan" in intents:
        return "today plan and useful movement decision"
    if "workout_decision" in intents:
        return "workout intensity, session type, and effort-cap decision"
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        return "recovery explanation and training-readiness decision"
    if "activity_load" in intents:
        return "recent load and movement-volume interpretation"
    if "goal" in intents:
        return "goal-progress and consistency decision"
    return "general health and fitness context decision"


def _question_context_cues(question: str) -> list[dict[str, str]]:
    text = question.lower()
    cues: list[dict[str, str]] = []
    minutes = _minutes_from_question(text)
    if minutes is not None:
        cues.append(
            {
                "cue": "time_budget",
                "value": f"{minutes} minutes",
                "how_to_use": "Make the recommendation fit the available time and avoid turning a short window into an all-out session.",
            }
        )
    if _contains_context_term(
        text,
        (
            "later",
            "tonight",
            "tomorrow",
            "dinner",
            "meeting",
            "after work",
            "before work",
            "work later",
            "workday",
            "shift",
            "travel",
            "plans",
            "long walk",
            "walk later",
            "basketball",
            "pickleball",
            "soccer",
            "match",
            "game",
            "practice",
            "preserve",
            "save energy",
            "drained",
            "wiped",
        ),
    ):
        cues.append(
            {
                "cue": "reserve_energy_or_future_event",
                "value": "user mentioned a later obligation, future activity, or desire not to be drained",
                "how_to_use": "Protect the rest of the day by lowering volume, avoiding finishers, and leaving reps or effort in reserve.",
            }
        )
    if _contains_context_term(
        text,
        (
            "walked",
            "steps",
            "long walk",
            "run",
            "running",
            "hike",
            "legs",
            "leg day",
            "lower body",
            "basketball",
            "soccer",
            "squash",
            "tennis",
        ),
    ):
        cues.append(
            {
                "cue": "load_stacking",
                "value": "question mentions movement volume, legs, running, walking, or sport",
                "how_to_use": "Count this as load context before adding hard conditioning or lower-body stress.",
            }
        )
    if any(term in text for term in ("push", "hard", "interval", "sprint", "heavy", "pr", "max", "intense")):
        cues.append(
            {
                "cue": "higher_intensity_interest",
                "value": "user is considering hard training",
                "how_to_use": "Require stronger agreement from sleep, heart, load, freshness, and warm-up before endorsing high intensity.",
            }
        )
    if any(term in text for term in ("pain", "dizzy", "dizziness", "chest", "sick", "fever", "symptom", "breathing")):
        cues.append(
            {
                "cue": "safety_or_symptom_context",
                "value": "question includes pain, symptoms, breathing, dizziness, illness, or heart concern",
                "how_to_use": "Use safety-first language, avoid diagnosis, and name stop or clinical-care triggers.",
            }
        )
    if not cues:
        cues.append(
            {
                "cue": "no_special_constraint_detected",
                "value": "no time, future-event, symptom, or load-stacking cue was detected",
                "how_to_use": "Default to a data-guided normal plan and do not assume the user feels off.",
            }
        )
    return cues


def _minutes_from_question(text: str) -> int | None:
    matches = re.findall(
        r"\b(?:only\s+have|have|got|with|for|about|around|approximately|under)?\s*(\d{1,3})\s*(?:min|mins|minute|minutes)\b",
        text,
    )
    if not matches:
        return None
    return max(5, min(int(matches[0]), 180))


def _contains_context_term(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if " " in term or "-" in term:
            if term in text:
                return True
            continue
        if re.search(rf"\b{re.escape(term)}\b", text):
            return True
    return False


def _signal_roles_for_intents(
    intents: list[str],
    overview: dict[str, Any],
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = [
        {
            "signal": "readiness",
            "metric_ids": ["sleep", "daily-heart-rate-variability", "daily-resting-heart-rate", "active-zone-minutes"],
            "role": "starting point for training room",
            "how_to_use": "Green supports a normal session; yellow or red should lower intensity. Never use it as permission for max effort by itself.",
        },
        {
            "signal": "data_freshness",
            "metric_ids": [],
            "role": "confidence in time-sensitive decisions",
            "how_to_use": "Fresh is fine for normal coaching. Aging is usable for controlled choices. Stale should trigger sync before hard or time-sensitive advice.",
        },
    ]
    if "workout_decision" in intents or "daily_plan" in intents:
        roles.extend(
            [
                {
                    "signal": "sleep",
                    "metric_ids": ["sleep"],
                    "role": "recovery capacity",
                    "how_to_use": "Strong sleep gives more room to train; short or restless sleep should lower volume or RPE.",
                },
                {
                    "signal": "heart_recovery",
                    "metric_ids": ["daily-heart-rate-variability", "daily-resting-heart-rate"],
                    "role": "stress and recovery cross-check",
                    "how_to_use": "Use HRV and resting HR together, and mention low-confidence baselines when sample size is small.",
                },
                {
                    "signal": "breathing_oxygen_temperature_context",
                    "metric_ids": [
                        "daily-respiratory-rate",
                        "respiratory-rate-sleep-summary",
                        "daily-oxygen-saturation",
                        "oxygen-saturation",
                        "daily-sleep-temperature-derivations",
                    ],
                    "role": "secondary recovery and safety context",
                    "how_to_use": "Use unusual oxygen, respiratory-rate, or sleep-temperature signals as caution context; normal values are background, not permission for max effort.",
                },
                {
                    "signal": "training_load",
                    "metric_ids": [
                        "active-zone-minutes",
                        "time-in-heart-rate-zone",
                        "activity-level",
                        "exercise",
                        "steps",
                        "distance",
                        "floors",
                    ],
                    "role": "load already accumulated",
                    "how_to_use": "High AZM, hard workouts, or lots of steps should make the next session more controlled.",
                },
                {
                    "signal": "capacity_progress",
                    "metric_ids": ["daily-vo2-max", "exercise", "time-in-heart-rate-zone"],
                    "role": "longer-term cardio capacity and progress context",
                    "how_to_use": "Use VO2 max and workout history to shape endurance direction, but do not use them as same-day permission for max effort.",
                },
                {
                    "signal": "personal_context",
                    "metric_ids": [],
                    "role": "goals, check-ins, and constraints",
                    "how_to_use": "Use stated energy, soreness, stress, goals, and future plans to tune the plan even when wearable data looks green.",
                },
            ]
        )
    if "active_workout" in intents:
        roles.append(
            {
                "signal": "live_session_inputs",
                "metric_ids": ["heart-rate", "time-in-heart-rate-zone"],
                "role": "in-session safety and pacing",
                "how_to_use": "Combine current HR, RPE, pain, symptoms, elapsed time, and planned session purpose to choose continue, hold, downshift, or stop.",
            }
        )
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        roles.append(
            {
                "signal": "recovery_comparison",
                "metric_ids": [
                    "sleep",
                    "daily-heart-rate-variability",
                    "daily-resting-heart-rate",
                    "daily-respiratory-rate",
                    "respiratory-rate-sleep-summary",
                    "daily-oxygen-saturation",
                    "oxygen-saturation",
                    "daily-sleep-temperature-derivations",
                ],
                "role": "pattern explanation",
                "how_to_use": "Explain which recovery signals agree, which conflict, and whether the baseline has enough samples.",
                "available": comparison.get("status") == "ok",
            }
        )
    if "goal" in intents:
        goal_present = bool(
            ((overview.get("personal_context") or {}).get("goal") or {}).get("goal")
        ) if overview.get("status") == "ok" else False
        roles.append(
            {
                "signal": "goal_progress",
                "metric_ids": ["exercise", "active-zone-minutes"],
                "role": "consistency target",
                "how_to_use": "Use the goal to choose the smallest useful session that preserves recovery when needed.",
                "available": goal_present,
            }
        )
    if "symptom_safety" in intents:
        roles.insert(
            0,
            {
                "signal": "symptoms_and_red_flags",
                "metric_ids": [
                    "daily-resting-heart-rate",
                    "heart-rate",
                    "sleep",
                    "daily-respiratory-rate",
                    "respiratory-rate-sleep-summary",
                    "daily-oxygen-saturation",
                    "daily-sleep-temperature-derivations",
                ],
                "role": "safety override",
                "how_to_use": "Symptoms, chest tightness, dizziness, severe shortness of breath, faintness, fever, or worsening illness override training optimization.",
            },
        )
    return roles


def _output_contract_for_intents(intents: list[str], freshness: dict[str, Any]) -> list[str]:
    contract = [
        "Start with a one-sentence decision in plain language.",
        "Name the data used and why each signal changes the recommendation.",
        "Explain labels the first time they appear, including Readiness, RPE, AZM, HRV, Resting HR, SpO2, respiratory rate, or VO2 max when used.",
    ]
    if "active_workout" in intents:
        contract.extend(
            [
                "Give continue/hold/back-off/stop guidance for the next 3-10 minutes.",
                "Name exactly what would make you stop the session.",
            ]
        )
    if "workout_decision" in intents or "daily_plan" in intents:
        contract.extend(
            [
                "Convert the data into session type, duration, intensity, RPE cap, and what to avoid.",
                "Use future plans and time limits to preserve energy when the user asks for that.",
            ]
        )
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        contract.append(
            "Say which recovery signals agree or disagree, including oxygen/breathing context when available, and whether baselines are low confidence."
        )
    if "activity_load" in intents:
        contract.append("When using steps or load, include the window/date and whether it matters for legs, fatigue, or intensity.")
    if "symptom_safety" in intents:
        contract.append("Use medical-caution language for severe, new, or worsening symptoms; do not diagnose.")
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        contract.insert(0, "Ask to sync before a hard, risky, or time-sensitive training decision.")
    return _dedupe(contract)


def _question_clue_takeaways(
    intents: list[str],
    context: dict[str, Any],
    overview: dict[str, Any],
    comparison: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str]]:
    clues: list[str] = []
    positives: list[str] = []
    watchouts: list[str] = []
    next_actions: list[str] = []
    readiness = context.get("readiness", {})
    today = context.get("today", {})
    sections = overview.get("sections", {}) if overview.get("status") == "ok" else {}
    sleep = sections.get("sleep", {})
    heart = sections.get("heart", {})
    activity = sections.get("activity", {})
    signal_snapshot = overview.get("available_signal_snapshot", {}) if overview.get("status") == "ok" else {}
    workouts = sections.get("workouts", {})
    freshness = context.get("data_freshness", {})
    personal_context = overview.get("personal_context", {}) if overview.get("status") == "ok" else {}
    recent_checkins = personal_context.get("recent_checkins") or []
    goal = personal_context.get("goal") or {}
    goal_payload = goal.get("goal") or {}

    if readiness:
        clues.append(
            f"Readiness is {readiness.get('label', 'unknown')} at {readiness.get('score', '?')}/100."
        )
        clues.extend(readiness.get("evidence", [])[:3])

    latest_sleep = sleep.get("latest_asleep_hours") or today.get("sleep", {}).get("asleep_hours") or today.get("sleep", {}).get("duration_hours")
    average_sleep = sleep.get("average_asleep_hours")
    if latest_sleep is not None:
        clues.append(f"Latest sleep is {latest_sleep:.1f}h.")
        if latest_sleep < 6:
            watchouts.append("Latest sleep is short enough to affect training intensity and recovery.")
        elif latest_sleep >= 7:
            positives.append("Latest sleep duration is supportive for training.")
        if average_sleep is not None:
            delta = _delta(latest_sleep, average_sleep)
            if delta is not None and delta <= -0.75:
                watchouts.append(f"Latest sleep is {abs(delta):.1f}h below the recent average.")

    if heart.get("latest_hrv_ms") is not None:
        clues.append(f"Latest HRV is {heart['latest_hrv_ms']:.1f} ms.")
    if heart.get("latest_resting_heart_rate") is not None:
        clues.append(f"Latest resting heart rate is {heart['latest_resting_heart_rate']} bpm.")

    if comparison.get("status") == "ok":
        current = comparison.get("current_vs_baseline", {})
        hrv_pct = current.get("hrv_percent_delta")
        rhr_delta = current.get("resting_heart_rate_delta")
        resp_delta = current.get("respiratory_rate_delta")
        spo2_delta = current.get("spo2_delta")
        if hrv_pct is not None:
            direction = "above" if hrv_pct >= 0 else "below"
            clues.append(f"HRV is {abs(round(hrv_pct))}% {direction} recent baseline.")
            if hrv_pct <= -15:
                watchouts.append("HRV is meaningfully suppressed versus baseline.")
            elif hrv_pct >= 10:
                positives.append("HRV is above recent baseline.")
        if rhr_delta is not None:
            direction = "above" if rhr_delta >= 0 else "below"
            clues.append(f"Resting heart rate is {abs(round(rhr_delta, 1))} bpm {direction} baseline.")
            if rhr_delta >= 5:
                watchouts.append("Resting heart rate is elevated versus baseline.")
        if resp_delta is not None:
            direction = "above" if resp_delta >= 0 else "below"
            clues.append(
                f"Respiratory rate is {abs(round(resp_delta, 1))} breaths/min {direction} baseline."
            )
            if resp_delta >= 2:
                watchouts.append("Respiratory rate is elevated versus baseline.")
        if spo2_delta is not None:
            direction = "above" if spo2_delta >= 0 else "below"
            clues.append(f"SpO2 is {abs(round(spo2_delta, 1))}% {direction} baseline.")
        clues.extend(comparison.get("insights", [])[:3])
        positives.extend(comparison.get("positives", [])[:2])
        watchouts.extend(comparison.get("watchouts", [])[:3])

    for line in _snapshot_takeaway_lines(signal_snapshot, intents):
        clues.append(line)

    latest_load = today.get("latest_training_load", {})
    active_zone_minutes = today.get("active_zone_minutes") or latest_load.get("active_zone_minutes")
    if active_zone_minutes is not None:
        clues.append(f"Latest available load is {active_zone_minutes} Active Zone Minutes.")
        if active_zone_minutes > 45:
            watchouts.append("Recent zone-minute load is high, so avoid stacking hard conditioning.")
    if activity.get("totals", {}).get("steps") is not None:
        step_total = int(activity["totals"]["steps"])
        step_avg = activity.get("averages", {}).get("steps_per_day")
        step_summary = activity.get("step_window_summary") or {}
        step_window_text = step_summary.get("display")
        step_average_text = step_summary.get("average_display")
        if not step_window_text:
            window_days = overview.get("window_days")
            day_word = "day" if window_days == 1 else "days"
            window_text = f"over the last {window_days} {day_word}" if window_days else "in the synced window"
            step_window_text = f"{step_total:,} steps {window_text}"
        average_text = f"; {step_average_text}" if step_average_text else (
            f"; {int(step_avg):,}/day average across recorded step days" if step_avg is not None else ""
        )
        clues.append(
            f"Movement context: {step_window_text}{average_text}. "
            "Use this as background fatigue/load context, not as a standalone reason to train or rest."
        )
    if workouts.get("workout_count"):
        clues.append(f"{workouts['workout_count']} recent workout(s) are available for context.")
        hardest = workouts.get("hardest_workout") or {}
        if hardest:
            name = hardest.get("display_name") or hardest.get("type") or "workout"
            load = hardest.get("active_zone_minutes")
            if load is not None:
                clues.append(f"Hardest recent workout was {name} with {load} Active Zone Minutes.")

    soreness = _rating_from_checkins(recent_checkins, "soreness")
    energy = _rating_from_checkins(recent_checkins, "energy")
    stress = _rating_from_checkins(recent_checkins, "stress")
    latest_note = _latest_checkin_note(recent_checkins)
    if energy is not None:
        clues.append(f"Latest energy check-in is {energy}/10.")
        if energy <= 4:
            watchouts.append("Low self-reported energy supports a conservative training call.")
        elif energy >= 7:
            positives.append("Self-reported energy is strong.")
    if soreness is not None:
        clues.append(f"Latest soreness check-in is {soreness}/10.")
        if soreness >= 7:
            watchouts.append("High soreness should cap intensity and avoid loading sore areas.")
        elif soreness >= 5:
            watchouts.append("Moderate soreness means warm-up quality should decide final intensity.")
        elif soreness <= 3:
            positives.append("Self-reported soreness is low.")
    if stress is not None:
        clues.append(f"Latest stress check-in is {stress}/10.")
        if stress >= 7:
            watchouts.append("High stress can reduce recovery tolerance even if wearable signals look okay.")
        elif stress <= 4:
            positives.append("Self-reported stress is not elevated.")
    if latest_note:
        punctuation = "" if latest_note.endswith((".", "!", "?")) else "."
        clues.append(f"Latest check-in note: {latest_note}{punctuation}")

    goal_target = goal_payload.get("target")
    days_per_week = goal_payload.get("days_per_week")
    if goal_target:
        clues.append(f"Current goal: {goal_target}.")
    if days_per_week is not None:
        try:
            target_sessions = max(0, int(days_per_week))
        except (TypeError, ValueError):
            target_sessions = None
        if target_sessions is not None:
            workout_count = int(workouts.get("workout_count") or 0)
            remaining = max(0, target_sessions - workout_count)
            clues.append(
                f"Goal progress in this window: {workout_count}/{target_sessions} workout sessions logged."
            )
            if remaining and "workout_decision" in intents:
                next_actions.append(
                    f"{remaining} goal session(s) remain, but recovery and check-ins should decide today's intensity."
                )
            elif not remaining:
                positives.append("Recent workout count already covers the weekly session target.")

    if "workout_decision" in intents:
        next_actions.append("Use recommend_workout_today for the broad daily intensity call.")
        next_actions.append("Use plan_workout_with_health_context when the user names a specific workout.")
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        next_actions.append(
            "Use get_recovery_signal_comparison to explain sleep, HRV, resting heart rate, breathing/oxygen context, and load together."
        )
    if "activity_load" in intents:
        next_actions.append("Use get_activity_load and get_workout_history to understand recent load before prescribing intensity.")
    if freshness.get("freshness_level") == "fresh":
        positives.append("Synced data is fresh enough for normal coaching context.")
    elif freshness.get("freshness_level"):
        watchouts.append(f"Data freshness is {freshness.get('freshness_label', freshness['freshness_level'])}.")

    if not clues:
        clues.append("Use the available synced metric catalog to choose follow-up queries.")
    if not next_actions:
        next_actions.append("Use get_health_overview before answering broad health and fitness questions.")
    return clues, positives, watchouts, next_actions


def _snapshot_takeaway_lines(snapshot: dict[str, Any], intents: list[str]) -> list[str]:
    if snapshot.get("status") != "ok":
        return []
    signals = snapshot.get("signals") or []
    wanted_ids: list[str] = []
    if any(intent in intents for intent in ("recovery", "sleep", "heart", "symptom_safety")):
        wanted_ids.extend(["spo2", "respiratory_rate", "sleep_temperature", "heart_rate_samples"])
    if any(intent in intents for intent in ("activity_load", "workout_decision", "daily_plan")):
        wanted_ids.extend(["heart_rate_zones", "activity_levels", "sedentary_minutes", "floors", "distance"])
    if any(intent in intents for intent in ("workout_decision", "daily_plan", "active_workout")):
        wanted_ids.extend(["spo2", "respiratory_rate", "sleep_temperature", "vo2_max", "active_zone_minutes"])
    if "general_overview" in intents:
        wanted_ids.extend(["spo2", "respiratory_rate", "sleep_temperature", "vo2_max", "heart_rate_zones"])
    wanted = set(wanted_ids)
    lines: list[str] = []
    for signal in signals:
        if signal.get("id") not in wanted:
            continue
        display = signal.get("display")
        if not display:
            continue
        lines.append(
            f"{signal.get('label')}: latest {display}. {signal.get('coaching_use')}"
        )
        if len(lines) >= 5:
            break
    return lines


def _question_safety_flags(question: str, context: dict[str, Any]) -> list[str]:
    text = question.lower()
    flags: list[str] = []
    urgent_terms = (
        "chest pain",
        "shortness of breath",
        "trouble breathing",
        "faint",
        "fainting",
        "dizzy",
        "dizziness",
        "palpitation",
        "palpitations",
        "irregular",
        "arrhythmia",
    )
    concern_terms = (
        "should i worry",
        "worried",
        "concerning",
        "concerned",
        "abnormal",
        "too high",
        "heart rate high",
        "high heart rate",
        "pulse high",
    )
    if any(term in text for term in urgent_terms):
        flags.append(
            "The question mentions symptoms or heart concerns that need medical caution; do not diagnose from wearable data and recommend urgent care for severe, new, or worsening symptoms."
        )
    elif any(term in text for term in concern_terms):
        flags.append(
            "Treat this as a health-safety question, not only a fitness question; explain wearable limits and suggest clinical advice for persistent or concerning heart-rate changes."
        )

    resting_hr = context.get("today", {}).get("resting_heart_rate")
    if resting_hr is not None and resting_hr >= 90:
        flags.append(
            f"Latest resting heart rate is high at {resting_hr} bpm, so avoid hard training advice without caution and context."
        )
    return _dedupe(flags)


def _question_illness_flags(question: str, personal_context: dict[str, Any]) -> list[str]:
    notes = " ".join(
        str((item.get("checkin") or {}).get(key) or "")
        for item in personal_context.get("recent_checkins") or []
        for key in ("notes", "symptoms", "illness")
    )
    text = f"{question} {notes}".lower()
    if any(_has_unnegated_phrase(text, phrase) for phrase in ILLNESS_PHRASES):
        return [
            "Illness symptoms are present in the question or recent check-in; avoid hard training advice and suggest rest or very easy movement unless symptoms are mild and improving."
        ]
    return []


def _has_unnegated_phrase(text: str, phrase: str) -> bool:
    for match in re.finditer(rf"\b{re.escape(phrase)}\b", text):
        prefix = text[max(0, match.start() - 28) : match.start()]
        if re.search(r"\b(no|not|without|denies|deny|none)\b[\s,;:.-]{0,12}$", prefix):
            continue
        return True
    return False


def _question_clue_headline(
    intents: list[str],
    context: dict[str, Any],
    comparison: dict[str, Any],
) -> str:
    readiness = context.get("readiness", {})
    if "daily_plan" in intents:
        return f"Use the daily brief, readiness {readiness.get('score', '?')}/100, goals, and check-ins to choose today's plan."
    if comparison.get("status") == "ok" and any(intent in intents for intent in ("recovery", "sleep", "heart")):
        return comparison.get("headline", "Sleep, heart, and load signals are ready to compare.")
    if "workout_decision" in intents:
        return f"Use readiness {readiness.get('score', '?')}/100 plus sleep, HRV, resting HR, load, goals, and check-ins."
    return "Use the synced Fitbit metric catalog plus overview context to choose the right follow-up tools."


def _compact_today_context(today: dict[str, Any]) -> dict[str, Any]:
    sleep = today.get("sleep", {})
    return {
        "activity_date": today.get("activity_date"),
        "recovery_date": today.get("recovery_date"),
        "steps": today.get("steps"),
        "active_minutes": today.get("active_minutes"),
        "active_zone_minutes": today.get("active_zone_minutes"),
        "sleep_hours": sleep.get("asleep_hours") or sleep.get("duration_hours"),
        "sleep_sessions": sleep.get("sessions_count"),
        "hrv_ms": today.get("hrv_ms"),
        "resting_heart_rate": today.get("resting_heart_rate"),
        "spo2_avg": today.get("spo2_avg") or (today.get("spo2_sample") or {}).get("avg"),
        "respiratory_rate": today.get("respiratory_rate")
        or (today.get("respiratory_rate_sleep") or {}).get("full_sleep_breaths_per_minute"),
        "sleep_temperature": today.get("sleep_temperature"),
        "vo2_max": today.get("vo2_max"),
        "heart": today.get("heart"),
        "latest_training_load": today.get("latest_training_load"),
    }


def _compact_overview_context(overview: dict[str, Any]) -> dict[str, Any]:
    if overview.get("status") != "ok":
        return {"status": overview.get("status"), "message": overview.get("message")}
    sections = overview.get("sections", {})
    return {
        "status": "ok",
        "headline": overview.get("headline"),
        "daily_brief": overview.get("daily_brief"),
        "date_range": overview.get("date_range"),
        "activity": sections.get("activity"),
        "sleep": sections.get("sleep"),
        "heart": sections.get("heart"),
        "recovery": sections.get("recovery"),
        "workouts": sections.get("workouts"),
        "personal_context": overview.get("personal_context"),
        "data_coverage": overview.get("data_coverage"),
        "available_signal_summary": _compact_signal_snapshot_reference(
            overview.get("available_signal_snapshot")
        ),
    }


def _compact_recovery_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    if comparison.get("status") != "ok":
        return {"status": comparison.get("status"), "message": comparison.get("message")}
    return {
        "status": "ok",
        "headline": comparison.get("headline"),
        "latest": comparison.get("latest"),
        "baseline": comparison.get("baseline"),
        "current_vs_baseline": comparison.get("current_vs_baseline"),
        "correlations": comparison.get("correlations"),
        "insights": comparison.get("insights"),
        "watchouts": comparison.get("watchouts"),
        "positives": comparison.get("positives"),
        "available_signal_summary": _compact_signal_snapshot_reference(
            comparison.get("available_signal_snapshot")
        ),
    }


def _compact_signal_snapshot_reference(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = snapshot or {}
    return {
        "status": snapshot.get("status"),
        "window_days": snapshot.get("window_days"),
        "date_range": snapshot.get("date_range"),
        "available_signal_ids": snapshot.get("available_signal_ids", []),
        "available_categories": snapshot.get("available_categories", []),
        "signal_count": len(snapshot.get("signals") or []),
    }


def _overview_workouts(records: list[dict[str, Any]]) -> dict[str, Any]:
    workouts = []
    for item in records:
        exercise = item["payload"].get("exercise", {})
        interval = exercise.get("interval", {})
        duration_minutes = _duration_minutes(exercise.get("activeDuration"))
        if duration_minutes is not None and duration_minutes < 2:
            continue
        workouts.append(
            {
                "date": item["observed_date"],
                "type": exercise.get("exerciseType"),
                "display_name": exercise.get("displayName"),
                "start_time": interval.get("startTime"),
                "duration_minutes": duration_minutes,
                "active_zone_minutes": _int(exercise.get("metricsSummary", {}), ["activeZoneMinutes"]),
                "average_heart_rate": exercise.get("metricsSummary", {}).get(
                    "averageHeartRateBeatsPerMinute"
                ),
            }
        )
    hardest = max(
        workouts,
        key=lambda item: (item.get("active_zone_minutes") or 0, item.get("average_heart_rate") or 0),
        default=None,
    )
    return {
        "status": "ok" if workouts else "missing",
        "workout_count": len(workouts),
        "recent": workouts[:10],
        "hardest_workout": hardest,
    }


def _overview_coaching(
    context: dict[str, Any],
    activity: dict[str, Any],
    sleep: dict[str, Any],
    heart: dict[str, Any],
    recovery: dict[str, Any],
    workouts: dict[str, Any],
    goal: dict[str, Any] | None,
    checkins: list[dict[str, Any]],
    freshness: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    readiness = context["readiness"]
    today = context.get("today", {})
    label = readiness.get("label")
    positives: list[str] = []
    watchouts: list[str] = []
    next_actions: list[str] = []
    freshness = freshness or {}

    if freshness.get("freshness_level") == "stale":
        watchouts.append(
            f"Synced data may be stale: latest observed date is {freshness.get('latest_observed_date') or context.get('latest_date')}."
        )
        next_actions.append("Run sync_latest_fitbit_data before time-sensitive workout decisions.")
    elif freshness.get("freshness_level") == "aging":
        watchouts.append("Data is from today, but the last sync is aging.")
        next_actions.append("Sync latest Fitbit data before making a hard training call.")

    if label == "green":
        positives.append(f"Readiness is green at {readiness.get('score')}/100.")
        next_actions.append("A normal session is reasonable if warm-up movement feels good.")
    elif label == "yellow":
        watchouts.append(f"Readiness is yellow at {readiness.get('score')}/100.")
        next_actions.append("Keep training controlled: technique, zone 2, or submax strength.")
    else:
        watchouts.append(f"Readiness is red at {readiness.get('score')}/100.")
        next_actions.append("Bias toward recovery, mobility, walking, and earlier sleep.")

    latest_sleep = sleep.get("latest_asleep_hours")
    if latest_sleep is not None:
        if latest_sleep >= 7:
            positives.append(f"Latest sleep is supportive at {latest_sleep:.1f}h.")
        elif latest_sleep < 6:
            watchouts.append(f"Latest sleep is short at {latest_sleep:.1f}h.")
            next_actions.append("Avoid stacking high-intensity work on short sleep.")
    if sleep.get("latest_vs_average_hours") is not None:
        delta = sleep["latest_vs_average_hours"]
        if delta >= 0.5:
            positives.append(f"Sleep is {delta:.1f}h above your recent average.")
        elif delta <= -0.5:
            watchouts.append(f"Sleep is {abs(delta):.1f}h below your recent average.")

    latest_load = today.get("latest_training_load", {})
    if latest_load.get("active_zone_minutes", 0) > 45:
        watchouts.append(
            f"Recent training load is high: {latest_load['active_zone_minutes']} zone minutes on {latest_load.get('date')}."
        )
        next_actions.append("Do not add another max-effort conditioning block today.")
    elif activity.get("totals", {}).get("active_zone_minutes", 0) > 0:
        positives.append(
            f"Recent activity load is visible: {activity['totals']['active_zone_minutes']:.0f} zone minutes in the window."
        )

    if heart.get("latest_hrv_ms") and heart.get("average_hrv_ms"):
        if heart["latest_hrv_ms"] >= heart["average_hrv_ms"] * 1.05:
            positives.append("HRV is running above the recent average.")
        elif heart["latest_hrv_ms"] < heart["average_hrv_ms"] * 0.9:
            watchouts.append("HRV is running below the recent average.")
    if heart.get("latest_resting_heart_rate") and heart.get("average_resting_heart_rate"):
        if heart["latest_resting_heart_rate"] > heart["average_resting_heart_rate"] + 5:
            watchouts.append("Resting heart rate is elevated versus the recent average.")
        else:
            positives.append("Resting heart rate is not elevated versus the recent average.")

    if recovery.get("latest_spo2"):
        positives.append(f"Latest SpO2 is {recovery['latest_spo2']:.1f}% as context, not a standalone training signal.")
    if recovery.get("latest_respiratory_rate"):
        positives.append(f"Latest respiratory rate is {recovery['latest_respiratory_rate']:.1f} breaths/min.")
    sleep_temp = recovery.get("latest_sleep_temperature") or {}
    if sleep_temp.get("delta_celsius") is not None:
        delta = sleep_temp["delta_celsius"]
        if abs(delta) >= 0.6:
            watchouts.append(f"Sleep temperature is {delta:+.2f} C versus baseline.")
        else:
            positives.append(f"Sleep temperature is {delta:+.2f} C versus baseline.")
    if recovery.get("latest_vo2_max") is not None:
        positives.append(f"VO2 max is available at {recovery['latest_vo2_max']:.1f} ml/kg/min for capacity context.")
    if workouts.get("workout_count"):
        positives.append(f"{workouts['workout_count']} workout sessions are available in this window.")

    soreness = _rating_from_checkins(checkins, "soreness")
    energy = _rating_from_checkins(checkins, "energy")
    if soreness and soreness >= 5:
        watchouts.append(f"Your latest soreness check-in is {soreness}/10.")
        next_actions.append("Choose exercises that avoid sore areas unless warm-up pain stays under 3/10.")
    if energy and energy <= 4:
        watchouts.append(f"Your latest energy check-in is low at {energy}/10.")
    if energy and energy >= 7:
        positives.append(f"Your latest energy check-in is strong at {energy}/10.")

    goal_text = (goal or {}).get("goal", {}).get("target")
    if goal_text:
        next_actions.append(f"Keep the plan aligned with your goal: {goal_text}.")

    if not positives:
        positives.append("Enough synced data is present to produce a personalized overview.")
    if not watchouts:
        watchouts.append("No major recovery red flags were detected in the synced window.")
    next_actions.append("Ask for a specific workout plan before training so the assistant can factor in soreness and constraints.")
    return _dedupe(positives), _dedupe(watchouts), _dedupe(next_actions)


def _daily_coaching_brief(
    *,
    context: dict[str, Any],
    activity: dict[str, Any],
    sleep: dict[str, Any],
    heart: dict[str, Any],
    recovery: dict[str, Any],
    workouts: dict[str, Any],
    goal: dict[str, Any] | None,
    checkins: list[dict[str, Any]],
    freshness: dict[str, Any],
    positives: list[str],
    watchouts: list[str],
    next_actions: list[str],
) -> dict[str, Any]:
    readiness = context["readiness"]
    label = readiness.get("label")
    score = readiness.get("score")
    priority_signals: list[dict[str, Any]] = []
    context_gaps: list[str] = []

    def add_signal(category: str, label_text: str, detail: str, impact: str, status: str) -> None:
        if detail:
            priority_signals.append(
                {
                    "category": category,
                    "label": label_text,
                    "detail": detail,
                    "impact": impact,
                    "status": status,
                }
            )

    if freshness.get("freshness_level") in {"aging", "stale"}:
        add_signal(
            "freshness",
            "Data freshness",
            f"{freshness.get('freshness_label') or freshness.get('freshness_level')} from {freshness.get('latest_observed_date')}.",
            freshness.get("recommendation") or "Sync before time-sensitive coaching.",
            "watchout",
        )

    add_signal(
        "readiness",
        "Readiness",
        f"{str(label or 'pending').title()} at {score}/100.",
        readiness.get("recommendation") or "Use readiness as the starting point, then adjust for symptoms and goals.",
        "positive" if label == "green" else "watchout" if label == "red" else "context",
    )

    latest_sleep = sleep.get("latest_asleep_hours")
    sleep_delta = sleep.get("latest_vs_average_hours")
    if latest_sleep is not None:
        if sleep_delta is not None:
            direction = "above" if sleep_delta >= 0 else "below"
            detail = f"{latest_sleep:.1f}h, {abs(sleep_delta):.1f}h {direction} recent average."
        else:
            detail = f"{latest_sleep:.1f}h latest sleep."
        add_signal(
            "sleep",
            "Sleep",
            detail,
            "Short sleep should cap intensity; supportive sleep gives more room to train.",
            "positive" if latest_sleep >= 7 else "watchout" if latest_sleep < 6 else "context",
        )

    hrv = heart.get("latest_hrv_ms")
    avg_hrv = heart.get("average_hrv_ms")
    if hrv is not None:
        if avg_hrv:
            delta = round(((hrv - avg_hrv) / avg_hrv) * 100)
            detail = f"{hrv:.1f} ms, {abs(delta)}% {'above' if delta >= 0 else 'below'} recent average."
            status = "positive" if delta >= 5 else "watchout" if delta <= -10 else "context"
        else:
            detail = f"{hrv:.1f} ms latest HRV."
            status = "context"
        add_signal("heart", "HRV", detail, "HRV helps explain recovery pressure and training readiness.", status)

    resting_hr = heart.get("latest_resting_heart_rate")
    avg_resting_hr = heart.get("average_resting_heart_rate")
    if resting_hr is not None:
        if avg_resting_hr:
            delta = round(resting_hr - avg_resting_hr, 1)
            detail = f"{resting_hr} bpm, {abs(delta):.1f} bpm {'above' if delta >= 0 else 'below'} recent average."
            status = "watchout" if delta > 5 else "positive"
        else:
            detail = f"{resting_hr} bpm latest resting heart rate."
            status = "context"
        add_signal(
            "heart",
            "Resting HR",
            detail,
            "Elevated resting HR can point to stress, illness, fatigue, or under-recovery.",
            status,
        )

    latest_load = context.get("today", {}).get("latest_training_load") or activity.get("highest_load_day") or {}
    load_minutes = latest_load.get("active_zone_minutes")
    if load_minutes is not None:
        add_signal(
            "activity",
            "Training load (AZM)",
            f"{load_minutes} Active Zone Minutes on {latest_load.get('date') or 'latest load day'}.",
            "AZM are Fitbit hard-work minutes; high recent load should reduce extra intensity.",
            "watchout" if load_minutes > 45 else "context",
        )

    energy = _rating_from_checkins(checkins, "energy")
    soreness = _rating_from_checkins(checkins, "soreness")
    stress = _rating_from_checkins(checkins, "stress")
    if not checkins:
        context_gaps.append(
            "No recent subjective check-in is logged; ask for energy, soreness, stress, pain, or illness before hard training."
        )
    elif energy is None or soreness is None or stress is None:
        context_gaps.append(
            "Recent check-ins are missing energy, soreness, or stress, so subjective readiness is incomplete."
        )
    if energy is not None:
        add_signal(
            "checkin",
            "Energy",
            f"{energy}/10 latest check-in.",
            "Self-reported energy should confirm or soften the wearable-based plan.",
            "positive" if energy >= 7 else "watchout" if energy <= 4 else "context",
        )
    if soreness is not None:
        add_signal(
            "checkin",
            "Soreness",
            f"{soreness}/10 latest check-in.",
            "Soreness should shape exercise choice and loading, especially for specific body areas.",
            "watchout" if soreness >= 5 else "positive",
        )
    if stress is not None:
        add_signal(
            "checkin",
            "Stress",
            f"{stress}/10 latest check-in.",
            "High stress should keep the session predictable and away from all-out work.",
            "watchout" if stress >= 7 else "context",
        )

    goal_payload = (goal or {}).get("goal") or {}
    days_per_week = goal_payload.get("days_per_week")
    if not goal_payload:
        context_gaps.append("No coaching goal is saved; set a weekly goal to make recommendations more targeted.")
    if days_per_week is not None:
        try:
            target_sessions = max(0, int(days_per_week))
            workout_count = int(workouts.get("workout_count") or 0)
            remaining = max(0, target_sessions - workout_count)
            add_signal(
                "goal",
                "Goal progress",
                f"{workout_count}/{target_sessions} workout sessions logged; {remaining} remaining.",
                "Use the goal as pressure only after recovery and safety signals are considered.",
                "positive" if remaining == 0 else "context",
            )
        except (TypeError, ValueError):
            pass
    elif goal_payload.get("target"):
        add_signal(
            "goal",
            "Current goal",
            str(goal_payload["target"]),
            "Keep recommendations aligned with this goal.",
            "context",
        )

    if sleep.get("status") != "ok":
        context_gaps.append("Sleep data is missing in this window, so recovery confidence is lower.")
    if heart.get("status") != "ok":
        context_gaps.append("Heart recovery data is missing in this window, so HRV/resting-HR context is unavailable.")
    if activity.get("status") != "ok":
        context_gaps.append("Activity/load data is missing in this window, so training-load context is limited.")

    if recovery.get("latest_spo2") is not None:
        add_signal(
            "recovery",
            "SpO2",
            f"{recovery['latest_spo2']:.1f}% latest average.",
            "Use alongside respiratory and heart signals, not as a standalone diagnosis.",
            "context",
        )
    if recovery.get("latest_respiratory_rate") is not None:
        add_signal(
            "recovery",
            "Respiratory rate",
            f"{recovery['latest_respiratory_rate']:.1f} breaths/min latest.",
            "Use against your usual breathing rate; elevated values can support a controlled training call.",
            "context",
        )
    sleep_temp = recovery.get("latest_sleep_temperature") or {}
    if sleep_temp.get("delta_celsius") is not None:
        delta = sleep_temp["delta_celsius"]
        add_signal(
            "recovery",
            "Sleep temperature",
            f"{delta:+.2f} C versus baseline.",
            "Temperature deviation can be a stress or illness clue, but it is not diagnostic.",
            "watchout" if abs(delta) >= 0.6 else "context",
        )
    if recovery.get("latest_vo2_max") is not None:
        add_signal(
            "capacity",
            "VO2 max",
            f"{recovery['latest_vo2_max']:.1f} ml/kg/min latest.",
            "Use for endurance capacity and progress, not same-day readiness.",
            "context",
        )

    if freshness.get("needs_sync_before_time_sensitive_advice"):
        training_bias = "sync-first"
        summary = "Sync first before a time-sensitive training decision; use the stored overview only as background."
    elif label == "green":
        training_bias = "train-ready"
        summary = "Training is available today if warm-up movement and symptoms agree."
    elif label == "yellow":
        training_bias = "controlled"
        summary = "A controlled session is the smart default: useful work without chasing max effort."
    else:
        training_bias = "recovery-first"
        summary = "Make today recovery-first unless there is a strong non-negotiable reason to train hard."

    if watchouts:
        summary = f"{summary} Main constraint: {watchouts[0]}"
    elif positives:
        summary = f"{summary} Main support: {positives[0]}"

    prompt_suggestions = [
        "What should I focus on today based on my data?",
        "Can I train hard today, or should I keep it controlled?",
        "I only have 30 minutes. What is the best use of it?",
        "What are the main reasons behind today's plan?",
    ]
    if training_bias in {"controlled", "recovery-first"}:
        prompt_suggestions.append("I feel off but still want to move. What is the safest useful option?")
    if not checkins or energy is None or soreness is None or stress is None:
        prompt_suggestions.append("Log how my energy, soreness, and stress feel right now.")
    if not goal_payload:
        prompt_suggestions.append("Help me set a simple weekly fitness goal.")
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        prompt_suggestions.insert(0, "Sync my latest Fitbit data before you answer.")
    if soreness is not None and soreness >= 5:
        prompt_suggestions.append("My body feels sore. Plan around that.")

    section_count = sum(
        1
        for section in (activity, sleep, heart, recovery, workouts)
        if section.get("status") == "ok"
    )
    if freshness.get("freshness_level") == "stale" or section_count < 2:
        confidence = "low"
    elif freshness.get("freshness_level") == "aging" or section_count < 4:
        confidence = "moderate"
    else:
        confidence = "high"

    return {
        "summary": summary,
        "training_bias": training_bias,
        "today_plan": _dedupe(next_actions)[:5],
        "priority_signals": priority_signals[:14],
        "context_gaps": _dedupe(context_gaps)[:5],
        "prompt_suggestions": _dedupe(prompt_suggestions)[:6],
        "confidence": confidence,
        "data_used": {
            "activity_date": context.get("activity_date"),
            "recovery_date": context.get("recovery_date"),
            "freshness_level": freshness.get("freshness_level"),
            "sections_with_data": section_count,
        },
    }


def _overview_headline(
    readiness: dict[str, Any],
    sleep: dict[str, Any],
    activity: dict[str, Any],
    heart: dict[str, Any],
) -> str:
    parts = [f"{str(readiness.get('label', 'pending')).title()} readiness at {readiness.get('score')}/100"]
    if sleep.get("latest_asleep_hours") is not None:
        parts.append(f"{sleep['latest_asleep_hours']:.1f}h latest sleep")
    if activity.get("totals", {}).get("active_zone_minutes") is not None:
        parts.append(f"{activity['totals']['active_zone_minutes']:.0f} zone minutes")
    if heart.get("latest_hrv_ms") is not None:
        parts.append(f"{heart['latest_hrv_ms']:.1f} ms HRV")
    return "; ".join(parts) + "."


def _last_with(daily_rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any] | None:
    for day in reversed(daily_rows):
        if any(day.get(key) is not None for key in keys):
            return day
    return None


def _latest_number(daily_rows: list[dict[str, Any]], key: str) -> float | None:
    latest = _last_with(daily_rows, (key,))
    if not latest:
        return None
    return _float({"value": latest.get(key)}, ["value"])


def _round_optional(value: Any, digits: int = 1) -> float | int | None:
    if value is None:
        return None
    try:
        rounded = round(float(value), digits)
    except (TypeError, ValueError):
        return None
    if digits == 0 or float(rounded).is_integer():
        return int(rounded)
    return rounded


def _format_signal_value(value: Any, unit: str = "") -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        text = f"{value:.1f}" if not value.is_integer() else str(int(value))
    else:
        text = str(value)
    return f"{text} {unit}".strip()


def _sleep_temperature_display(temp: dict[str, Any]) -> str | None:
    if not temp:
        return None
    delta = temp.get("delta_celsius")
    nightly = temp.get("nightly_celsius")
    if delta is not None:
        return f"{delta:+.2f} C vs baseline"
    if nightly is not None:
        return f"{nightly:.2f} C nightly"
    return None


def _sum_daily_mapping(daily_rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for day in daily_rows:
        for name, amount in (day.get(key) or {}).items():
            totals[str(name)] += _float({"value": amount}, ["value"])
    return {name: round(amount, 1) for name, amount in sorted(totals.items()) if amount}


def _format_minutes_mapping(values: dict[str, float]) -> str | None:
    if not values:
        return None
    parts = [f"{name.replace('_', ' ')} {amount:g}m" for name, amount in values.items()]
    return ", ".join(parts[:4])


def _date_from_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def _datetime_from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _average(values: list[Any]) -> float | None:
    usable = [number for value in values if (number := _number_or_none(value)) is not None and number > 0]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 2)


def _number_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _delta(current: Any, baseline: Any) -> float | None:
    current_number = _number_or_none(current)
    baseline_number = _number_or_none(baseline)
    if current_number is None or baseline_number is None:
        return None
    return round(current_number - baseline_number, 2)


def _percent_delta(current: Any, baseline: Any) -> float | None:
    current_number = _number_or_none(current)
    baseline_number = _number_or_none(baseline)
    if current_number is None or baseline_number in (None, 0):
        return None
    return round(((current_number - baseline_number) / baseline_number) * 100, 1)


def _pearson(pairs: list[tuple[Any, Any]]) -> float | None:
    usable = [
        (x_number, y_number)
        for x, y in pairs
        if (x_number := _number_or_none(x)) is not None and (y_number := _number_or_none(y)) is not None
    ]
    if len(usable) < 3:
        return None
    xs = [x for x, _ in usable]
    ys = [y for _, y in usable]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in usable)
    denominator_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denominator_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denominator_x == 0 or denominator_y == 0:
        return None
    return round(numerator / (denominator_x * denominator_y), 3)


def _stage_averages(sleep_days: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for day in sleep_days:
        for stage, minutes in day.get("sleep", {}).get("stages_minutes", {}).items():
            totals[stage] += _float({"value": minutes}, ["value"])
            counts[stage] += 1
    return {stage: round(total / counts[stage], 1) for stage, total in sorted(totals.items()) if counts[stage]}


def _rating_from_checkins(checkins: list[dict[str, Any]], key: str) -> int | None:
    for item in checkins:
        value = item.get("checkin", {}).get(key)
        if value is None:
            continue
        try:
            return max(1, min(10, int(value)))
        except (TypeError, ValueError):
            continue
    return None


def _latest_checkin_note(checkins: list[dict[str, Any]]) -> str | None:
    for item in checkins:
        note = str(item.get("checkin", {}).get("notes") or "").strip()
        if note:
            return note[:180]
    return None


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    daily: dict[str, dict[str, Any]] = defaultdict(dict)
    heart_samples: dict[str, list[float]] = defaultdict(list)
    hrv_samples: dict[str, list[float]] = defaultdict(list)
    spo2_samples: dict[str, list[float]] = defaultdict(list)
    compact_summary_days = {
        (item["data_type"], item["observed_date"] or observed_date(item["payload"]))
        for item in records
        if _uses_compact_sync_storage(item["data_type"])
        and _is_compact_sync_summary(item["payload"])
        and (item["observed_date"] or observed_date(item["payload"]))
    }

    for item in records:
        payload = item["payload"]
        day = item["observed_date"] or observed_date(payload)
        if not day:
            continue
        data_type = item["data_type"]
        if (
            _uses_compact_sync_storage(data_type)
            and not _is_compact_sync_summary(payload)
            and (data_type, day) in compact_summary_days
        ):
            continue
        values = daily[day]
        if data_type in {"steps", "steps-daily-summary"}:
            values["steps"] = values.get("steps", 0) + _int(payload, ["steps", "count"])
        elif data_type in {"active-zone-minutes", "active-zone-minutes-daily-summary"}:
            values["active_zone_minutes"] = values.get("active_zone_minutes", 0) + _int(
                payload, ["activeZoneMinutes", "activeZoneMinutes"]
            )
        elif data_type in {"active-minutes", "active-minutes-daily-summary"}:
            values["active_minutes"] = values.get("active_minutes", 0) + sum(
                _int(part, ["activeMinutes"])
                for part in payload.get("activeMinutes", {}).get("activeMinutesByActivityLevel", [])
            )
        elif data_type in {"distance", "distance-daily-summary"}:
            values["distance_mm"] = values.get("distance_mm", 0) + _int(payload, ["distance", "millimeters"])
        elif data_type in {"active-energy-burned", "active-energy-burned-daily-summary"}:
            values["active_kcal"] = values.get("active_kcal", 0.0) + _float(
                payload, ["activeEnergyBurned", "kcal"]
            )
        elif data_type == "total-calories":
            values["total_kcal"] = _float(payload, ["totalCalories", "kcalSum"])
        elif data_type == "heart-rate":
            heart_rate = payload.get("heartRate", {})
            sample_summary = heart_rate.get("summary", {})
            if sample_summary:
                avg_bpm = _float(sample_summary, ["averageBeatsPerMinute"]) or _float(
                    heart_rate,
                    ["beatsPerMinute"],
                )
                values["heart"] = {
                    "avg_bpm": round(avg_bpm, 1) if avg_bpm else None,
                    "min_bpm": _round_number(_float(sample_summary, ["minBeatsPerMinute"])),
                    "max_bpm": _round_number(_float(sample_summary, ["maxBeatsPerMinute"])),
                    "samples": _int(sample_summary, ["samples"]) or 1,
                }
            elif bpm := _float(payload, ["heartRate", "beatsPerMinute"]):
                heart_samples[day].append(bpm)
        elif data_type == "heart-rate-variability":
            hrv_payload = payload.get("heartRateVariability", {})
            sample_summary = hrv_payload.get("summary", {})
            if sample_summary:
                values["hrv_sample_ms"] = {
                    "avg": round(_float(sample_summary, ["averageMilliseconds"]), 1),
                    "min": round(_float(sample_summary, ["minMilliseconds"]), 1),
                    "max": round(_float(sample_summary, ["maxMilliseconds"]), 1),
                    "samples": _int(sample_summary, ["samples"]) or 1,
                }
            elif hrv := _float(
                payload,
                ["heartRateVariability", "rootMeanSquareOfSuccessiveDifferencesMilliseconds"],
            ):
                hrv_samples[day].append(hrv)
        elif data_type == "daily-resting-heart-rate":
            values["resting_heart_rate"] = _int(payload, ["dailyRestingHeartRate", "beatsPerMinute"])
        elif data_type == "daily-heart-rate-variability":
            values["hrv_ms"] = _float(
                payload,
                ["dailyHeartRateVariability", "averageHeartRateVariabilityMilliseconds"],
            )
        elif data_type == "daily-oxygen-saturation":
            values["spo2_avg"] = _float(payload, ["dailyOxygenSaturation", "averagePercentage"])
        elif data_type == "oxygen-saturation":
            spo2_payload = payload.get("oxygenSaturation", {})
            sample_summary = spo2_payload.get("summary", {})
            if sample_summary:
                values["spo2_sample"] = {
                    "avg": round(_float(sample_summary, ["averagePercentage"]), 1),
                    "min": round(_float(sample_summary, ["minPercentage"]), 1),
                    "max": round(_float(sample_summary, ["maxPercentage"]), 1),
                    "samples": _int(sample_summary, ["samples"]) or 1,
                }
            elif spo2 := _float(payload, ["oxygenSaturation", "percentage"]):
                spo2_samples[day].append(spo2)
        elif data_type == "daily-respiratory-rate":
            values["respiratory_rate"] = _float(payload, ["dailyRespiratoryRate", "breathsPerMinute"])
        elif data_type == "respiratory-rate-sleep-summary":
            summary = payload.get("respiratoryRateSleepSummary", {})
            full_stats = _sleep_resp_stats(summary, "fullSleepStats")
            stage_stats = {
                "deep": _sleep_resp_stats(summary, "deepSleepStats"),
                "light": _sleep_resp_stats(summary, "lightSleepStats"),
                "rem": _sleep_resp_stats(summary, "remSleepStats"),
            }
            if full_stats:
                values["respiratory_rate_sleep"] = {
                    "full_sleep_breaths_per_minute": full_stats.get("breaths_per_minute"),
                    "full_sleep_signal_to_noise": full_stats.get("signal_to_noise"),
                    "stages": {stage: stats for stage, stats in stage_stats.items() if stats},
                }
                if values.get("respiratory_rate") is None:
                    values["respiratory_rate"] = full_stats.get("breaths_per_minute")
        elif data_type == "daily-sleep-temperature-derivations":
            temp = payload.get("dailySleepTemperatureDerivations", {})
            nightly = _first_float(
                temp,
                ("nightlyTemperatureCelsius", "nightly_temperature_celsius"),
            )
            baseline = _first_float(
                temp,
                ("baselineTemperatureCelsius", "baseline_temperature_celsius"),
            )
            relative_stddev = _first_float(
                temp,
                (
                    "relativeNightlyStddev30dCelsius",
                    "relative_nightly_stddev_30d_celsius",
                ),
            )
            if nightly is not None or baseline is not None or relative_stddev is not None:
                values["sleep_temperature"] = {
                    "nightly_celsius": _round_optional(nightly, 2),
                    "baseline_celsius": _round_optional(baseline, 2),
                    "delta_celsius": _round_optional(nightly - baseline, 2)
                    if nightly is not None and baseline is not None
                    else None,
                    "relative_nightly_stddev_30d_celsius": _round_optional(relative_stddev, 2),
                }
        elif data_type == "daily-vo2-max":
            vo2_payload = payload.get("dailyVo2Max", {})
            vo2 = _first_float(
                vo2_payload,
                ("vo2Max", "vo2_max", "millilitersPerMinuteKilogram"),
            )
            if vo2 is not None:
                values["vo2_max"] = vo2
                values["vo2_max_detail"] = {
                    "vo2_max": _round_optional(vo2, 1),
                    "estimated": vo2_payload.get("estimated"),
                    "cardio_fitness_level": vo2_payload.get("cardioFitnessLevel")
                    or vo2_payload.get("cardio_fitness_level"),
                    "vo2_max_covariance": _round_optional(
                        _first_float(vo2_payload, ("vo2MaxCovariance", "vo2_max_covariance")),
                        2,
                    ),
                }
        elif data_type == "floors":
            values["floors"] = values.get("floors", 0) + _int(payload, ["floors", "countSum"])
        elif data_type == "activity-level":
            level = payload.get("activityLevel", {}).get("activityLevelType", "UNKNOWN").lower()
            minutes = _interval_minutes(payload.get("activityLevel", {}))
            levels = values.setdefault("activity_levels_minutes", defaultdict(float))
            levels[level] += minutes
        elif data_type == "activity-level-daily-summary":
            levels = values.setdefault("activity_levels_minutes", defaultdict(float))
            for level, minutes in payload.get("activityLevel", {}).get(
                "activityLevelsMinutes",
                {},
            ).items():
                levels[str(level).lower()] += _float({"value": minutes}, ["value"])
        elif data_type == "sedentary-period":
            values["sedentary_minutes"] = values.get("sedentary_minutes", 0.0) + _interval_minutes(
                payload.get("sedentaryPeriod", {})
            )
        elif data_type == "time-in-heart-rate-zone":
            zone = payload.get("timeInHeartRateZone", {}).get("heartRateZoneType", "UNKNOWN").lower()
            minutes = _interval_minutes(payload.get("timeInHeartRateZone", {}))
            zones = values.setdefault("time_in_hr_zones_minutes", defaultdict(float))
            zones[zone] += minutes
        elif data_type == "time-in-heart-rate-zone-daily-summary":
            zones = values.setdefault("time_in_hr_zones_minutes", defaultdict(float))
            for zone, minutes in payload.get("timeInHeartRateZone", {}).get(
                "heartRateZonesMinutes",
                {},
            ).items():
                zones[str(zone).lower()] += _float({"value": minutes}, ["value"])
        elif data_type == "calories-in-heart-rate-zone":
            zones = values.setdefault("calories_in_hr_zones_kcal", defaultdict(float))
            for zone in payload.get("caloriesInHeartRateZone", {}).get("caloriesInHeartRateZones", []):
                zones[zone.get("heartRateZone", "UNKNOWN").lower()] += _float(zone, ["kcal"])
        elif data_type == "sleep":
            sessions = values.setdefault("sleep_sessions", [])
            sessions.append(sleep_summary(payload))
            values["sleep"] = aggregate_sleep_sessions(sessions)

    for day, samples in heart_samples.items():
        if samples:
            daily[day]["heart"] = {
                "avg_bpm": round(sum(samples) / len(samples), 1),
                "min_bpm": min(samples),
                "max_bpm": max(samples),
                "samples": len(samples),
            }
    for day, samples in hrv_samples.items():
        if samples and "hrv_ms" not in daily[day]:
            daily[day]["hrv_sample_ms"] = {
                "avg": round(sum(samples) / len(samples), 1),
                "min": round(min(samples), 1),
                "max": round(max(samples), 1),
                "samples": len(samples),
            }
    for day, samples in spo2_samples.items():
        if samples and "spo2_avg" not in daily[day]:
            daily[day]["spo2_sample"] = {
                "avg": round(sum(samples) / len(samples), 1),
                "min": round(min(samples), 1),
                "max": round(max(samples), 1),
                "samples": len(samples),
            }
    for values in daily.values():
        for key in ("activity_levels_minutes", "time_in_hr_zones_minutes", "calories_in_hr_zones_kcal"):
            if isinstance(values.get(key), defaultdict):
                values[key] = {zone: round(amount, 1) for zone, amount in values[key].items()}
        if values.get("sedentary_minutes") is not None:
            values["sedentary_minutes"] = round(values["sedentary_minutes"], 1)

    sorted_days = sorted(daily)
    return {
        "latest_date": sorted_days[-1] if sorted_days else None,
        "daily": dict(daily),
    }


def combine_daily_context(
    activity_day: dict[str, Any],
    recovery_day: dict[str, Any],
    activity_date: str | None,
    recovery_date: str | None,
) -> dict[str, Any]:
    combined = dict(activity_day)
    for key in ("steps", "active_zone_minutes", "active_minutes", "distance_mm", "active_kcal"):
        combined.setdefault(key, 0)
    for key in RECOVERY_KEYS:
        if key in recovery_day and key not in combined:
            combined[key] = recovery_day[key]
    combined["activity_date"] = activity_date
    combined["recovery_date"] = recovery_date
    combined["recovery_signal_source"] = (
        "same_day" if activity_date == recovery_date else "latest_completed_recovery_day"
    )
    return combined


def _context_from_summary(summary: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    daily = summary.get("daily") or {}
    latest_date = summary.get("latest_date")
    if not daily or not latest_date:
        return empty_data()

    activity_date = _latest_day_with(daily, ("steps", "active_minutes", "heart", "distance_mm"))
    activity_date = activity_date or latest_date
    recovery_date = _latest_day_with(daily, RECOVERY_KEYS) or activity_date
    activity_day = dict(daily.get(activity_date, {}))
    recovery_day = daily.get(recovery_date, {})
    today = combine_daily_context(activity_day, recovery_day, activity_date, recovery_date)
    load_date, load_minutes = _latest_load(daily, activity_date)
    today["latest_training_load"] = {
        "date": load_date,
        "active_zone_minutes": load_minutes,
    }
    readiness = readiness_from_day(today, daily)
    daily_rows = [
        {"date": day, **_public_daily_values(values)}
        for day, values in sorted(daily.items())[-14:]
    ]
    return {
        "status": "ok",
        "latest_date": latest_date,
        "activity_date": activity_date,
        "recovery_date": recovery_date,
        "readiness": readiness,
        "today": today,
        "evidence": readiness["evidence"],
        "data_coverage": data_coverage(daily),
        "data_freshness": freshness,
        "available_signal_snapshot": _available_signal_snapshot(
            daily_rows,
            lookback_days=min(14, len(daily_rows)) or None,
        ),
    }


def data_coverage(daily: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "activity_days": sum(1 for values in daily.values() if any(key in values for key in ("steps", "active_minutes", "distance_mm"))),
        "sleep_days": sum(1 for values in daily.values() if "sleep" in values),
        "heart_days": sum(1 for values in daily.values() if any(key in values for key in ("heart", "resting_heart_rate", "hrv_ms"))),
        "breathing_recovery_days": sum(
            1
            for values in daily.values()
            if any(
                key in values
                for key in (
                    "spo2_avg",
                    "spo2_sample",
                    "respiratory_rate",
                    "respiratory_rate_sleep",
                    "sleep_temperature",
                )
            )
        ),
        "capacity_days": sum(1 for values in daily.values() if "vo2_max" in values),
        "first_date": min(daily) if daily else None,
        "last_date": max(daily) if daily else None,
    }


def readiness_from_day(day: dict[str, Any], daily: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    score = 50
    evidence: list[str] = []
    daily = daily or {}
    recovery_date = day.get("recovery_date")
    activity_date = day.get("activity_date")
    sleep = day.get("sleep", {})
    sleep_hours = sleep.get("asleep_hours") or sleep.get("duration_hours")
    if sleep_hours is not None:
        if sleep_hours >= 7:
            score += 18
            evidence.append(f"Latest sleep is strong at {sleep_hours:.1f}h.")
        elif sleep_hours >= 6:
            score += 8
            evidence.append(f"Latest sleep is moderate at {sleep_hours:.1f}h.")
        else:
            score -= 15
            evidence.append(f"Latest sleep is short at {sleep_hours:.1f}h.")
    if day.get("hrv_ms"):
        hrv_baseline, hrv_baseline_days = _baseline_summary(daily, "hrv_ms", recovery_date)
        if hrv_baseline and hrv_baseline_days >= 3:
            ratio = day["hrv_ms"] / hrv_baseline
            if ratio >= 1.05:
                score += 10
                evidence.append(f"HRV is above recent baseline: {day['hrv_ms']:.1f} ms vs {hrv_baseline:.1f} ms.")
            elif ratio >= 0.9:
                score += 4
                evidence.append(f"HRV is near recent baseline: {day['hrv_ms']:.1f} ms vs {hrv_baseline:.1f} ms.")
            else:
                score -= 10
                evidence.append(f"HRV is below recent baseline: {day['hrv_ms']:.1f} ms vs {hrv_baseline:.1f} ms.")
        elif hrv_baseline_days:
            score += 6
            evidence.append(
                f"HRV is {day['hrv_ms']:.1f} ms; only {hrv_baseline_days} prior HRV "
                "day(s) are available, so the baseline trend is low confidence."
            )
        else:
            score += 6
            evidence.append(f"HRV is {day['hrv_ms']:.1f} ms.")
    if day.get("resting_heart_rate"):
        rhr_baseline, rhr_baseline_days = _baseline_summary(daily, "resting_heart_rate", recovery_date)
        if rhr_baseline and rhr_baseline_days >= 3:
            delta = day["resting_heart_rate"] - rhr_baseline
            if delta <= 2:
                score += 6
                evidence.append(f"Resting heart rate is steady: {day['resting_heart_rate']} bpm.")
            elif delta <= 5:
                evidence.append(f"Resting heart rate is slightly elevated: {day['resting_heart_rate']} bpm.")
            else:
                score -= 8
                evidence.append(f"Resting heart rate is elevated: {day['resting_heart_rate']} bpm vs {rhr_baseline:.0f} bpm baseline.")
        elif rhr_baseline_days:
            score += 4
            evidence.append(
                f"Resting heart rate is {day['resting_heart_rate']} bpm; only "
                f"{rhr_baseline_days} prior resting-heart-rate day(s) are available, so "
                "the baseline trend is low confidence."
            )
        else:
            score += 4
            evidence.append(f"Resting heart rate is {day['resting_heart_rate']} bpm.")
    respiratory_rate = day.get("respiratory_rate")
    if respiratory_rate is not None:
        resp_baseline, resp_baseline_days = _baseline_summary(daily, "respiratory_rate", recovery_date)
        if resp_baseline and resp_baseline_days >= 3:
            resp_delta = respiratory_rate - resp_baseline
            if resp_delta >= 2:
                score -= 4
                evidence.append(
                    f"Respiratory rate is elevated: {respiratory_rate:.1f} vs {resp_baseline:.1f} breaths/min baseline."
                )
            else:
                evidence.append(f"Respiratory rate is not elevated: {respiratory_rate:.1f} breaths/min.")
        else:
            evidence.append(f"Respiratory rate is {respiratory_rate:.1f} breaths/min; baseline is low confidence.")
    spo2 = day.get("spo2_avg") or (day.get("spo2_sample") or {}).get("avg")
    if spo2 is not None:
        if spo2 < 94:
            score -= 6
            evidence.append(f"SpO2 is {spo2:.1f}%, so treat oxygen context as a training caution signal.")
        else:
            evidence.append(f"SpO2 is {spo2:.1f}%; useful context, not a standalone green light.")
    sleep_temperature = day.get("sleep_temperature") or {}
    temp_delta = sleep_temperature.get("delta_celsius")
    if temp_delta is not None:
        if abs(temp_delta) >= 0.6:
            score -= 4
            evidence.append(f"Sleep temperature is {temp_delta:+.2f} C versus baseline.")
        else:
            evidence.append(f"Sleep temperature is {temp_delta:+.2f} C versus baseline.")
    load_date, load_minutes = _latest_load(daily, activity_date)
    if load_minutes > 45:
        score -= 6
        when = "today" if load_date == activity_date else f"on {load_date}"
        evidence.append(f"Recent training load is high: {load_minutes} zone minutes {when}.")
    if activity_date and recovery_date and activity_date != recovery_date:
        evidence.append(f"Recovery signals are from {recovery_date}; today's activity is still partial.")
    score = max(0, min(100, score))
    if score >= 75:
        label = "green"
        recommendation = "A normal training day is reasonable if you feel good."
    elif score >= 55:
        label = "yellow"
        recommendation = "Choose moderate cardio, technique, or strength without max efforts."
    else:
        label = "red"
        recommendation = "Prioritize recovery, mobility, walking, and sleep."
    return {
        "score": score,
        "label": label,
        "recommendation": recommendation,
        "evidence": evidence or ["Not enough synced data to personalize readiness deeply yet."],
    }


def sleep_summary(payload: dict[str, Any]) -> dict[str, Any]:
    sleep = payload.get("sleep", {})
    interval = sleep.get("interval", {})
    start = _parse_time(interval.get("startTime"))
    end = _parse_time(interval.get("endTime"))
    duration_hours = None
    if start and end:
        duration_hours = round((end - start).total_seconds() / 3600, 2)
    summary = sleep.get("summary", {})
    asleep_minutes = _float(summary, ["minutesAsleep"])
    awake_minutes = _float(summary, ["minutesAwake"])
    in_period_minutes = _float(summary, ["minutesInSleepPeriod"])
    if in_period_minutes:
        duration_hours = round(in_period_minutes / 60, 2)
    stages: dict[str, float] = defaultdict(float)
    for stage in summary.get("stagesSummary", []):
        stages[stage.get("type", "UNKNOWN").lower()] += _float(stage, ["minutes"])
    if not stages:
        for stage in sleep.get("stages", []):
            s = _parse_time(stage.get("startTime"))
            e = _parse_time(stage.get("endTime"))
            if s and e:
                stages[stage.get("type", "UNKNOWN").lower()] += (e - s).total_seconds() / 60
    return {
        "start_time": interval.get("startTime"),
        "end_time": interval.get("endTime"),
        "duration_hours": duration_hours,
        "asleep_hours": round(asleep_minutes / 60, 2) if asleep_minutes else duration_hours,
        "awake_minutes": round(awake_minutes, 1) if awake_minutes else None,
        "stages_minutes": {key: round(value, 1) for key, value in stages.items()},
    }


def aggregate_sleep_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    total_duration = 0.0
    total_asleep = 0.0
    total_awake = 0.0
    stages: dict[str, float] = defaultdict(float)
    normalized_sessions = sorted(sessions, key=lambda item: item.get("start_time") or "")
    for session in normalized_sessions:
        total_duration += _float({"value": session.get("duration_hours")}, ["value"])
        total_asleep += _float({"value": session.get("asleep_hours")}, ["value"])
        total_awake += _float({"value": session.get("awake_minutes")}, ["value"])
        for stage, minutes in session.get("stages_minutes", {}).items():
            stages[stage] += _float({"value": minutes}, ["value"])
    return {
        "duration_hours": round(total_duration, 2) if total_duration else None,
        "asleep_hours": round(total_asleep, 2) if total_asleep else None,
        "awake_minutes": round(total_awake, 1) if total_awake else None,
        "sessions_count": len(normalized_sessions),
        "sessions": normalized_sessions,
        "stages_minutes": {key: round(value, 1) for key, value in stages.items()},
    }


def observed_date(payload: dict[str, Any]) -> str | None:
    dates: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if {"year", "month", "day"}.issubset(value):
                dates.append(f"{int(value['year']):04d}-{int(value['month']):02d}-{int(value['day']):02d}")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            dates.append(value[:10])

    walk(payload)
    return sorted(dates)[0] if dates else None


AGGREGATE_SYNC_METRICS = {
    "steps",
    "active-zone-minutes",
    "active-minutes",
    "distance",
    "active-energy-burned",
    "activity-level",
    "time-in-heart-rate-zone",
}

DAILY_SAMPLE_SUMMARY_SYNC_METRICS = {
    "heart-rate",
    "heart-rate-variability",
    "oxygen-saturation",
}

SAMPLE_SYNC_METRICS: set[str] = set()


def _prepare_records_for_sync(
    metric: str,
    records: list[dict[str, Any]],
    record_limit: int,
) -> list[dict[str, Any]]:
    if not records:
        return []
    if metric in DAILY_SAMPLE_SUMMARY_SYNC_METRICS:
        return _aggregate_metric_records(metric, records)
    if metric in AGGREGATE_SYNC_METRICS:
        return _aggregate_metric_records(metric, records)
    if metric in SAMPLE_SYNC_METRICS and len(records) > record_limit:
        return _downsample_records(records, record_limit)
    if len(records) > record_limit:
        return _downsample_records(records, record_limit)
    return records


def _storage_strategy(metric: str) -> str:
    if metric in DAILY_SAMPLE_SUMMARY_SYNC_METRICS:
        return "daily_sample_summary"
    if metric in AGGREGATE_SYNC_METRICS:
        return "daily_aggregate"
    if metric in SAMPLE_SYNC_METRICS:
        return "bounded_samples"
    return "raw_bounded"


def _uses_compact_sync_storage(metric: str) -> bool:
    return metric in AGGREGATE_SYNC_METRICS or metric in DAILY_SAMPLE_SUMMARY_SYNC_METRICS


def _is_compact_sync_summary(record: dict[str, Any]) -> bool:
    return str(record.get("name") or "").startswith("summary/") and isinstance(
        record.get("summary"),
        dict,
    )


def _aggregate_metric_records(metric: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        day = observed_date(record)
        if day:
            by_day[day].append(record)

    output: list[dict[str, Any]] = []
    for day, day_records in sorted(by_day.items()):
        if metric == "steps":
            count = sum(_int(record, ["steps", "count"]) for record in day_records)
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "steps": {"count": count},
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "active-zone-minutes":
            minutes = sum(
                _int(record, ["activeZoneMinutes", "activeZoneMinutes"])
                for record in day_records
            )
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "activeZoneMinutes": {"activeZoneMinutes": minutes},
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "active-minutes":
            totals: dict[str, int] = defaultdict(int)
            for record in day_records:
                for part in record.get("activeMinutes", {}).get(
                    "activeMinutesByActivityLevel",
                    [],
                ):
                    level = str(part.get("activityLevel") or "UNKNOWN")
                    totals[level] += _int(part, ["activeMinutes"])
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "activeMinutes": {
                        "activeMinutesByActivityLevel": [
                            {"activityLevel": level, "activeMinutes": minutes}
                            for level, minutes in sorted(totals.items())
                        ]
                    },
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "distance":
            millimeters = sum(_int(record, ["distance", "millimeters"]) for record in day_records)
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "distance": {"millimeters": millimeters},
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "active-energy-burned":
            kcal = sum(_float(record, ["activeEnergyBurned", "kcal"]) for record in day_records)
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "activeEnergyBurned": {"kcal": round(kcal, 2)},
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "activity-level":
            totals_float: dict[str, float] = defaultdict(float)
            for record in day_records:
                level = record.get("activityLevel", {}).get("activityLevelType", "UNKNOWN")
                totals_float[level] += _interval_minutes(record.get("activityLevel", {}))
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "activityLevel": {
                        "activityLevelsMinutes": {
                            level: round(minutes, 2)
                            for level, minutes in sorted(totals_float.items())
                        }
                    },
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "time-in-heart-rate-zone":
            totals_float = defaultdict(float)
            for record in day_records:
                zone = record.get("timeInHeartRateZone", {}).get("heartRateZoneType", "UNKNOWN")
                totals_float[zone] += _interval_minutes(record.get("timeInHeartRateZone", {}))
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "timeInHeartRateZone": {
                        "heartRateZonesMinutes": {
                            zone: round(minutes, 2)
                            for zone, minutes in sorted(totals_float.items())
                        }
                    },
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "heart-rate":
            values = [
                _float(record, ["heartRate", "beatsPerMinute"])
                for record in day_records
                if _float(record, ["heartRate", "beatsPerMinute"]) > 0
            ]
            if not values:
                continue
            stats = _numeric_summary(values)
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "heartRate": {
                        "beatsPerMinute": stats["average"],
                        "summary": {
                            "averageBeatsPerMinute": stats["average"],
                            "minBeatsPerMinute": stats["min"],
                            "maxBeatsPerMinute": stats["max"],
                            "samples": stats["samples"],
                        },
                    },
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "heart-rate-variability":
            values = [
                _float(
                    record,
                    ["heartRateVariability", "rootMeanSquareOfSuccessiveDifferencesMilliseconds"],
                )
                for record in day_records
                if _float(
                    record,
                    ["heartRateVariability", "rootMeanSquareOfSuccessiveDifferencesMilliseconds"],
                )
                > 0
            ]
            if not values:
                continue
            stats = _numeric_summary(values)
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "heartRateVariability": {
                        "rootMeanSquareOfSuccessiveDifferencesMilliseconds": stats["average"],
                        "summary": {
                            "averageMilliseconds": stats["average"],
                            "minMilliseconds": stats["min"],
                            "maxMilliseconds": stats["max"],
                            "samples": stats["samples"],
                        },
                    },
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
        elif metric == "oxygen-saturation":
            values = [
                _float(record, ["oxygenSaturation", "percentage"])
                for record in day_records
                if _float(record, ["oxygenSaturation", "percentage"]) > 0
            ]
            if not values:
                continue
            stats = _numeric_summary(values)
            output.append(
                {
                    "name": f"summary/{metric}/{day}",
                    "date": _date_payload(day),
                    "oxygenSaturation": {
                        "percentage": stats["average"],
                        "summary": {
                            "averagePercentage": stats["average"],
                            "minPercentage": stats["min"],
                            "maxPercentage": stats["max"],
                            "samples": stats["samples"],
                        },
                    },
                    "summary": {"sourceRecords": len(day_records)},
                }
            )
    return output


def _downsample_records(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(records) <= limit:
        return records
    sorted_records = sorted(records, key=lambda record: dumps(record))
    if limit == 1:
        return [sorted_records[-1]]
    step = (len(sorted_records) - 1) / (limit - 1)
    return [sorted_records[round(index * step)] for index in range(limit)]


def _date_payload(day: str) -> dict[str, int]:
    year, month, day_num = [int(part) for part in day.split("-")]
    return {"year": year, "month": month, "day": day_num}


def _numeric_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "average": round(sum(values) / len(values), 1),
        "min": _round_number(min(values)),
        "max": _round_number(max(values)),
        "samples": len(values),
    }


def _round_number(value: float) -> int | float | None:
    if value <= 0:
        return None
    if float(value).is_integer():
        return int(value)
    return round(value, 1)


def _normalize_metric_request(metrics: list[str] | None, stored_types: set[str]) -> list[str]:
    if not metrics:
        return sorted(stored_types or SYNC_DATA_TYPE_IDS)
    normalized = []
    for metric_id in metrics:
        metric_id = str(metric_id).strip().lower()
        if metric_id == "*":
            normalized.extend(sorted(stored_types or SYNC_DATA_TYPE_IDS))
        elif metric_id:
            normalized.append(metric_id)
    return list(dict.fromkeys(normalized))


def _coerce_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except ValueError:
        return None


def _public_daily_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != "sleep_sessions"}


def _stable_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def _latest_day_with(
    daily: dict[str, dict[str, Any]],
    keys: tuple[str, ...],
    max_date: str | None = None,
) -> str | None:
    for day in sorted(daily, reverse=True):
        if max_date and day > max_date:
            continue
        values = daily[day]
        if any(values.get(key) is not None for key in keys):
            return day
    return None


def _baseline_average(
    daily: dict[str, dict[str, Any]],
    key: str,
    before_date: str | None,
    max_days: int = 14,
) -> float | None:
    values = _baseline_values(daily, key, before_date, max_days)
    if not values:
        return None
    return sum(values) / len(values)


def _baseline_summary(
    daily: dict[str, dict[str, Any]],
    key: str,
    before_date: str | None,
    max_days: int = 14,
) -> tuple[float | None, int]:
    values = _baseline_values(daily, key, before_date, max_days)
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


def _baseline_values(
    daily: dict[str, dict[str, Any]],
    key: str,
    before_date: str | None,
    max_days: int = 14,
) -> list[float]:
    values = [
        _float({"value": day_values.get(key)}, ["value"])
        for day, day_values in sorted(daily.items(), reverse=True)
        if (not before_date or day < before_date) and day_values.get(key) is not None
    ][:max_days]
    return [value for value in values if value > 0]


def _ordered_unique(values: list[str], order: dict[str, int]) -> list[str]:
    return sorted(set(values), key=lambda value: order.get(value, len(order)))


def _chunks(values: list[Any], size: int) -> list[list[Any]]:
    safe_size = max(1, size)
    return [values[index : index + safe_size] for index in range(0, len(values), safe_size)]


def _sync_coverage_summary(
    metrics_synced: list[str],
    metrics_deferred: list[str],
    metric_errors: list[dict[str, str]],
) -> dict[str, Any]:
    synced = set(metrics_synced)
    recovery_core = [
        "sleep",
        "daily-resting-heart-rate",
        "daily-heart-rate-variability",
        "active-zone-minutes",
        "steps",
    ]
    heart_detail = ["heart-rate", "time-in-heart-rate-zone", "heart-rate-variability"]
    recovery_extended = [
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-sleep-temperature-derivations",
        "respiratory-rate-sleep-summary",
        "oxygen-saturation",
    ]
    return {
        "core_recovery_ready": all(metric in synced for metric in recovery_core),
        "heart_detail_ready": any(metric in synced for metric in heart_detail),
        "workout_sessions_ready": "exercise" in synced,
        "extended_recovery_ready": any(metric in synced for metric in recovery_extended),
        "synced_count": len(metrics_synced),
        "deferred_count": len(metrics_deferred),
        "error_count": len(metric_errors),
        "usable_for_today_plan": any(metric in synced for metric in recovery_core),
    }


def _annotate_write_timings(
    metric_timings: list[dict[str, Any]],
    results: list[dict[str, Any]],
    write_seconds: float,
) -> None:
    if not results:
        return
    result_metrics = {item["metric"] for item in results if item.get("storage_records")}
    if not result_metrics:
        return
    for timing in metric_timings:
        if timing.get("metric") in result_metrics:
            timing["write_batch_seconds"] = write_seconds
            timing["write_batch_metric_count"] = len(result_metrics)


def _annotate_secondary_timings(
    metric_timings: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    result_metrics = {item["metric"] for item in results}
    for timing in metric_timings:
        if timing.get("metric") in result_metrics:
            timing["persistence"] = "deferred_after_fetch"


def _annotate_no_record_timings(
    metric_timings: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    result_metrics = {item["metric"] for item in results}
    for timing in metric_timings:
        if timing.get("metric") in result_metrics:
            timing["persistence"] = "no_records_to_store"


def _latest_load(daily: dict[str, dict[str, Any]], max_date: str | None) -> tuple[str | None, int]:
    day = _latest_day_with(daily, ("active_zone_minutes",), max_date=max_date)
    if not day:
        return None, 0
    return day, _int({"value": daily[day].get("active_zone_minutes")}, ["value"])


def _int(value: dict[str, Any], path: list[str]) -> int:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)
    try:
        return int(current)
    except (TypeError, ValueError):
        return 0


def _float(value: dict[str, Any], path: list[str]) -> float:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(key)
    try:
        return float(current)
    except (TypeError, ValueError):
        return 0.0


def _first_float(value: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in value or value.get(key) is None:
            continue
        try:
            return float(value[key])
        except (TypeError, ValueError):
            continue
    return None


def _sleep_resp_stats(summary: dict[str, Any], camel_key: str) -> dict[str, Any]:
    snake_key = _camel_to_snake(camel_key)
    stats = summary.get(camel_key) or summary.get(snake_key) or {}
    breaths = _first_float(stats, ("breathsPerMinute", "breaths_per_minute"))
    if breaths is None:
        return {}
    return {
        "breaths_per_minute": _round_optional(breaths, 1),
        "standard_deviation": _round_optional(
            _first_float(stats, ("standardDeviation", "standard_deviation")),
            2,
        ),
        "signal_to_noise": _round_optional(
            _first_float(stats, ("signalToNoise", "signal_to_noise")),
            2,
        ),
    }


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _duration_minutes(value: str | None) -> float | None:
    if not value or not value.endswith("s"):
        return None
    try:
        return round(float(value.removesuffix("s")) / 60, 1)
    except ValueError:
        return None


def _interval_minutes(value: dict[str, Any]) -> float:
    interval = value.get("interval", {})
    start = _parse_time(interval.get("startTime"))
    end = _parse_time(interval.get("endTime"))
    if not start or not end:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 60)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
