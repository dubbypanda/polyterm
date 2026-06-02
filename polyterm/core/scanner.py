"""Market scanner for detecting shifts and anomalies"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ..api.gamma import GammaClient
from ..api.clob import CLOBClient
from ..utils.json_output import safe_float
from ..api.aggregator import APIAggregator
from ..api.market_utils import get_primary_clob_token_id, market_probability_price
from .archive import ArchiveCollector


class MarketSnapshot:
    """Snapshot of market data at a point in time"""
    
    def __init__(self, market_id: str, data: Dict[str, Any], timestamp: float):
        self.market_id = market_id
        self.data = data
        self.timestamp = timestamp
        
        # Extract key metrics
        self.probability = data.get("probability", 0.0)
        self.volume = data.get("volume", 0.0)
        self.liquidity = data.get("liquidity", 0.0)
        self.price = data.get("price", 0.0)
        self.title = data.get("title", data.get("question", ""))
        
        # Data source tracking
        self.data_sources = data.get("_data_sources", ["unknown"])
        self.is_fresh = data.get("_is_fresh", True)
        self.market_end_date = data.get("endDate", data.get("end_date_iso", ""))
    
    def calculate_shift(self, previous: "MarketSnapshot") -> Dict[str, float]:
        """Calculate changes from previous snapshot"""
        if not previous:
            return {
                "probability_change": 0.0,
                "volume_change": 0.0,
                "liquidity_change": 0.0,
                "price_change": 0.0,
            }
        
        prob_change = self.probability - previous.probability
        vol_change = ((self.volume - previous.volume) / previous.volume * 100) if previous.volume > 0 else 0
        liq_change = ((self.liquidity - previous.liquidity) / previous.liquidity * 100) if previous.liquidity > 0 else 0
        price_change = ((self.price - previous.price) / previous.price * 100) if previous.price > 0 else 0
        
        return {
            "probability_change": prob_change,
            "volume_change": vol_change,
            "liquidity_change": liq_change,
            "price_change": price_change,
        }


class MarketScanner:
    """Scanner for monitoring market shifts across multiple data sources"""
    
    def __init__(
        self,
        gamma_client: GammaClient,
        clob_client: CLOBClient,
        check_interval: int = 60,
    ):
        self.gamma_client = gamma_client
        self.clob_client = clob_client
        self.check_interval = check_interval

        # Initialize aggregator for live data with fallback
        self.aggregator = APIAggregator(gamma_client, clob_client)
        
        # Storage for market snapshots
        self.snapshots: Dict[str, List[MarketSnapshot]] = {}
        self.max_snapshots_per_market = 100
        
        # Callbacks
        self.shift_callbacks: List[Callable] = []
        
        # State
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # Data validation settings
        self.require_fresh_data = True
        self.max_data_age_hours = 24
    
    def add_shift_callback(self, callback: Callable):
        """Add callback to be called when shift is detected"""
        self.shift_callbacks.append(callback)
    
    def get_market_snapshot(self, market_id: str) -> Optional[MarketSnapshot]:
        """Get aggregated market snapshot from all sources"""
        try:
            # Fetch from multiple sources
            gamma_data = self.gamma_client.get_market(market_id)
            gamma_prices = self.gamma_client.get_market_prices(market_id)
            token_id = get_primary_clob_token_id(gamma_data)
            
            # Get CLOB data
            try:
                clob_ticker = self.clob_client.get_ticker(token_id) if token_id else {}
                clob_book = self.clob_client.get_order_book(token_id) if token_id else {}
            except Exception:
                clob_ticker = {}
                clob_book = {}

            price = safe_float(gamma_prices.get("price", market_probability_price(gamma_data)))

            # Aggregate data
            aggregated_data = {
                "market_id": market_id,
                "title": gamma_data.get("question", ""),
                "probability": price * 100,
                "price": price,
                "volume": safe_float(gamma_data.get("volume", 0)),
                "liquidity": safe_float(gamma_data.get("liquidity", 0)),
                "last_trade_price": safe_float(clob_ticker.get("last", 0)) if clob_ticker else 0,
                "spread": self.clob_client.calculate_spread(clob_book) if clob_book else 0,
            }
            
            return MarketSnapshot(market_id, aggregated_data, time.time())
            
        except Exception as e:
            print(f"Error getting snapshot for {market_id}: {e}")
            return None
    
    def store_snapshot(self, snapshot: MarketSnapshot):
        """Store market snapshot with history limit"""
        if snapshot.market_id not in self.snapshots:
            self.snapshots[snapshot.market_id] = []
        
        self.snapshots[snapshot.market_id].append(snapshot)
        
        # Limit history
        if len(self.snapshots[snapshot.market_id]) > self.max_snapshots_per_market:
            self.snapshots[snapshot.market_id] = self.snapshots[snapshot.market_id][-self.max_snapshots_per_market:]
    
    def get_previous_snapshot(self, market_id: str) -> Optional[MarketSnapshot]:
        """Get previous snapshot for comparison"""
        if market_id not in self.snapshots or len(self.snapshots[market_id]) < 2:
            return None
        return self.snapshots[market_id][-2]
    
    def detect_shift(
        self,
        current: MarketSnapshot,
        previous: Optional[MarketSnapshot],
        thresholds: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """Detect if a significant shift occurred"""
        if not previous:
            return None
        
        changes = current.calculate_shift(previous)
        
        # Check thresholds
        shift_detected = False
        shift_type = []
        
        if abs(changes["probability_change"]) >= thresholds.get("probability", 10.0):
            shift_detected = True
            shift_type.append("probability")
        
        if abs(changes["volume_change"]) >= thresholds.get("volume", 50.0):
            shift_detected = True
            shift_type.append("volume")
        
        if abs(changes["liquidity_change"]) >= thresholds.get("liquidity", 30.0):
            shift_detected = True
            shift_type.append("liquidity")
        
        if shift_detected:
            return {
                "market_id": current.market_id,
                "title": current.title,
                "timestamp": current.timestamp,
                "shift_type": shift_type,
                "changes": changes,
                "current": current.data,
                "previous": previous.data,
            }
        
        return None
    
    def scan_market(
        self,
        market_id: str,
        thresholds: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """Scan a single market for shifts"""
        # Get current snapshot
        current = self.get_market_snapshot(market_id)
        if not current:
            return None
        
        # Get previous snapshot
        previous = self.get_previous_snapshot(market_id)
        
        # Store current snapshot
        self.store_snapshot(current)
        
        # Detect shift
        shift = self.detect_shift(current, previous, thresholds)
        
        if shift:
            # Call callbacks
            for callback in self.shift_callbacks:
                try:
                    callback(shift)
                except Exception as e:
                    print(f"Error in shift callback: {e}")
        
        return shift
    
    def scan_markets(
        self,
        market_ids: List[str],
        thresholds: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """Scan multiple markets concurrently"""
        shifts = []
        
        # Use thread pool for concurrent scanning
        futures = []
        for market_id in market_ids:
            future = self.executor.submit(self.scan_market, market_id, thresholds)
            futures.append(future)
        
        # Collect results
        for future in futures:
            try:
                result = future.result(timeout=10)
                if result:
                    shifts.append(result)
            except Exception as e:
                print(f"Error scanning market: {e}")
        
        return shifts
    
    def scan_all_active_markets(self, thresholds: Dict[str, float]) -> List[Dict[str, Any]]:
        """Scan all active markets (uses aggregator for live data with fallback)"""
        try:
            # Use aggregator to get live markets with validation
            markets = self.aggregator.get_live_markets(
                limit=100,
                require_volume=self.require_fresh_data,
                min_volume=0.01
            )
            
            if not markets:
                print("Warning: No live markets found")
                return []
            
            # Validate data freshness
            validation_report = self.aggregator.validate_data_freshness(markets)
            
            if validation_report['stale_markets'] > 0:
                print(f"Warning: {validation_report['stale_markets']} stale markets detected")
            
            if validation_report.get('issues'):
                for issue in validation_report['issues'][:3]:  # Show first 3 issues
                    print(f"  - {issue}")
            
            market_ids = [m.get("id") for m in markets if m.get("id")]
            return self.scan_markets(market_ids, thresholds)
        except Exception as e:
            print(f"Error scanning all markets: {e}")
            return []
    
    def start_monitoring(
        self,
        market_ids: List[str],
        thresholds: Dict[str, float],
    ):
        """Start continuous monitoring loop"""
        self.running = True
        
        while self.running:
            try:
                shifts = self.scan_markets(market_ids, thresholds)
                
                if shifts:
                    print(f"Detected {len(shifts)} shifts at {datetime.now()}")
                
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(self.check_interval)
    
    def stop_monitoring(self):
        """Stop monitoring loop"""
        self.running = False
    
    def get_market_history(self, market_id: str, hours: int = 24) -> List[MarketSnapshot]:
        """Get historical snapshots for a market"""
        if market_id not in self.snapshots:
            return []
        
        cutoff_time = time.time() - (hours * 3600)
        return [s for s in self.snapshots[market_id] if s.timestamp >= cutoff_time]
    
    def calculate_volatility(self, market_id: str, window: int = 10) -> float:
        """Calculate volatility (standard deviation of probability changes)"""
        if market_id not in self.snapshots or len(self.snapshots[market_id]) < window:
            return 0.0
        
        recent_snapshots = self.snapshots[market_id][-window:]
        prob_changes = []
        
        for i in range(1, len(recent_snapshots)):
            change = recent_snapshots[i].probability - recent_snapshots[i-1].probability
            prob_changes.append(change)
        
        if not prob_changes:
            return 0.0
        
        # Calculate standard deviation
        mean = sum(prob_changes) / len(prob_changes)
        variance = sum((x - mean) ** 2 for x in prob_changes) / len(prob_changes)
        return variance ** 0.5


class MarketOpportunityScanner:
    """One-shot market scanner for agent opportunity and anomaly workflows."""

    def __init__(
        self,
        gamma_client: Optional[GammaClient] = None,
        archive_status_provider: Optional[Callable[..., Dict[str, Any]]] = None,
    ):
        self.gamma = gamma_client or GammaClient()
        self._archive_status_provider = archive_status_provider

    def scan(
        self,
        query: str = "",
        limit: int = 20,
        min_volume: float = 1000,
        min_liquidity: float = 0,
        max_archive_age_hours: int = 24,
    ) -> Dict[str, Any]:
        """Scan active markets for research-worthy opportunities."""
        errors: List[str] = []
        quality_flags = ["agent_market_scan", "read_only_scan"]
        try:
            markets = self._fetch_markets(query=query, limit=max(limit * 5, 50))
        except Exception as exc:
            errors.append(str(exc))
            markets = []
            quality_flags.append("live_market_scan_unavailable")

        opportunities = []
        stale_archive_count = 0
        for market in markets:
            if not _is_current_market(market):
                continue

            item = self._score_market(
                market,
                min_volume=min_volume,
                min_liquidity=min_liquidity,
                max_archive_age_hours=max_archive_age_hours,
            )
            if item["archive_status"] in {"stale", "missing"}:
                stale_archive_count += 1
            if item["score"] > 0:
                opportunities.append(item)

        opportunities.sort(key=lambda row: row["score"], reverse=True)
        opportunities = opportunities[:limit]
        if not opportunities:
            quality_flags.append("no_ranked_opportunities")

        return {
            "query": query,
            "limit": limit,
            "min_volume": min_volume,
            "min_liquidity": min_liquidity,
            "max_archive_age_hours": max_archive_age_hours,
            "scanned_count": len(markets),
            "opportunity_count": len(opportunities),
            "stale_archive_count": stale_archive_count,
            "opportunities": opportunities,
            "recommended_actions": self._recommended_actions(opportunities),
            "quality_flags": sorted(set(quality_flags)),
            "errors": errors,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    def _fetch_markets(self, query: str, limit: int) -> List[Dict[str, Any]]:
        if query:
            return self.gamma.search_markets(query, limit=limit)
        if hasattr(self.gamma, "get_markets"):
            return self.gamma.get_markets(limit=limit)
        return self.gamma.search_markets("", limit=limit)

    def _score_market(
        self,
        market: Dict[str, Any],
        min_volume: float,
        min_liquidity: float,
        max_archive_age_hours: int,
    ) -> Dict[str, Any]:
        market_id = str(market.get("id") or market.get("conditionId") or market.get("condition_id") or "")
        slug = str(market.get("slug") or "")
        title = str(market.get("question") or market.get("title") or market_id or slug)
        probability = market_probability_price(market)
        previous_price = safe_float(
            market.get("previousYesPrice", market.get("previous_yes_price", market.get("lastDayPrice"))),
            probability,
        )
        volume_24h = safe_float(market.get("volume24hr", market.get("volume24Hr", market.get("volume", 0))))
        liquidity = safe_float(market.get("liquidity", 0))
        change_24h = _price_change_pct(probability, previous_price)
        archive = self._archive_status(
            query=slug or title,
            market_id=market_id,
            max_age_hours=max_archive_age_hours,
        )
        archive_status = _archive_research_status(archive)

        signals: List[str] = []
        score = 0.0

        if abs(change_24h) >= 10:
            signals.append("fresh_move")
            score += min(abs(change_24h), 50) * 1.4
        elif abs(change_24h) >= 5:
            signals.append("moderate_move")
            score += abs(change_24h)

        if volume_24h >= min_volume:
            signals.append("volume_threshold_met")
            score += min(volume_24h / max(min_volume, 1), 10) * 5
        if liquidity >= min_liquidity and liquidity > 0:
            signals.append("liquid_enough")
            score += min(liquidity / max(min_liquidity or 1, 1), 10) * 3
        if archive_status in {"stale", "missing"}:
            signals.append("archive_refresh_needed")
            score += 15
        if _has_whale_signal(market):
            signals.append("whale_context_available")
            score += 8
        if volume_24h < min_volume and liquidity < min_liquidity:
            signals.append("thin_market")

        actions = list(archive.get("recommended_actions") or [])
        if "fresh_move" in signals or "archive_refresh_needed" in signals:
            actions.append(f"Run market.research with persist=true for {slug or market_id or title}.")
        if "thin_market" in signals:
            actions.append("Treat any apparent edge cautiously because liquidity and volume are thin.")

        return {
            "market_id": market_id,
            "slug": slug,
            "title": title,
            "probability": round(probability, 6),
            "previous_probability": round(previous_price, 6),
            "change_24h": round(change_24h, 6),
            "volume_24h": volume_24h,
            "liquidity": liquidity,
            "score": round(score, 6),
            "signals": signals,
            "archive_status": archive_status,
            "archive_quality_flags": archive.get("quality_flags", []),
            "recommended_actions": _dedupe(actions),
            "evidence_sources": [
                {"type": "gamma_market", "fields": ["outcomePrices", "previousYesPrice", "volume24hr", "liquidity"]},
                {"type": "archive_status", "market_id": market_id, "max_age_hours": max_archive_age_hours},
            ],
            "quality_flags": self._item_quality_flags(market, archive_status),
        }

    def _archive_status(self, query: str, market_id: str, max_age_hours: int) -> Dict[str, Any]:
        try:
            provider = self._archive_status_provider
            if provider is None:
                provider = ArchiveCollector().status
            return provider(query=query, market_id=market_id, max_age_hours=max_age_hours)
        except Exception as exc:
            return {
                "freshness": {"research_briefs": {"status": "unknown"}},
                "recommended_actions": [],
                "quality_flags": ["archive_status_unavailable", str(exc)],
            }

    def _item_quality_flags(self, market: Dict[str, Any], archive_status: str) -> List[str]:
        flags = ["live_gamma_market"]
        if not market.get("volume24hr") and not market.get("volume24Hr"):
            flags.append("missing_24h_volume")
        if not market.get("previousYesPrice"):
            flags.append("missing_previous_price")
        if archive_status in {"stale", "missing", "unknown"}:
            flags.append(f"{archive_status}_archive")
        return flags

    def _recommended_actions(self, opportunities: List[Dict[str, Any]]) -> List[str]:
        actions = []
        for item in opportunities[:5]:
            actions.extend(item.get("recommended_actions", []))
        return _dedupe(actions)


def _price_change_pct(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return ((current - previous) / previous) * 100


def _archive_research_status(archive: Dict[str, Any]) -> str:
    freshness = archive.get("freshness") or {}
    brief_status = freshness.get("research_briefs") or {}
    return str(brief_status.get("status") or "unknown")


def _has_whale_signal(market: Dict[str, Any]) -> bool:
    return bool(
        market.get("whale_activity")
        or market.get("largeTrades")
        or market.get("smartMoney")
        or market.get("smart_money")
    )


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _is_current_market(market: Dict[str, Any]) -> bool:
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
