# Whales

> Track large trades (whale activity)

## Overview

Track large trades (whale activity).

## Usage

### CLI

```bash
polyterm whales [options]
```

### TUI

In the TUI main menu, use any of these shortcuts: `3`, `w`


## Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--min-amount` | int | `10000` | Minimum trade size to track |
| `--market` | string | `none` | Filter by market ID |
| `--hours` | int | `24` | Hours of history to check |
| `--limit` | int | `20` | Maximum number of trades to show |
| `--wallets` | flag | `false` | Show wallet-level whale trades from the public Data API trade tape |
| `--local` | flag | `false` | With `--wallets`, use only the local observed-trades database |
| `--format` | ['table', 'json'] | `table` | Output format |

## Examples

```bash
# Basic usage
polyterm whales

# With min-amount option
polyterm whales --min-amount 10000

# JSON output
polyterm whales --format json
```

## Data Sources

- Gamma Markets REST API
- CLOB REST API
- WebSocket real-time feed


## Related Commands

- [Follow](follow.md)
- [Wallets](wallets.md)
- [Clusters](clusters.md)
- [Attribution](attribution.md)
- [Groups](groups.md)

---

*Source: `polyterm/cli/commands/whales.py`*

## June 2026 Wallet-Level Mode

`polyterm whales --wallets` exposes wallet-level whale activity from the public Polymarket Data API trade tape. This mode is intended for whale watchers and agents that need wallet addresses instead of only high-volume market proxies.

```bash
polyterm whales --wallets --min-amount 100000 --hours 72 --limit 5 --format json
```

The wallet mode calls Data API `/trades` with `filterType=CASH` and `filterAmount=<min-amount>`, then filters by timestamp and returns both top trades and wallet rollups. Its JSON output includes wallet address, trade count, notional value, largest trade, top markets, rows/pages scanned, and quality flags.

Use `--local` only when you explicitly want the older local SQLite observed-trades cache:

```bash
polyterm whales --wallets --local --min-amount 50000 --hours 24 --format json
```
