"""Prepare sampled states and exact liquidation events for one backtest scope."""

from __future__ import annotations

import argparse

from curator import universe

from .historical import DAY_SECONDS, HistoryStore
from .pull_events import pull_liquidations
from .pull_history import DEFAULT_DB, pull, timestamp
from curator.models import VaultConfig
from curator.mandate import APPROVED_MARKET_IDS, selection_filters


def prepare(
    start_date: str,
    days: int,
    resolution: str = "DAY",
    database=DEFAULT_DB,
) -> list[str]:
    start = timestamp(start_date)
    end = start + days * DAY_SECONDS
    # Bootstrap the daily states needed for point-in-time selection.
    pull(
        database=database,
        start=start,
        end=end,
        interval="DAY",
        market_ids=tuple(APPROVED_MARKET_IDS),
    )
    with HistoryStore(database) as store:
        selected = universe.select(
            store.markets_at(start), VaultConfig(), filters=selection_filters()
        ).universe
    market_ids = [market.unique_key for market in selected]
    if not market_ids:
        raise ValueError(f"no eligible markets at {start_date}")
    if resolution == "HOUR":
        pull(
            database=database,
            start=start,
            end=end,
            interval="HOUR",
            market_ids=tuple(market_ids),
        )
    pull_liquidations(database, start, end, market_ids)
    return market_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--start", required=True)
    parser.add_argument("--days", required=True, type=int)
    parser.add_argument("--resolution", choices=("DAY", "HOUR"), default="DAY")
    args = parser.parse_args()
    ids = prepare(args.start, args.days, args.resolution, args.database)
    print(f"prepared {len(ids)} selected markets")


if __name__ == "__main__":
    main()
