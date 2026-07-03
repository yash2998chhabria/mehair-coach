from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .auth import AuthService
from .db import Database, dumps, loads
from .google_health import GoogleHealthClient, SYNC_DATA_TYPE_IDS, SYNC_DATA_TYPES, metric_catalog
from .settings import Settings
from .time_utils import iso_now, utc_now

RECOVERY_KEYS = ("sleep", "hrv_ms", "resting_heart_rate", "spo2_avg", "respiratory_rate")
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
        "steps",
        "exercise",
    ],
    "workout_decision": [
        "exercise",
        "active-zone-minutes",
        "time-in-heart-rate-zone",
        "steps",
        "heart-rate",
        "daily-resting-heart-rate",
        "daily-heart-rate-variability",
        "sleep",
    ],
    "active_workout": [
        "heart-rate",
        "time-in-heart-rate-zone",
        "active-zone-minutes",
        "exercise",
        "daily-resting-heart-rate",
        "daily-heart-rate-variability",
        "sleep",
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
        "active-minutes",
        "steps",
        "distance",
        "exercise",
    ],
    "subjective": ["sleep", "exercise", "active-zone-minutes", "daily-heart-rate-variability"],
    "goal": ["exercise", "active-zone-minutes", "steps", "sleep"],
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
        "steps",
        "exercise",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
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
}


