# Market Utilities

> Shared helpers for normalizing Polymarket market identifiers and market metadata.

## Overview

`polyterm.api.market_utils` keeps endpoint-specific identifier handling out of command modules and API clients. Polymarket exposes several related identifiers: Gamma numeric market IDs, Gamma slugs, CLOB condition IDs, and CLOB outcome token IDs. CLOB order book and price endpoints require token IDs, while Gamma market lookup uses numeric IDs or `/markets/slug/{slug}` for slugs.

## Functions

| Function | Signature | Description |
|---|---|---|
| `parse_list_field` | `(value: Any) -> List[Any]` | Parses fields that may arrive as JSON strings or native lists |
| `get_clob_token_ids` | `(market: Dict[str, Any]) -> List[str]` | Extracts token IDs from Gamma `clobTokenIds` or CLOB sampling `tokens` |
| `get_primary_clob_token_id` | `(market: Dict[str, Any]) -> Optional[str]` | Returns the first token ID for YES-side price/orderbook lookups |
| `get_market_condition_id` | `(market: Dict[str, Any]) -> Optional[str]` | Extracts the CLOB condition ID / market hash |
| `looks_like_slug` | `(identifier: str) -> bool` | Distinguishes slug-like identifiers from numeric IDs and condition IDs |
| `market_probability_price` | `(market: Dict[str, Any]) -> float` | Derives a current price from documented market metadata fields |

## Data Flow

1. Gamma clients fetch market metadata using ID or slug routes.
2. Callers pass the market dict to `get_clob_token_ids` before hitting CLOB token-only endpoints such as `/book`, `/price`, `/spread`, and `/fee-rate`.
3. Scanner and aggregator code use `market_probability_price` as a metadata-based fallback when no CLOB token can be resolved.

## Related

- [Gamma API](gamma.md)
- [CLOB API](clob.md)
- [Data API](data_api.md)
