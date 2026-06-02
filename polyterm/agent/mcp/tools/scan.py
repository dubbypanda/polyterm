"""Scan tools for agent adapters."""

from ...contracts import envelope
from ....core.scanner import MarketOpportunityScanner


def opportunities(
    query: str = "",
    limit: int = 20,
    min_volume: float = 1000,
    min_liquidity: float = 0,
    max_archive_age_hours: int = 24,
) -> dict:
    scanner = MarketOpportunityScanner()
    return envelope(
        scanner.scan(
            query=query,
            limit=limit,
            min_volume=min_volume,
            min_liquidity=min_liquidity,
            max_archive_age_hours=max_archive_age_hours,
        ),
        meta={"tool": "scan.opportunities"},
    )
