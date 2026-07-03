from __future__ import annotations

from app.db import Database


def test_libsql_rows_support_sqlite_row_style_access(tmp_path) -> None:
    db = Database.from_url(f"file:{tmp_path / 'libsql-local.db'}")
    db.init()

    with db.connect() as conn:
        cursor = conn.execute(
            "INSERT INTO users (id, created_at, updated_at) VALUES (?, ?, ?)",
            ("user_1", "now", "now"),
        )

    row = db.one("SELECT id, created_at FROM users WHERE id = ?", ("user_1",))

    assert cursor.lastrowid == 1
    assert row is not None
    assert row["id"] == "user_1"
    assert row[0] == "user_1"
    assert row.keys() == ["id", "created_at"]
    assert dict(row) == {"id": "user_1", "created_at": "now"}
