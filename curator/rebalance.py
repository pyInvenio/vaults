"""Generate reallocation instructions from live positions and market state."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Mapping

from . import irm
from .allocator import AllocationPolicy, allocate, risk_family
from .models import Allocation, CollateralTier, Market, VaultConfig
from .rates import MarketCurve

IDLE = ""
EPSILON = 1e-6


@dataclass(frozen=True)
class Move:
    """One proposed transfer. An empty market ID represents vault idle USDC."""

    source: str
    destination: str
    amount_usd: float
    reason: str
    forced: bool = False
    projected_gain_bps: float | None = None

    @property
    def turnover_usd(self) -> float:
        return _turnover_charge(self.source, self.destination, self.amount_usd)


@dataclass
class RebalancePlan:
    """Desired allocation and currently executable moves toward it."""

    target: Allocation
    moves: list[Move] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def external_market_view(
    markets: list[Market], positions: Mapping[str, float]
) -> list[Market]:
    """Remove our positions from indexed supply before recomputing the target."""

    view: list[Market] = []
    for market in markets:
        item = copy.deepcopy(market)
        state = item.state
        rate_at_target = irm.rate_at_target_from(
            state.borrow_apy,
            state.utilization,
            state.rate_at_target,
        )
        state.supply_assets = max(
            state.supply_assets - positions.get(item.unique_key, 0.0),
            1.0,
        )
        state.utilization = min(state.borrow_assets / state.supply_assets, 1.0)
        state.rate_at_target = rate_at_target
        state.borrow_apy = irm.apr_to_apy(
            irm.borrow_rate(rate_at_target, state.utilization)
        )
        state.supply_apy = irm.apr_to_apy(
            irm.supply_rate(rate_at_target, state.utilization, state.fee)
        )
        view.append(item)
    return view


def _move_gain(
    source: str,
    destination: str,
    amount: float,
    planned: Mapping[str, float],
    curves: Mapping[str, MarketCurve],
    idle_apr: float,
) -> tuple[float, float]:
    gain = 0.0
    if destination:
        current = planned.get(destination, 0.0)
        gain += curves[destination].revenue(current + amount)
        gain -= curves[destination].revenue(current)
    else:
        gain += amount * idle_apr

    if source:
        current = planned.get(source, 0.0)
        gain -= curves[source].revenue(current)
        gain += curves[source].revenue(current - amount)
    else:
        gain -= amount * idle_apr
    return gain, gain / amount * 10_000.0


def _turnover_charge(source: str, destination: str, amount: float) -> float:
    """Count both withdrawal and supply legs for market-to-market moves."""

    return amount * (2.0 if source and destination else 1.0)


def _constraint_reductions(
    markets: list[Market],
    positions: Mapping[str, float],
    target: Allocation,
    cfg: VaultConfig,
    policy: AllocationPolicy,
) -> dict[str, float]:
    """Return minimum target-directed withdrawals needed to restore hard limits."""

    by_key = {market.unique_key: market for market in markets}
    desired = target.amounts
    reductions = {key: 0.0 for key in by_key}

    def remaining(key: str) -> float:
        return positions.get(key, 0.0) - reductions[key]

    def reduce_group(keys: list[str], excess: float) -> None:
        for key in sorted(
            keys,
            key=lambda item: remaining(item) - desired.get(item, 0.0),
            reverse=True,
        ):
            available = max(remaining(key) - desired.get(key, 0.0), 0.0)
            amount = min(available, excess)
            reductions[key] += amount
            excess -= amount
            if excess <= EPSILON:
                return

    for key in by_key:
        hard_cap = float(target.diagnostics[key]["hard_cap_usd"])
        reductions[key] = max(positions.get(key, 0.0) - hard_cap, 0.0)

    for family, cap_weight in policy.family_caps.items():
        members = [
            key for key, market in by_key.items() if risk_family(market) == family
        ]
        total = sum(remaining(key) for key in members)
        reduce_group(members, max(total - cap_weight * cfg.total_usd, 0.0))

    non_blue = [
        key for key, market in by_key.items() if market.tier != CollateralTier.BLUE_CHIP
    ]
    total_non_blue = sum(remaining(key) for key in non_blue)
    reduce_group(
        non_blue,
        max(total_non_blue - policy.max_non_blue_weight * cfg.total_usd, 0.0),
    )

    deployed = sum(remaining(key) for key in by_key)
    stressed_liquidity = (
        cfg.total_usd
        - deployed
        + sum(
            min(remaining(key), market.state.liquidity)
            for key, market in by_key.items()
        )
    )
    shortfall = max(
        policy.min_stressed_liquidity_weight * cfg.total_usd - stressed_liquidity,
        0.0,
    )
    liquidity_excess = [
        key
        for key, market in by_key.items()
        if remaining(key) > max(desired.get(key, 0.0), market.state.liquidity)
    ]
    reduce_group(liquidity_excess, shortfall)
    return {key: amount for key, amount in reductions.items() if amount > EPSILON}


def plan_rebalance(
    markets: list[Market],
    positions: Mapping[str, float],
    cfg: VaultConfig,
    policy: AllocationPolicy | None = None,
    *,
    enabled_market_ids: set[str] | None = None,
    disabled_market_ids: set[str] | None = None,
    turnover_7d_usd: float = 0.0,
    pt_exit_days: float = 30.0,
) -> RebalancePlan:
    """Recompute the target and propose gated moves; never execute them."""

    policy = policy or AllocationPolicy()
    disabled = set(disabled_market_ids or ())
    by_key = {market.unique_key: market for market in markets}
    enabled = (
        set(by_key) if enabled_market_ids is None else set(enabled_market_ids)
    ) - disabled

    clean_positions = {key: float(value) for key, value in positions.items()}
    if any(value < 0 for value in clean_positions.values()):
        raise ValueError("positions cannot be negative")
    if sum(clean_positions.values()) > cfg.total_usd + EPSILON:
        raise ValueError("positions exceed vault NAV")
    if turnover_7d_usd < 0:
        raise ValueError("turnover_7d_usd cannot be negative")

    for market in markets:
        if (
            market.pt_maturity_days is not None
            and market.pt_maturity_days <= pt_exit_days
        ):
            disabled.add(market.unique_key)
            enabled.discard(market.unique_key)

    view = external_market_view(markets, clean_positions)
    target_markets = [market for market in view if market.unique_key in enabled]
    target = allocate(target_markets, cfg, policy)
    plan = RebalancePlan(target=target)

    for key, amount in clean_positions.items():
        if amount <= 0 or key in enabled:
            continue
        market = by_key.get(key)
        if market is None:
            plan.alerts.append(
                f"{key}: position is outside the current market feed; verify on-chain "
                "cash and exit manually"
            )
            continue
        withdrawable = min(amount, market.state.liquidity)
        if withdrawable > 0:
            plan.moves.append(
                Move(
                    key,
                    IDLE,
                    withdrawable,
                    "risk or eligibility exit; recompute after withdrawal",
                    forced=True,
                )
            )
        residual = amount - withdrawable
        if residual > EPSILON:
            plan.alerts.append(f"{key}: ${residual:,.0f} remains liquidity-constrained")

    if plan.moves or plan.alerts:
        return plan

    enabled_view = [market for market in view if market.unique_key in enabled]
    reductions = _constraint_reductions(
        enabled_view,
        clean_positions,
        target,
        cfg,
        policy,
    )
    for key, amount in reductions.items():
        withdrawable = min(amount, by_key[key].state.liquidity)
        if withdrawable > 0:
            plan.moves.append(
                Move(
                    key,
                    IDLE,
                    withdrawable,
                    "restore hard portfolio constraints; recompute after withdrawal",
                    forced=True,
                )
            )
        residual = amount - withdrawable
        if residual > EPSILON:
            plan.alerts.append(
                f"{key}: ${residual:,.0f} required reduction remains liquidity-constrained"
            )
    if plan.moves or plan.alerts:
        return plan

    if sum(clean_positions.values()) <= cfg.min_move_usd:
        plan.moves.extend(
            Move(IDLE, key, amount, "initial deployment to target")
            for key, amount in target.amounts.items()
            if amount >= cfg.min_ticket
        )
        return plan

    current = {key: clean_positions.get(key, 0.0) for key in enabled}
    desired = {key: target.amounts.get(key, 0.0) for key in enabled}
    current_idle = cfg.total_usd - sum(clean_positions.values())
    desired_idle = cfg.total_usd - sum(desired.values())
    current[IDLE] = current_idle
    desired[IDLE] = desired_idle

    band = cfg.drift_band_abs * cfg.total_usd
    overs = {
        key: current[key] - desired[key]
        for key in current
        if current[key] - desired[key] > band
    }
    unders = {
        key: desired[key] - current[key]
        for key in desired
        if desired[key] - current[key] > band
    }
    if not overs or not unders:
        return plan

    curves = {market.unique_key: MarketCurve(market, cfg) for market in target_markets}
    planned = dict(current)
    withdrawable = {
        key: min(clean_positions.get(key, 0.0), by_key[key].state.liquidity)
        for key in enabled
    }
    turnover_left = max(
        cfg.max_weekly_turnover * cfg.total_usd - turnover_7d_usd,
        0.0,
    )

    while turnover_left >= cfg.min_move_usd and overs and unders:
        candidates: list[tuple[float, str, str, float, float]] = []
        for source, excess in overs.items():
            source_available = excess
            if source:
                source_available = min(source_available, withdrawable.get(source, 0.0))
            for destination, shortfall in unders.items():
                charge_multiple = 2.0 if source and destination else 1.0
                amount = min(
                    source_available,
                    shortfall,
                    turnover_left / charge_multiple,
                )
                if amount < cfg.min_move_usd:
                    continue
                gain, gain_bps = _move_gain(
                    source,
                    destination,
                    amount,
                    planned,
                    curves,
                    cfg.idle_parking_apr,
                )
                gas_cost = cfg.gas_cost_per_move_usd * (
                    int(bool(source)) + int(bool(destination))
                )
                horizon_gain = gain * cfg.horizon_days / 365.0
                if gain_bps < cfg.min_gain_bps or horizon_gain < gas_cost:
                    continue
                candidates.append((gain_bps, source, destination, amount, gain))
        if not candidates:
            break

        gain_bps, source, destination, amount, _ = max(candidates)
        reason = f"target drift; projected gain {gain_bps:.1f} bp on moved capital"
        plan.moves.append(
            Move(
                source,
                destination,
                amount,
                reason,
                projected_gain_bps=gain_bps,
            )
        )
        planned[source] -= amount
        planned[destination] += amount
        overs[source] -= amount
        unders[destination] -= amount
        if source:
            withdrawable[source] -= amount
        turnover_left -= _turnover_charge(source, destination, amount)
        if overs[source] < cfg.min_move_usd:
            del overs[source]
        if unders[destination] < cfg.min_move_usd:
            del unders[destination]

    return plan
