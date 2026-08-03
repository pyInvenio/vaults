from pathlib import Path

import pytest

from curator import api, discovery, sensitivity, universe
from curator.allocator import AllocationPolicy, allocate
from curator.mandate import REVIEWED_MARKET_IDS, selection_filters
from curator.models import VaultConfig


SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshot_2026-08-01.json"


def snapshot_markets():
    return api.to_markets(api.load_snapshot(str(SNAPSHOT)))


def reviewed_universe():
    markets = snapshot_markets()
    return universe.select(markets, VaultConfig(), filters=selection_filters()).universe


def test_shortlist_separates_mechanical_rank_from_human_approval():
    rows = discovery.shortlist(snapshot_markets(), VaultConfig())
    dispositions = {row["disposition"] for row in rows}

    assert "reviewed" in dispositions
    assert "diligence" in dispositions
    assert "excluded" in dispositions
    assert all(row["probe_apr"] >= rows[-1]["probe_apr"] for row in rows)
    assert {
        row["market_id"] for row in rows if row["disposition"] == "reviewed"
    } <= REVIEWED_MARKET_IDS


def test_base_policy_encodes_capacity_frontier_and_loss_budgets():
    policy = AllocationPolicy()

    assert policy.max_market_weight == 0.50
    assert policy.family_caps == {
        "btc": 0.675,
        "eth": 0.25,
        "sky": 0.05,
        "re_credit": 0.10,
        "falconx_credit": 0.05,
        "comp": 0.05,
    }
    assert policy.min_deployed_weight == 1.0
    assert policy.min_funded_markets == 0


def test_current_policy_deploys_full_nav_without_forced_market_count():
    result = allocate(reviewed_universe(), VaultConfig(), AllocationPolicy())

    assert result.diagnostics["_deployed_weight"] == pytest.approx(1.0)
    assert sum(amount > 0 for amount in result.amounts.values()) == 10
    assert result.diagnostics["_family_weights"]["btc"] == pytest.approx(0.675)
    assert (
        result.diagnostics[
            "0x24852d8d7464402ddcd717415e009d42bf7427d6a8893487f83c75ee0f4a0ea6"
        ]["rate_calibration_source"]
        == "spot_borrow_fallback"
    )


def test_rewards_are_optional_and_attributed_separately():
    markets = reviewed_universe()
    rewarded = markets[0]
    rewarded.state.reward_supply_apr = 0.02

    native = allocate(markets, VaultConfig(), AllocationPolicy(reward_weight=0.0))
    effective = allocate(markets, VaultConfig(), AllocationPolicy(reward_weight=1.0))

    assert native.diagnostics["_reward_projected_apr"] == 0.0
    assert effective.diagnostics["_reward_projected_apr"] > 0.0
    assert effective.projected_apr > native.projected_apr


def test_mechanical_ceiling_is_labeled_and_below_35_percent():
    rows = sensitivity.mechanical_screen_ceiling(snapshot_markets())

    assert [row["scenario"] for row in rows] == [
        "native only",
        "100% current incentives",
    ]
    assert rows[1]["reward_apr"] > 0.0
    assert rows[1]["projected_apr"] < 0.035
