from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_timestamp() -> int:
    return int(utc_now().timestamp())


def iso_now() -> str:
    return utc_now().isoformat()


def iso_date(days_ago: int = 0) -> str:
    return (utc_now().date() - timedelta(days=days_ago)).isoformat()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])
