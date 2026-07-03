from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  google_email TEXT,
  google_subject TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_subject
ON users(google_subject)
WHERE google_subject IS NOT NULL;

CREATE TABLE IF NOT EXISTS google_tokens (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_encrypted TEXT,
  access_token_encrypted TEXT,
  access_token_expires_at INTEGER,
  scopes TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_clients (
  client_id TEXT PRIMARY KEY,
  client_secret TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_states (
  state TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_codes (
  code TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  scopes TEXT NOT NULL,
  resource TEXT,
  expires_at INTEGER NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_access_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  scopes TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_refresh_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id TEXT NOT NULL,
  scopes TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_health_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  data_type TEXT NOT NULL,
  record_key TEXT NOT NULL,
  observed_date TEXT,
  payload_json TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  UNIQUE(user_id, data_type, record_key)
);

CREATE INDEX IF NOT EXISTS idx_raw_health_user_observed
ON raw_health_records(user_id, observed_date DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_raw_health_user_type_observed
ON raw_health_records(user_id, data_type, observed_date DESC);

CREATE INDEX IF NOT EXISTS idx_raw_health_user_synced
ON raw_health_records(user_id, synced_at DESC);

CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  records_upserted INTEGER NOT NULL DEFAULT 0,
  message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_user_started
ON sync_runs(user_id, started_at DESC);

CREATE TABLE IF NOT EXISTS goals (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  goal_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkins_user_recent
ON checkins(user_id, id DESC);
"""


class NamedRow(Sequence[Any]):
    def __init__(self, columns: Sequence[str], values: Sequence[Any]):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._by_name = dict(zip(self._columns, self._values, strict=False))

    def __getitem__(self, key: int | slice | str) -> Any:
        if isinstance(key, str):
            return self._by_name[key]
        return self._values[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> list[str]:
        return list(self._columns)

    def get(self, key: str, default: Any = None) -> Any:
        return self._by_name.get(key, default)


class NamedCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def fetchone(self) -> NamedRow | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return self._wrap(row)

    def fetchall(self) -> list[NamedRow]:
        return [self._wrap(row) for row in self._cursor.fetchall()]

    def fetchmany(self, size: int | None = None) -> list[NamedRow]:
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [self._wrap(row) for row in rows]

    def __iter__(self) -> Iterator[NamedRow]:
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row

    def _wrap(self, row: Sequence[Any]) -> NamedRow:
        columns = [item[0] for item in (self._cursor.description or ())]
        return NamedRow(columns, row)


class LibsqlConnection:
    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> NamedCursor:
        return NamedCursor(self._connection.execute(query, params))

    def executemany(self, query: str, params: Sequence[tuple[Any, ...]]) -> NamedCursor:
        return NamedCursor(self._connection.executemany(query, params))

    def executescript(self, sql_script: str) -> NamedCursor:
        return NamedCursor(self._connection.executescript(sql_script))

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


class Database:
    def __init__(
        self,
        path: Path | None = None,
        *,
        database_url: str | None = None,
        libsql_auth_token: str = "",
    ):
        if database_url is None:
            if path is None:
                raise ValueError("Either path or database_url is required.")
            database_url = f"sqlite:///{path}"
        self.database_url = database_url
        self.libsql_auth_token = libsql_auth_token
        parsed = urlparse(database_url)
        self.kind = "sqlite" if parsed.scheme == "sqlite" else "libsql"
        if self.kind == "sqlite":
            self.path = Path(database_url.removeprefix("sqlite:///"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.path = None

    @classmethod
    def from_url(cls, database_url: str, libsql_auth_token: str = "") -> "Database":
        parsed = urlparse(database_url)
        if parsed.scheme == "sqlite":
            return cls(database_url=database_url)
        if parsed.scheme in {"libsql", "wss", "ws", "https", "http", "file"}:
            return cls(database_url=database_url, libsql_auth_token=libsql_auth_token)
        raise ValueError(
            "DATABASE_URL must start with sqlite:///, libsql://, wss://, ws://, https://, http://, or file:."
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection | LibsqlConnection]:
        if self.kind == "sqlite":
            if self.path is None:
                raise ValueError("SQLite path is not configured.")
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
        else:
            import libsql

            connect_kwargs = {"database": self.database_url}
            if self.libsql_auth_token:
                connect_kwargs["auth_token"] = self.libsql_auth_token
            conn = LibsqlConnection(libsql.connect(**connect_kwargs))
            conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def one(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | NamedRow | None:
        with self.connect() as conn:
            return conn.execute(query, params).fetchone()

    def all(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row | NamedRow]:
        with self.connect() as conn:
            return list(conn.execute(query, params).fetchall())


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)
