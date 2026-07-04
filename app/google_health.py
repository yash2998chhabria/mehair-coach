from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import urlencode

import httpx

MIN_PAGE_TIMEOUT_SECONDS = 0.05


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
        timeout_seconds: int = 8,
        max_pages: int = 8,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = ""
        pages = 0
        deadline = monotonic() + max(MIN_PAGE_TIMEOUT_SECONDS, float(timeout_seconds))
        default_timeout = _http_timeout(timeout_seconds)
        filter_value = self._filter(spec, start_time, end_time)

        async def fetch_pages(http_client: httpx.AsyncClient) -> list[dict[str, Any]]:
            nonlocal page_token, pages
            while pages < max(1, max_pages):
                remaining_seconds = deadline - monotonic()
                if remaining_seconds <= 0:
                    if records:
                        break
                    raise TimeoutError("Google Health metric request timed out.")
                if records and remaining_seconds < MIN_PAGE_TIMEOUT_SECONDS:
                    break

                params: dict[str, str | int] = {"pageSize": page_size}
                if page_token:
                    params["pageToken"] = page_token
                if filter_value:
                    params["filter"] = filter_value
                try:
                    response = await _await_with_timeout(
                        http_client.get(
                            f"{self.base_url}/users/me/dataTypes/{spec.id}/dataPoints?{urlencode(params)}",
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=_http_timeout(
                                remaining_seconds,
                                minimum=MIN_PAGE_TIMEOUT_SECONDS,
                            ),
                        ),
                        timeout_seconds=remaining_seconds,
                    )
                except (TimeoutError, httpx.TimeoutException):
                    if records:
                        break
                    raise
                response.raise_for_status()
                body = response.json()
                records.extend(body.get("dataPoints", []))
                page_token = body.get("nextPageToken") or ""
                pages += 1
                if not page_token:
                    break
            return records

        if client is not None:
            return await fetch_pages(client)
        async with httpx.AsyncClient(timeout=default_timeout) as local_client:
            await fetch_pages(local_client)
        return records

    async def daily_rollup(
        self,
        access_token: str,
        spec: DataTypeSpec,
        start_date: str,
        end_date: str,
        timeout_seconds: int = 8,
        client: httpx.AsyncClient | None = None,
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
        timeout = _http_timeout(timeout_seconds)

        async def post_rollup(http_client: httpx.AsyncClient) -> httpx.Response:
            return await http_client.post(
                f"{self.base_url}/users/me/dataTypes/{spec.id}/dataPoints:dailyRollUp",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=timeout,
            )

        if client is not None:
            response = await post_rollup(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as local_client:
                response = await post_rollup(local_client)
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


async def _await_with_timeout(awaitable: Any, timeout_seconds: float) -> Any:
    return await asyncio.wait_for(awaitable, timeout=max(MIN_PAGE_TIMEOUT_SECONDS, timeout_seconds))


def _http_timeout(timeout_seconds: int | float, *, minimum: float = 1.0) -> httpx.Timeout:
    total = max(minimum, float(timeout_seconds))
    connect = min(2.0, total)
    return httpx.Timeout(total, connect=connect, read=total, write=total, pool=connect)
