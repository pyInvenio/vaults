"""Historical-replay adapter for the constrained yield allocator."""

from __future__ import annotations

import copy

from curator import irm
from curator.allocator import AllocationPolicy, allocate
from curator.models import VaultConfig
from curator.rates import MarketCurve
from curator.strategy import Strategy


HOURLY_DAYS = 1.0 / 24.0


def _period_label(days: float) -> str:
    if days < 1.0:
        return f"{days * 24:.0f}h"
    return f"{days:g}d"


class ConstrainedYieldStrategy(Strategy):
    """Size on post-impact marginal return, recomputed on a fixed cadence.

    Day zero can deploy directly to the desired book.  Later routine target
    changes are staged through a rolling seven-day turnover
    budget and ignored when the largest market drift is inside the configured
    band. Exact-event exits in the historical runner remain a separate,
    immediate safety path.
    """

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
            state.supply_assets = sm.supply_ext
            state.borrow_assets = min(sm.borrow, sm.supply_ext * 0.999)
            state.rate_at_target = sm.rate_at_target
            state.utilization = state.borrow_assets / max(state.supply_assets, 1.0)
            state.supply_apy = irm.apr_to_apy(
                irm.supply_rate(sm.rate_at_target, state.utilization)
            )
            state.borrow_apy = irm.apr_to_apy(
                irm.borrow_rate(sm.rate_at_target, state.utilization)
            )
            markets.append(market)
        result = allocate(
            markets,
            cfg,
            self.budget,
            chunk=cfg.total_usd / 400.0,
        )
        desired = {k: result.amounts.get(k, 0.0) for k in world}
        current = {k: max(sm.our_position, 0.0) for k, sm in world.items()}
        current_deployed = sum(current.values())
        desired_deployed = sum(desired.values())

        if current_deployed <= cfg.min_move_usd:
            self._target = desired
            return self._target

        deltas = {k: desired[k] - current[k] for k in world}
        defensive_rebalance = desired_deployed < current_deployed - cfg.min_move_usd
        largest_drift = max(
            (abs(delta) / cfg.total_usd for delta in deltas.values()),
            default=0.0,
        )
        if not defensive_rebalance and largest_drift <= cfg.drift_band_abs:
            self._target = current
            return self._target

        curves = {market.unique_key: MarketCurve(market, cfg) for market in markets}
        current_value = sum(curves[key].revenue(current[key]) for key in world)
        desired_value = sum(curves[key].revenue(desired[key]) for key in world)
        desired_turnover = sum(abs(delta) for delta in deltas.values())
        gain_on_moved_notional = (desired_value - current_value) / max(
            desired_turnover, 1.0
        )
        if (
            not defensive_rebalance
            and gain_on_moved_notional < cfg.min_gain_bps / 10_000.0
        ):
            self._target = current
            return self._target

        routine_budget = self._available_turnover(day, cfg)
        scale = min(1.0, routine_budget / max(desired_turnover, 1.0))
        charged_turnover = scale * desired_turnover
        if charged_turnover > 0:
            self._routine_turnover.append((day, charged_turnover))
        self._target = {
            key: max(0.0, current[key] + scale * deltas[key]) for key in world
        }
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
