"""Watch tools for agent adapters."""

from ...contracts import envelope
from ....core.alert_engine import AlertEngine
from ....db.database import Database


def scheduled_scan(market: str = "", schedule: str = "", runs: int = 1) -> dict:
    engine = AlertEngine(database=Database())
    safe_runs = max(int(runs or 1), 1)
    results = [engine.run_once(market=market) for _ in range(safe_runs)]
    return envelope(
        {
            "market": market,
            "schedule": schedule,
            "runs": len(results),
            "results": results,
            "long_running": bool(schedule),
            "quality_flags": ["bounded_agent_scan"],
        },
        meta={"tool": "watch.scheduled_scan"},
    )
