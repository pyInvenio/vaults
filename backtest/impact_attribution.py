"""Compare post-deposit rates with a price-taker counterfactual."""

from __future__ import annotations

import argparse

from .historical import (
    BacktestSpec,
    HistoryStore,
    MorphoHistoricalBacktester,
    print_results,
    replay_spec,
    write_csv,
)
from .pull_history import DEFAULT_DB, timestamp
from .strategy import ConstrainedYieldStrategy


def run(start: str, days: int, resolution: str, cadence: float, database=DEFAULT_DB):
    backtester = MorphoHistoricalBacktester(database)
    spec = BacktestSpec(f"{start}-{days}d-impact", timestamp(start), days, resolution)
    rows = []
    with HistoryStore(database) as store:
        for impact in (True, False):
            rows.append(
                replay_spec(
                    store,
                    spec,
                    ConstrainedYieldStrategy(period_days=cadence),
                    backtester.cfg,
                    backtester.filters,
                    apply_market_impact=impact,
                )
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--start", required=True)
    parser.add_argument("--days", required=True, type=int)
    parser.add_argument("--resolution", choices=("DAY", "HOUR"), default="DAY")
    parser.add_argument("--cadence", type=float, default=3.0)
    parser.add_argument("--output")
    args = parser.parse_args()
    rows = run(args.start, args.days, args.resolution, args.cadence, args.database)
    print_results(rows)
    if args.output:
        write_csv(rows, args.output)
    impact_bps = (rows[1].net_apr - rows[0].net_apr) * 10_000
    print(f"\nrate-impact cost: {impact_bps:.1f} bps/year on whole-vault NAV")


if __name__ == "__main__":
    main()
