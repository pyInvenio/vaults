"""Hard-filter and rank a candidate market universe."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import CollateralTier, Market, VaultConfig
from .rates import MarketCurve


@dataclass
class Decision:
    market: Market
    included: bool
    reasons: list[str] = field(default_factory=list)
    probe_apr: float = 0.0


@dataclass
class SelectionReport:
    included: list[Decision]
    excluded: list[Decision]

    @property
    def universe(self) -> list[Market]:
        return [d.market for d in self.included]


DEFAULT_FILTERS = {
    "min_supply_usd": 30_000_000,
    "min_borrow_usd": 5_000_000,
    "max_utilization": 0.995,
    "allowed_loan_symbols": ("USDC",),
    "banned_tiers": (CollateralTier.EXOTIC,),
    "allowed_market_ids": None,
    "min_pt_maturity_days": 30.0,
}


def hard_filter(market: Market, filters: dict | None = None) -> list[str]:
    """Return list of violated-rule strings (empty = passes)."""
    f = {**DEFAULT_FILTERS, **(filters or {})}
    violations: list[str] = []
    allowed = f.get("allowed_market_ids")
    if allowed is not None and market.unique_key not in allowed:
        violations.append("market ID not in the human-reviewed universe")
    if market.loan_symbol not in f["allowed_loan_symbols"]:
        violations.append(f"loan asset {market.loan_symbol} outside vault scope")
    if market.tier in f["banned_tiers"]:
        violations.append(f"collateral tier {market.tier.name} excluded by policy")
    if market.tier == CollateralTier.PT_FIXED:
        if market.pt_maturity_days is None:
            violations.append("PT maturity not verified")
        elif market.pt_maturity_days < f["min_pt_maturity_days"]:
            violations.append(
                f"PT maturity {market.pt_maturity_days:.0f}d < "
                f"{f['min_pt_maturity_days']:.0f}d exit floor"
            )
    if market.state.supply_assets < f["min_supply_usd"]:
        violations.append(
            f"supply ${market.state.supply_assets / 1e6:.1f}M < "
            f"${f['min_supply_usd'] / 1e6:.0f}M floor"
        )
    if market.state.borrow_assets < f["min_borrow_usd"]:
        violations.append("insufficient organic borrow demand")
    if market.state.utilization > f["max_utilization"]:
        violations.append(
            f"utilization {market.state.utilization:.1%} - entry/exit impaired"
        )
    if not market.whitelisted:
        violations.append("market is not listed")
    return violations


def select(
    markets: list[Market],
    cfg: VaultConfig,
    max_markets: int = 10,
    min_markets: int = 7,
    probe_fraction: float = 0.10,
    filters: dict | None = None,
) -> SelectionReport:
    """Build the allocation universe and retain every inclusion decision."""
    included: list[Decision] = []
    excluded: list[Decision] = []
    probe = cfg.total_usd * probe_fraction

    candidates: list[Decision] = []
    for market in markets:
        violations = hard_filter(market, filters)
        if violations:
            excluded.append(Decision(market, False, reasons=violations))
            continue

        apr = MarketCurve(market, cfg).projected_apr(probe)
        candidates.append(Decision(market, True, probe_apr=apr))

    candidates.sort(key=lambda d: d.probe_apr, reverse=True)

    for decision in candidates:
        if len(included) >= max_markets:
            decision.included = False
            decision.reasons.append("universe full - outranked on post-impact APR")
            excluded.append(decision)
            continue
        decision.reasons.append(
            f"projected native APR {decision.probe_apr:.2%} at "
            f"${probe / 1e6:.0f}M probe"
        )
        included.append(decision)

    if len(included) < min_markets:
        for decision in included:
            decision.reasons.append(f"note: universe has only {len(included)} markets")

    return SelectionReport(included=included, excluded=excluded)
