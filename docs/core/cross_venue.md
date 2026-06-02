# Cross Venue

> Cross-venue hedge and arbitrage monitoring.

## Overview

`polyterm/core/cross_venue.py` normalizes Polymarket and external venue markets so PolyTerm can detect hedge or arbitrage candidates. The first implementation supports Polymarket and a read-only Kalshi public market lookup.

The monitor is read-only. It does not place trades, open positions, or manage credentials.

## Usage

### CLI

```bash
polyterm arbitrage --venues polymarket,kalshi --query bitcoin --format json
polyterm arbitrage --venues polymarket,kalshi --query election
```

### Python

```python
from polyterm.core.cross_venue import CrossVenueMonitor

monitor = CrossVenueMonitor()
result = monitor.scan("bitcoin", venues=["polymarket", "kalshi"])
```

## Public API

| Method | Description |
|--------|-------------|
| `scan(query, min_spread, venues, limit)` | Return matched cross-venue opportunities. |

## How It Works

The monitor fetches Polymarket markets through Gamma and external markets through a venue adapter. It normalizes each market into `VenueMarket`, compares titles with a simple token-overlap score, and reports spreads when the match confidence and price gap pass thresholds.

Each opportunity includes fee-adjusted spread, match confidence, spread confidence, execution caveats, resolution caveats, and quality flags so traders and agents can avoid overtrusting loose text matches.

## Data Sources

- Gamma API for Polymarket markets.
- Kalshi public market endpoint for read-only external venue candidates.

## Quality Flags

Cross-venue output can include:

- `manual_review_match`
- `stale_external_data`
- `fee_estimate_only`
- `venue_mismatch`
- `resolution_mismatch_possible`
- `fees_may_consume_spread`
- `no_trade_execution`

Agents should treat low-confidence matches as research leads, not executable instructions. `execution_caveats` explains fee, slippage, fill, venue, custody, and stale-data limits. `resolution_caveats` calls out cases where titles match loosely but resolution criteria may not be equivalent.

## Identifier Requirements

Polymarket rows include Gamma IDs and slugs where available. External venue rows include venue-specific IDs such as Kalshi tickers. These identifiers are not interchangeable.

## Verification

```bash
polyterm arbitrage --venues polymarket,kalshi --query bitcoin --format json
```

Mock external venue responses in focused tests to avoid depending on live Kalshi availability.

## Related Features

- [Arbitrage CLI](../cli/arbitrage.md)
- [Arbitrage Core](arbitrage.md)
- [Alert Engine](alert_engine.md)
- [Agent Mode](../AGENT_MODE.md)
