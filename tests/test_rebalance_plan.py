import copy
from dataclasses import replace

import pytest

from curator import irm
from curator.allocator import AllocationPolicy, allocate
from curator.models import VaultConfig
from curator.rates import MarketCurve
from curator.rebalance import IDLE, external_market_view, plan_rebalance


def observed_with_positions(markets, positions, cfg):
    observed = copy.deepcopy(markets)
    for market in observed:
        state = market.state
        rate_at_target = MarketCurve(market, cfg).rate_at_target
        state.supply_assets += positions.get(market.unique_key, 0.0)
        state.utilization = state.borrow_assets / state.supply_assets
        state.rate_at_target = rate_at_target
        state.borrow_apy = irm.apr_to_apy(
            irm.borrow_rate(rate_at_target, state.utilization)
        )
        state.supply_apy = irm.apr_to_apy(
            irm.supply_rate(rate_at_target, state.utilization, state.fee)
        )
    return observed


def test_external_view_removes_our_supply(sample_universe):
    positions = {sample_universe[0].unique_key: 12_000_000.0}
    observed = observed_with_positions(sample_universe, positions, VaultConfig())

    (restored, *_) = external_market_view(observed, positions)

    assert restored.state.supply_assets == pytest.approx(
        sample_universe[0].state.supply_assets
    )
    assert restored.state.borrow_assets == sample_universe[0].state.borrow_assets


def test_target_book_produces_no_rebalance(sample_universe):
    cfg = VaultConfig()
    policy = AllocationPolicy()
    target = allocate(sample_universe, cfg, policy)
    observed = observed_with_positions(sample_universe, target.amounts, cfg)

    plan = plan_rebalance(observed, target.amounts, cfg, policy)

    assert plan.moves == []
    assert plan.alerts == []


def test_initial_deployment_is_not_limited_by_routine_turnover(sample_universe):
    cfg = VaultConfig()

    plan = plan_rebalance(sample_universe, {}, cfg)

    assert sum(move.amount_usd for move in plan.moves) == pytest.approx(
        sum(plan.target.amounts.values())
    )


def test_routine_move_repairs_material_drift(sample_universe):
    cfg = replace(VaultConfig(), min_gain_bps=0.0, gas_cost_per_move_usd=0.0)
    policy = AllocationPolicy()
    target = allocate(sample_universe, cfg, policy)
    destination = next(
        key for key, amount in target.amounts.items() if amount >= 5_000_000
    )
    positions = dict(target.amounts)
    positions[destination] -= 5_000_000
    observed = observed_with_positions(sample_universe, positions, cfg)

    plan = plan_rebalance(observed, positions, cfg, policy)

    assert plan.moves
    assert any(
        move.source == IDLE and move.destination == destination and move.amount_usd > 0
        for move in plan.moves
    )


def test_turnover_budget_blocks_routine_move(sample_universe):
    cfg = replace(VaultConfig(), min_gain_bps=0.0, gas_cost_per_move_usd=0.0)
    policy = AllocationPolicy()
    target = allocate(sample_universe, cfg, policy)
    destination = next(
        key for key, amount in target.amounts.items() if amount >= 5_000_000
    )
    positions = dict(target.amounts)
    positions[destination] -= 5_000_000
    observed = observed_with_positions(sample_universe, positions, cfg)

    plan = plan_rebalance(
        observed,
        positions,
        cfg,
        policy,
        turnover_7d_usd=cfg.max_weekly_turnover * cfg.total_usd,
    )

    assert plan.moves == []


def test_horizon_gain_must_cover_gas(sample_universe):
    cfg = replace(
        VaultConfig(),
        min_gain_bps=0.0,
        gas_cost_per_move_usd=1_000_000.0,
    )
    target = allocate(sample_universe, cfg)
    destination = next(
        key for key, amount in target.amounts.items() if amount >= 5_000_000
    )
    positions = dict(target.amounts)
    positions[destination] -= 5_000_000
    observed = observed_with_positions(sample_universe, positions, cfg)

    plan = plan_rebalance(observed, positions, cfg)

    assert plan.moves == []


def test_family_cap_reduction_bypasses_routine_gates(sample_universe):
    cfg = VaultConfig()
    positions = {"wbtc": 40_000_000.0, "cbbtc": 30_000_000.0}
    observed = observed_with_positions(sample_universe, positions, cfg)

    plan = plan_rebalance(
        observed,
        positions,
        cfg,
        turnover_7d_usd=cfg.max_weekly_turnover * cfg.total_usd,
    )

    assert sum(move.amount_usd for move in plan.moves) == pytest.approx(2_500_000.0)
    assert all(move.forced for move in plan.moves)


def test_empty_enabled_set_exits_every_position(sample_universe):
    cfg = VaultConfig()
    positions = {sample_universe[0].unique_key: 2_000_000.0}
    observed = observed_with_positions(sample_universe, positions, cfg)

    plan = plan_rebalance(observed, positions, cfg, enabled_market_ids=set())

    assert len(plan.moves) == 1
    assert plan.moves[0].destination == IDLE
    assert plan.target.amounts == {}


def test_disabled_market_exit_is_limited_by_cash(sample_universe):
    cfg = VaultConfig()
    disabled = sample_universe[0]
    positions = {disabled.unique_key: 20_000_000.0}
    observed = observed_with_positions(sample_universe, positions, cfg)
    observed[0].state.borrow_assets = observed[0].state.supply_assets - 3_000_000

    plan = plan_rebalance(
        observed,
        positions,
        cfg,
        disabled_market_ids={disabled.unique_key},
    )

    assert len(plan.moves) == 1
    move = plan.moves[0]
    assert move.source == disabled.unique_key
    assert move.destination == IDLE
    assert move.amount_usd == 3_000_000
    assert move.forced
    assert plan.alerts


def test_missing_market_position_raises_alert(sample_universe):
    plan = plan_rebalance(
        sample_universe,
        {"missing-market": 2_000_000.0},
        VaultConfig(),
    )

    assert plan.moves == []
    assert "outside the current market feed" in plan.alerts[0]
