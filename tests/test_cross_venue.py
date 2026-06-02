"""Tests for cross-venue arbitrage caveats and confidence."""

from polyterm.core.cross_venue import CrossVenueMonitor, VenueMarket


def test_cross_venue_scan_adds_confidence_and_execution_caveats(monkeypatch):
    monitor = CrossVenueMonitor()
    monkeypatch.setattr(
        monitor,
        "_polymarket_markets",
        lambda query, limit: [
            VenueMarket("polymarket", "pm1", "Will Bitcoin hit 100k in 2026?", 0.62),
        ],
    )
    monkeypatch.setattr(
        monitor,
        "_kalshi_markets",
        lambda query, limit: [
            VenueMarket("kalshi", "k1", "Will Bitcoin hit 100k in 2026?", 0.54),
        ],
    )

    result = monitor.scan("bitcoin", min_spread=0.025, venues=["polymarket", "kalshi"])

    assert result["count"] == 1
    opportunity = result["opportunities"][0]
    assert opportunity["spread_confidence"] == "high"
    assert "venue_mismatch" in opportunity["quality_flags"]
    assert "no_trade_execution" in opportunity["quality_flags"]
    assert any("Venue fee models" in item for item in opportunity["execution_caveats"])
    assert opportunity["resolution_caveats"] == []


def test_cross_venue_scan_flags_loose_and_stale_matches(monkeypatch):
    monitor = CrossVenueMonitor()
    monkeypatch.setattr(
        monitor,
        "_polymarket_markets",
        lambda query, limit: [
            VenueMarket("polymarket", "pm1", "Will Bitcoin reach 100k by December?", 0.70),
        ],
    )
    monkeypatch.setattr(
        monitor,
        "_kalshi_markets",
        lambda query, limit: [
            VenueMarket("kalshi", "k1", "Bitcoin reaches 100k by December", 0.60, stale=True),
        ],
    )

    result = monitor.scan("bitcoin", min_spread=0.025, venues=["polymarket", "kalshi"])

    opportunity = result["opportunities"][0]
    assert opportunity["spread_confidence"] == "low"
    assert "manual_review_match" in opportunity["quality_flags"]
    assert "resolution_mismatch_possible" in opportunity["quality_flags"]
    assert "stale_external_data" in opportunity["quality_flags"]
    assert any("resolution" in item.lower() for item in opportunity["resolution_caveats"])
    assert any("stale" in item.lower() for item in opportunity["execution_caveats"])
