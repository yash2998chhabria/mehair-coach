from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .auth import AuthService
from .db import Database, dumps, loads
from .google_health import GoogleHealthClient, SYNC_DATA_TYPE_IDS, SYNC_DATA_TYPES, metric_catalog
from .settings import Settings
from .time_utils import iso_now, utc_now

RECOVERY_KEYS = ("sleep", "hrv_ms", "resting_heart_rate", "spo2_avg", "respiratory_rate")


class HealthStore:
    def __init__(self, db: Database, auth: AuthService, settings: Settings):
        self.db = db
        self.auth = auth
        self.settings = settings
        self.google = GoogleHealthClient(settings.google_health_api_base)

    async def sync_latest(self, user_id: str) -> dict[str, Any]:
        if not self.auth.refresh_token_available(user_id):
            return setup_required()
        access_token = await self.auth.ensure_google_access_token(user_id)
        if not access_token:
            return setup_required("Google access token is unavailable. Reconnect Google Health.")

        started_at = iso_now()
        sync_id = self._start_sync(user_id, started_at)
        upserted = 0
        now = utc_now()
        start = now - timedelta(days=self.settings.sync_lookback_days)
        start_time = start.isoformat().replace("+00:00", "Z")
        end_time = (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        start_date = start.date().isoformat()
        end_date = (now.date() + timedelta(days=1)).isoformat()

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
            "lookback_days": self.settings.sync_lookback_days,
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
                }
            )
        return result

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
