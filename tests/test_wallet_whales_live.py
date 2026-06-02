from datetime import datetime, timedelta, timezone

from polyterm.core.wallet_intelligence import WalletIntelligence


class FakeDataAPI:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get_recent_trades(self, limit=1000, offset=0, **kwargs):
        self.calls.append({"limit": limit, "offset": offset, **kwargs})
        return self.pages.get(offset, [])


class FakeDatabase:
    def get_large_trades(self, min_notional=10000, hours=24):
        return []


def test_live_whales_returns_public_trades_and_wallet_rollups_by_timeframe():
    now = datetime(2026, 6, 2, 17, 0, 0, tzinfo=timezone.utc)
    recent_ts = int((now - timedelta(hours=2)).timestamp())
    older_ts = int((now - timedelta(hours=80)).timestamp())
    pages = {
        0: [
            {
                "proxyWallet": "0xaaa",
                "side": "BUY",
                "size": 150_000,
                "price": 0.80,
                "timestamp": recent_ts,
                "title": "Fed cuts rates in June?",
                "slug": "fed-cuts-rates-in-june",
                "outcome": "Yes",
                "transactionHash": "0xtrade1",
            },
            {
                "proxyWallet": "0xbbb",
                "side": "SELL",
                "size": 75_000,
                "price": 0.50,
                "timestamp": recent_ts,
                "title": "Below threshold",
                "slug": "below-threshold",
                "outcome": "No",
                "transactionHash": "0xsmall",
            },
            {
                "proxyWallet": "0xccc",
                "side": "BUY",
                "size": 200_000,
                "price": 0.75,
                "timestamp": older_ts,
                "title": "Too old",
                "slug": "too-old",
                "outcome": "Yes",
                "transactionHash": "0xold",
            },
        ],
        1000: [],
    }
    engine = WalletIntelligence(data_api=FakeDataAPI(pages), database=FakeDatabase())

    result = engine.live_whales(min_notional=100_000, hours=72, limit=5, now=now, page_size=1000)

    assert result["source"] == "public_data_api"
    assert result["trade_count"] == 1
    assert result["wallet_count"] == 1
    assert result["trades"][0]["wallet"] == "0xaaa"
    assert result["trades"][0]["notional"] == 120_000
    assert result["wallets"][0]["address"] == "0xaaa"
    assert result["wallets"][0]["notional"] == 120_000
    assert result["quality_flags"] == ["public_data_api", "trade_direction_may_be_inferred"]


def test_live_whales_paginates_public_trades_until_limit_or_cutoff():
    now = datetime(2026, 6, 2, 17, 0, 0, tzinfo=timezone.utc)
    recent_ts = int((now - timedelta(hours=1)).timestamp())
    pages = {
        0: [{"proxyWallet": "0xaaa", "size": 10, "price": 1, "timestamp": recent_ts}],
        1000: [{"proxyWallet": "0xbbb", "size": 200_000, "price": 1, "timestamp": recent_ts}],
        2000: [],
    }
    api = FakeDataAPI(pages)
    engine = WalletIntelligence(data_api=api, database=FakeDatabase())

    result = engine.live_whales(min_notional=100_000, hours=72, limit=5, now=now, page_size=1000)

    assert [call["offset"] for call in api.calls] == [0, 1000, 2000]
    assert api.calls[0]["filter_type"] == "CASH"
    assert api.calls[0]["filter_amount"] == 100_000
    assert result["trade_count"] == 1
    assert result["trades"][0]["wallet"] == "0xbbb"


def test_live_whales_limits_displayed_trades_without_hiding_wallet_rollups():
    now = datetime(2026, 6, 2, 17, 0, 0, tzinfo=timezone.utc)
    recent_ts = int((now - timedelta(hours=1)).timestamp())
    pages = {
        0: [
            {"proxyWallet": "0xaaa", "size": 200_000, "price": 1, "timestamp": recent_ts, "transactionHash": "0x1"},
            {"proxyWallet": "0xaaa", "size": 190_000, "price": 1, "timestamp": recent_ts, "transactionHash": "0x2"},
            {"proxyWallet": "0xbbb", "size": 180_000, "price": 1, "timestamp": recent_ts, "transactionHash": "0x3"},
        ],
        1000: [],
    }
    engine = WalletIntelligence(data_api=FakeDataAPI(pages), database=FakeDatabase())

    result = engine.live_whales(min_notional=100_000, hours=72, limit=2, now=now, page_size=1000)

    assert result["trade_count"] == 3
    assert [trade["wallet"] for trade in result["trades"]] == ["0xaaa", "0xaaa"]
    assert [wallet["address"] for wallet in result["wallets"]] == ["0xaaa", "0xbbb"]
