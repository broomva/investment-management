"""Dispatcher routing tests."""

from __future__ import annotations

import pytest

from tradingview_bridge.dispatch import Dispatcher, route_asset_class
from tradingview_bridge.schemas import TVAlert


@pytest.mark.parametrize(
    ("asset_class", "expected_broker"),
    [
        ("stock", "ibkr"),
        ("etf", "ibkr"),
        ("bond", "ibkr"),
        ("fx", "ibkr"),
        ("crypto", "kraken"),
        ("prediction", "polymarket"),
    ],
)
def test_route_asset_class(asset_class: str, expected_broker: str) -> None:
    assert route_asset_class(asset_class) == expected_broker  # type: ignore[arg-type]


def test_route_asset_class_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown asset class"):
        route_asset_class("options")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dispatch_stock_returns_stubbed_ibkr(
    valid_alert_body: dict[str, object],
) -> None:
    alert = TVAlert(**valid_alert_body)
    result = await Dispatcher().dispatch(alert)
    assert result.status == "stubbed"
    assert result.broker == "ibkr"
    assert "PR 2" in result.detail
    assert result.alert_id == "test-alert-001"


@pytest.mark.asyncio
async def test_dispatch_crypto_returns_stubbed_kraken(
    valid_alert_body: dict[str, object],
) -> None:
    valid_alert_body["asset_class"] = "crypto"
    valid_alert_body["symbol"] = "BTC/USD"
    alert = TVAlert(**valid_alert_body)
    result = await Dispatcher().dispatch(alert)
    assert result.status == "stubbed"
    assert result.broker == "kraken"


@pytest.mark.asyncio
async def test_dispatch_prediction_returns_stubbed_polymarket(
    valid_alert_body: dict[str, object],
) -> None:
    valid_alert_body["asset_class"] = "prediction"
    valid_alert_body["symbol"] = "0xMARKET"
    alert = TVAlert(**valid_alert_body)
    result = await Dispatcher().dispatch(alert)
    assert result.status == "stubbed"
    assert result.broker == "polymarket"
