# CLOBClient

> CLOB (Central Limit Order Book) REST and WebSocket client for order books, trades, price history, and real-time data.

## Overview

The `CLOBClient` class provides access to Polymarket's CLOB V2 API via REST endpoints and the public CLOB market WebSocket. The production REST host remains `https://clob.polymarket.com`. The REST interface covers order books, price history, price/spread/last-trade helpers, fee-rate lookup, sampling markets, and order-book-derived depth. The CLOB market WebSocket streams live trade executions, order book updates, price changes, and market resolution events. The client includes a two-tier supervisor pattern for WebSocket resilience.

## Key Classes and Functions

### `CLOBClient`

Client for the Polymarket CLOB API, managing both REST requests and WebSocket connections.

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rest_endpoint` | `str` | `"https://clob.polymarket.com"` | CLOB REST API base URL |
| `ws_endpoint` | `str` | `"wss://ws-subscriptions-clob.polymarket.com/ws/market"` | CLOB market WebSocket URL for trade feeds |

#### Instance Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `session` | `requests.Session` | Persistent HTTP session for REST calls |
| `ws_connection` | WebSocket or `None` | CLOB market WebSocket connection |
| `clob_ws` | WebSocket or `None` | CLOB order book WebSocket connection |
| `subscriptions` | `dict` | Map of market slugs to trade callbacks |
| `_ws_permanently_failed` | `bool` | Set to `True` when supervisor exhausts all retries |

#### REST Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_price_history` | `(token_id: str, interval: str = "1h", fidelity: int = 60, start_ts: Optional[int] = None, end_ts: Optional[int] = None) -> List[Dict[str, Any]]` | Get historical price data points |
| `get_order_book` | `(token_id: str, depth: int = 20) -> Dict[str, Any]` | Get order book (bids and asks) for a token |
| `get_price` | `(token_id: str, side: str = "BUY") -> Dict[str, Any]` | Get current CLOB V2 price for a token and side |
| `get_spread` | `(token_id: str) -> Dict[str, Any]` | Get current spread for a token |
| `get_last_trade_price` | `(token_id: str) -> Dict[str, Any]` | Get latest trade price and side for a token |
| `get_fee_rate` | `(token_id: str) -> Dict[str, Any]` | Get CLOB fee-rate metadata for a token |
| `get_ticker` | `(token_id: str) -> Dict[str, Any]` | Compatibility helper composed from V2 last-trade and spread endpoints |
| `get_recent_trades` | `(market: str, limit: int = 100) -> List[Dict[str, Any]]` | Authenticated CLOB `/trades` compatibility helper; public history should use Data API `/trades` |
| `get_market_depth` | `(token_id: str) -> Dict[str, Any]` | Derive depth statistics from `/book` |
| `get_current_markets` | `(limit: int = 100) -> List[Dict[str, Any]]` | Get active markets via paginated `/sampling-markets` endpoint |
| `calculate_spread` | `(order_book: Dict[str, Any]) -> float` | Calculate bid-ask spread percentage from order book data |
| `is_market_current` | `(market: Dict[str, Any]) -> bool` | Check if a market is current (future end date, not closed) |
| `detect_large_trade` | `(trade: Dict[str, Any], threshold: float = 10000) -> bool` | Detect whale trades by notional value |

#### CLOB Market WebSocket Methods (Trade Feeds)

| Method | Signature | Description |
|--------|-----------|-------------|
| `connect_websocket` | `() -> bool` | Connect to the CLOB market WebSocket |
| `subscribe_to_trades` | `(token_ids: List[str], callback: Callable) -> None` | Subscribe to trade feeds for explicit CLOB token IDs |
| `listen_for_trades` | `(max_reconnects: int = 5, message_timeout: float = 30.0, on_error: Optional[Callable] = None, supervisor_retries: int = 3, supervisor_cooldown: float = 60.0) -> None` | Listen with two-tier supervisor resilience |

#### CLOB Order Book WebSocket Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `connect_clob_websocket` | `() -> bool` | Connect to CLOB order book WebSocket |
| `subscribe_orderbook` | `(token_ids: list, callback: Callable, resolution_callback: Optional[Callable] = None) -> None` | Subscribe to real-time order book updates |
| `listen_orderbook` | `(max_reconnects: int = 5, message_timeout: float = 60.0) -> None` | Listen for order book messages with reconnection |

#### Lifecycle Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `close_websocket` | `() -> None` | Close all WebSocket connections and clear subscriptions (async) |
| `close` | `() -> None` | Close REST session and best-effort close WebSockets (sync) |

## API Endpoints Used

### REST Endpoints (base: `https://clob.polymarket.com`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/prices-history` | GET | Historical price data. Params: `market`, `interval`, `fidelity`, `startTs`, `endTs` |
| `/book` | GET | Order book for a token. Params: `token_id` |
| `/price` | GET | Current price. Params: `token_id`, `side` |
| `/spread` | GET | Current spread. Params: `token_id` |
| `/last-trade-price` | GET | Latest trade price. Params: `token_id` |
| `/fee-rate` | GET | Fee-rate metadata. Params: `token_id` |
| `/trades` | GET | Recent/user trades when available. Params include `market`, `limit`, `maker_address`, `asset_id` |
| `/sampling-markets` | GET | Currently active markets. Params: `limit`, `next_cursor` |

