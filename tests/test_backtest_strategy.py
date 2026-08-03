from types import SimpleNamespace

from curator.models import CollateralTier, VaultConfig
from curator.allocator import AllocationPolicy, allocate, risk_family
from backtest.strategy import ConstrainedYieldStrategy
from conftest import make_market


def test_constrained_allocation_respects_portfolio_caps(sample_universe):
    cfg = VaultConfig()
    budget = AllocationPolicy()
    result = allocate(sample_universe, cfg, budget)
    by_key = {m.unique_key: m for m in sample_universe}

    assert max(result.weights.values()) <= budget.max_market_weight + 1e-9
    non_blue = (
        sum(
            amount
            for key, amount in result.amounts.items()
            if by_key[key].tier != CollateralTier.BLUE_CHIP
        )
        / cfg.total_usd
    )
    assert non_blue <= budget.max_non_blue_weight + 1e-9
    for family, cap in budget.family_caps.items():
        exposure = (
            sum(
                amount
                for key, amount in result.amounts.items()
                if risk_family(by_key[key]) == family
            )
            / cfg.total_usd
        )
        assert exposure <= cap + 1e-9
    assert sum(amount >= cfg.min_ticket for amount in result.amounts.values()) >= 7


def test_liquidity_driven_derisking_bypasses_yield_gate():
    cfg = VaultConfig()
    markets = [
        make_market("btc", "WBTC", supply=400e6, utilization=0.50),
        make_market("eth", "WETH", supply=400e6, utilization=0.50),
    ]
    world = {
        market.unique_key: SimpleNamespace(
            market=market,
            supply_ext=market.state.supply_assets,
            borrow=market.state.borrow_assets,
            rate_at_target=0.04,
            our_position=0.0,
        )
        for market in markets
    }
    # This fixture isolates defensive de-risking.  Its two-market universe
    # cannot fill $100M under the production 67.5% BTC / 25% ETH family limits,
    # so use a permissive family budget rather than weakening live policy.
    strategy = ConstrainedYieldStrategy(
        period_days=7,
        budget=AllocationPolicy(family_caps={"btc": 1.0, "eth": 1.0}),
    )
    initial = strategy.target(world, 0.0, cfg)
    assert sum(initial.values()) == cfg.total_usd
    for simulated in world.values():
        simulated.our_position = initial[simulated.market.unique_key]
        simulated.borrow = simulated.supply_ext - 1e6
    defensive = strategy.target(world, 7.0, cfg)
    assert sum(defensive.values()) < sum(initial.values())


def test_default_strategy_recomputes_hourly():
    strategy = ConstrainedYieldStrategy()
    assert strategy.period_days == 1 / 24
    assert strategy.name == "constrained-yield(1h)"


def test_routine_turnover_is_capped_over_rolling_seven_days():
    cfg = VaultConfig()
    strategy = ConstrainedYieldStrategy()
    strategy._routine_turnover = [(0.0, 6e6), (1.0, 4e6)]

    assert strategy._available_turnover(6.0, cfg) == 0.0
    assert strategy._available_turnover(7.0, cfg) == 6e6
