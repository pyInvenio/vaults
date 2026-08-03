#!/usr/bin/env python3
"""CLI for live allocation, reproducible snapshots, and experiments."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from curator import api, discovery, sensitivity, universe
from curator.allocator import AllocationPolicy, allocate
from curator.mandate import scan_filters, selection_filters
from curator.models import Market, VaultConfig
from curator.rates import portfolio_apr

DEFAULT_SNAPSHOT = Path(__file__).parent / "data" / "snapshot_2026-08-01.json"


def load_markets(path: str | Path) -> list[Market]:
    return api.to_markets(api.load_snapshot(path))


def load_live_allocation_markets() -> list[Market]:
    """Fetch current allocation inputs; exceptions propagate without fallback."""
    items = api.attach_curated_shares(api.fetch_usdc_markets())
    return api.to_markets(items)


def observation_time(markets: list[Market]) -> str:
    timestamps = [m.state.timestamp for m in markets if m.state.timestamp is not None]
    if not timestamps:
        return "unknown"
    observed = datetime.fromtimestamp(max(timestamps), tz=timezone.utc)
    return observed.isoformat(timespec="seconds").replace("+00:00", "Z")


def cmd_fetch(args: argparse.Namespace) -> None:
    items = api.attach_curated_shares(api.fetch_usdc_markets())
    out = Path(args.output)
    api.save_snapshot(items, str(out))
    print(f"fetched {len(items)} markets -> {out}")


def print_shortlist(markets: list[Market], cfg: VaultConfig) -> None:
    rows = discovery.shortlist(markets, cfg)
    print()
    print("MECHANICAL SHORTLIST  ($10M post-impact probe; not auto-approval)")
    print("-" * 78)
    print(
        f"  {'market':<27}{'probe':>8}{'supply':>9}{'borrow':>9}"
        f"{'cash':>8}{'LLTV':>7}  decision"
    )
    for row in rows:
        print(
            f"  {row['label']:<27}{row['probe_apr']:>8.2%}"
            f"{row['supply_usd'] / 1e6:>8.1f}M{row['borrow_usd'] / 1e6:>8.1f}M"
            f"{row['cash_usd'] / 1e6:>7.1f}M{row['lltv']:>7.1%}  "
            f"{row['disposition']}"
        )
        print(f"    {row['reason']}")


def print_market_changes(
    markets: list[Market],
    previous_markets: list[Market],
    reviewed_ids: set[str],
) -> None:
    previous = {market.unique_key: market for market in previous_markets}
    print()
    print("CHANGE SINCE COMPARISON SNAPSHOT  (monitoring input, not a forecast)")
    print("-" * 78)
    print(
        f"  {'market':<29}{'supply change':>16}{'borrow change':>16}{'util change':>14}"
    )
    for market in markets:
        if market.unique_key not in reviewed_ids or market.unique_key not in previous:
            continue
        old = previous[market.unique_key]
        print(
            f"  {market.label:<29}"
            f"{market.state.supply_assets - old.state.supply_assets:>15,.0f}"
            f"{market.state.borrow_assets - old.state.borrow_assets:>16,.0f}"
            f"{market.state.utilization - old.state.utilization:>14.2%}"
        )


def print_allocation(
    markets: list[Market],
    source: str,
    *,
    cfg: VaultConfig | None = None,
    budget: AllocationPolicy | None = None,
    show_exclusions: bool = False,
    show_shortlist: bool = False,
    previous_markets: list[Market] | None = None,
) -> None:
    cfg = cfg or VaultConfig()
    budget = budget or AllocationPolicy()
    print(f"data: {source} | observed: {observation_time(markets)}")
    report = universe.select(markets, cfg, filters=selection_filters())
    scan_count = sum(
        not universe.hard_filter(market, scan_filters()) for market in markets
    )
    print("=" * 78)
    print("MARKET DISCOVERY")
    print("=" * 78)
    print(f"  discovered: {len(markets)} listed collateralized USDC markets")
    print(f"  scan pass:  {scan_count} meet mechanical activity/investability floors")
    print(
        f"  reviewed:   {len(report.included)} exact market IDs in allocation universe"
    )
    if show_exclusions:
        print()
        for tag, decisions in (("IN", report.included), ("OUT", report.excluded)):
            for decision in decisions:
                print(
                    f"  [{tag:<3}] {decision.market.label:<28} "
                    f"{'; '.join(decision.reasons)}"
                )
    else:
        print("  use --show-exclusions for the full decision log")

    if show_shortlist:
        print_shortlist(markets, cfg)
    if previous_markets is not None:
        print_market_changes(
            markets,
            previous_markets,
            {market.unique_key for market in report.universe},
        )

    result = allocate(report.universe, cfg, budget)
    print()
    print("=" * 78)
    print(
        f"TARGET ALLOCATION  (${cfg.total_usd / 1e6:.0f}M, "
        f"{budget.min_deployed_weight:.0%} deployment goal, "
        f"{cfg.idle_parking_apr:.2%} idle APR, "
        f"{cfg.horizon_days:.0f}d projection horizon)"
    )
    print("=" * 78)
    hdr = (
        f"  {'market':<28}{'alloc':>9}{'weight':>8}{'spot':>7}{'proj':>7}"
        f"{'MR':>7}{'own%':>7}{'u_post':>8}"
    )
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    diags = result.diagnostics
    order = sorted((k for k in result.amounts), key=lambda k: -result.amounts[k])
    for k in order:
        d = diags[k]
        if d["amount_usd"] <= 0:
            continue
        print(
            f"  {d['label']:<28}"
            f"{d['amount_usd'] / 1e6:>8.1f}M"
            f"{d['weight']:>8.1%}"
            f"{d['spot_supply_apy']:>7.2%}"
            f"{d['projected_apr']:>7.2%}"
            f"{d['marginal_revenue']:>7.2%}"
            f"{d['ownership_share']:>7.1%}"
            f"{d['post_utilization']:>8.1%}" + ("  [capped]" if d["capped"] else "")
        )
    funded = sum(amount > 0 for amount in result.amounts.values())
    stress_cfg = replace(cfg, horizon_days=90.0)
    held_stress_apr = portfolio_apr(report.universe, result.amounts, stress_cfg)
    print(
        f"\n  Summary: {funded} funded | ${diags['_idle_usd'] / 1e6:.1f}M idle | "
        f"${diags['_stressed_liquidity_usd'] / 1e6:.1f}M stressed-withdrawable"
    )
    print(
        f"  APR: {result.projected_apr:.2%} projected over "
        f"{cfg.horizon_days:g}d | "
        f"{held_stress_apr:.2%} in the 90d zero-borrow-growth stress"
    )
    if result.diagnostics["_reward_projected_apr"] > 0:
        print(
            f"  attribution: {result.diagnostics['_native_projected_apr']:.2%} native "
            f"+ {result.diagnostics['_reward_projected_apr']:.2%} incentives"
        )


def cmd_allocate(args: argparse.Namespace) -> None:
    previous = load_markets(args.compare_snapshot) if args.compare_snapshot else None
    print_allocation(
        load_live_allocation_markets(),
        "live Morpho API",
        show_exclusions=args.show_exclusions,
        show_shortlist=args.show_shortlist,
        previous_markets=previous,
    )


def cmd_allocate_snapshot(args: argparse.Namespace) -> None:
    previous = load_markets(args.compare_snapshot) if args.compare_snapshot else None
    print_allocation(
        load_markets(args.snapshot),
        f"offline snapshot: {args.snapshot}",
        show_exclusions=args.show_exclusions,
        show_shortlist=args.show_shortlist,
        previous_markets=previous,
    )


def cmd_sensitivity_snapshot(args: argparse.Namespace) -> None:
    markets = load_markets(args.snapshot)
    cfg = VaultConfig()
    report = universe.select(markets, cfg, filters=selection_filters())
    print(
        f"data: offline snapshot: {args.snapshot} | observed: {observation_time(markets)}"
    )
    print("POLICY SENSITIVITY")
    print("-" * 88)
    print(
        f"  {'scenario':<25}{'APR':>8}{'deployed':>11}{'funded':>9}"
        f"{'BTC':>9}{'stress liq.':>13}"
    )
    for row in sensitivity.policy_sensitivity(report.universe, cfg):
        print(
            f"  {row['scenario']:<25}{row['projected_apr']:>8.2%}"
            f"{row['deployed_weight']:>11.1%}{row['funded_markets']:>9}"
            f"{row['btc_weight']:>9.1%}"
            f"{row['stressed_liquidity_weight']:>13.1%}"
        )
    print()
    print("MECHANICAL-SCAN CAPACITY CEILING  (not an investable portfolio)")
    print("-" * 88)
    print(
        f"  {'scenario':<26}{'effective APR':>15}{'native':>10}"
        f"{'rewards':>10}{'funded':>9}"
    )
    for row in sensitivity.mechanical_screen_ceiling(markets, cfg):
        print(
            f"  {row['scenario']:<26}{row['projected_apr']:>15.2%}"
            f"{row['native_apr']:>10.2%}{row['reward_apr']:>10.2%}"
            f"{row['funded_markets']:>9}"
        )
    print("  assumes every mechanical scan pass is acceptable collateral; it is not")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument(
        "--output",
        default=str(DEFAULT_SNAPSHOT),
        help="immutable JSON destination for the verified API response",
    )

    def add_allocation_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--show-exclusions",
            action="store_true",
            help="print every included/excluded market and its reasons",
        )
        parser.add_argument(
            "--show-shortlist",
            action="store_true",
            help="rank the top 15 mechanical scan passes before underwriting",
        )
        parser.add_argument(
            "--compare-snapshot",
            help="show supply/borrow/utilization changes from a prior snapshot",
        )

    allocate_parser = sub.add_parser("allocate")
    add_allocation_args(allocate_parser)
    snapshot_parser = sub.add_parser("allocate-snapshot")
    snapshot_parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    add_allocation_args(snapshot_parser)
    sensitivity_parser = sub.add_parser("sensitivity-snapshot")
    sensitivity_parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    args = p.parse_args()
    {
        "fetch": cmd_fetch,
        "allocate": cmd_allocate,
        "allocate-snapshot": cmd_allocate_snapshot,
        "sensitivity-snapshot": cmd_sensitivity_snapshot,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
