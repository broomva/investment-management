"""End-to-end smoke tests against the FastAPI app.

These tests exercise the full pipeline:
  request → IP check → JSON parse → secret check → schema validation → dispatcher stub.

The dispatcher returns a `stubbed` result in PR 1, so the smoke test asserts on
that — proving the entire receiver pipeline is intact without any broker code.

Tests build their own TestClient per case (no shared fixture-level client) so
the lifespan re-runs cleanly with the test's env vars in effect. `importlib.reload`
is used to pick up new settings after monkeypatch.setenv.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tradingview_bridge import app as app_module
from tradingview_bridge import settings as settings_module

TV_IP_OK = "52.89.214.238"
TV_IP_BAD = "203.0.113.42"


def _headers(ip: str = TV_IP_OK) -> dict[str, str]:
    """TestClient defaults to 127.0.0.1; we set X-Forwarded-For and trust it."""
    return {"X-Forwarded-For": ip}


@pytest.fixture
def trusted_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Honor X-Forwarded-For so tests can simulate TV's source IP."""
    monkeypatch.setenv("TVBRIDGE_TRUST_FORWARDED_FOR", "true")


@pytest.fixture
def fresh_app(paper_env: None, trusted_proxy_env: None) -> Iterator[TestClient]:
    """Build a fresh app + TestClient for each test.

    `importlib.reload` ensures the lifespan reads the current env vars.
    Using a fixture-yielded TestClient inside a `with` block guarantees
    the lifespan startup runs and shutdown fires after the test.
    """
    settings_module.get_settings.cache_clear()
    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


def test_health(fresh_app: TestClient) -> None:
    resp = fresh_app.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "paper"


def test_webhook_happy_path(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "stubbed"
    assert body["broker"] == "ibkr"
    assert body["alert_id"] == "test-alert-001"
    assert "PR 2" in body["detail"]


def test_webhook_wrong_secret(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    valid_alert_body["secret"] = "wrong-secret"
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 401, resp.text


def test_webhook_missing_secret(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    del valid_alert_body["secret"]
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 401


def test_webhook_wrong_ip(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_BAD))
    assert resp.status_code == 403


def test_webhook_validation_error_after_auth(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    """Wrong secret returns 401 even when other fields are also invalid.

    We check auth before validation to avoid leaking schema info to an
    unauthenticated caller.
    """
    valid_alert_body["secret"] = "wrong"
    valid_alert_body["action"] = "yolo"  # also invalid
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 401  # auth fails first, schema error never surfaces


def test_webhook_422_on_bad_action_with_good_secret(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    valid_alert_body["action"] = "yolo"
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 422


def test_webhook_400_on_bad_json(
    fresh_app: TestClient,
) -> None:
    resp = fresh_app.post(
        "/webhook",
        content=b"not json",
        headers={**_headers(TV_IP_OK), "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_paper_only_assertion_blocks_live(live_env: None) -> None:
    """Test the safety function directly — not via the TestClient lifespan.

    When `assert_paper_only` is called in a `live` environment it raises
    `PaperOnlyViolation` (a `SystemExit` subclass). Starlette wraps lifespan
    exceptions in `BaseExceptionGroup` (Python 3.11+) so calling the function
    directly is simpler and the underlying invariant is the same.
    """
    settings_module.get_settings.cache_clear()
    settings = settings_module.get_settings()
    assert settings.trading_mode == "live"
    with pytest.raises(SystemExit) as ei:
        settings_module.assert_paper_only(settings)
    assert ei.value.code is not None
    assert "paper-only" in str(ei.value).lower()


def test_paper_only_assertion_passes_in_paper(paper_env: None) -> None:
    """Sanity — `assert_paper_only` does NOT raise when mode is paper."""
    settings_module.get_settings.cache_clear()
    settings = settings_module.get_settings()
    assert settings.trading_mode == "paper"
    # Should be a no-op.
    settings_module.assert_paper_only(settings)
