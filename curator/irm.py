"""Morpho AdaptiveCurveIRM math and post-deposit rate projections.

Deposits reduce utilization immediately and change ``rateAtTarget`` over time.
Internal rates are continuously compounded APRs; API rates are APYs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TARGET_UTILIZATION = 0.90
CURVE_STEEPNESS = 4.0
ADJUSTMENT_SPEED = 50.0  # 1/year
INITIAL_RATE_AT_TARGET = 0.04  # APR
MIN_RATE_AT_TARGET = 0.001
MAX_RATE_AT_TARGET = 2.0


def apy_to_apr(apy: float) -> float:
    """Compounded APY -> continuously compounded APR."""
    return math.log1p(max(apy, -0.999999))


def apr_to_apy(apr: float) -> float:
    """Continuously compounded APR -> compounded APY."""
    return math.expm1(apr)


def err(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    if u >= TARGET_UTILIZATION:
        return (u - TARGET_UTILIZATION) / (1.0 - TARGET_UTILIZATION)
    return (u - TARGET_UTILIZATION) / TARGET_UTILIZATION


def curve(rate_at_target: float, e: float) -> float:
    """Instantaneous borrow APR given rateAtTarget and utilization error."""
    if e >= 0:
        coeff = 1.0 + (CURVE_STEEPNESS - 1.0) * e
    else:
        coeff = 1.0 + (1.0 - 1.0 / CURVE_STEEPNESS) * e
    return rate_at_target * coeff


def borrow_rate(rate_at_target: float, u: float) -> float:
    return curve(rate_at_target, err(u))


def supply_rate(rate_at_target: float, u: float, fee: float = 0.0) -> float:
    return borrow_rate(rate_at_target, u) * u * (1.0 - fee)


def implied_rate_at_target(borrow_apr: float, u: float) -> float:
    """Recover a bounded rateAtTarget from borrow APR and utilization."""
    e = err(u)
    if e >= 0:
        coeff = 1.0 + (CURVE_STEEPNESS - 1.0) * e
    else:
        coeff = 1.0 + (1.0 - 1.0 / CURVE_STEEPNESS) * e
    r = borrow_apr / coeff if coeff > 1e-12 else MAX_RATE_AT_TARGET
    return min(max(r, MIN_RATE_AT_TARGET), MAX_RATE_AT_TARGET)


def evolve_rate_at_target(rate_at_target: float, u: float, dt_years: float) -> float:
    """rateAtTarget after dt at (assumed constant) utilization u."""
    r = rate_at_target * math.exp(ADJUSTMENT_SPEED * err(u) * dt_years)
    return min(max(r, MIN_RATE_AT_TARGET), MAX_RATE_AT_TARGET)


def interval_borrow_rate(
    rate_at_target: float, u: float, dt_years: float
) -> tuple[float, float]:
    """Morpho contract's borrow APR for an elapsed interval and ending anchor.

    ``AdaptiveCurveIrm._borrowRate`` evaluates the ending and midpoint
    ``rateAtTarget`` and applies its N=2 trapezoidal approximation. Because
    the utilization curve is linear in ``rateAtTarget``, the contract first
    averages those anchors and then applies the curve.
    """
    end = evolve_rate_at_target(rate_at_target, u, dt_years)
    mid = evolve_rate_at_target(rate_at_target, u, dt_years / 2.0)
    avg_rate_at_target = (rate_at_target + end + 2.0 * mid) / 4.0
    return borrow_rate(avg_rate_at_target, u), end


def rate_at_target_from(
    borrow_apy: float, utilization: float, rate_at_target: "float | None" = None
) -> float:
    """Use the indexed anchor unless nearby-block skew exceeds 0.05 bp."""
    observed_borrow_apr = apy_to_apr(borrow_apy)
    if rate_at_target is not None:
        modeled_borrow_apr = borrow_rate(rate_at_target, utilization)
        if abs(modeled_borrow_apr - observed_borrow_apr) <= 0.05 / 10_000.0:
            return rate_at_target
    return implied_rate_at_target(observed_borrow_apr, utilization)


def relax(current: float, target: float, dt_days: float, tau_days: float) -> float:
    """Relax ``current`` toward ``target`` with time constant ``tau_days``."""
    k = 1.0 - math.exp(-dt_days / max(tau_days, 1e-6))
    return current + (target - current) * k


@dataclass
class MarketSim:
    """Forward-simulate IRM adaptation and optional borrower response.

    Demand follows a constant-elasticity curve anchored to observed borrow and
    rate. Zero elasticity holds borrower principal demand fixed.
    """

    supply: float
    borrow: float
    rate_at_target: float
    fee: float = 0.0
    demand_elasticity: float = 0.0
    demand_lag_days: float = 5.0
    # Pre-deposit demand anchor.
    b_anchor: float = None  # type: ignore[assignment]
    r_anchor: float = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.b_anchor is None:
            self.b_anchor = self.borrow
        if self.r_anchor is None:
            self.r_anchor = max(
                borrow_rate(self.rate_at_target, self.utilization), 1e-6
            )

    @property
    def utilization(self) -> float:
        return self.borrow / self.supply if self.supply > 0 else 0.0

    def step(self, dt_days: float) -> float:
        """Advance one accrual interval; return suppliers' interval return.

        Zero borrower response means no new principal demand. Existing debt
        still accrues interest, as it does in Morpho, and that interest raises
        both total borrow assets and total supply assets. Utilization therefore
        evolves even in the zero-response downside.
        """
        dt_years = dt_days / 365.0
        u = self.utilization
        avg_borrow_apr, end_rate_at_target = interval_borrow_rate(
            self.rate_at_target, u, dt_years
        )

        # Fee-share minting dilutes suppliers' claim on accrued interest.
        interest = self.borrow * math.expm1(avg_borrow_apr * dt_years)
        supplier_return = (
            interest * (1.0 - self.fee) / self.supply if self.supply > 0 else 0.0
        )
        self.borrow += interest
        self.supply += interest
        self.rate_at_target = end_rate_at_target

        if self.demand_elasticity > 0 and self.r_anchor > 0:
            r_b = borrow_rate(self.rate_at_target, self.utilization)
            target_b = self.b_anchor * (max(r_b, 1e-6) / self.r_anchor) ** (
                -self.demand_elasticity
            )
            target_b = min(target_b, 0.999 * self.supply)
            self.borrow = relax(self.borrow, target_b, dt_days, self.demand_lag_days)
        return supplier_return

    def average_supply_apr(self, horizon_days: float, dt_days: float = 0.25) -> float:
        """Continuously compounded annual supplier return over the horizon."""
        if horizon_days <= 0:
            return supply_rate(self.rate_at_target, self.utilization, self.fee)
        t, log_growth = 0.0, 0.0
        while t < horizon_days - 1e-9:
            step = min(dt_days, horizon_days - t)
            log_growth += math.log1p(self.step(step))
            t += step
        return log_growth / (horizon_days / 365.0)


def projected_supply_apr(
    supply: float,
    borrow: float,
    rate_at_target: float,
    extra_supply: float,
    horizon_days: float = 14.0,
    fee: float = 0.0,
    demand_elasticity: float = 0.0,
    demand_lag_days: float = 5.0,
) -> float:
    """Project supply APR after a deposit or withdrawal over the horizon."""
    u0 = borrow / supply if supply > 0 else 0.0
    r0 = max(borrow_rate(rate_at_target, u0), 1e-6)
    new_supply = max(supply + extra_supply, 1.0)
    if borrow > 0.999 * new_supply:
        borrow = 0.999 * new_supply  # withdrawal bounded by liquidity
    sim = MarketSim(
        supply=new_supply,
        borrow=borrow,
        rate_at_target=rate_at_target,
        fee=fee,
        demand_elasticity=demand_elasticity,
        demand_lag_days=demand_lag_days,
        b_anchor=borrow,
        r_anchor=r0,
    )
    return sim.average_supply_apr(horizon_days)
