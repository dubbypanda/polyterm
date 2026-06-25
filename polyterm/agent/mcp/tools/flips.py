"""CLOB-backed market flip detection for agent adapters."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ...contracts import envelope
from ....api.clob import CLOBClient
from ....api.gamma import GammaClient
from ....api.market_utils import get_clob_token_ids, get_market_condition_id
from ....utils.json_output import safe_float


def market_flips(
    hours: int = 72,
    limit: int = 3,
    min_volume: float = 500,
    min_liquidity: float = 0,
    direction: str = "both",
    active_only: bool = True,
    sample_size: int = 5000,
    rank_by: str = "largest_crossing_move",
) -> dict:
    """Return markets whose YES price crossed 50% in a CLOB history window."""
    safe_hours = max(int(hours), 1)
    safe_limit = min(max(int(limit), 1), 50)
    safe_sample_size = min(max(int(sample_size), safe_limit), 5000)
    direction_filter = _normalize_direction(direction)
    rank_mode = _normalize_rank(rank_by)
    start_ts, end_ts = _build_time_bounds(safe_hours)
    interval, fidelity = _select_clob_granularity(safe_hours)

    gamma = GammaClient()
    clob = CLOBClient()
    scanned_markets = 0
    candidate_count = 0
    skipped = {
        "missing_clob_token_id": 0,
        "missing_price_history": 0,
        "no_50_percent_crossing": 0,
    }

    try:
        markets = gamma.get_markets(
            limit=safe_sample_size,
            active=True if active_only else None,
            closed=False if active_only else None,
        )
        flips = []
        for market in markets if isinstance(markets, list) else []:
            scanned_markets += 1
            summary = _market_summary(market)
            if summary["volume_24h"] < min_volume or summary["liquidity"] < min_liquidity:
                continue
            candidate_count += 1

            token_id = summary["clob_token_id"]
            if not token_id:
                skipped["missing_clob_token_id"] += 1
                continue

            history = _price_history(clob, token_id, interval, fidelity, start_ts, end_ts)
            if len(history) < 2:
                skipped["missing_price_history"] += 1
                continue

            flip = _detect_flip(history, direction_filter)
            if flip is None:
                skipped["no_50_percent_crossing"] += 1
                continue

            orderbook = _orderbook_summary(clob, token_id)
            flips.append({
                **summary,
                **flip,
                **orderbook,
                "hours": safe_hours,
                "history_points": len(history),
                "window_start": start_ts,
                "window_start_iso": _timestamp_iso(start_ts),
                "window_end": end_ts,
                "window_end_iso": _timestamp_iso(end_ts),
                "quality_flags": _quality_flags(history, orderbook, summary),
            })

        flips.sort(key=_rank_key(rank_mode), reverse=rank_mode != "near_50_after_flip")
        rows = [{**row, "rank": index + 1} for index, row in enumerate(flips[:safe_limit])]
        return envelope(
            {
                "hours": safe_hours,
                "limit": safe_limit,
                "min_volume": min_volume,
                "min_liquidity": min_liquidity,
                "direction": direction_filter,
                "rank_by": rank_mode,
                "active_only": active_only,
                "sample_size": safe_sample_size,
                "window_start": start_ts,
                "window_start_iso": _timestamp_iso(start_ts),
                "window_end": end_ts,
                "window_end_iso": _timestamp_iso(end_ts),
                "scanned_markets": scanned_markets,
                "candidate_count": candidate_count,
                "confirmed_flips": len(flips),
                "count": len(rows),
                "markets": rows,
                "skipped": skipped,
                "quality_flags": [
                    "live_gamma_data",
                    "live_clob_price_history",
                    "explicit_start_end_window",
                    "crossing_detected_at_50_percent",
                ],
            },
            meta={"tool": "market.flips"},
        )
    finally:
        gamma.close()
        clob.close()


def _market_summary(market: Dict[str, Any]) -> Dict[str, Any]:
    token_ids = get_clob_token_ids(market)
    return {
        "gamma_market_id": str(market.get("id") or ""),
        "gamma_slug": market.get("slug") or "",
        "condition_id": get_market_condition_id(market),
        "clob_token_id": token_ids[0] if token_ids else "",
        "clob_token_ids": token_ids,
        "question": market.get("question") or market.get("title") or "",
        "event_slug": market.get("event_slug") or market.get("eventSlug") or "",
        "volume_24h": safe_float(market.get("volume24hr") or market.get("volume24h")),
        "volume": safe_float(market.get("volume")),
        "liquidity": safe_float(market.get("liquidity")),
        "active": bool(market.get("active", True)),
        "closed": bool(market.get("closed", False)),
    }


def _price_history(
    clob: CLOBClient,
    token_id: str,
    interval: str,
    fidelity: int,
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, Any]]:
    try:
        raw = clob.get_price_history(
            token_id,
            interval=interval,
            fidelity=fidelity,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception:
        return []

    rows = []
    for point in raw if isinstance(raw, list) else []:
        timestamp = _extract_timestamp(point)
        price = _extract_price(point)
        if timestamp is None or price is None:
            continue
        if start_ts <= timestamp <= end_ts:
            rows.append({"timestamp": timestamp, "price": price})
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def _detect_flip(history: List[Dict[str, Any]], direction: str) -> Optional[Dict[str, Any]]:
    start_price = history[0]["price"]
    end_price = history[-1]["price"]
    crossings = []
    for previous, current in zip(history, history[1:]):
        prev_price = previous["price"]
        curr_price = current["price"]
        if prev_price < 0.5 <= curr_price:
            crossings.append(_crossing_row(previous, current, "above"))
        elif prev_price > 0.5 >= curr_price:
            crossings.append(_crossing_row(previous, current, "below"))

    if direction != "both":
        crossings = [row for row in crossings if row["crossing_direction"] == direction]
    if not crossings:
        return None

    crossing = crossings[-1]
    prices = [row["price"] for row in history]
    absolute_change = end_price - start_price
    return {
        **crossing,
        "start_price": round(start_price, 4),
        "end_price": round(end_price, 4),
        "absolute_change": round(absolute_change, 4),
        "absolute_change_points": round(absolute_change * 100, 2),
        "largest_crossing_move": round(abs(absolute_change), 4),
        "min_price": round(min(prices), 4),
        "max_price": round(max(prices), 4),
        "crossings_in_window": len(crossings),
    }


def _crossing_row(previous: Dict[str, Any], current: Dict[str, Any], direction: str) -> Dict[str, Any]:
    timestamp = _estimate_crossing_ts(previous, current)
    return {
        "crossing_direction": direction,
        "crossing_timestamp": timestamp,
        "crossing_timestamp_iso": _timestamp_iso(timestamp),
        "crossing_from_price": round(previous["price"], 4),
        "crossing_to_price": round(current["price"], 4),
    }


def _estimate_crossing_ts(previous: Dict[str, Any], current: Dict[str, Any]) -> int:
    prev_price = previous["price"]
    curr_price = current["price"]
    prev_ts = previous["timestamp"]
    curr_ts = current["timestamp"]
    if curr_price == prev_price:
        return int(curr_ts)
    ratio = (0.5 - prev_price) / (curr_price - prev_price)
    ratio = min(max(ratio, 0.0), 1.0)
    return int(prev_ts + ((curr_ts - prev_ts) * ratio))


def _orderbook_summary(clob: CLOBClient, token_id: str) -> Dict[str, Any]:
    try:
        book = clob.get_order_book(token_id, depth=20)
    except Exception:
        return {
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "thin_or_illiquid": True,
            "orderbook_available": False,
        }
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    best_bid = _book_price(bids[0]) if bids else None
    best_ask = _book_price(asks[0]) if asks else None
    spread = round(best_ask - best_bid, 4) if best_bid is not None and best_ask is not None else None
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "thin_or_illiquid": spread is None or spread > 0.1 or len(bids) < 2 or len(asks) < 2,
        "orderbook_available": True,
    }


def _quality_flags(
    history: List[Dict[str, Any]],
    orderbook: Dict[str, Any],
    market: Dict[str, Any],
) -> List[str]:
    flags = ["explicit_start_end_window", "clob_price_history_crossed_50_percent"]
    if history:
        flags.append("price_history_available")
    if orderbook.get("orderbook_available"):
        flags.append("orderbook_available")
    if orderbook.get("thin_or_illiquid"):
        flags.append("thin_or_illiquid")
    if market["volume_24h"] <= 0:
        flags.append("missing_or_zero_24h_volume")
    if market["liquidity"] <= 0:
        flags.append("missing_or_zero_liquidity")
    return flags


def _rank_key(rank_by: str):
    if rank_by == "highest_24h_volume":
        return lambda row: row["volume_24h"]
    if rank_by == "highest_liquidity":
        return lambda row: row["liquidity"]
    if rank_by == "freshest_cross":
        return lambda row: row["crossing_timestamp"]
    if rank_by == "near_50_after_flip":
        return lambda row: abs(row["end_price"] - 0.5)
    return lambda row: row["largest_crossing_move"]


def _normalize_direction(direction: str) -> str:
    value = str(direction or "both").lower().strip()
    if value in {"up", "above", "yes_above", "flipped_above"}:
        return "above"
    if value in {"down", "below", "yes_below", "flipped_below"}:
        return "below"
    return "both"


def _normalize_rank(rank_by: str) -> str:
    value = str(rank_by or "").lower().strip()
    allowed = {
        "largest_crossing_move",
        "highest_24h_volume",
        "highest_liquidity",
        "freshest_cross",
        "near_50_after_flip",
    }
    return value if value in allowed else "largest_crossing_move"


def _build_time_bounds(hours: int) -> Tuple[int, int]:
    end_ts = int(datetime.now(timezone.utc).timestamp())
    return end_ts - (hours * 3600), end_ts


def _select_clob_granularity(hours: int) -> Tuple[str, int]:
    if hours <= 1:
        return "1h", 60
    if hours <= 6:
        return "6h", 60
    if hours <= 24:
        return "1d", 300
    return "max", 3600


def _extract_timestamp(point: Dict[str, Any]) -> Optional[int]:
    for key in ("t", "timestamp", "time"):
        if key not in point:
            continue
        try:
            return int(float(point[key]))
        except (TypeError, ValueError):
            continue
    return None


def _extract_price(point: Dict[str, Any]) -> Optional[float]:
    for key in ("p", "price", "value"):
        if key not in point:
            continue
        try:
            return float(point[key])
        except (TypeError, ValueError):
            continue
    return None


def _book_price(row: Dict[str, Any]) -> Optional[float]:
    try:
        return round(float(row.get("price")), 4)
    except (AttributeError, TypeError, ValueError):
        return None


def _timestamp_iso(timestamp: int) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
