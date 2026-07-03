from __future__ import annotations

from pathlib import Path


def test_render_blueprint_has_persistent_sqlite_service() -> None:
    blueprint = Path("render.yaml").read_text()

    assert "name: mehair-coach" in blueprint
    assert "runtime: python" in blueprint
    assert "PYTHON_VERSION" in blueprint
    assert "3.12.12" in blueprint
    assert "buildCommand: uv sync --frozen --no-dev" in blueprint
    assert "startCommand: uv run --no-sync python -m app.main" in blueprint
    assert "healthCheckPath: /health" in blueprint
    assert "mountPath: /var/data" in blueprint
    assert "sqlite:////var/data/mehair-coach.sqlite3" in blueprint
    assert "TOKEN_ENCRYPTION_KEY" in blueprint
    assert "GOOGLE_CLIENT_ID" in blueprint
    assert "GOOGLE_CLIENT_SECRET" in blueprint
