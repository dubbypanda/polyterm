"""Market tools for agent adapters."""

from datetime import datetime, timezone

from ...contracts import envelope
from ....api.clob import CLOBClient
from ....api.gamma import GammaClient
from ....api.market_utils import get_clob_token_ids, get_market_condition_id, market_probability_price
from ....core.market_compare import MarketComparisonEngine
from ....core.market_move import MarketMoveExplainer
from ....core.market_research import MarketResearchEngine
from ....core.orderbook import OrderBookAnalyzer
from ....utils.json_output import format_orderbook_json


def search(query: str, limit: int = 10) -> dict:
    gamma = GammaClient()
    try:
        markets = gamma.search_markets(query, limit=limit)
        return envelope({"query": query, "count": len(markets), "markets": markets}, meta={"tool": "market.search"})
    finally:
        gamma.close()


def resolve(identifier: str) -> dict:
    gamma = GammaClient()
    try:
        try:
            market = gamma.get_market(identifier)
        except Exception:
            results = gamma.search_markets(identifier, limit=5)
            market = next(
                (item for item in results if _is_current_market(item)),
                results[0] if results else {},
            )

        data = {
            "input": identifier,
            "market": market,
            "gamma_market_id": market.get("id"),
            "gamma_slug": market.get("slug"),
            "condition_id": get_market_condition_id(market),
            "clob_token_ids": get_clob_token_ids(market),
            "probability": market_probability_price(market),
        }
        return envelope(data, meta={"tool": "market.resolve"})
    finally:
        gamma.close()


def orderbook(token_id: str, depth: int = 20) -> dict:
    clob = CLOBClient()
    try:
        analyzer = OrderBookAnalyzer(clob)
        analysis = analyzer.analyze(token_id, depth=depth)
        return envelope(
            {
                "token_id": token_id,
                "depth": depth,
                "analysis": format_orderbook_json(analysis) if analysis else None,
                "quality_flags": ["clob_orderbook"] if analysis else ["orderbook_unavailable"],
            },
            meta={"tool": "market.orderbook"},
        )
    finally:
        clob.close()


def price_history(market: str, hours: int = 24) -> dict:
    gamma = GammaClient()
    clob = CLOBClient()
    try:
        selected = _resolve_market(gamma, market)
        token_ids = get_clob_token_ids(selected)
        interval, fidelity = _select_clob_granularity(hours)
        start_ts, end_ts = _build_time_bounds(hours)
        points = []
        quality_flags = ["clob_price_history"]
        if token_ids:
            history = clob.get_price_history(
                token_ids[0],
                interval=interval,
                fidelity=fidelity,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            for row in history or []:
                if "t" not in row or "p" not in row:
                    continue
                timestamp = int(float(row["t"]))
                if start_ts <= timestamp <= end_ts:
                    points.append({"timestamp": datetime.fromtimestamp(timestamp).isoformat(), "price": float(row["p"])})
        else:
            quality_flags.append("missing_token_ids")

        points.sort(key=lambda row: row["timestamp"])
        if not points:
            quality_flags.append("price_history_unavailable")

        return envelope(
            {
                "market": market,
                "gamma_market_id": selected.get("id"),
                "slug": selected.get("slug"),
                "condition_id": get_market_condition_id(selected),
                "clob_token_ids": token_ids,
                "title": selected.get("question") or selected.get("title") or "",
                "hours": hours,
                "data_points": len(points),
                "prices": points,
                "quality_flags": quality_flags,
            },
            meta={"tool": "market.price_history"},
        )
    finally:
        gamma.close()
        clob.close()


def research(
    market: str,
    prefetch_whales: bool = False,
    min_notional: float = 100000,
    hours: int = 72,
    limit: int = 5,
    persist: bool = False,
) -> dict:
    engine = MarketResearchEngine()
    return envelope(
        engine.build(
            market,
            prefetch_whales=prefetch_whales,
            min_notional=min_notional,
            hours=hours,
            limit=limit,
            persist=persist,
        ),
        meta={"tool": "market.research"},
    )


def explain_move(market: str, hours: int = 24) -> dict:
    engine = MarketMoveExplainer()
    return envelope(engine.explain(market, hours=hours), meta={"tool": "market.explain_move"})


def compare(markets: list[str], hours: int = 24) -> dict:
    engine = MarketComparisonEngine()
    return envelope(engine.compare(markets, hours=hours), meta={"tool": "market.compare"})


def _resolve_market(gamma: GammaClient, market: str) -> dict:
    try:
        data = gamma.get_market(market)
        if data:
            return data
    except Exception:
        pass
    results = gamma.search_markets(market, limit=5)
    return next((item for item in results if _is_current_market(item)), results[0] if results else {})


def _select_clob_granularity(hours: int):
    if hours <= 1:
        return "1h", 60
    if hours <= 6:
        return "6h", 60
    if hours <= 24:
        return "1d", 300
    return "max", 3600


def _build_time_bounds(hours: int):
    safe_hours = max(int(hours), 1)
    end_ts = int(datetime.now().timestamp())
    return end_ts - (safe_hours * 3600), end_ts


def _is_current_market(market):
    if not market.get("active", True) or market.get("closed", False):
        return False
    end_date = market.get("endDate") or market.get("end_date_iso")
    if not end_date:
        return True
    try:
        parsed = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(timezone.utc)
    except Exception:
        return True
