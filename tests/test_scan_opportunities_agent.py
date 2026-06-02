"""Tests for agent adapters exposing scan.opportunities."""

from polyterm.agent import registry
from polyterm.agent.mcp import server
from polyterm.agent.mcp.tools import scan


class FakeOpportunityScanner:
    def scan(self, query="", limit=20, min_volume=1000, min_liquidity=0, max_archive_age_hours=24):
        return {
            "query": query,
            "limit": limit,
            "min_volume": min_volume,
            "min_liquidity": min_liquidity,
            "max_archive_age_hours": max_archive_age_hours,
            "opportunities": [{"market_id": "m1"}],
        }


def test_scan_opportunities_tool_wraps_core_result(monkeypatch):
    monkeypatch.setattr(scan, "MarketOpportunityScanner", lambda: FakeOpportunityScanner())

    result = scan.opportunities(
        query="bitcoin",
        limit=5,
        min_volume=5000,
        min_liquidity=1000,
        max_archive_age_hours=12,
    )

    assert result["success"] is True
    assert result["data"]["query"] == "bitcoin"
    assert result["data"]["opportunities"] == [{"market_id": "m1"}]
    assert result["meta"]["tool"] == "scan.opportunities"


def test_jsonl_server_routes_scan_opportunities(monkeypatch):
    monkeypatch.setattr(
        server.scan,
        "opportunities",
        lambda query="", limit=20, min_volume=1000, min_liquidity=0, max_archive_age_hours=24: {
            "success": True,
            "data": {"query": query, "limit": limit},
            "error": None,
            "meta": {"tool": "scan.opportunities"},
            "schema_version": "2026-06-02",
        },
    )
    monkeypatch.setitem(server.TOOL_HANDLERS, "scan.opportunities", server.scan.opportunities)

    result = server.handle_request({"tool": "scan.opportunities", "args": {"query": "bitcoin", "limit": 3}})

    assert result["success"] is True
    assert result["data"] == {"query": "bitcoin", "limit": 3}
    assert result["meta"]["tool"] == "scan.opportunities"


def test_manifest_declares_scan_opportunities():
    tools = {tool["name"]: tool for tool in registry.get_manifest()["tools"]}

    assert "scan.opportunities" in tools
    assert tools["scan.opportunities"]["read_only"] is True
    assert tools["scan.opportunities"]["args"] == {
        "query": "string",
        "limit": "integer",
        "min_volume": "number",
        "min_liquidity": "number",
        "max_archive_age_hours": "integer",
    }
