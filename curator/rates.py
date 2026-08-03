"""Post-allocation Morpho rate curves used by selection and allocation."""

from __future__ import annotations

from collections.abc import Mapping

from . import irm
from .models import Market, VaultConfig


class MarketCurve:
    """Cache the projected native supply APR for hypothetical allocations."""

    def __init__(self, market: Market, cfg: VaultConfig):
        self.market = market
        self.cfg = cfg
        state = market.state
        self.rate_at_target = irm.rate_at_target_from(
            state.borrow_apy,
            state.utilization,
            state.rate_at_target,
        )
        self.rate_calibration_source = (
            "api"
            if state.rate_at_target is not None
            and self.rate_at_target == state.rate_at_target
            else "spot_borrow_fallback"
        )
        ownership = cfg.max_ownership_share
        ownership_cap = state.supply_assets * ownership / (1.0 - ownership)
        tier_cap = cfg.max_weight.get(market.tier, 0.0) * cfg.total_usd
        self.cap = min(ownership_cap, tier_cap)
        self._cache: dict[int, float] = {}

    def projected_apr(self, amount: float) -> float:
        key = round(amount)
        if key not in self._cache:
            state = self.market.state
            self._cache[key] = irm.projected_supply_apr(
                state.supply_assets,
                state.borrow_assets,
                self.rate_at_target,
                extra_supply=amount,
                horizon_days=self.cfg.horizon_days,
                fee=state.fee,
                demand_elasticity=0.0,
            )
        return self._cache[key]

    def revenue(self, amount: float) -> float:
        """Projected annual native-interest revenue in USD."""
        return max(amount, 0.0) * self.projected_apr(max(amount, 0.0))

    def marginal_revenue(self, amount: float, step: float) -> float:
        return (self.revenue(amount + step) - self.revenue(amount)) / step


def portfolio_apr(
    markets: list[Market], amounts: Mapping[str, float], cfg: VaultConfig
) -> float:
    """NAV-weighted APR for a fixed allocation under ``cfg``."""
    curves = {market.unique_key: MarketCurve(market, cfg) for market in markets}
    revenue = sum(curves[key].revenue(amount) for key, amount in amounts.items())
    idle = cfg.total_usd - sum(amounts.values())
    return (revenue + idle * cfg.idle_parking_apr) / cfg.total_usd
