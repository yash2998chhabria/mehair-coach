from __future__ import annotations

from typing import Any

import httpx
import pytest

import app.google_health as google_health_module
from app.google_health import DataTypeSpec, GoogleHealthClient


def ok_response(payload: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("GET", "https://health.example/fake")
    return httpx.Response(200, json=payload, request=request)


class RecordingClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: httpx.Timeout,
    ) -> httpx.Response:
        self.requests.append({"url": url, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


class LocalAsyncClient(RecordingClient):
    instances: list["LocalAsyncClient"] = []
    next_responses: list[httpx.Response] = []

    def __init__(self, *, timeout: httpx.Timeout) -> None:
        super().__init__(self.next_responses.copy())
        self.default_timeout = timeout
        self.instances.append(self)

    async def __aenter__(self) -> "LocalAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_list_data_points_uses_one_deadline_for_paginated_metric(monkeypatch) -> None:
    ticks = iter([100.0, 100.0, 100.98])
    monkeypatch.setattr(google_health_module, "monotonic", lambda: next(ticks))
    client = RecordingClient(
        [
            ok_response(
                {
                    "dataPoints": [{"name": "page-one"}],
                    "nextPageToken": "next-page",
                }
            ),
            ok_response({"dataPoints": [{"name": "page-two"}]}),
        ]
    )

    records = await GoogleHealthClient("https://health.example").list_data_points(
        "access-token",
        DataTypeSpec("steps", "interval"),
        "2026-07-03T00:00:00Z",
        "2026-07-04T00:00:00Z",
        timeout_seconds=1,
        max_pages=4,
        client=client,
    )

    assert records == [{"name": "page-one"}]
    assert len(client.requests) == 1
    assert "pageToken" not in client.requests[0]["url"]


@pytest.mark.asyncio
async def test_list_data_points_keeps_fetched_pages_when_later_page_times_out(monkeypatch) -> None:
    client = RecordingClient(
        [
            ok_response(
                {
                    "dataPoints": [{"name": "page-one"}],
                    "nextPageToken": "next-page",
                }
            ),
            ok_response({"dataPoints": [{"name": "page-two"}]}),
        ]
    )
    attempts = 0

    async def fake_await_with_timeout(awaitable: Any, timeout_seconds: float) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            awaitable.close()
            raise TimeoutError("simulated slow second page")
        return await awaitable

    monkeypatch.setattr(google_health_module, "_await_with_timeout", fake_await_with_timeout)

    records = await GoogleHealthClient("https://health.example").list_data_points(
        "access-token",
        DataTypeSpec("steps", "interval"),
        "2026-07-03T00:00:00Z",
        "2026-07-04T00:00:00Z",
        timeout_seconds=4,
        max_pages=4,
        client=client,
    )

    assert records == [{"name": "page-one"}]
    assert attempts == 2


@pytest.mark.asyncio
async def test_list_data_points_local_client_path_uses_default_timeout(monkeypatch) -> None:
    LocalAsyncClient.instances = []
    LocalAsyncClient.next_responses = [ok_response({"dataPoints": [{"name": "page-one"}]})]
    monkeypatch.setattr(google_health_module.httpx, "AsyncClient", LocalAsyncClient)

    records = await GoogleHealthClient("https://health.example").list_data_points(
        "access-token",
        DataTypeSpec("steps", "interval"),
        "2026-07-03T00:00:00Z",
        "2026-07-04T00:00:00Z",
        timeout_seconds=2,
    )

    assert records == [{"name": "page-one"}]
    assert len(LocalAsyncClient.instances) == 1
    assert LocalAsyncClient.instances[0].default_timeout.read == 2
