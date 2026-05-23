"""FastAPI app — POST /webhook (TradingView Pine Script alerts) + GET /health.

PR 1: webhook receiver only. No broker clients wired. Paper-only enforced
at startup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import ValidationError

from .auth import require_valid_secret, verify_source_ip
from .dispatch import Dispatcher
from .logging_setup import configure_logging
from .schemas import DispatchResult, TVAlert
from .settings import assert_paper_only, get_settings

dispatcher = Dispatcher()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup + shutdown hook.

    Wires logging, then runs the paper-only assertion BEFORE the server
    accepts any traffic. If we're not in paper mode the assertion exits
    the process with code 1.
    """
    log = configure_logging()
    settings = get_settings()
    assert_paper_only(settings)
    log.info(
        "tradingview_bridge_started",
        mode=settings.trading_mode,
        allowed_ips=list(settings.tv_allowed_ips),
        rate_limit_per_minute=settings.rate_limit_per_minute,
        trust_forwarded_for=settings.trust_forwarded_for,
    )
    yield
    log.info("tradingview_bridge_stopped")


app = FastAPI(
    title="TradingView Bridge",
    description=(
        "Webhook receiver for TradingView Pine Script alerts. "
        "PR 1: receiver only, paper-only, no broker execution."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness probe. Does NOT report broker connectivity (no brokers wired)."""
    s = get_settings()
    return {
        "status": "ok",
        "mode": s.trading_mode,
        "version": "0.1.0",
        "pr_stage": "1 — receiver only, no execution",
    }


@app.post(
    "/webhook",
    response_model=DispatchResult,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_source_ip)],
)
async def webhook(request: Request) -> DispatchResult:
    """Receive a Pine Script alert, validate, authenticate, dispatch.

    - 403 if source IP not in TV allowlist (raised by verify_source_ip dep)
    - 422 if payload doesn't validate as TVAlert
    - 401 if shared secret doesn't match
    - 200 with DispatchResult otherwise
    """
    log = structlog.get_logger("tradingview_bridge.webhook")

    # Parse body. ValidationError → 422 via FastAPI's automatic conversion when
    # we use a Pydantic model as the param type — but we read the raw body and
    # parse manually because we want to authenticate the secret BEFORE letting
    # any other validation error leak details to an unauthenticated caller.
    try:
        body = await request.json()
    except Exception as e:
        log.warning("webhook_bad_json", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON",
        ) from e

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Request body must be a JSON object",
        )

    # Authenticate FIRST — pull just the secret, verify constant-time.
    provided_secret = body.get("secret")
    if not isinstance(provided_secret, str) or not provided_secret:
        log.warning("webhook_missing_secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty shared secret",
        )
    require_valid_secret(provided_secret)

    # Now validate the full schema.
    try:
        alert = TVAlert(**body)
    except ValidationError as e:
        log.info("webhook_validation_failed", errors=e.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=e.errors(),
        ) from e

    # Dispatch (PR 1: stubbed for all brokers).
    result = await dispatcher.dispatch(alert)
    return result
