"""Alert tools for agent adapters."""

from ...contracts import envelope
from ....core.alert_engine import AlertEngine
from ....db.database import Database


def create_price_rule(market: str, above: float = None, below: float = None) -> dict:
    engine = AlertEngine(database=Database())
    return envelope(
        engine.create_price_rule(market=market, above=above, below=below),
        meta={"tool": "alerts.create_price_rule"},
    )
