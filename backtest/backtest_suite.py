"""Run the October-10 event case plus seeded, non-overlapping quiet periods."""

from __future__ import annotations

import argparse

from .historical import (
    BacktestSpec,
    HistoryStore,
    MorphoHistoricalBacktester,
    print_results,
    replay_spec,
    strategy_factories,
    write_csv,
)
from .pull_history import DEFAULT_DB, timestamp


def suite_specs(
    backtester: MorphoHistoricalBacktester,
    normal_days: int = 30,
    normal_count: int = 2,
    seed: int = 20_251_010,
) -> list[BacktestSpec]:
    event = BacktestSpec("oct10-cascade-7d", timestamp("2025-10-10"), 7, "HOUR")
    normal = backtester.sample_normal_periods(
        normal_days,
        normal_count,
        seed,
        exclude=(("2025-10-01", "2025-10-20"),),
    )
    return [event, *normal]


def run_suite(
    database=DEFAULT_DB,
    cadences=(1, 3, 7, 14),
    normal_days: int = 30,
    normal_count: int = 2,
    seed: int = 20_251_010,
):
    backtester = MorphoHistoricalBacktester(database)
    results = []
    with HistoryStore(database) as store:
        for spec in suite_specs(backtester, normal_days, normal_count, seed):
            for factory in strategy_factories(cadences):
                results.append(
                    replay_spec(
                        store, spec, factory(), backtester.cfg, backtester.filters
                    )
                )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--cadences", default="1,3,7,14")
    parser.add_argument("--normal-days", type=int, default=30)
    parser.add_argument("--normal-count", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20_251_010)
    parser.add_argument(
        "--output", default="backtest/data/event_and_normal_results.csv"
    )
    args = parser.parse_args()
    results = run_suite(
        args.database,
        tuple(float(value) for value in args.cadences.split(",")),
        args.normal_days,
        args.normal_count,
        args.seed,
    )
    print_results(results)
    write_csv(results, args.output)


if __name__ == "__main__":
    main()
