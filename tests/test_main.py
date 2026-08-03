from types import SimpleNamespace

import json

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


def test_load_position_state_accepts_rebalance_metadata(tmp_path):
    path = tmp_path / "positions.json"
    path.write_text(
        json.dumps(
            {
                "positions": {"market-a": 12_000_000},
                "turnover_7d_usd": 2_000_000,
                "disabled_market_ids": ["market-b"],
            }
        )
    )

    positions, turnover, disabled = main.load_position_state(path)

    assert positions == {"market-a": 12_000_000.0}
    assert turnover == 2_000_000.0
    assert disabled == {"market-b"}
