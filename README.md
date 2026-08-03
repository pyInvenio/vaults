# $100M Morpho USDC curator take-home

This repository discovers Ethereum mainnet Morpho Blue markets and builds a
capacity-aware allocation for a $100M USDC vault.

## Result

The reproducible snapshot observed at `2026-08-01T23:36:11Z` contains 118
collateralized USDC markets. Forty-six pass the mechanical scan and ten exact
market IDs are selected after preliminary collateral, oracle, LLTV, incident,
and liquidity review.

The target deploys all $100M, retains $82.2M of stressed-withdrawable market
liquidity, and projects 2.56% native APR over 14 days with borrowing held fixed.
The lower rate than smaller live vaults is primarily the utilization impact of
adding $100M.

Historical replay provides the main validation:

| window | constrained | static | spot chaser |
|---|---:|---:|---:|
| Oct 10–16, 2025 cascade | 2.76% | 2.93% | 1.95% |
| Oct 10–Dec 25, 2025 | 2.27% | 2.44% | 1.76% |
| Jun 25–Jul 24, 2026 | 2.32% | 2.35% | 0.86% |

The constrained rows use hourly recomputation where hourly source data exists
and daily recomputation on the daily June tape. Rebalancing is a risk and
execution policy; these samples do not establish timing alpha.

## Run

```bash
uv sync
uv run pytest

# Fresh API state; fails rather than falling back to the committed snapshot
uv run main.py allocate

# Reproduce the memo result and policy sensitivities
uv run main.py allocate-snapshot \
  --snapshot data/snapshot_2026-08-01.json
uv run main.py sensitivity-snapshot

# Inspect discovery and underwriting decisions
uv run main.py allocate --show-shortlist --show-exclusions

# Generate live reallocation instructions from current positions; no transaction
# is submitted. The JSON may also include turnover_7d_usd and disabled_market_ids.
uv run main.py rebalance --positions positions.json

# Reproduce historical tests
uv run python -m backtest.backtest_suite \
  --output backtest/data/verified_event_and_normal_results.csv
uv run python -m backtest.impact_attribution \
  --start 2025-10-10 --days 77 --resolution HOUR --cadence 0.0416666667
```

`positions.json` uses USDC-value notionals keyed by exact market ID:

```json
{
  "positions": {"0x<64-hex-market-id>": 10000000},
  "turnover_7d_usd": 0,
  "disabled_market_ids": []
}
```
