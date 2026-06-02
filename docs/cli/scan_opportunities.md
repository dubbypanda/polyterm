# Scan Opportunities

`polyterm scan-opportunities` runs a one-shot, agent-friendly market scan.
It is designed for workflows where an agent needs a ranked list of markets
that deserve research, not a long-running terminal monitor.

## Purpose

The command scans active Polymarket markets and ranks them using simple,
explainable signals:

- recent YES price movement
- 24 hour volume
- market liquidity
- local archive freshness
- available whale or smart-money context

The result is a research queue. It does not place trades, submit orders,
manage funds, or mutate external market state.

## Basic Usage

```bash
polyterm scan-opportunities --query bitcoin
```

The default output is a compact table with score, market title, probability,
recent change, volume, and signal labels.

## JSON Usage

```bash
polyterm scan-opportunities --query bitcoin --limit 5 --format json
```

JSON mode returns the stable PolyTerm agent envelope:

```json
{
  "schema_version": "2026-06-02",
  "success": true,
  "data": {
    "query": "bitcoin",
    "opportunities": []
  },
  "error": null,
  "meta": {
    "tool": "scan.opportunities"
  }
}
```

## Options

`--query` filters the live market universe through Gamma search. If omitted,
PolyTerm scans the active market feed when the configured API client supports
it.

`--limit` controls how many ranked opportunities are returned.

`--min-volume` sets the threshold for volume-related scoring.

`--min-liquidity` sets the threshold for liquidity-related scoring.

`--max-archive-age-hours` controls when local research archive evidence is
considered stale.

`--format json` emits machine-readable output suitable for MCP and automation.

## Scoring

The score is intentionally transparent rather than predictive. Large recent
price moves add movement signal. Markets above the configured volume and
liquidity thresholds add market-quality signal. Missing or stale archive
coverage adds a refresh signal because the market may need a new research
brief before an agent can make a well-supported claim.

Scores are relative within a scan result. A high score means the market is
worth investigating first, not that the market is a profitable trade.

## Signals

`fresh_move` means the current YES probability moved substantially from the
previous available price.

`moderate_move` means the move is notable but below the stronger movement
threshold.

`volume_threshold_met` means reported 24 hour volume is above the configured
minimum.

`liquid_enough` means reported liquidity is above the configured minimum.

`archive_refresh_needed` means local evidence is stale or missing.

`thin_market` means volume and liquidity are both below the configured
thresholds, so any apparent edge needs extra caution.

## Recommended Workflow

Use this command to build a short research queue:

```bash
polyterm scan-opportunities --query crypto --limit 10 --format json
polyterm research --market <slug-or-title> --persist --format json
polyterm explain-move --market <slug-or-title> --format json
polyterm compare -m <market-a> -m <market-b> --format json
```

Agents should treat scan results as triage. The next step for a promising
result is usually `market.research` with persistence enabled, followed by
`market.explain_move` when the score is driven by price movement.

## Safety

The command is read-only. It reads live public market data and local archive
state. It does not create alerts, write research briefs, execute trades, or
change Polymarket state.

## Data Caveats

Gamma fields can be sparse or delayed. Price movement uses the previous YES
price field when available. Archive freshness only reflects local PolyTerm
SQLite data. Whale context is used only when the market payload includes a
public signal or prior cached evidence exposes one.
