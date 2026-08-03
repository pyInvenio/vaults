import pytest

from conftest import make_market
from curator import allocator, universe
from curator.models import CollateralTier, VaultConfig


def test_full_deployment(sample_universe):
    cfg = VaultConfig()
    res = allocator.allocate(sample_universe, cfg)
    deployed = sum(res.amounts.values())
    assert deployed == pytest.approx(
        cfg.total_usd * (1 - cfg.idle_buffer_weight), rel=1e-6
    )


def test_never_all_in_on_highest_apr(sample_universe):
    """The highest-APY market (sUSDe at 8.5% borrow) must NOT take the whole
    book: caps + marginal dilution force diversification."""
    cfg = VaultConfig()
    res = allocator.allocate(sample_universe, cfg)
    top = max(res.amounts, key=res.amounts.get)
    assert res.amounts[top] < 0.5 * cfg.total_usd
    funded = [k for k, v in res.amounts.items() if v > 0]
    assert len(funded) >= 4


def test_tier_weight_caps_respected(sample_universe):
    cfg = VaultConfig()
    res = allocator.allocate(sample_universe, cfg)
    by_key = {m.unique_key: m for m in sample_universe}
    for k, amt in res.amounts.items():
        cap = cfg.max_weight[by_key[k].tier] * cfg.total_usd
        assert amt <= cap + 1e-6


def test_ownership_cap_respected(sample_universe):
    cfg = VaultConfig()
    res = allocator.allocate(sample_universe, cfg)
    by_key = {m.unique_key: m for m in sample_universe}
    for k, amt in res.amounts.items():
        if amt > 0:
            share = amt / (by_key[k].state.supply_assets + amt)
            assert share <= cfg.max_ownership_share + 1e-6


def test_no_profitable_chunk_exchange_between_uncapped_positions(sample_universe):
    """The completed book is locally optimal on the allocator's grid.

    Forward marginal returns need not be equal at a non-smooth IRM kink; the
    relevant condition is that no destination's next chunk earns more than
    the annual revenue lost by removing a chunk from another position.
    """
    from curator.rates import MarketCurve

    cfg = VaultConfig()
    res = allocator.allocate(sample_universe, cfg)
    chunk = cfg.total_usd / 400.0
    curves = {m.unique_key: MarketCurve(m, cfg) for m in sample_universe}
    keys = [
        k
        for k, d in res.diagnostics.items()
        if not k.startswith("_") and d["amount_usd"] > 0 and not d["capped"]
    ]
    for source in keys:
        source_amount = res.amounts[source]
        if 0 < source_amount - chunk < cfg.min_ticket:
            continue
        loss = curves[source].revenue(source_amount) - curves[source].revenue(
            source_amount - chunk
        )
        for destination in keys:
            if destination == source:
                continue
            destination_amount = res.amounts[destination]
            gain = curves[destination].revenue(destination_amount + chunk) - curves[
                destination
            ].revenue(destination_amount)
            assert gain <= loss + 1e-6


def test_no_dust_positions(sample_universe):
    cfg = VaultConfig()
    res = allocator.allocate(sample_universe, cfg)
    for amt in res.amounts.values():
        assert amt == 0 or amt >= cfg.min_ticket


def test_tier_policy_limits_non_blue_exposure():
    """Collateral judgment is expressed as a cap, not a fake APR charge."""
    cfg = VaultConfig()
    safe = make_market("safe", "wstETH", supply=300e6, borrow_apy=0.05)
    risky = make_market(
        "risky",
        "sUSDe",
        supply=300e6,
        borrow_apy=0.05,
        tier=CollateralTier.YIELD_STABLE,
        lltv=0.915,
    )
    res = allocator.allocate([safe, risky], cfg)
    assert res.amounts["safe"] > res.amounts["risky"]


def test_selection_excludes_thin_and_exotic():
    cfg = VaultConfig()
    markets = [
        make_market("big", "wstETH", supply=300e6),
        make_market("thin", "wstETH", supply=5e6),
        make_market("exotic", "XYZ", supply=300e6, tier=CollateralTier.EXOTIC),
    ]
    rep = universe.select(markets, cfg)
    keys = {d.market.unique_key for d in rep.included}
    assert keys == {"big"}
