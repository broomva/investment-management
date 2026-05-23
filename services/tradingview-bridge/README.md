# tradingview-bridge

Webhook receiver for TradingView Pine Script alerts. Dispatches to broker executors by `asset_class` (IBKR for stocks/bonds/FX, Kraken for crypto, Polymarket for prediction markets).

**Status: PR 1 — webhook receiver only. No execution. Paper-only enforced at startup.**

- Workspace ticket: [`broomva/workspace#tasks/bro-167`](https://github.com/broomva/workspace/blob/main/tasks/bro-167-cross-asset-trading-platform.md)
- Canonical decision record (broker selection): [`broomva/workspace docs/specs/2026-05-22-broker-selection-cross-asset.html`](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-22-broker-selection-cross-asset.html)

## Architecture (target — PR 1 ships the left half)

```
TradingView Pine Script alert
        │
        │ POST /webhook  (shared-secret in body, TV source IP)
        ▼
  ┌──────────────────────────────┐
  │  FastAPI app                 │   ← PR 1 ships this
  │  ├ verify source IP          │
  │  ├ parse + validate TVAlert  │
  │  ├ constant-time secret cmp  │
  │  ├ structured log            │
  │  └ dispatcher.dispatch()     │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │  Dispatcher (asset_class →   │   ← PR 1 ships routing + stubs
  │  broker)                     │       PR 2 fills in clients
  │  ├ stock/etf/bond/fx → IBKR  │
  │  ├ crypto            → Kraken│
  │  └ prediction        → Polymarket
  └──────────────────────────────┘
                 │
                 ▼  (PR 2)
  ┌──────────────────────────────┐
  │  Broker clients (paper)      │
  │  ├ ib_async      (IBKR)      │
  │  ├ ccxt          (Kraken)    │
  │  └ py-clob-client(Polymarket)│
  └──────────────────────────────┘
                 │
                 ▼  (PR 2)
        Bookkeeping P6 journal
        finance-substrate ledger
```

## What's in PR 1

- **`app.py`** — FastAPI app, single `POST /webhook` endpoint, `GET /health`
- **`schemas.py`** — `TVAlert`, `DispatchResult` Pydantic models
- **`auth.py`** — TradingView IP allowlist, constant-time shared-secret comparison
- **`dispatch.py`** — `Dispatcher` class routing by `asset_class` to broker stubs (all raise `NotImplementedError` with "PR 2" message)
- **`settings.py`** — pydantic-settings; `TVBRIDGE_TRADING_MODE` required; rejects `live` at startup
- **`logging_setup.py`** — structlog JSON formatter
- **`.control/policy.yaml`** — service-local gates (paper-only-mode startup gate; placeholders for PR 2 gates)
- **`tests/`** — unit + smoke (httpx); covers schema validation, auth (good/wrong secret/wrong IP), dispatch routing, paper-mode startup assertion
- **`pyproject.toml`** — uv-managed; runtime + dev deps pinned to current majors

## What's deliberately NOT in PR 1

- Any broker client (`ib_async`, `ccxt`, `py-clob-client`) — PR 2
- Idempotency layer (SQLite by alert_id) — PR 2
- Bookkeeping journal writes — PR 2
- Per-broker position-cap gate — PR 2
- Formulario 4 reminder gate — PR 2
- Pine Script library — PR 3
- Interceptor chart screencap — PR 3

## Local dev

```bash
cd services/tradingview-bridge
uv sync --extra dev
cp .env.example .env  # then edit TVBRIDGE_TV_WEBHOOK_SECRET

# run tests
uv run pytest -v

# run the service
TVBRIDGE_TRADING_MODE=paper uv run uvicorn tradingview_bridge.app:app --reload --port 8787

# smoke test (in another terminal)
curl -X POST http://127.0.0.1:8787/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-Forwarded-For: 52.89.214.238' \
  -d '{
    "alert_id": "test-001",
    "secret": "<your secret>",
    "strategy_name": "smoke-test",
    "asset_class": "stock",
    "symbol": "AAPL",
    "action": "buy",
    "size": "10",
    "size_type": "units",
    "time": "2026-05-22T15:00:00Z"
  }'
```

Expected `200 OK` with body `{"status":"stubbed","broker":"ibkr","detail":"PR 2 — IBKR client (ib_async) not wired yet. ..."}`.

## TradingView Pine Script alert template (for PR 3, included here for reference)

```pinescript
// In Pine Script v5 alert message:
{
  "alert_id": "{{strategy.order.id}}",
  "secret": "REPLACE_WITH_YOUR_TVBRIDGE_TV_WEBHOOK_SECRET",
  "strategy_name": "momentum-spy-15m",
  "asset_class": "stock",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "size": "{{strategy.position_size}}",
  "size_type": "units",
  "price_hint": "{{close}}",
  "time": "{{time}}"
}
```

Configure the webhook URL in the alert dialog: `https://your-host/webhook`. TradingView requires HTTPS — use Cloudflare Tunnel, ngrok, or similar for local dev.

## Safety

- **PAPER_ONLY** enforced at startup: `TVBRIDGE_TRADING_MODE` must be `paper`. Any other value → process exits 1 immediately. This is structural, not a runtime check.
- **No broker clients in PR 1**: there is literally no code path that places an order. Even if PAPER_ONLY were bypassed, no order would ship.
- **Shared-secret comparison**: `hmac.compare_digest` (constant-time) — prevents timing attacks.
- **IP allowlist**: TradingView's published webhook source IPs are pinned in config; override via `TVBRIDGE_TV_ALLOWED_IPS`. Defense-in-depth alongside the secret.
- **Rate limit**: PR 2 will wire 60 req/min default.

## See also

- `SKILL.md` (this repo) — parent skill
- [`broomva/finance-substrate`](https://github.com/broomva/finance-substrate) — tax substrate layer
- [Broker selection ADR](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-22-broker-selection-cross-asset.html)
- [Linear ticket BRO-167](https://github.com/broomva/workspace/blob/main/tasks/bro-167-cross-asset-trading-platform.md)
