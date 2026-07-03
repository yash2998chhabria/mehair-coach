from __future__ import annotations

from pathlib import Path


def test_render_blueprint_has_free_web_service_with_remote_database() -> None:
    blueprint = Path("render.yaml").read_text()

    assert "name: mehair-coach" in blueprint
    assert "runtime: python" in blueprint
    assert "plan: free" in blueprint
    assert "PYTHON_VERSION" in blueprint
    assert "3.12.12" in blueprint
    assert "buildCommand: uv sync --frozen --no-dev" in blueprint
    assert "startCommand: uv run --no-sync python -m app.main" in blueprint
    assert "healthCheckPath: /health" in blueprint
    assert "mountPath: /var/data" not in blueprint
    assert "TOKEN_ENCRYPTION_KEY" in blueprint
    assert "DATABASE_URL" in blueprint
    assert "LIBSQL_AUTH_TOKEN" in blueprint
    assert "GOOGLE_CLIENT_ID" in blueprint
    assert "GOOGLE_CLIENT_SECRET" in blueprint
