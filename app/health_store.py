from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .auth import AuthService
from .db import Database, dumps, loads
from .google_health import GoogleHealthClient, SYNC_DATA_TYPES
from .settings import Settings
from .time_utils import iso_now, utc_now


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

        return {
            "status": "ok",
            "message": "Google Health sync complete.",
            "records_upserted": upserted,
            "lookback_days": self.settings.sync_lookback_days,
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
        today = summary["daily"].get(latest_date, {})
        readiness = readiness_from_day(today)
        return {
            "status": "ok",
            "latest_date": latest_date,
            "readiness": readiness,
            "today": today,
            "evidence": readiness["evidence"],
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
        return {
            "status": "ok",
            "days": sleep_days,
            "latest": sleep_days[-1],
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
        return {"status": "ok", "days": days_out}

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
        return {"status": "ok", "days": days_out}

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
        for item in records:
            exercise = item["payload"].get("exercise", {})
            interval = exercise.get("interval", {})
            workouts.append(
                {
                    "date": item["observed_date"],
                    "type": exercise.get("exerciseType"),
                    "display_name": exercise.get("displayName"),
                    "start_time": interval.get("startTime"),
                    "end_time": interval.get("endTime"),
                    "active_duration": exercise.get("activeDuration"),
                    "average_heart_rate": exercise.get("metricsSummary", {}).get(
                        "averageHeartRateBeatsPerMinute"
                    ),
                }
            )
        return {"status": "ok", "workouts": workouts}

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
        elif data_type == "daily-resting-heart-rate":
            values["resting_heart_rate"] = _int(payload, ["dailyRestingHeartRate", "beatsPerMinute"])
        elif data_type == "daily-heart-rate-variability":
            values["hrv_ms"] = _float(
                payload,
                ["dailyHeartRateVariability", "averageHeartRateVariabilityMilliseconds"],
            )
        elif data_type == "daily-oxygen-saturation":
            values["spo2_avg"] = _float(payload, ["dailyOxygenSaturation", "averagePercentage"])
        elif data_type == "daily-respiratory-rate":
            values["respiratory_rate"] = _float(payload, ["dailyRespiratoryRate", "breathsPerMinute"])
        elif data_type == "sleep":
            values["sleep"] = sleep_summary(payload)

    for day, samples in heart_samples.items():
        if samples:
            daily[day]["heart"] = {
                "avg_bpm": round(sum(samples) / len(samples), 1),
                "min_bpm": min(samples),
                "max_bpm": max(samples),
                "samples": len(samples),
            }

    sorted_days = sorted(daily)
    return {
        "latest_date": sorted_days[-1] if sorted_days else None,
        "daily": dict(daily),
    }


def readiness_from_day(day: dict[str, Any]) -> dict[str, Any]:
    score = 50
    evidence: list[str] = []
    sleep_hours = day.get("sleep", {}).get("duration_hours")
    if sleep_hours is not None:
        if sleep_hours >= 7:
            score += 18
            evidence.append(f"Sleep duration is {sleep_hours:.1f}h.")
        elif sleep_hours >= 6:
            score += 8
            evidence.append(f"Sleep is moderate at {sleep_hours:.1f}h.")
        else:
            score -= 12
            evidence.append(f"Sleep is short at {sleep_hours:.1f}h.")
    if day.get("hrv_ms"):
        score += 8
        evidence.append(f"HRV is {day['hrv_ms']:.1f} ms.")
    if day.get("resting_heart_rate"):
        score += 4
        evidence.append(f"Resting heart rate is {day['resting_heart_rate']} bpm.")
    if day.get("active_zone_minutes", 0) > 45:
        score -= 6
        evidence.append("Recent zone minutes are already high.")
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
    stages: dict[str, float] = defaultdict(float)
    for stage in sleep.get("stages", []):
        s = _parse_time(stage.get("startTime"))
        e = _parse_time(stage.get("endTime"))
        if s and e:
            stages[stage.get("type", "UNKNOWN").lower()] += (e - s).total_seconds() / 60
    return {
        "duration_hours": duration_hours,
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


def _stable_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


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


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