class HealthStore:
    def __init__(self, db: Database, auth: AuthService, settings: Settings):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.google = GoogleHealthClient(settings.google_health_api_base)

    async def sync_latest(self, user_id: str, force: bool = False) -> dict[str, Any]:
        if not self.auth.refresh_token_available(user_id):
            return setup_required()

        if not force:
            recent = self._recent_sync_result(user_id)
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
                "start_time": start_time,
                "end_time": end_time,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

        try:
            for spec in SYNC_DATA_TYPES:
                if spec.operation == "dailyRollUp":
                    records = await self.google.daily_rollup(access_token, spec, start_date, end_date)
                else:
                    records = await self.google.list_data_points(access_token, spec, start_time, end_time)
                upserted += self.upsert_records(user_id, spec.id, records)
            self._finish_sync(sync_id, "ok", upserted, "Sync complete.")
        except Exception as exc:
            self._finish_sync(sync_id, "error", upserted, str(exc))
            return {
                "status": "error",
                "message": "Google Health sync failed.",
                "detail": str(exc),
                "records_upserted": upserted,
            }

        result = {
            "status": "ok",
            "message": "Google Health sync complete.",
            "records_upserted": upserted,
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

    def _recent_sync_result(self, user_id: str) -> dict[str, Any] | None:
        min_interval = max(0, int(self.settings.sync_min_interval_minutes or 0))
        if min_interval <= 0:
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
        with self.db.connect() as conn:
            for record in records:
                key = record.get("name") or _stable_hash(record)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO raw_health_records
                      (user_id, data_type, record_key, observed_date, payload_json, synced_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        data_type,
                        key,
                        observed_date(record),
                        dumps(record),
                        iso_now(),
                    ),
                )
        return len(records)

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
            SELECT data_type, COUNT(*) AS records, MAX(observed_date) AS latest_observed
            FROM raw_health_records
            WHERE user_id = ?
            GROUP BY data_type
            """,
            (user_id,),
        )
        stored_types = {row["data_type"] for row in stored_rows}
        latest_observed = max((row["latest_observed"] for row in stored_rows if row["latest_observed"]), default=None)
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
        records = self.records_for_user(user_id)
        if not records:
            return empty_data()
        summary = summarize_records(records)
        latest_date = summary["latest_date"]
        activity_date = _latest_day_with(summary["daily"], ("steps", "active_minutes", "heart", "distance_mm"))
        activity_date = activity_date or latest_date
        recovery_date = _latest_day_with(summary["daily"], RECOVERY_KEYS) or activity_date
        activity_day = dict(summary["daily"].get(activity_date, {}))
        recovery_day = summary["daily"].get(recovery_date, {})
        today = combine_daily_context(activity_day, recovery_day, activity_date, recovery_date)
        load_date, load_minutes = _latest_load(summary["daily"], activity_date)
        today["latest_training_load"] = {
            "date": load_date,
            "active_zone_minutes": load_minutes,
        }
        readiness = readiness_from_day(today, summary["daily"])
        return {
            "status": "ok",
            "latest_date": latest_date,
            "activity_date": activity_date,
            "recovery_date": recovery_date,
            "readiness": readiness,
            "today": today,
            "evidence": readiness["evidence"],
            "data_coverage": data_coverage(summary["daily"]),
            "data_freshness": self.freshness(user_id),
        }

    def health_overview(self, user_id: str, days: int = 14) -> dict[str, Any]:
        records = self.records_for_user(user_id)
        if not records:
            return empty_data()

        safe_days = max(1, min(int(days or 14), 30))
        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return context

        summary = summarize_records(records)
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
        activity = _overview_activity(daily_rows)
        sleep = _overview_sleep(daily_rows)
        heart = _overview_heart(daily_rows)
        recovery = _overview_recovery(daily_rows)
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
                "raw_record_count": len(records),
                "activity_date": context.get("activity_date"),
                "recovery_date": context.get("recovery_date"),
            },
            "message": "Overview generated from all currently synced local Google Health/Fitbit records.",
            "safety_note": "This is fitness coaching context, not medical advice.",
        }

    def sleep_analysis(self, user_id: str, days: int = 7) -> dict[str, Any]:
        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return context
        summary = summarize_records(self.records_for_user(user_id))
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
        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return context
        summary = summarize_records(self.records_for_user(user_id))
        days_out = []
        for day, values in sorted(summary["daily"].items())[-days:]:
            days_out.append(
                {
                    "date": day,
                    "steps": values.get("steps", 0),
                    "active_zone_minutes": values.get("active_zone_minutes", 0),
                    "active_minutes": values.get("active_minutes", 0),
                    "distance_km": round(values.get("distance_mm", 0) / 1_000_000, 2),
                }
            )
        totals = {
            "steps": sum(day["steps"] for day in days_out),
            "active_zone_minutes": sum(day["active_zone_minutes"] for day in days_out),
            "active_minutes": sum(day["active_minutes"] for day in days_out),
        }
        highest_load = max(days_out, key=lambda day: day["active_zone_minutes"], default=None)
        return {"status": "ok", "days": days_out, "totals": totals, "highest_load_day": highest_load}

    def heart_trends(self, user_id: str, days: int = 7) -> dict[str, Any]:
        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return context
        summary = summarize_records(self.records_for_user(user_id))
        days_out = []
        for day, values in sorted(summary["daily"].items())[-days:]:
            heart = values.get("heart", {})
            days_out.append(
                {
                    "date": day,
                    "avg_bpm": heart.get("avg_bpm"),
                    "resting_bpm": values.get("resting_heart_rate"),
                    "hrv_ms": values.get("hrv_ms"),
                }
            )
        latest = days_out[-1] if days_out else None
        hrv_values = [day["hrv_ms"] for day in days_out if day.get("hrv_ms") is not None]
        rhr_values = [day["resting_bpm"] for day in days_out if day.get("resting_bpm") is not None]
        return {
            "status": "ok",
            "days": days_out,
            "latest": latest,
            "summary": {
                "average_hrv_ms": round(sum(hrv_values) / len(hrv_values), 1) if hrv_values else None,
                "average_resting_bpm": round(sum(rhr_values) / len(rhr_values), 1) if rhr_values else None,
            },
        }

    def recovery_signal_comparison(self, user_id: str, days: int = 14) -> dict[str, Any]:
        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return context
        summary = summarize_records(self.records_for_user(user_id))
        recent_days = sorted(summary["daily"].items())[-max(1, min(days, 30)):]
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
            "data_used": {
                "activity_date": context.get("activity_date"),
                "recovery_date": context.get("recovery_date"),
                "days_compared": len(rows),
                "signals": ["sleep_hours", "hrv_ms", "resting_heart_rate", "active_zone_minutes"],
            },
            "safety_note": "This is fitness coaching context, not medical advice.",
        }

    def health_question_clues(self, user_id: str, question: str, days: int = 14) -> dict[str, Any]:
        context = self.latest_context(user_id)
        if context.get("status") != "ok":
            return context

        safe_days = max(1, min(int(days or 14), 30))
        question_text = str(question or "").strip()
        intents = _question_intents(question_text)
        catalog = self.available_metrics(user_id)
        catalog_by_id = {item["id"]: item for item in catalog.get("metrics", [])}
        metric_ids = _metric_ids_for_intents(intents)
        relevant_metrics = _relevant_metric_cards(metric_ids, catalog_by_id, intents)
        overview = self.health_overview(user_id, safe_days)
        comparison = self.recovery_signal_comparison(user_id, safe_days)
        clues, positives, watchouts, next_actions = _question_clue_takeaways(
            intents=intents,
            context=context,
            overview=overview,
            comparison=comparison,
        )
        personal_context = overview.get("personal_context", {}) if overview.get("status") == "ok" else {}
        workout_context = overview.get("sections", {}).get("workouts", {}) if overview.get("status") == "ok" else {}
        illness_flags = _question_illness_flags(question_text, personal_context)
        if illness_flags:
            intents = _dedupe(["symptom_safety", *intents])
        safety_flags = _dedupe(_question_safety_flags(question_text, context) + illness_flags)
        watchouts = safety_flags + watchouts
        if context.get("data_freshness", {}).get("needs_sync_before_time_sensitive_advice"):
            next_actions.insert(0, "Run sync_latest_fitbit_data before answering time-sensitive training questions.")

        return {
            "status": "ok",
            "clue_type": "health_question_clues",
            "question": question_text or "General health and fitness coaching question",
            "window_days": safe_days,
            "headline": _question_clue_headline(intents, context, comparison),
            "intent_hints": intents,
            "recommended_tool_sequence": _recommended_tool_sequence(intents, context.get("data_freshness", {})),
            "relevant_metrics": relevant_metrics,
            "available_metric_ids": [item["id"] for item in relevant_metrics if item["records"] > 0],
            "missing_metric_ids": [item["id"] for item in relevant_metrics if item["records"] == 0],
            "query_suggestions": _metric_query_suggestions(intents, relevant_metrics, safe_days),
            "clues": _dedupe(clues),
            "positives": _dedupe(positives),
            "watchouts": _dedupe(watchouts),
            "next_actions": _dedupe(next_actions),
            "safety_flags": safety_flags,
            "readiness": context["readiness"],
            "today": _compact_today_context(context["today"]),
            "overview_context": _compact_overview_context(overview),
            "personal_context": personal_context,
            "recovery_comparison": _compact_recovery_comparison(comparison),
            "data_freshness": context["data_freshness"],
            "answering_guidance": [
                "Use the relevant_metrics list to decide which synced signals to inspect next.",
                "Treat missing metrics as absent, not zero.",
                "For workout decisions, combine readiness, sleep, HRV, resting HR, load, recent workouts, goals, and check-ins.",
                "For symptom, pain, illness, or abnormal-heart-rate concerns, recommend appropriate clinical care instead of diagnosing.",
            ],
            "answer_rubric": _answer_rubric_for_intents(intents),
            "data_used": {
                "activity_date": context.get("activity_date"),
                "recovery_date": context.get("recovery_date"),
                "synced_metric_count": catalog.get("synced_metric_count", 0),
                "supported_metric_count": catalog.get("supported_metric_count", 0),
                "comparison_available": comparison.get("status") == "ok",
                "goal_present": bool((personal_context.get("goal") or {}).get("goal")),
                "recent_checkins_count": len(personal_context.get("recent_checkins") or []),
                "recent_workout_count": workout_context.get("workout_count", 0),
            },
            "safety_note": "This is fitness coaching context, not medical advice.",
        }

    def workout_history(self, user_id: str, days: int = 14) -> dict[str, Any]:
        cutoff = (utc_now() - timedelta(days=days)).date().isoformat()
        records = [
            item
            for item in self.records_for_user(user_id)
            if item["data_type"] == "exercise" and (item["observed_date"] or "") >= cutoff
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
        "next_actions": ["Connect Google Health from the ChatGPT app OAuth prompt."],
    }


def empty_data(message: str = "No Fitbit data has synced yet.") -> dict[str, Any]:
    return {
        "status": "empty",
        "message": message,
        "next_actions": ["Run sync_latest_fitbit_data after connecting Google Health."],
    }


def freshness_details(latest_observed_date: str | None, last_sync: str | None) -> dict[str, Any]:
    now = utc_now()
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
    elif observed_days_ago == 0 and (sync_age_minutes is None or sync_age_minutes <= 120):
        level = "fresh"
        label = "fresh today"
        recommendation = "Synced data is current enough for normal coaching."
    elif observed_days_ago == 0 and (sync_age_minutes is None or sync_age_minutes <= 720):
        level = "aging"
        label = "sync if needed"
        recommendation = "Data is from today, but sync again before time-sensitive workout decisions."
    else:
        level = "stale"
        label = "sync recommended"
        recommendation = "Run sync_latest_fitbit_data before time-sensitive workout decisions."

    return {
        "freshness_level": level,
        "freshness_label": label,
        "observed_days_ago": observed_days_ago,
        "sync_age_minutes": sync_age_minutes,
        "is_observed_today": observed_days_ago == 0,
        "needs_sync_before_time_sensitive_advice": level in {"aging", "stale", "unknown"},
        "recommendation": recommendation,
    }


def _overview_activity(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
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
        "latest": _last_with(daily_rows, ("steps", "active_minutes", "active_zone_minutes", "distance_mm")) or {},
        "totals": {
            "steps": round(total_steps),
            "active_minutes": round(total_active, 1),
            "active_zone_minutes": round(total_zone, 1),
            "distance_km": round(total_distance_km, 2),
        },
        "averages": {
            "steps_per_day": round(total_steps / len(step_days)) if step_days else None,
            "active_minutes_per_day": round(total_active / len(active_days), 1) if active_days else None,
            "active_zone_minutes_per_day": round(total_zone / len(active_days), 1) if active_days else None,
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
    vo2_day = _last_with(daily_rows, ("vo2_max",))
    latest_spo2 = None
    if spo2_day:
        latest_spo2 = spo2_day.get("spo2_avg") or spo2_day.get("spo2_sample", {}).get("avg")
    return {
        "status": "ok" if spo2_day or resp_day or vo2_day else "missing",
        "latest_spo2": latest_spo2,
        "latest_spo2_date": spo2_day.get("date") if spo2_day else None,
        "latest_respiratory_rate": resp_day.get("respiratory_rate") if resp_day else None,
        "latest_respiratory_rate_date": resp_day.get("date") if resp_day else None,
        "latest_vo2_max": vo2_day.get("vo2_max") if vo2_day else None,
        "latest_vo2_max_date": vo2_day.get("date") if vo2_day else None,
    }


def _recovery_row(day: str, values: dict[str, Any]) -> dict[str, Any]:
    sleep = values.get("sleep", {})
    return {
        "date": day,
        "sleep_hours": sleep.get("asleep_hours") or sleep.get("duration_hours"),
        "sleep_sessions": sleep.get("sessions_count"),
        "hrv_ms": values.get("hrv_ms"),
        "resting_heart_rate": values.get("resting_heart_rate"),
        "active_zone_minutes": values.get("active_zone_minutes", 0),
        "steps": values.get("steps", 0),
        "respiratory_rate": values.get("respiratory_rate"),
        "spo2_avg": values.get("spo2_avg") or values.get("spo2_sample", {}).get("avg"),
    }


def _has_recovery_comparison_signal(row: dict[str, Any]) -> bool:
    return any(row.get(key) is not None for key in ("sleep_hours", "hrv_ms", "resting_heart_rate"))


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
    }


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
    hrv_pct_delta = current_vs_baseline.get("hrv_percent_delta")
    rhr_delta = current_vs_baseline.get("resting_heart_rate_delta")
    sleep_delta = current_vs_baseline.get("sleep_hours_delta")
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
    return "Latest recovery comparison: " + "; ".join(parts) + "."


def _question_intents(question: str) -> list[str]:
    text = question.lower()
    intents: list[str] = []

    def has(*words: str) -> bool:
        return any(word in text for word in words)

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
        )
    ) or ("today" in text and any(word in text for word in ("recommend", "suggest", "plan", "focus")))
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

    if has(
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
        "squash",
        "sport",
        "legs",
        "chest",
        "back",
        "shoulder",
    ):
        intents.extend(["workout_decision", "recovery", "activity_load", "heart", "sleep", "subjective", "goal"])
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
    if has("sleep", "nap", "bed", "insomnia", "awake", "restless"):
        intents.extend(["sleep", "recovery", "heart"])
    if has("heart", "hrv", "bpm", "pulse", "resting", "cardio"):
        intents.extend(["heart", "recovery", "activity_load"])
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
        intents.extend(["goal", "workout_decision", "activity_load"])

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
            "Pair activity-zone minutes, exercises, and steps for training-load questions.",
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


def _recommended_tool_sequence(intents: list[str], freshness: dict[str, Any]) -> list[str]:
    tools: list[str] = ["get_health_question_clues"]
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        tools.extend(["get_data_freshness", "sync_latest_fitbit_data"])
    if "general_overview" in intents or "daily_plan" in intents:
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


def _metric_query_suggestions(
    intents: list[str],
    relevant_metrics: list[dict[str, Any]],
    days: int,
) -> list[dict[str, Any]]:
    available = {item["id"] for item in relevant_metrics if item.get("records", 0) > 0}
    groups = [
        (
            "recovery",
            "Compare sleep, HRV, resting heart rate, and load.",
            ["sleep", "daily-heart-rate-variability", "daily-resting-heart-rate", "active-zone-minutes"],
        ),
        (
            "heart",
            "Inspect heart-rate and HRV details.",
            ["heart-rate", "heart-rate-variability", "daily-heart-rate-variability", "daily-resting-heart-rate"],
        ),
        (
            "load",
            "Inspect movement and workout load.",
            ["active-zone-minutes", "time-in-heart-rate-zone", "active-minutes", "steps", "exercise"],
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
        "Separate wearable evidence, user-reported context, and missing data.",
        "Mention freshness when the user asks about today, latest data, or real-time decisions.",
    ]
    if "workout_decision" in intents or "daily_plan" in intents:
        rubric.append("For training advice, convert the signals into intensity, RPE cap, session type, and avoid-list.")
    if "active_workout" in intents:
        rubric.append("For in-session advice, prioritize stop/continue/downshift guidance from symptoms, RPE, pain, and heart rate.")
    if any(intent in intents for intent in ("recovery", "sleep", "heart")):
        rubric.append("For recovery explanations, compare latest sleep, HRV, resting heart rate, and load against recent baseline.")
    if "symptom_safety" in intents:
        rubric.append("For symptoms or illness, avoid diagnosis, advise rest or easy movement, and suggest clinical care for severe or worsening symptoms.")
    if "goal" in intents:
        rubric.append("Tie the recommendation back to the user's stored goal without overriding recovery or safety signals.")
    return _dedupe(rubric)


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
        clues.extend(comparison.get("insights", [])[:3])
        positives.extend(comparison.get("positives", [])[:2])
        watchouts.extend(comparison.get("watchouts", [])[:3])

    latest_load = today.get("latest_training_load", {})
    active_zone_minutes = today.get("active_zone_minutes") or latest_load.get("active_zone_minutes")
    if active_zone_minutes is not None:
        clues.append(f"Latest available load is {active_zone_minutes} Active Zone Minutes.")
        if active_zone_minutes > 45:
            watchouts.append("Recent zone-minute load is high, so avoid stacking hard conditioning.")
    if activity.get("totals", {}).get("steps") is not None:
        clues.append(f"Window step volume is {activity['totals']['steps']} steps.")
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
        next_actions.append("Use get_recovery_signal_comparison to explain sleep, HRV, resting heart rate, and load together.")
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
        positives.append(f"Latest SpO2 is {recovery['latest_spo2']:.1f}%.")
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
            "Training load",
            f"{load_minutes} Active Zone Minutes on {latest_load.get('date') or 'latest load day'}.",
            "High recent load should reduce extra intensity; low load can support easy volume.",
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
        "Plan today's workout using this brief.",
        "Explain the top recovery signal in plain English.",
        "Compare sleep, HRV, resting heart rate, and load.",
    ]
    if not checkins or energy is None or soreness is None or stress is None:
        prompt_suggestions.append("Log a quick energy, soreness, and stress check-in.")
    if not goal_payload:
        prompt_suggestions.append("Set a weekly fitness goal.")
    if freshness.get("needs_sync_before_time_sensitive_advice"):
        prompt_suggestions.insert(0, "Sync latest Fitbit data.")
    if soreness is not None and soreness >= 5:
        prompt_suggestions.append("Plan around my sore areas.")

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
        "priority_signals": priority_signals[:9],
        "context_gaps": _dedupe(context_gaps)[:5],
        "prompt_suggestions": _dedupe(prompt_suggestions)[:5],
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
    heart_samples: dict[str, list[int]] = defaultdict(list)
    hrv_samples: dict[str, list[float]] = defaultdict(list)
    spo2_samples: dict[str, list[float]] = defaultdict(list)

    for item in records:
        payload = item["payload"]
        day = item["observed_date"] or observed_date(payload)
        if not day:
            continue
        values = daily[day]
        data_type = item["data_type"]
        if data_type == "steps":
            values["steps"] = values.get("steps", 0) + _int(payload, ["steps", "count"])
        elif data_type == "active-zone-minutes":
            values["active_zone_minutes"] = values.get("active_zone_minutes", 0) + _int(
                payload, ["activeZoneMinutes", "activeZoneMinutes"]
            )
        elif data_type == "active-minutes":
            values["active_minutes"] = values.get("active_minutes", 0) + sum(
                _int(part, ["activeMinutes"])
                for part in payload.get("activeMinutes", {}).get("activeMinutesByActivityLevel", [])
            )
        elif data_type == "distance":
            values["distance_mm"] = values.get("distance_mm", 0) + _int(payload, ["distance", "millimeters"])
        elif data_type == "active-energy-burned":
            values["active_kcal"] = values.get("active_kcal", 0.0) + _float(
                payload, ["activeEnergyBurned", "kcal"]
            )
        elif data_type == "total-calories":
            values["total_kcal"] = _float(payload, ["totalCalories", "kcalSum"])
        elif data_type == "heart-rate":
            bpm = _int(payload, ["heartRate", "beatsPerMinute"])
            if bpm:
                heart_samples[day].append(bpm)
        elif data_type == "heart-rate-variability":
            hrv = _float(
                payload,
                ["heartRateVariability", "rootMeanSquareOfSuccessiveDifferencesMilliseconds"],
            )
            if hrv:
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
            spo2 = _float(payload, ["oxygenSaturation", "percentage"])
            if spo2:
                spo2_samples[day].append(spo2)
        elif data_type == "daily-respiratory-rate":
            values["respiratory_rate"] = _float(payload, ["dailyRespiratoryRate", "breathsPerMinute"])
        elif data_type == "daily-vo2-max":
            values["vo2_max"] = _float(payload, ["dailyVo2Max", "millilitersPerMinuteKilogram"])
        elif data_type == "floors":
            values["floors"] = values.get("floors", 0) + _int(payload, ["floors", "countSum"])
        elif data_type == "activity-level":
            level = payload.get("activityLevel", {}).get("activityLevelType", "UNKNOWN").lower()
            minutes = _interval_minutes(payload.get("activityLevel", {}))
            levels = values.setdefault("activity_levels_minutes", defaultdict(float))
            levels[level] += minutes
        elif data_type == "sedentary-period":
            values["sedentary_minutes"] = values.get("sedentary_minutes", 0.0) + _interval_minutes(
                payload.get("sedentaryPeriod", {})
            )
        elif data_type == "time-in-heart-rate-zone":
            zone = payload.get("timeInHeartRateZone", {}).get("heartRateZoneType", "UNKNOWN").lower()
            minutes = _interval_minutes(payload.get("timeInHeartRateZone", {}))
            zones = values.setdefault("time_in_hr_zones_minutes", defaultdict(float))
            zones[zone] += minutes
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


def data_coverage(daily: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "activity_days": sum(1 for values in daily.values() if any(key in values for key in ("steps", "active_minutes", "distance_mm"))),
        "sleep_days": sum(1 for values in daily.values() if "sleep" in values),
        "heart_days": sum(1 for values in daily.values() if any(key in values for key in ("heart", "resting_heart_rate", "hrv_ms"))),
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
        hrv_baseline = _baseline_average(daily, "hrv_ms", recovery_date)
        if hrv_baseline:
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
        else:
            score += 6
            evidence.append(f"HRV is {day['hrv_ms']:.1f} ms.")
    if day.get("resting_heart_rate"):
        rhr_baseline = _baseline_average(daily, "resting_heart_rate", recovery_date)
        if rhr_baseline:
            delta = day["resting_heart_rate"] - rhr_baseline
            if delta <= 2:
                score += 6
                evidence.append(f"Resting heart rate is steady: {day['resting_heart_rate']} bpm.")
            elif delta <= 5:
                evidence.append(f"Resting heart rate is slightly elevated: {day['resting_heart_rate']} bpm.")
            else:
                score -= 8
                evidence.append(f"Resting heart rate is elevated: {day['resting_heart_rate']} bpm vs {rhr_baseline:.0f} bpm baseline.")
        else:
            score += 4
            evidence.append(f"Resting heart rate is {day['resting_heart_rate']} bpm.")
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
    values = [
        _float({"value": day_values.get(key)}, ["value"])
        for day, day_values in sorted(daily.items(), reverse=True)
        if (not before_date or day < before_date) and day_values.get(key) is not None
    ][:max_days]
    values = [value for value in values if value > 0]
    if not values:
        return None
    return sum(values) / len(values)


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
