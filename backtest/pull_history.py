"""Download Morpho daily market history into the local SQLite database.

Usage:
    .venv/bin/python -m backtest.pull_history

The downloader queries individual ``marketById`` records because Morpho does
not expose ``historicalState`` from the markets list query. Completed windows
are recorded, so interrupted pulls resume without repeating successful calls.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from curator import api
from curator.market_metadata import lookup
from curator.models import CollateralTier, Market, MarketState

from .history_db import (
    connect,
    coverage,
    record_window,
    upsert_market,
    upsert_states,
    window_fetched,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "data" / "snapshot_2026-08-01.json"
DEFAULT_DB = ROOT / "backtest" / "data" / "morpho_history.sqlite3"

HISTORY_QUERY = """
query MarketHistory($marketId: String!, $chainId: Int!, $options: TimeseriesOptions) {
  marketById(marketId: $marketId, chainId: $chainId) {
    marketId
    historicalState {
      supplyAssetsUsd(options: $options) { x y }
      borrowAssetsUsd(options: $options) { x y }
      supplyApy(options: $options) { x y }
      borrowApy(options: $options) { x y }
    }
  }
}
"""

LIVE_USDC_MARKETS_QUERY = """
query UsdcMarkets($first: Int!, $skip: Int!) {
  markets(
    first: $first
    skip: $skip
    orderBy: SupplyAssetsUsd
    orderDirection: Desc
    where: {
      chainId_in: [1]
      loanAssetAddress_in: ["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"]
    }
  ) {
    items {
      marketId
      lltv
      listed
      loanAsset { symbol }
      collateralAsset { symbol }
      state { supplyAssetsUsd borrowAssetsUsd supplyApy borrowApy utilization }
    }
    pageInfo { count countTotal }
  }
}
"""


def timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def iso_day(ts: int | None) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def post(query: str, variables: dict, timeout: float = 60.0) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        api.API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "morpho-curator-history/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def discover_approved_usdc_markets(page_size: int = 1000) -> list[Market]:
    """Discover real market IDs, retaining approved collateral tiers only.

    The query intentionally does not filter on ``listed`` so expired/delisted
    markets remain available for historical replay.
    """
    items = []
    skip = 0
    while True:
        data = post(LIVE_USDC_MARKETS_QUERY, {"first": page_size, "skip": skip})
        page = data["markets"]["items"]
        items.extend(page)
        if len(page) < page_size:
            break
        skip += page_size

    markets = []
    for item in items:
        collateral = item.get("collateralAsset")
        if not collateral:
            continue
        market_id = item["marketId"]
        symbol = collateral["symbol"]
        meta = lookup(market_id, symbol)
        if meta.tier == CollateralTier.EXOTIC:
            continue
        state = item["state"]
        supply = float(state.get("supplyAssetsUsd") or 0.0)
        borrow = float(state.get("borrowAssetsUsd") or 0.0)
        raw_lltv = float(item["lltv"])
        lltv = raw_lltv / 1e18 if raw_lltv > 10 else raw_lltv
        markets.append(
            Market(
                unique_key=market_id,
                collateral_symbol=symbol,
                loan_symbol=item["loanAsset"]["symbol"],
                lltv=lltv,
                state=MarketState(
                    supply_assets=supply,
                    borrow_assets=borrow,
                    supply_apy=float(state.get("supplyApy") or 0.0),
                    borrow_apy=float(state.get("borrowApy") or 0.0),
                    utilization=float(
                        state.get("utilization") or (borrow / supply if supply else 0.0)
                    ),
                ),
                tier=meta.tier,
                oracle_note=meta.oracle_note,
                whitelisted=bool(item.get("listed", False)),
                pt_maturity_days=meta.pt_maturity_days,
                notes=meta.notes,
            )
        )
    return markets


def normalize(historical: dict) -> list[dict]:
    names = ("supplyAssetsUsd", "borrowAssetsUsd", "supplyApy", "borrowApy")
    series = {
        name: {int(point["x"]): point["y"] for point in historical.get(name, [])}
        for name in names
    }
    common = (
        set.intersection(*(set(values) for values in series.values()))
        if series
        else set()
    )
    rows = []
    for ts in sorted(common):
        supply = float(series["supplyAssetsUsd"][ts] or 0.0)
        borrow = float(series["borrowAssetsUsd"][ts] or 0.0)
        supply_apy = series["supplyApy"][ts]
        borrow_apy = series["borrowApy"][ts]
        if supply <= 0 or supply_apy is None or borrow_apy is None:
            continue
        rows.append(
            {
                "timestamp": ts,
                "supply_assets_usd": supply,
                "borrow_assets_usd": max(borrow, 0.0),
                "supply_apy": float(supply_apy),
                "borrow_apy": float(borrow_apy),
                "utilization": max(borrow, 0.0) / supply,
            }
        )
    return rows


def windows(start: int, end: int, days: int):
    cursor = start
    step = days * 86400
    while cursor <= end:
        stop = min(cursor + step, end)
        yield cursor, stop
        cursor = stop + 86400


def pull(
    snapshot: str | Path = DEFAULT_SNAPSHOT,
    database: str | Path = DEFAULT_DB,
    start: int = timestamp("2024-01-01"),
    end: int = timestamp("2026-08-02"),
    window_days: int = 180,
    force: bool = False,
    discovery: str = "live-approved",
    interval: str = "DAY",
    market_ids: tuple[str, ...] = (),
) -> None:
    if discovery == "live-approved":
        markets = discover_approved_usdc_markets()
    else:
        markets = api.to_markets(api.load_snapshot(str(snapshot)))
    if market_ids:
        requested = set(market_ids)
        markets = [market for market in markets if market.unique_key in requested]
        missing = requested - {market.unique_key for market in markets}
        if missing:
            raise ValueError(f"unknown or unapproved market IDs: {sorted(missing)}")
    db = connect(database)
    for market in markets:
        upsert_market(db, market)
    db.commit()

    total_windows = sum(1 for _ in windows(start, end, window_days)) * len(markets)
    completed = 0
    for market in markets:
        print(f"{market.collateral_symbol:<24} {market.unique_key[:12]}...", flush=True)
        for window_start, window_end in windows(start, end, window_days):
            completed += 1
            if not force and window_fetched(
                db, market.unique_key, window_start, window_end, interval
            ):
                continue
            data = post(
                HISTORY_QUERY,
                {
                    "marketId": market.unique_key,
                    "chainId": 1,
                    "options": {
                        "startTimestamp": window_start,
                        "endTimestamp": window_end,
                        "interval": interval,
                    },
                },
            )
            record = data.get("marketById")
            if record is None:
                rows = []
            else:
                rows = normalize(record.get("historicalState") or {})
            upsert_states(db, market.unique_key, rows, interval=interval)
            record_window(
                db,
                market.unique_key,
                window_start,
                window_end,
                interval,
                len(rows),
                int(time.time()),
            )
            db.commit()
            print(
                f"  [{completed:>3}/{total_windows}] "
                f"{iso_day(window_start)}..{iso_day(window_end)}: {len(rows):>3} rows",
                flush=True,
            )

    print("\ncoverage")
    print(f"{'market':<26}{'rows':>7}{'first':>13}{'last':>13}")
    for row in coverage(db):
        print(
            f"{row['collateral_symbol']:<26}{row['points']:>7}"
            f"{iso_day(row['first_timestamp']):>13}{iso_day(row['last_timestamp']):>13}"
        )
    db.execute("PRAGMA optimize")
    db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2024-01-01", help="inclusive UTC date")
    parser.add_argument("--end", default="2026-08-01", help="inclusive UTC date")
    parser.add_argument("--window-days", type=int, default=180)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--interval", choices=("DAY", "HOUR"), default="DAY")
    parser.add_argument(
        "--market-id",
        action="append",
        default=[],
        help="restrict the pull to one approved market ID; repeat as needed",
    )
    parser.add_argument(
        "--discovery",
        choices=("live-approved", "snapshot"),
        default="live-approved",
    )
    args = parser.parse_args()
    pull(
        snapshot=args.snapshot,
        database=args.database,
        start=timestamp(args.start),
        end=timestamp(args.end),
        window_days=args.window_days,
        force=args.force,
        discovery=args.discovery,
        interval=args.interval,
        market_ids=tuple(args.market_id),
    )


if __name__ == "__main__":
    main()
