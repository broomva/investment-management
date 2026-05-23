"""Dispatcher — routes a validated TVAlert to the right broker client.

PR 1: routing logic is complete; broker clients are stubs that raise
NotImplementedError with a clear "PR 2" message. The handler in `app.py`
catches NotImplementedError and returns a `stubbed` DispatchResult so a
smoke test can exercise the full pipeline end-to-end without touching
any broker API.

PR 2 will replace the stubs with real client calls (paper-only) and remove
the NotImplementedError catch in the handler.
"""

from __future__ import annotations

from typing import Literal

import structlog

from .schemas import AssetClass, DispatchResult, TVAlert

log = structlog.get_logger("tradingview_bridge.dispatch")

BrokerName = Literal["ibkr", "kraken", "polymarket"]


def route_asset_class(asset_class: AssetClass) -> BrokerName:
    """Pure function — returns the broker name responsible for an asset class.

    Extracted as a top-level function so tests can exercise routing without
    instantiating the dispatcher and so future broker additions only touch
    this function.
    """
    if asset_class in ("stock", "etf", "bond", "fx"):
        return "ibkr"
    if asset_class == "crypto":
        return "kraken"
    if asset_class == "prediction":
        return "polymarket"
    # Pydantic Literal validation should prevent this branch, but defense
    # in depth — explicit error beats AttributeError.
    raise ValueError(f"Unknown asset class: {asset_class!r}")


class Dispatcher:
    """Async dispatcher to broker clients.

    PR 1: every `_dispatch_*` method raises NotImplementedError. The webhook
    handler catches this and returns a `stubbed` result, so the full pipeline
    is testable without any broker integration.
    """

    async def dispatch(self, alert: TVAlert) -> DispatchResult:
        """Route the alert and return the (stubbed in PR 1) dispatch result."""
        broker = route_asset_class(alert.asset_class)
        log.info(
            "alert_dispatched",
            alert_id=alert.alert_id,
            strategy=alert.strategy_name,
            asset_class=alert.asset_class,
            symbol=alert.symbol,
            action=alert.action,
            size=str(alert.size),
            size_type=alert.size_type,
            broker=broker,
        )
        try:
            if broker == "ibkr":
                return await self._dispatch_ibkr(alert)
            if broker == "kraken":
                return await self._dispatch_kraken(alert)
            if broker == "polymarket":
                return await self._dispatch_polymarket(alert)
            raise AssertionError(f"unreachable: broker={broker}")
        except NotImplementedError as e:
            log.info("alert_stubbed", alert_id=alert.alert_id, broker=broker, detail=str(e))
            return DispatchResult(
                status="stubbed",
                broker=broker,
                detail=str(e),
                alert_id=alert.alert_id,
            )

    async def _dispatch_ibkr(self, alert: TVAlert) -> DispatchResult:
        raise NotImplementedError(
            "PR 2 — IBKR client (ib_async) not wired yet. "
            f"Would route asset_class={alert.asset_class} symbol={alert.symbol}."
        )

    async def _dispatch_kraken(self, alert: TVAlert) -> DispatchResult:
        raise NotImplementedError(
            "PR 2 — Kraken client (ccxt) not wired yet. "
            f"Would route asset_class={alert.asset_class} symbol={alert.symbol}."
        )

    async def _dispatch_polymarket(self, alert: TVAlert) -> DispatchResult:
        raise NotImplementedError(
            "PR 2 — Polymarket client (py-clob-client) not wired yet. "
            f"Would route asset_class={alert.asset_class} symbol={alert.symbol}."
        )
