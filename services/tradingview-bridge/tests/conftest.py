"""Test fixtures — set env vars and reset settings cache before each test."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from tradingview_bridge import settings as settings_module

TEST_SECRET = "test-secret-do-not-use-in-prod-or-anywhere-real"


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Clear the lru_cache on get_settings() so each test reads fresh env."""
    settings_module.get_settings.cache_clear()
    yield
    settings_module.get_settings.cache_clear()


@pytest.fixture
def paper_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default safe env — paper mode, test secret, default TV IPs."""
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "paper")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", TEST_SECRET)
    # Clear .env-leaked vars defensively
    for k in ("TVBRIDGE_TV_ALLOWED_IPS", "TVBRIDGE_TRUST_FORWARDED_FOR"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env with TRADING_MODE=live — used to assert PaperOnlyViolation."""
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "live")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", TEST_SECRET)


@pytest.fixture
def valid_alert_body() -> dict[str, object]:
    """Canonical valid alert body for a stock buy."""
    return {
        "alert_id": "test-alert-001",
        "secret": TEST_SECRET,
        "strategy_name": "smoke-test-strategy",
        "asset_class": "stock",
        "symbol": "AAPL",
        "action": "buy",
        "size": "10",
        "size_type": "units",
        "price_hint": "180.50",
        "order_type": "market",
        "time": "2026-05-22T15:00:00Z",
        "metadata": {"timeframe": "15m"},
    }


# Ensure tests don't pick up a real .env from the developer's machine.
@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """Force settings to NOT load a .env file during tests.

    pydantic-settings looks for .env in CWD; we override by setting the env
    file path to a nonexistent location.
    """
    monkeypatch.chdir(str(tmp_path))
    # Belt-and-suspenders: unset any TVBRIDGE_* var that might leak in
    for k in list(os.environ):
        if k.startswith("TVBRIDGE_"):
            monkeypatch.delenv(k, raising=False)
