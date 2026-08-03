# Verified allocation and historical evaluation

This package contains the historical replay and reproducible evidence used by
the submission. The primary allocator lives in `curator/allocator.py`.

## Primary policy

- $100M initial NAV;
- ten exact approved market IDs from `curator/mandate.py`;
- 50% market cap, 67.5% BTC cap, 25% ETH/LST/LRT cap, 5% Sky and COMP caps;
- 25% aggregate non-blue cap and 35% post-deposit ownership cap;
- at least 50% pre-deposit exit coverage per funded market and 60% stressed
  withdrawability across the portfolio;
- $1M minimum ticket;
- no arbitrary funded-count requirement; the current economics fund all ten
  approved markets;
- neutral policy seeks full deployment; hard capacity constraints and incident
  response may deliberately leave cash;
- borrower-demand recovery is zero in the primary projection and only varied
  as a sensitivity;
- block/minute safety monitoring, hourly target recomputation, gated
  event-driven execution, and separate emergency exits.

## Historical mechanics

`MorphoHistoricalBacktester.run(start_date, days, strategy, resolution)` accepts
any UTC start and positive duration. Observations remain in chronological order;
there are no random walks and no shuffled returns. Normal-regime randomness
selects seeded, non-overlapping start dates only.

Market states use `DAY` or `HOUR` API observations. Liquidations preserve exact
block and log ordering. Missing event coverage is an error. All results use the
full $100M denominator and count idle at 0%.

## Key verified results

| window | constrained yield | static | spot chaser | avg deployed | events / repaid |
|---|---:|---:|---:|---:|---:|
| Oct 10–16 cascade | 3.00% | 2.93% | 1.95% | 86.5% | 27 / $7.69M |
| Oct 10–Dec 25 | 2.57% | 2.44% | 1.76% | 87.8% | 128 / $41.61M |
| Apr 21–May 20 | 2.00% | 2.09% | 1.04% | 78.3% | 7 / <$0.01M |
| Jun 25–Jul 24 | 2.30% | 2.35% | 0.86% | 83.7% | 13 / $0.07M |

The October cascade had zero reported bad debt. Two later events contain
$0.029681 of aggregate bad-debt dust; the modeled vault books about $0.007 and
does not activate the material emergency exit.

The first two rows use the hourly-recomputed strategy. Normal-period rows use
daily recomputation on daily source states;
daily data cannot identify sub-daily target timing. Dedicated cadence CSVs
report 1h through 7d on the available hourly tape.

The October 10–December 25 price-taker counterfactual is 3.23% versus 2.54%
post-impact on the matched seven-day attribution path. The 69 bp difference
quantifies the cost of supplying at $100M scale on that same allocation path.

## Commands

```bash
uv run python -m backtest.current_snapshot_report
uv run python -m backtest.prepare_backtest --start 2025-10-10 --days 7 --resolution HOUR
uv run python -m backtest.historical --start 2025-10-10 --days 7 --resolution HOUR
uv run python -m backtest.historical --start 2025-10-10 --days 77 \
  --resolution HOUR --cadences 0.0416666667,0.0833333333,0.25,0.5,1,7
uv run python -m backtest.backtest_suite
uv run python -m backtest.impact_attribution \
  --start 2025-10-10 --days 77 --resolution HOUR --cadence 3
```

Synthetic scenarios and subjective risk-premium models are not used in the
submitted allocation or historical results.
