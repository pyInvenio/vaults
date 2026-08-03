"""Export the verified ten-market snapshot and $100M target as a CSV."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from curator import api, universe
from curator.allocator import allocate
from curator.mandate import REVIEWED_MARKETS, selection_filters
from curator.models import VaultConfig

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "data" / "snapshot_2026-08-01.json"


def rows(snapshot: str | Path = DEFAULT_SNAPSHOT) -> list[dict[str, object]]:
    snapshot = Path(snapshot)
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    raw_by_id = {item["uniqueKey"]: item for item in payload["items"]}
    markets = api.to_markets(api.load_snapshot(snapshot))
    cfg = VaultConfig()
    report = universe.select(markets, cfg, filters=selection_filters())
    selected = {market.unique_key: market for market in report.universe}
    allocation = allocate(list(selected.values()), cfg)
    reviewed = {market.market_id: market for market in REVIEWED_MARKETS}
    fetched = datetime.fromtimestamp(payload["fetched_at"], timezone.utc).isoformat()
    output: list[dict[str, object]] = []
    for market_id, policy in reviewed.items():
        market = selected[market_id]
        raw = raw_by_id[market_id]
        state = raw["state"]
        oracle = raw["oracle"]
        amount = allocation.amounts[market_id]
        diagnostic = allocation.diagnostics[market_id]
        output.append(
            {
                "snapshot_utc": fetched,
                "market_id": market_id,
                "symbol": policy.symbol,
                "role": policy.role,
                "lltv": market.lltv,
                "oracle_address": oracle["address"],
                "oracle_type": oracle["type"],
                "supply_usd": state["supplyAssetsUsd"],
                "borrow_usd": state["borrowAssetsUsd"],
                "liquidity_usd": state["liquidityAssetsUsd"],
                "utilization": state["utilization"],
                "native_supply_apy": state["supplyApy"],
                "target_usd": amount,
                "target_weight": amount / cfg.total_usd,
                "post_allocation_utilization": diagnostic["post_utilization"],
                "projected_14d_apr_no_borrower_response": diagnostic["projected_apr"],
                "marginal_post_impact_apr": diagnostic["marginal_revenue"],
                "vault_post_allocation_ownership": diagnostic["ownership_share"],
                "stressed_withdrawable_usd": diagnostic["stressed_withdrawable_usd"],
                "exit_coverage": diagnostic["exit_coverage"],
                "hard_cap_usd": diagnostic["hard_cap_usd"],
                "rationale": policy.rationale,
            }
        )
    idle = allocation.diagnostics["_idle_usd"]
    output.append(
        {
            "snapshot_utc": fetched,
            "market_id": "IDLE",
            "symbol": "USDC",
            "role": "idle",
            "target_usd": idle,
            "target_weight": idle / cfg.total_usd,
            "stressed_withdrawable_usd": idle,
            "exit_coverage": 1.0,
            "rationale": "unused capacity after allocation constraints",
        }
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument(
        "--output", default="backtest/data/verified_current_allocation.csv"
    )
    args = parser.parse_args()
    data = rows(args.snapshot)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = list(data[0])
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
    print(f"wrote {len(data) - 1} markets + idle -> {destination}")


if __name__ == "__main__":
    main()
