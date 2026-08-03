"""Reproducible sensitivities for the allocator's load-bearing policies."""

from __future__ import annotations

import copy
from dataclasses import replace

from .allocator import AllocationPolicy, allocate
from .mandate import scan_filters
from .models import CollateralTier, Market, VaultConfig
from .universe import hard_filter


def _policy(
    *,
    btc_cap: float = 0.675,
    market_cap: float = 0.50,
    min_funded: int = 0,
    min_deployed: float = 1.0,
) -> AllocationPolicy:
    base = AllocationPolicy()
    families = dict(base.family_caps)
    families["btc"] = btc_cap
    return replace(
        base,
        max_market_weight=market_cap,
        family_caps=families,
        min_funded_markets=min_funded,
        min_deployed_weight=min_deployed,
    )


def policy_sensitivity(
    markets: list[Market], cfg: VaultConfig | None = None
) -> list[dict]:
    """Return a compact set of independently reproducible policy scenarios."""
    base_cfg = cfg if cfg is not None else VaultConfig()
    scenarios = [
        ("BTC cap 70%", base_cfg, _policy(btc_cap=0.70)),
        ("base: 67.5% BTC", base_cfg, _policy()),
        ("BTC cap 65%", base_cfg, _policy(btc_cap=0.65)),
        ("BTC cap 60%", base_cfg, _policy(btc_cap=0.60)),
        ("BTC cap 50%", base_cfg, _policy(btc_cap=0.50)),
        ("market cap 40%", base_cfg, _policy(market_cap=0.40)),
        ("minimum 7 funded", base_cfg, _policy(min_funded=7)),
        ("7-day horizon", replace(base_cfg, horizon_days=7.0), _policy()),
        ("30-day horizon", replace(base_cfg, horizon_days=30.0), _policy()),
        (
            "relaxed deploy; idle 2%",
            replace(base_cfg, idle_parking_apr=0.02),
            _policy(min_deployed=0.0),
        ),
        (
            "relaxed deploy; idle 4%",
            replace(base_cfg, idle_parking_apr=0.04),
            _policy(min_deployed=0.0),
        ),
    ]
    rows = []
    for label, scenario_cfg, policy in scenarios:
        result = allocate(markets, scenario_cfg, policy)
        rows.append(
            {
                "scenario": label,
                "projected_apr": result.projected_apr,
                "deployed_weight": result.diagnostics["_deployed_weight"],
                "funded_markets": sum(amount > 0 for amount in result.amounts.values()),
                "btc_weight": result.diagnostics["_family_weights"]["btc"],
                "stressed_liquidity_weight": result.diagnostics[
                    "_stressed_liquidity_weight"
                ],
            }
        )
    return rows


def mechanical_screen_ceiling(
    markets: list[Market], cfg: VaultConfig | None = None
) -> list[dict]:
    """Measure capacity with every mechanical scan pass treated as blue-chip."""
    base_cfg = cfg if cfg is not None else VaultConfig()
    candidates = [
        copy.deepcopy(market)
        for market in markets
        if not hard_filter(market, scan_filters())
    ]
    for market in candidates:
        market.tier = CollateralTier.BLUE_CHIP
    permissive_weights = {
        tier: (1.0 if tier == CollateralTier.BLUE_CHIP else 0.0)
        for tier in CollateralTier
    }
    ceiling_cfg = replace(base_cfg, max_weight=permissive_weights)
    family_caps = dict.fromkeys(AllocationPolicy().family_caps, 1.0)
    rows = []
    for label, reward_weight in (
        ("native only", 0.0),
        ("100% current incentives", 1.0),
    ):
        policy = AllocationPolicy(
            max_market_weight=1.0,
            max_non_blue_weight=1.0,
            family_caps=family_caps,
            min_funded_markets=0,
            min_deployed_weight=1.0,
            min_market_exit_coverage=0.50,
            min_stressed_liquidity_weight=0.60,
            reward_weight=reward_weight,
        )
        result = allocate(candidates, ceiling_cfg, policy)
        rows.append(
            {
                "scenario": label,
                "projected_apr": result.projected_apr,
                "native_apr": result.diagnostics["_native_projected_apr"],
                "reward_apr": result.diagnostics["_reward_projected_apr"],
                "deployed_weight": result.diagnostics["_deployed_weight"],
                "funded_markets": sum(amount > 0 for amount in result.amounts.values()),
            }
        )
    return rows
