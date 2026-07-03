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


SYNC_DATA_TYPES: list[DataTypeSpec] = [
    DataTypeSpec("steps", "interval"),
    DataTypeSpec("heart-rate", "sample"),
    DataTypeSpec("sleep", "session"),
    DataTypeSpec("exercise", "session"),
    DataTypeSpec("active-minutes", "interval"),
    DataTypeSpec("active-zone-minutes", "interval"),
    DataTypeSpec("active-energy-burned", "interval"),
    DataTypeSpec("activity-level", "interval"),
    DataTypeSpec("distance", "interval"),
    DataTypeSpec("heart-rate-variability", "sample"),
    DataTypeSpec("oxygen-saturation", "sample"),
    DataTypeSpec("respiratory-rate-sleep-summary", "sample"),
    DataTypeSpec("sedentary-period", "interval"),
    DataTypeSpec("swim-lengths-data", "interval"),
    DataTypeSpec("time-in-heart-rate-zone", "interval"),
    DataTypeSpec("daily-heart-rate-variability", "daily"),
    DataTypeSpec("daily-resting-heart-rate", "daily"),
    DataTypeSpec("daily-oxygen-saturation", "daily"),
    DataTypeSpec("daily-respiratory-rate", "daily"),
    DataTypeSpec("daily-sleep-temperature-derivations", "daily"),
    DataTypeSpec("daily-vo2-max", "daily"),
    DataTypeSpec("calories-in-heart-rate-zone", "interval", "dailyRollUp"),
    DataTypeSpec("total-calories", "interval", "dailyRollUp"),
    DataTypeSpec("floors", "interval", "dailyRollUp"),
]


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
