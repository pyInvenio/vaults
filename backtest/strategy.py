"""Historical-replay adapter for the constrained yield allocator."""

from __future__ import annotations

import copy

from curator import irm
from curator.allocator import AllocationPolicy
from curator.models import VaultConfig
from curator.rebalance import plan_rebalance
from curator.strategy import Strategy


HOURLY_DAYS = 1.0 / 24.0


def _period_label(days: float) -> str:
    if days < 1.0:
        return f"{days * 24:.0f}h"
    return f"{days:g}d"


class ConstrainedYieldStrategy(Strategy):
    """Replay target allocation with live-style drift and turnover gates."""

    def __init__(
        self,
        period_days: float = HOURLY_DAYS,
        budget: AllocationPolicy | None = None,
    ) -> None:
        self.period_days = period_days
        self.budget = budget if budget is not None else AllocationPolicy()
        self.name = f"constrained-yield({_period_label(period_days)})"
        self._last = -1e9
        self._target: dict[str, float] = {}
        self._routine_turnover: list[tuple[float, float]] = []

    def _available_turnover(self, day: float, cfg: VaultConfig) -> float:
        """Return unused routine turnover in the trailing seven-day window."""
        cap = cfg.max_weekly_turnover * cfg.total_usd
        self._routine_turnover = [
            (trade_day, amount)
            for trade_day, amount in self._routine_turnover
            if trade_day > day - 7.0
        ]
        return max(cap - sum(amount for _, amount in self._routine_turnover), 0.0)

    def target(self, world: dict, day: float, cfg: VaultConfig) -> dict:
        if day - self._last < self.period_days and self._target:
            return self._target
        self._last = day
        markets = []
        for sm in world.values():
            market = copy.deepcopy(sm.market)
            state = market.state
            state.supply_assets = sm.supply_ext + sm.our_position
            state.borrow_assets = min(sm.borrow, state.supply_assets * 0.999)
            state.rate_at_target = sm.rate_at_target
            state.utilization = state.borrow_assets / max(state.supply_assets, 1.0)
            state.supply_apy = irm.apr_to_apy(
                irm.supply_rate(sm.rate_at_target, state.utilization)
            )
            state.borrow_apy = irm.apr_to_apy(
                irm.borrow_rate(sm.rate_at_target, state.utilization)
            )
            markets.append(market)
        current = {k: max(sm.our_position, 0.0) for k, sm in world.items()}
        current_deployed = sum(current.values())
        turnover_used = (
            cfg.max_weekly_turnover * cfg.total_usd - self._available_turnover(day, cfg)
        )
        plan = plan_rebalance(
            markets,
            current,
            cfg,
            self.budget,
            turnover_7d_usd=turnover_used,
        )

        if current_deployed <= cfg.min_move_usd:
            self._target = {key: plan.target.amounts.get(key, 0.0) for key in world}
            return self._target

        staged = dict(current)
        charged_turnover = 0.0
        for move in plan.moves:
            if move.source:
                staged[move.source] -= move.amount_usd
            if move.destination:
                staged[move.destination] += move.amount_usd
            charged_turnover += move.turnover_usd
        if charged_turnover > 0:
            self._routine_turnover.append((day, charged_turnover))
        self._target = staged
        return self._target


class StaticConstrainedStrategy(Strategy):
    """Matched baseline: compute the candidate's day-zero book and hold."""

    name = "static-constrained"

    def __init__(self, budget: AllocationPolicy | None = None) -> None:
        self._allocator = ConstrainedYieldStrategy(budget=budget)
        self._target: dict[str, float] | None = None

    def target(self, world: dict, day: float, cfg: VaultConfig) -> dict:
        if self._target is None:
            self._target = self._allocator.target(world, day, cfg)
        return self._target