### WebSocket Endpoints

| URL | Protocol | Description |
|-----|----------|-------------|
| `wss://ws-subscriptions-clob.polymarket.com/ws/market` | CLOB WS | Real-time trade executions, order book updates, price changes, and market resolution |

## Configuration

- Default REST timeout: 15 seconds per request
- Default retry count: 3 attempts per request
- No API key required for public endpoints

## Rate Limiting / Error Handling

### REST Retry Logic

The `_request` method implements exponential backoff with retry:

| Condition | Behavior |
|-----------|----------|
| HTTP 429 (rate limited) | Wait `min(2^attempt * 2, 30)` seconds; respects `Retry-After` header (capped at 60s) |
| HTTP 5xx (server error) | Wait `2^attempt` seconds, retry up to `retries - 1` times |
| Timeout | Wait `2^attempt` seconds, retry; raise on final attempt |
| Connection error | Wait `2^attempt` seconds, retry; raise on final attempt |

### WebSocket Resilience

**CLOB Market Trade Feed -- Two-Tier Supervisor:**

| Tier | Parameter | Default | Description |
|------|-----------|---------|-------------|
| Inner loop | `max_reconnects` | 5 | Reconnect attempts per supervisor cycle |
| Inner loop | `message_timeout` | 30.0s | Force reconnect if no message received |
| Outer supervisor | `supervisor_retries` | 3 | Total supervisor restart cycles |
| Outer supervisor | `supervisor_cooldown` | 60.0s | Wait between supervisor restarts |

- Reconnect counter resets to 0 on each successful message
- Exponential backoff on reconnects: `min(2^attempt, 30)` seconds
- Sets `_ws_permanently_failed = True` and calls `on_error` callback when supervisor is exhausted

**CLOB Order Book WebSocket:**

- Single-tier reconnect loop with `max_reconnects` (default 5) and `message_timeout` (default 60s)
- Resubscribes to stored token IDs on reconnect
- Clears callbacks when max reconnects exhausted

## WebSocket Protocols

### CLOB Market Trade Feed

**Subscribe message:**
```json
{
    "assets_ids": ["<token_id_1>", "<token_id_2>"],
    "type": "market",
    "custom_feature_enabled": true
}
```

**Incoming message types:**
- `PING` -- respond with `PONG`
- Trade messages with `event_type: "last_trade_price"` containing `asset_id`, `market`, `price`, `size`, and `side`
- Callbacks are matched by subscribed token ID; legacy RTDS-shaped messages are still parsed for explicit non-default configurations

### CLOB Order Book WebSocket

**Subscribe message:**
```json
{
    "assets_ids": ["<token_id_1>", "<token_id_2>"],
    "type": "market",
    "custom_feature_enabled": true
}
```

**Incoming message types:**

| Type | Description | Callback |
|------|-------------|----------|
| `book` | Full or partial order book update | `_ob_callback` |
| `last_trade_price` | Latest trade price | `_ob_callback` |
| `price_change` | Market price movement | `_ob_callback` |
| `tick_size_change` | Tick size update | `_ob_callback` |
| `market_resolved` | Market settlement with outcome and winning price | `_ob_resolution_callback` |

Setting `custom_feature_enabled: true` enables `market_resolved` events for real-time settlement detection.

## Data Flow

1. **REST**: Caller invokes a method -> `_request` applies retry/backoff -> returns parsed JSON.
2. **CLOB market trades**: `connect_websocket` -> `subscribe_to_trades` (registers callbacks by token ID) -> `listen_for_trades` (supervisor loop dispatches `last_trade_price` events).
3. **Order book**: `connect_clob_websocket` -> `subscribe_orderbook` (registers callbacks and token IDs) -> `listen_orderbook` (dispatches `book`/`price_change` to callback, `market_resolved` to resolution callback).
4. **Fallback path**: When `_ws_permanently_failed` is set, upstream consumers can switch to REST/Data API polling where supported. Data API `/trades` is the public source for historical trade polling.

## External Dependencies

- `requests` -- HTTP client for REST calls
- `websockets` (optional) -- async WebSocket library; guarded by `HAS_WEBSOCKETS` flag
- `python-dateutil` (optional) -- date parsing; guarded by `HAS_DATEUTIL` flag
- `asyncio` -- event loop for WebSocket operations

## Related

- **CLI commands**: `orderbook` (live order book display), `chart` (price history), `monitor`, `live_monitor`, `whales`, `arbitrage`, `negrisk`, `crypto15m`, `quicktrade`, `trade`, `fees`, `depth`, `spread`, `volume`, `watch`, `replay`, `sentiment`, `compare`, `mywallet`, `ladder`, `liquidity`, `portfolio`, `export_cmd`, `timing`
- **TUI screens**: `orderbook_screen.py` (live order book with Rich Live rendering), `analytics.py`, `live_monitor.py`
- **Core modules**: `core/orderbook.py` (`LiveOrderBook` consumes CLOB WS), `core/whale_tracker.py` (uses CLOB WS + Data API fallback), `core/arbitrage.py` (live WS prices), `core/scanner.py`, `core/negrisk.py`, `core/historical.py`, `core/analytics.py`
- **Aggregator**: `APIAggregator` uses `CLOBClient` as fallback source and for order book enrichment
