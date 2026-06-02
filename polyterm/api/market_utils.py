"""Helpers for normalizing Polymarket market identifiers."""

import json
from typing import Any, Dict, List, Optional


def parse_list_field(value: Any) -> List[Any]:
    """Return list data from Gamma fields that may arrive as JSON strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [value] if value else []
        return parsed if isinstance(parsed, list) else []
    return []


def get_clob_token_ids(market: Dict[str, Any]) -> List[str]:
    """Extract CLOB token IDs from Gamma or CLOB sampling market shapes."""
    token_ids: List[str] = []

    for token_id in parse_list_field(market.get("clobTokenIds")):
        if token_id:
            token_ids.append(str(token_id))

    for token in market.get("tokens", []) or []:
        if isinstance(token, dict):
            token_id = token.get("token_id") or token.get("tokenId") or token.get("asset_id")
            if token_id:
                token_ids.append(str(token_id))

    seen = set()
    unique_ids = []
    for token_id in token_ids:
        if token_id not in seen:
            unique_ids.append(token_id)
            seen.add(token_id)
    return unique_ids


def get_primary_clob_token_id(market: Dict[str, Any]) -> Optional[str]:
    """Return the first CLOB token ID for YES-side style price lookups."""
    token_ids = get_clob_token_ids(market)
    return token_ids[0] if token_ids else None


def get_market_condition_id(market: Dict[str, Any]) -> Optional[str]:
    """Return the CLOB condition ID/market hash when present."""
    value = (
        market.get("conditionId")
        or market.get("condition_id")
        or market.get("market")
        or market.get("market_id")
    )
    return str(value) if value else None


def looks_like_slug(identifier: str) -> bool:
    """Heuristic for Gamma slug routes versus numeric IDs/condition IDs."""
    identifier = str(identifier)
    if identifier.startswith("0x"):
        return False
    if identifier.isdigit():
        return False
    return "-" in identifier


def market_probability_price(market: Dict[str, Any]) -> float:
    """Best-effort current YES price from documented Gamma market fields."""
    outcome_prices = parse_list_field(market.get("outcomePrices"))
    if outcome_prices:
        try:
            return float(outcome_prices[0])
        except (TypeError, ValueError):
            pass

    for key in ("lastTradePrice", "last_trade_price", "bestAsk", "bestBid", "price"):
        value = market.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0
