from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx


@dataclass(frozen=True)
class DataTypeSpec:
    id: str
    kind: str
    operation: str = "list"
    label: str = ""
    category: str = "Other"
    description: str = ""

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label or self.id.replace("-", " ").title(),
            "category": self.category,
            "record_type": self.kind,
            "operation": self.operation,
            "description": self.description,
            "synced_by_default": True,
        }


def metric(
    data_type: str,
    kind: str,
    label: str,
    category: str,
    description: str,
    operation: str = "list",
) -> DataTypeSpec:
    return DataTypeSpec(
        id=data_type,
        kind=kind,
        operation=operation,
        label=label,
        category=category,
        description=description,
    )


SYNC_DATA_TYPES: list[DataTypeSpec] = [
    metric("steps", "interval", "Steps", "Activity", "Step counts over time."),
    metric("active-minutes", "interval", "Active minutes", "Activity", "Minutes by activity intensity."),
    metric("active-zone-minutes", "interval", "Active Zone Minutes", "Activity", "Fitbit zone-minute load by heart-rate zone."),
    metric("activity-level", "interval", "Activity level", "Activity", "Sedentary, light, moderate, or vigorous movement intervals."),
    metric("distance", "interval", "Distance", "Activity", "Movement distance in millimeters."),
    metric("floors", "interval", "Floors", "Activity", "Daily floor/elevation count rollups.", "dailyRollUp"),
    metric("active-energy-burned", "interval", "Active energy", "Activity", "Active calories burned."),
    metric("total-calories", "interval", "Total calories", "Activity", "Daily total calorie expenditure.", "dailyRollUp"),
    metric("sedentary-period", "interval", "Sedentary periods", "Activity", "Detected sedentary windows."),
    metric("calories-in-heart-rate-zone", "interval", "Calories in heart-rate zones", "Activity", "Daily calories split by heart-rate zone.", "dailyRollUp"),
    metric("heart-rate", "sample", "Heart rate", "Heart", "Heart-rate samples."),
    metric("time-in-heart-rate-zone", "interval", "Time in heart-rate zones", "Heart", "Time spent in each heart-rate zone."),
    metric("heart-rate-variability", "sample", "HRV samples", "Heart", "Heart-rate variability samples."),
    metric("daily-heart-rate-variability", "daily", "Daily HRV", "Heart", "Daily HRV summary."),
    metric("daily-resting-heart-rate", "daily", "Resting heart rate", "Heart", "Daily resting heart rate."),
    metric("sleep", "session", "Sleep", "Sleep", "Sleep sessions, stages, and summary minutes."),
    metric("oxygen-saturation", "sample", "Oxygen saturation samples", "Recovery", "SpO2 samples."),
    metric("daily-oxygen-saturation", "daily", "Daily oxygen saturation", "Recovery", "Daily SpO2 summary."),
    metric("respiratory-rate-sleep-summary", "sample", "Respiratory sleep summary", "Recovery", "Respiratory-rate sleep summaries."),
    metric("daily-respiratory-rate", "daily", "Daily respiratory rate", "Recovery", "Daily respiratory-rate summary."),
    metric("daily-sleep-temperature-derivations", "daily", "Sleep temperature", "Recovery", "Nightly sleep-temperature derivations."),
    metric("exercise", "session", "Exercise sessions", "Workouts", "Workout sessions and metrics."),
    metric("swim-lengths-data", "interval", "Swim lengths", "Workouts", "Swim length intervals."),
    metric("daily-vo2-max", "daily", "Daily VO2 max", "Capacity", "Daily VO2 max estimate."),
]

SYNC_DATA_TYPE_IDS = {spec.id for spec in SYNC_DATA_TYPES}


def metric_catalog() -> list[dict[str, Any]]:
    return [spec.catalog_entry() for spec in SYNC_DATA_TYPES]


class GoogleHealthClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def list_data_points(
        self,
        access_token: str,
        spec: DataTypeSpec,
        start_time: str,
        end_time: str,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = ""
        pages = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while pages < 50:
                params: dict[str, str | int] = {"pageSize": page_size}
                if page_token:
                    params["pageToken"] = page_token
                filter_value = self._filter(spec, start_time, end_time)
                if filter_value:
                    params["filter"] = filter_value
                response = await client.get(
                    f"{self.base_url}/users/me/dataTypes/{spec.id}/dataPoints?{urlencode(params)}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                body = response.json()
                records.extend(body.get("dataPoints", []))
                page_token = body.get("nextPageToken") or ""
                pages += 1
                if not page_token:
                    break
        return records

    async def daily_rollup(
        self,
        access_token: str,
        spec: DataTypeSpec,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        body = {
            "range": {
                "start": self._civil_date(start_date),
                "end": self._civil_date(end_date),
            },
            "windowSizeDays": 1,
            "pageSize": 8,
            "dataSourceFamily": "users/me/dataSourceFamilies/google-wearables",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/users/me/dataTypes/{spec.id}/dataPoints:dailyRollUp",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
        return payload.get("rollupDataPoints", payload.get("dataPoints", []))

    @staticmethod
    def _filter(spec: DataTypeSpec, start_time: str, end_time: str) -> str | None:
        name = spec.id.replace("-", "_")
        if spec.kind == "daily":
            start = start_time[:10]
            end = end_time[:10]
            return f'{name}.date >= "{start}" AND {name}.date < "{end}"'
        if spec.kind == "session":
            if spec.id == "sleep":
                return f'sleep.interval.end_time >= "{start_time}" AND sleep.interval.end_time < "{end_time}"'
            civil_start = start_time.removesuffix("Z")
            civil_end = end_time.removesuffix("Z")
            return (
                f'{name}.interval.civil_start_time >= "{civil_start}" '
                f'AND {name}.interval.civil_start_time < "{civil_end}"'
            )
        if spec.kind == "interval":
            return f'{name}.interval.start_time >= "{start_time}" AND {name}.interval.start_time < "{end_time}"'
        if spec.kind == "sample":
            return f'{name}.sample_time.physical_time >= "{start_time}" AND {name}.sample_time.physical_time < "{end_time}"'
        return None

    @staticmethod
    def _civil_date(value: str) -> dict[str, Any]:
        year, month, day = [int(part) for part in value[:10].split("-")]
        return {"date": {"year": year, "month": month, "day": day}}
