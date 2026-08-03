from types import SimpleNamespace

import main


def test_live_allocation_loader_fetches_and_enriches(monkeypatch):
    calls = []
    raw = [{"uniqueKey": "live"}]

    monkeypatch.setattr(
        main.api,
        "fetch_usdc_markets",
        lambda: calls.append("fetch") or raw,
    )
    monkeypatch.setattr(
        main.api,
        "attach_curated_shares",
        lambda items: calls.append("enrich") or items,
    )
    monkeypatch.setattr(
        main.api,
        "to_markets",
        lambda items: calls.append("convert") or items,
    )

    markets = main.load_live_allocation_markets()

    assert markets == raw
    assert calls == ["fetch", "enrich", "convert"]


def test_observation_time_uses_newest_market_timestamp():
    markets = [
        SimpleNamespace(state=SimpleNamespace(timestamp=1_700_000_000)),
        SimpleNamespace(state=SimpleNamespace(timestamp=1_700_000_123)),
    ]

    assert main.observation_time(markets) == "2023-11-14T22:15:23Z"
