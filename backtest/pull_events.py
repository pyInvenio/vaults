"""Pull exact-block Morpho liquidation events into the local history store.

Market state time series are sampled, but liquidation transactions are not:
each row retains its Ethereum block, transaction hash, log index, repayment,
and realized bad debt.  Re-running a completed market/date scope is a no-op.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .history_db import (
    connect,
    event_scope_hash,
    event_window_fetched,
    record_event_window,
    upsert_liquidations,
)
from .pull_history import DEFAULT_DB, post, timestamp


def _query(market_ids: list[str], start: int, end: int, skip: int) -> str:
    ids = ",".join(json.dumps(market_id) for market_id in market_ids)
    return f"""
    query {{
      marketTransactions(
        first: 1000
        skip: {skip}
        orderBy: Timestamp
        orderDirection: Asc
        where: {{
          marketUniqueKey_in: [{ids}]
          type_in: [Liquidation]
          timestamp_gte: {start}
          timestamp_lte: {end - 1}
        }}
      ) {{
        items {{
          timestamp blockNumber txHash logIndex
          market {{ marketId }}
          data {{
            ... on MarketTransactionLiquidationData {{
              seizedAssets repaidAssets badDebtAssets liquidator
            }}
          }}
        }}
        pageInfo {{ count countTotal }}
      }}
    }}
    """


def pull_liquidations(
    database: str | Path,
    start: int,
    end: int,
    market_ids: list[str] | None = None,
    force: bool = False,
) -> int:
    """Fetch ``[start, end)`` liquidation events; return inserted event count."""
    if end <= start:
        raise ValueError("event window end must be after start")
    db = connect(database)
    known = {
        row["market_id"]: row
        for row in db.execute("SELECT market_id, loan_symbol FROM markets")
    }
    ids = sorted(market_ids or known)
    unknown = set(ids) - set(known)
    if unknown:
        db.close()
        raise ValueError(f"unknown market IDs: {sorted(unknown)}")
    non_usdc = [
        market_id for market_id in ids if known[market_id]["loan_symbol"] != "USDC"
    ]
    if non_usdc:
        db.close()
        raise ValueError(
            "event unit conversion currently supports USDC loan markets only"
        )
    scope = event_scope_hash(ids)
    if not force and event_window_fetched(db, scope, start, end):
        db.close()
        return 0

    rows: list[dict] = []
    skip = 0
    while True:
        data = post(_query(ids, start, end, skip), {})
        page = data["marketTransactions"]
        for item in page["items"]:
            event = item["data"]
            rows.append(
                {
                    "tx_hash": item["txHash"],
                    "log_index": item["logIndex"],
                    "market_id": item["market"]["marketId"],
                    "timestamp": item["timestamp"],
                    "block_number": item["blockNumber"],
                    "repaid_assets_usd": float(event["repaidAssets"]) / 1e6,
                    "bad_debt_assets_usd": float(event["badDebtAssets"]) / 1e6,
                    "seized_assets_raw": str(event["seizedAssets"]),
                    "liquidator": event["liquidator"],
                }
            )
        skip += len(page["items"])
        if skip >= page["pageInfo"]["countTotal"] or not page["items"]:
            break

    upsert_liquidations(db, rows)
    record_event_window(db, scope, start, end, len(rows), int(time.time()))
    db.commit()
    db.execute("PRAGMA optimize")
    db.close()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--start", required=True, help="inclusive UTC date")
    parser.add_argument("--days", required=True, type=int)
    parser.add_argument("--market-id", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    start = timestamp(args.start)
    count = pull_liquidations(
        args.database,
        start,
        start + args.days * 86_400,
        args.market_id or None,
        args.force,
    )
    print(f"stored {count} exact-block liquidation events")


if __name__ == "__main__":
    main()
