# Data provenance

## Current snapshot

File: `data/snapshot_2026-08-01.json`

- fetched at: `2026-08-01T23:36:20Z`;
- source: `https://api.morpho.org/graphql`;
- chain ID: `1`;
- loan asset: canonical Ethereum USDC
  (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`);
- query filter: `listed: true`;
- records: 119, of which 118 have collateral;
- SHA-256: `635807005fa26609195296aa34ed5890b8c9a33953895b7ce5e02125f645d508`.

The raw JSON stores exact market IDs, collateral addresses, LLTVs, IRM
addresses, oracle addresses/types/feed composition, supply, borrow, liquid
assets, utilization, native rates, fees, rewards, and timestamps. Values are
not manually reconstructed. The snapshot validator rejects estimated records.

The API query is implemented in `curator/api.py`; refresh with:

```bash
uv run main.py fetch --output data/snapshot_YYYY-MM-DD.json
```

Morpho's official API documentation describes market discovery, immutable
parameters, state, APYs, oracle composition, liquidations, and historical
intervals: <https://docs.morpho.org/developers/api/morpho/>.

## Human-reviewed allocation universe

The ten exact IDs and one-line decisions live in `curator/mandate.py`.
Market-specific metadata is in `curator/market_metadata.py`. Approval is not
inferred from a ticker or from Morpho's `listed` flag.

Oracle composition in the memo comes from the snapshot's nested `oracle.data`
response. Morpho explains why the oracle is a defining immutable market risk:
<https://docs.morpho.org/learn/concepts/oracle/>.

No live competitor rate is used as a benchmark. That avoids mismatched dates,
vault sizes, fee bases, rewards, and risk mandates.

## Historical state

The rebuildable SQLite cache is `backtest/data/morpho_history.sqlite3` and is
gitignored. `backtest/pull_history.py` queries `marketById.historicalState` for
each exact market. Stored fields are:

- timestamp;
- supplied USD;
- borrowed USD;
- native supply APY;
- native borrow APY;
- implied utilization.

The verified long windows use hourly points:

- 2025-10-10 through 2025-12-25: 1,848 observations per selected market;
- 2025-10-25 through 2025-12-25: 1,488 replay observations per market.

The downloader received an additional inclusive endpoint from the API; the
replay consumes exactly `days × 24` observations and reports its last consumed
timestamp.

## Liquidation events

`backtest/pull_events.py` stores exact transaction hash, log index, market ID,
timestamp, block number, repaid assets, bad-debt assets, seized collateral,
and liquidator. Event coverage is keyed by a hash of the exact market set and
date interval. A replay fails when coverage is absent instead of interpreting
missing data as zero events.

Verified event counts for the approved IDs that existed at each start:

| interval | events | repaid | market bad debt |
|---|---:|---:|---:|
| 2025-10-10 to 2025-10-16 | 27 | $7,685,251.50 | $0 |
| 2025-10-10 to 2025-12-25 | 131 | $41,612,758.41 | $0.029681 |
| 2025-10-25 to 2025-12-25 | 97 | $25,204,799.43 | $0.029681 |

An event count is the number of liquidation logs, not necessarily distinct
borrowers. Liquidators repay borrower debt and receive collateral; this does
not mean the lending vault was liquidated. Morpho's liquidation mechanics are
documented at <https://docs.morpho.org/learn/concepts/blue/>.

## Committed result artifacts

- `backtest/data/verified_current_allocation.csv`
- `backtest/data/verified_event_and_normal_results.csv`
- `backtest/data/verified_cadence_sweep_oct10_event_hourly.csv`
- `backtest/data/verified_oct10_dec25_hourly.csv`
- `backtest/data/verified_oct10_dec25_impact.csv`
- `backtest/data/verified_jun25_impact.csv`

Every historical result row includes initial and ending NAV, gross interest,
whole-vault APR, gas, turnover, move count, event counts, bad-debt counts,
principal loss, concentration, liquidity gap, average/min/max deployment, and
ending idle weight.

## Known limitations

The public API is an indexed source with no SLA. Aggregate states bottom out
at hourly resolution. Historical oracle prices, borrower health factors,
complete block-level market events, rewards, MEV, execution slippage, vault
flows, and competitor reactions are not reconstructed. Applying a mandate
chosen today to past dates is a conditional stress replay and carries
survivorship bias.
