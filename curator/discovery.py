"""Mechanical shortlist reporting before human exact-market underwriting."""

from __future__ import annotations

from .mandate import REVIEWED_MARKETS, REVIEWED_MARKET_IDS, scan_filters
from .models import Market, VaultConfig
from .rates import MarketCurve
from .universe import hard_filter


def shortlist(
    markets: list[Market],
    cfg: VaultConfig,
    limit: int = 15,
    probe_usd: float | None = None,
) -> list[dict[str, object]]:
    """Rank scan passes for diligence without granting market approval."""
    probe = probe_usd if probe_usd is not None else cfg.total_usd * 0.10
    reviewed = {item.market_id: item for item in REVIEWED_MARKETS}
    rows: list[dict[str, object]] = []
    for market in markets:
        if hard_filter(market, scan_filters()):
            continue
        projected = MarketCurve(market, cfg).projected_apr(probe)
        if market.unique_key in REVIEWED_MARKET_IDS:
            disposition = "reviewed"
            reason = reviewed[market.unique_key].rationale
        elif market.notes.upper().startswith("EXCLUDED"):
            disposition = "excluded"
            reason = market.notes.removeprefix("EXCLUDED: ").removeprefix(
                "EXCLUDED by judgment: "
            )
        else:
            disposition = "diligence"
            reason = (
                "mechanical pass only; collateral, oracle, redemption and "
                "liquidation review incomplete"
            )
        rows.append(
            {
                "market_id": market.unique_key,
                "label": market.label,
                "probe_apr": projected,
                "supply_usd": market.state.supply_assets,
                "borrow_usd": market.state.borrow_assets,
                "cash_usd": market.state.liquidity,
                "lltv": market.lltv,
                "disposition": disposition,
                "reason": reason,
            }
        )
    rows.sort(key=lambda row: row["probe_apr"], reverse=True)
    return rows[:limit]
