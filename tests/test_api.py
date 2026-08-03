import pytest
from pathlib import Path

from curator import api
from curator import irm
from curator.api import SECONDS_PER_YEAR, _annual_rate_at_target, load_snapshot
from curator.mandate import REVIEWED_MARKET_IDS
from curator.models import VaultConfig
from curator.rates import MarketCurve
from backtest.current_snapshot_report import rows as current_rows


def test_rate_at_target_converts_api_wad_per_second_to_annual_apr():
    raw = int(0.04 * 1e18 / SECONDS_PER_YEAR)
    assert _annual_rate_at_target(raw) == pytest.approx(0.04, rel=1e-8)


def test_rate_at_target_retains_legacy_annual_decimal():
    assert _annual_rate_at_target(0.04) == pytest.approx(0.04)


def test_rate_at_target_rejects_invalid_scale():
    with pytest.raises(ValueError):
        _annual_rate_at_target(100_000_000_000_000_000_000)


def test_market_discovery_paginates_to_reported_total(monkeypatch):
    pages = {
        0: [{"uniqueKey": "a"}, {"uniqueKey": "b"}],
        2: [{"uniqueKey": "c"}],
    }

    def fake_post(_query, variables):
        items = pages[variables["skip"]]
        return {
            "markets": {
                "items": items,
                "pageInfo": {"count": len(items), "countTotal": 3},
            }
        }

    monkeypatch.setattr(api, "_post", fake_post)

    assert [item["uniqueKey"] for item in api.fetch_usdc_markets(page_size=2)] == [
        "a",
        "b",
        "c",
    ]


def test_bundled_snapshot_is_verified_and_contains_exact_mandate_ids():
    snapshot = Path(__file__).resolve().parents[1] / "data" / "snapshot_2026-08-01.json"
    items = load_snapshot(str(snapshot))
    ids = {item["uniqueKey"] for item in items}
    assert len(items) == 119
    assert REVIEWED_MARKET_IDS <= ids
    assert not any(item.get("_estimated") for item in items)


def test_snapshot_rate_at_target_reproduces_api_spot_rates_for_reviewed_universe():
    snapshot = Path(__file__).resolve().parents[1] / "data" / "snapshot_2026-08-01.json"
    markets = {
        market.unique_key: market
        for market in api.to_markets(load_snapshot(str(snapshot)))
        if market.unique_key in REVIEWED_MARKET_IDS
    }

    assert markets.keys() == REVIEWED_MARKET_IDS
    for market_id, market in markets.items():
        state = market.state
        calibrated = irm.rate_at_target_from(
            state.borrow_apy, state.utilization, state.rate_at_target
        )
        modeled_borrow_apy = irm.apr_to_apy(
            irm.borrow_rate(calibrated, state.utilization)
        )
        modeled_supply_apy = irm.apr_to_apy(
            irm.supply_rate(calibrated, state.utilization)
        )

        # The API's displayed APYs and indexed rateAtTarget can be sampled or
        # rounded at slightly different precision. Borrow is the curve anchor;
        # the compounded supply conversion is allowed 0.01 APY bp.
        assert modeled_borrow_apy == pytest.approx(state.borrow_apy, abs=2e-7), (
            market_id
        )
        assert modeled_supply_apy == pytest.approx(state.supply_apy, abs=1e-6), (
            market_id
        )

    dcomp = markets[
        "0x24852d8d7464402ddcd717415e009d42bf7427d6a8893487f83c75ee0f4a0ea6"
    ]
    assert (
        irm.rate_at_target_from(
            dcomp.state.borrow_apy,
            dcomp.state.utilization,
            dcomp.state.rate_at_target,
        )
        != dcomp.state.rate_at_target
    )


def test_verified_target_accounts_for_exactly_100m_nav():
    report = current_rows()
    assert sum(float(row["target_usd"]) for row in report) == pytest.approx(100e6)
    assert {row["market_id"] for row in report[:-1]} == REVIEWED_MARKET_IDS
    assert report[-1]["market_id"] == "IDLE"


def test_market_curve_applies_api_market_fee():
    snapshot = Path(__file__).resolve().parents[1] / "data" / "snapshot_2026-08-01.json"
    market = next(
        market
        for market in api.to_markets(load_snapshot(str(snapshot)))
        if market.unique_key in REVIEWED_MARKET_IDS
    )
    market.state.fee = 0.10
    curve = MarketCurve(market, VaultConfig())

    with_fee = curve.projected_apr(1_000_000)
    without_fee = irm.projected_supply_apr(
        market.state.supply_assets,
        market.state.borrow_assets,
        curve.rate_at_target,
        extra_supply=1_000_000,
        horizon_days=14,
        fee=0.0,
    )

    assert with_fee < without_fee
