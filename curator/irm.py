"""Exact model of Morpho Blue's AdaptiveCurveIRM, plus forward projections.

Why this module exists
----------------------
A $100M vault is large relative to most Morpho markets. Depositing into a
market mechanically lowers its utilization, which (a) immediately moves the
rate down the curve and (b) makes the IRM's adaptive mechanism *compress the
whole curve* over the following days. Spot APY is therefore a biased
estimator of what we will actually earn. Every allocation decision in this
repo is made on *projected post-impact* rates computed here, never on spot.

Contract semantics (AdaptiveCurveIrm.sol, morpho-org/morpho-blue-irm)
---------------------------------------------------------------------
Constants (WAD-scaled on-chain, plain floats here):

  TARGET_UTILIZATION      = 0.9
  CURVE_STEEPNESS         = 4          (rate at u=1 is 4x rateAtTarget,
                                        rate at u=0 is rateAtTarget/4)
  ADJUSTMENT_SPEED        = 50 / year  (exponential drift of rateAtTarget)
  INITIAL_RATE_AT_TARGET  = 4% / year
  MIN_RATE_AT_TARGET      = 0.1% / year
  MAX_RATE_AT_TARGET      = 200% / year

Definitions:

  u          = borrow / supply
  err(u)     = (u - 0.9) / (1 - 0.9)   if u >= 0.9    (in [0, 1])
             = (u - 0.9) / 0.9         if u <  0.9    (in [-1, 0])
  curve(r,e) = r * (1 + (C - 1) * e)   if e >= 0
             = r * (1 + (1 - 1/C) * e) if e <  0
  borrow r.  = curve(rateAtTarget, err(u))
  rateAtTarget'(t) = ADJUSTMENT_SPEED * err(u) * rateAtTarget(t)
     => over dt at constant err: r_T(t+dt) = r_T(t) * exp(50 * err * dt_years)

  supply rate = borrow rate * u * (1 - fee)

Intuition for the adaptation speed: at err = -0.5 (u = 45%), rateAtTarget
halves roughly every 5 days (ln 2 / (50 * 0.5) years). Crowding a market
does not just slide down a static curve - it melts the curve itself.

Rates here are continuously-compounded APRs; the Morpho API reports
compounded APYs. Convert at the edges with apy_to_apr / apr_to_apy.
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
    """Invert the curve: recover rateAtTarget from an observed borrow APR.

    Used when the API doesn't hand us rateAtTarget directly. Clamped to the
    contract's bounds.
    """
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
    """Return a rateAtTarget consistent with the indexed market state.

    Prefer the API/contract field when it reproduces the observed borrow APR.
    Indexers can sample ``rateAtTarget``, utilization and displayed APY at
    slightly different blocks, so fall back to exact inversion when the
    resulting borrow-rate discrepancy exceeds 0.05 bp.  This is calibration
    to the same observed state, not an assumption about borrower response.
    """
    observed_borrow_apr = apy_to_apr(borrow_apy)
    if rate_at_target is not None:
        modeled_borrow_apr = borrow_rate(rate_at_target, utilization)
        if abs(modeled_borrow_apr - observed_borrow_apr) <= 0.05 / 10_000.0:
            return rate_at_target
    return implied_rate_at_target(observed_borrow_apr, utilization)


def relax(current: float, target: float, dt_days: float, tau_days: float) -> float:
    """One step of exponential relaxation toward `target` with time constant
    `tau_days` - the shared model for lagged borrower/supplier responses."""
    k = 1.0 - math.exp(-dt_days / max(tau_days, 1e-6))
    return current + (target - current) * k


@dataclass
class MarketSim:
    """Single-market forward simulator.

    State: total supply S, total borrow B, rateAtTarget. Borrow demand is
    modeled with a constant-elasticity schedule anchored at the observed
    (B0, r0): B*(r) = B0 * (r / r0)^(-elasticity), and B relaxes toward
    B*(r) with time constant `demand_lag_days`. This is deliberately simple;
    its only job is to capture the two first-order forces after we deposit:
    the curve compressing (IRM adaptation) and borrowers stepping in at
    cheaper rates (demand response). Elasticity 0 = worst case (no borrower
    response, all rate impact is permanent until the IRM re-equilibrates).
    """

    supply: float
    borrow: float
    rate_at_target: float
    fee: float = 0.0
    demand_elasticity: float = 0.0
    demand_lag_days: float = 5.0
    # demand anchor: (borrow, borrow-rate) pair the elasticity schedule pivots
    # around. Defaults to the state at construction; pass the *pre-shock*
    # observed pair when simulating a deposit, so the schedule reflects
    # actual revealed demand.
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

        # Morpho debt compounds at the interval-average borrow rate. Market
        # total supply assets receive the full interest; fee-share minting
        # dilutes existing suppliers, represented in their interval return.
        interest = self.borrow * math.expm1(avg_borrow_apr * dt_years)
        supplier_return = (
            interest * (1.0 - self.fee) / self.supply if self.supply > 0 else 0.0
        )
        self.borrow += interest
        self.supply += interest
        self.rate_at_target = end_rate_at_target

        # borrow demand relaxes toward its schedule
        if self.demand_elasticity > 0 and self.r_anchor > 0:
            r_b = borrow_rate(self.rate_at_target, self.utilization)
            target_b = self.b_anchor * (max(r_b, 1e-6) / self.r_anchor) ** (
                -self.demand_elasticity
            )
            target_b = min(target_b, 0.999 * self.supply)  # cannot exceed liquidity
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
    """Average supply APR we'd earn over `horizon_days` after depositing
    `extra_supply` (can be negative for withdrawals) into the market.

    This is the quantity the allocator optimizes. It prices in:
      1. the immediate slide down the rate curve (utilization dilution),
      2. the IRM compressing/expanding rateAtTarget over the horizon,
      3. optional borrower response only when an experimental caller supplies
         a non-zero elasticity. The primary allocator uses the zero default.
    """
    # anchor demand at the *observed* pre-shock (borrow, rate) pair
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
