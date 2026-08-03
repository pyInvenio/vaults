# Technical design

## Primary data flow

```text
Morpho GraphQL API
  ├─ listed Ethereum USDC markets ──> immutable JSON snapshot
  ├─ DAY/HOUR historicalState ──────> SQLite sampled-state tables
  └─ exact liquidation events ─────> SQLite event table

exact-ID reviewed universe ─> hard gates ─> post-impact market curves
                                             └─> constrained marginal allocator
                                                  └─> target allocation
current positions + live state ─> rebalance planner ─> proposed moves
                                          └─> historical strategy
```

`curator/api.py` uses the current GraphQL schema and converts the WAD-scaled
per-second `rateAtTarget` into annual APR. Snapshot loading requires verified
API provenance, valid 32-byte market IDs, and no estimated records. Approval
in `curator/mandate.py` is keyed by exact market ID, never ticker alone. The
live scan is broader than this review set: activity filters surface candidates,
but never auto-promote unfamiliar collateral.

## Rate model and objective

For utilization `u`, the AdaptiveCurveIRM normalized error is:

```text
e(u) = (u - 0.90) / 0.10   when u >= 0.90
e(u) = (u - 0.90) / 0.90   when u <  0.90
```

`curator/irm.py` models the immediate utilization dilution caused by our
deposit and the subsequent evolution of the target borrow rate. API APYs are
converted to continuous APR at the boundary. The primary case sets borrower
elasticity to zero; an uncalibrated borrower response is not used to improve
the headline return.

For allocation `a`, market `i` exposes projected native rate `R_i(a)` and
annual revenue:

```text
V_i(a) = a × R_i(a)
MR_i(a, Δ) = [V_i(a + Δ) - V_i(a)] / Δ
```

The allocator assigns $250k chunks to the admissible market with the highest
marginal revenue, then performs feasible pairwise chunk exchanges until no
exchange improves annual revenue. This includes dilution of the yield on the
existing position. The primary objective contains no reward haircut and no
subjective risk-premium subtraction. Qualitative collateral and oracle risk is
expressed through reviewed eligibility and hard limits.

## Constraints

`curator/allocator.py` enforces:

- 50% per market;
- 67.5% BTC, 25% ETH/LST/LRT, 5% Sky/stUSDS, 10% Re-credit, 5% FalconX-credit,
  and 5% COMP-governance-token family caps;
- 25% aggregate non-blue collateral;
- at most 35% of post-deposit market supply;
- at least 50% pre-deposit exit coverage per funded market;
- at least 60% stressed-withdrawability across the portfolio;
- $1M minimum ticket;
- no arbitrary minimum number of funded markets (the reviewed snapshot's
  economics fund all ten);
- 100% deployment as the neutral objective unless a hard constraint makes it
  infeasible.

The ownership cap is solved as `a <= S_external × f / (1 - f)`. Exit sizing
uses liquidity that existed before the deposit, so our own fresh USDC is not
mistaken for durable withdrawal capacity. APR is always divided by full NAV.

These values are transparent initial risk-policy choices, not fitted coefficients
or Morpho protocol limits. The memo gives the reasoning and identifies which
ones bind.

## Historical replay

`HistoricalBacktester.run(start_date, days, strategy, resolution)` is the
general interface, implemented over SQLite by `MorphoHistoricalBacktester`.
At the start it selects approved IDs that existed, verifies event coverage,
and initializes $100M cash. At every timestamp it:

1. reads external supply, borrow, APYs, and trailing data;
2. computes a causal target with no future observations;
3. executes liquidity-bounded withdrawals and cash-funded deposits;
4. applies exact liquidation events in timestamp/block/log order;
5. accrues interest at utilization including the hypothetical vault;
6. records NAV, deployment, concentration, liquidity, turnover, and loss.

`post-impact` is the primary pricing model. `price-taker` reuses the exact same
allocation path but accrues at external utilization, isolating the cost of
adding $100M. The hypothetical vault does not rewrite the next historical API
observation; this is a disclosed partial-equilibrium assumption.

## Resolution and safety behavior

- `DAY`: one aggregate state per UTC day.
- `HOUR`: one aggregate state per hour.
- Liquidations: exact timestamp, block, transaction, and log index.

No five-minute or block state is fabricated. A full block replay would require
an archive RPC, every market action, historical oracle prices, and transaction
ordering. Exact bad debt is always charged pro rata. A material incident can
disable a market immediately, while withdrawals remain bounded by available
market liquidity; a kill switch cannot force borrower repayment.

Production safety observation is block/minute based; market targets are
recomputed hourly and after material events. Recalculation alone does not send
a transaction. `curator/rebalance.py` first reconstructs external supply by
subtracting the vault's current position from indexed market supply. It then
reuses the allocator to produce a target and emits liquidity-bounded
instructions.

Disabled, ineligible, near-maturity, or hard-constraint reductions bypass
economic gates. Routine moves require 1 percentage point of target drift, a
$1M leg, and at least 15 bp of modeled annual improvement. Modeled improvement
over the 14-day horizon must also cover a placeholder $60 per withdrawal or
supply leg. Rolling seven-day turnover is capped at 10% of NAV and counts both
legs, so moving $5M between markets consumes $10M. These are policy assumptions,
not fitted alpha or live execution quotes. A production executor would replace
the fixed gas input with a transaction estimate and include adapter hops,
reverts, and time out of market. Initial construction follows the full feasible
target and is not treated as a rotation under the rolling limit.

## Verification

The test suite covers IRM identities, API unit conversion, provenance checks,
capital conservation, allocation constraints, liquidity-bounded exits,
bad-debt materiality, event ordering, and causal historical averages.
