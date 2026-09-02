import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_live_returns_alive() -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_live_echoes_trace_id() -> None:
    resp = client.get("/health/live", headers={"x-request-id": "trace-123"})
    assert resp.headers["x-request-id"] == "trace-123"


@pytest.mark.integration
def test_ready_ok_with_infra() -> None:
    """Requires Postgres and Redis (via `just up` locally, or CI service containers)."""
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ready",
        # `ai_provider` reports configuration presence, never reachability — a live
        # model call on a readiness probe would bill the account for uptime. It passes
        # unconditionally in local environments (including CI, which has no key), and
        # only carries information deployed. `/health/ai-probe` is what actually dials.
        "checks": {"database": True, "redis": True, "ai_provider": True},
    }
