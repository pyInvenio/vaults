# Curator memo: $100M USDC vault on Morpho Blue

## Executive summary

I propose ten exact Morpho markets spanning BTC, ETH/LST/LRT, Sky risk capital,
fixed-maturity reinsurance credit, private credit, and a governance-token
wrapper. The snapshot target deploys $100M across all ten markets: $48.25M cbBTC,
$19.25M WBTC, $9.25M PT-reUSD, $6.50M across two wstETH markets, $5.00M each
in AA_FalconXUSDC and dCOMP, $4.25M stUSDS, $1.50M weETH, and $1.00M WETH.
The portfolio has no idle USDC and $82.2M of stressed-withdrawable market
liquidity.

The projected 14-day whole-vault native APR is 2.56% under zero borrower
response. The main constraint is capacity, since adding $100M pushes the principal
markets below their starting utilization, reducing the immediate supplier rate
and the subsequent AdaptiveCurveIRM path. In historical replay, the constrained
strategy remains close to a matched static allocation and materially
outperforms a high-turnover spot-APY ranking rule.

## 1. Discovery and eligibility

### Market discovery

At startup, the program paginates Morpho's public GraphQL API
for listed Ethereum mainnet markets (`chainId = 1`) whose loan asset is
canonical USDC (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`). For every
result it retains the exact market ID, collateral, oracle and IRM addresses,
LLTV, fee, rewards,
supply, borrowing, unborrowed liquidity, utilization, rates, and recent APY
history.

### Scan and selection criteria

The snapshot contains 118 collateralized USDC markets. Discovery, mechanical
screening, preliminary desk review, and allocation are separate stages.

| stage | criterion | treatment and reason |
|---|---|---|
| discovery | Ethereum mainnet (`chainId = 1`) | Hard scope boundary; no bridge or cross-chain risk. |
| discovery | canonical USDC is the loan asset | Hard scope boundary; the vault supplies its existing asset without a swap or PYUSD/USDT basis exposure. |
| discovery | listed market with non-null collateral | Hard requirement; excludes idle markets and unlisted records. |
| mechanical scan | at least $1M supplied | Removes markets too small to support the operating ticket or meaningful capacity analysis. |
| mechanical scan | at least $0.5M borrowed | Requires evidence of borrower-paid demand; zero-demand headline rates are not scalable. |
| mechanical scan | utilization no higher than 99.5% | Removes effectively cashless markets where entry and withdrawal are already impaired. |
| desk review | collateral, oracle, LLTV, maturity, and known incidents | Select exact IDs only after the preliminary review described below; unresolved structures and incidents remain outside the universe. |
| capacity rank | projected native APR after a common $10M deposit | Uses the AdaptiveCurveIRM and our own dilution; spot APY is not a ranking objective. |
| allocation | ownership, family concentration and pre-deposit cash | Size within 35% post-deposit ownership, factor caps, 50% position exit coverage, and 60% portfolio stressed-withdrawable liquidity. |

The activity floors reduce 118 discoveries to 46 scan passes. Preliminary
exact-ID desk review selects ten. Each lends canonical USDC and uses Morpho's
AdaptiveCurveIRM, with zero market fees and no active rewards in the snapshot.
The projection is therefore native borrower-paid interest after utilization
impact.

### What market and collateral features matter most?


| feature | assessment completed for this submission | strategy use and limitation |
|---|---|---|
| protocol and market configuration | Confirmed Morpho Blue, canonical USDC, and the exact market ID, oracle, IRM, LLTV, fee, and collateral fields returned by the API. | Exact-ID approval prevents a safer ticker from implicitly approving a different configuration. Morpho contract and governance risk is common to every selected market and cannot be diversified inside this mandate. |
| collateral and redemption | Reviewed issuer and protocol documentation to identify the claim, custodian or borrower, stated redemption path, maturity, and loss-bearing role. Transparent liquid claims were preferred to gated or opaque claims. | Unresolved claims were excluded; distinct risks received family caps. Redemption behavior, complete admin controls, and legal enforceability were not independently verified. |
| oracle path | Inspected each exact oracle address, type, and the feed or vault-conversion components returned in the snapshot. This identified routes that include wrapper basis and routes, such as the selected cbBTC market, that assume wrapper parity. | The conclusion is recorded in the selected-ID metadata. Heartbeats, deviation thresholds, historical oracle accuracy, and oracle-versus-executable-price comparisons were not tested. |
| LLTV and liquidation depth | Fetched exact LLTV and calculated the nominal `1 − LLTV` buffer, then compared it qualitatively with collateral and oracle complexity. Lower LLTV was preferred for more complex collateral. | The exact LLTV/oracle pair informs eligibility and caps. Borrower health and liquidation-sized market depth were not reconstructed. |
| supplied TVL and ownership | Pulled supply from the API and calculated post-deposit ownership as `allocation / (existing supply + allocation)`. More external supply is preferable because it reduces concentration and market impact. | Automated $1M supply floor and 35% ownership cap. |
| borrowed TVL and demand | Pulled borrowing and utilization, compared the 32-hour supply and borrow changes, and replayed available historical states. Persistent borrowing is preferable to utilization caused only by supplier exits. | Automated $0.5M borrow floor. The projection holds borrowing fixed; borrower concentration and response elasticity were not estimated. |
| withdrawal risk | Calculated pre-deposit `supply − borrow` and coverage of each proposed position without counting our deposit as its own exit liquidity. Reviewed whether the collateral or lending structure also has gated redemption. | Automated 50% position coverage and 60% portfolio stressed-withdrawable constraints; live reductions are bounded by current market cash. These are capacity limits, not guarantees that borrowers will leave cash available. |
| utilization and IRM state | Recalculated utilization after every candidate allocation and integrated the AdaptiveCurveIRM path over 14 days. | Fully modeled input to post-impact and marginal APR; this replaces ranking by displayed APY. |
| rates and flows | Used spot, 1-day, and 30-day API rates plus historical replay. Supply growth without borrow growth was treated as crowding. | Used for validation, reporting, and recomputation—not as a fitted return forecast. |
| concentration | Manually mapped markets to shared BTC, ETH/LST/LRT, Sky, FalconX, re-credit, and COMP factors, and estimated the share of each market supplied by large curated vaults. | Per-market, 35% ownership, family, and aggregate non-blue caps are enforced in code. Curated-vault share is reported but not hard-gated because the enrichment is incomplete. |
| fees, rewards, and reallocation friction | Pulled market fees and rewards and separated incentives from native interest. For reallocation, the planner checks market cash, a minimum ticket, expected gain, gas, and rolling turnover. | Fees enter projected rates and rewards have zero base weight. Routine moves require their 14-day modeled benefit to cover a placeholder $60 per withdrawal or supply leg as well as a 15 bp annual gain hurdle. Production would replace $60 with a live transaction estimate and account for adapter hops, reverts, and execution delay. |

The primary allocator does not use a composite risk score or subtract a
subjective APR premium. A comparable expected-loss estimate would require
default probabilities, loss-given-default, oracle/depeg frequencies,
liquidation price-impact curves, and cross-market dependence that are not
identified by the available history. Risk is represented through exact-ID
eligibility and exposure constraints.

### Examples of excluded and deferred candidates

Mechanical scan passage is not approval. Selected-market risks and caps are
explained in Section 3; the examples below show what the strategy excludes or
defers before optimization.

| candidate | decision | controlling reason |
|---|---|---|
| PRIME/PYUSD | out of scope | PYUSD is the loan asset; a USDC vault would need a swap or cross-asset adapter and would add PYUSD basis and execution risk. |
| mF-ONE/USDC | excluded | Gated off-chain redemption, whitelisted borrower structure, and concentrated lender base are inconsistent with the vault's withdrawal objective. |
| OETH/USDC reviewed route | excluded | The observed ETH/USD route did not expose a separate OETH/ETH basis leg; a wrapper impairment could therefore be reflected too slowly. |
| wstUSR/USDC | excluded | The reviewed market was associated with the 2026 Resolv exploit path and no longer supplied usable exit liquidity. |
| sdeUSD/USDC | excluded | Realized collateral impairment, bad debt, and delisting fail the incident and redemption tests. |
| rETH/USDC `0x0a15…` | deferred | 86% LLTV is aggressive for the smaller LST venue and available cash does not support the required ticket with the desired exit margin. |
| LBTC/USDC `0xbf02…` | deferred | The yield-bearing BTC wrapper adds consortium, redemption, and basis risks; only $0.13M cash made the $1M ticket fail exit coverage. |
| alternate IDs for approved symbols | not automatically eligible | A symbol match does not validate a market's oracle, LLTV, IRM, fee, or liquidity. Only the exact IDs in Section 3 were selected. |

## 2. Allocation methodology

### Lower stable yield versus higher unstable yield

I compare markets in four steps:

1. Reject any market that fails collateral, oracle, LLTV, or liquidity review.
2. Project the rate after a common $10M deposit rather than rank spot APY.
3. Compare the whole position's projected revenue and the next dollar's
   marginal revenue, including dilution of capital already allocated there.
4. When projected marginal returns are close, prefer the market with greater
   observed rate persistence and withdrawal capacity.

The cbBTC/LBTC comparison shows why this ordering matters:

| market | spot APY | supply / unborrowed liquidity | projected APR at $10M | decision |
|---|---:|---:|---:|---|
| cbBTC | 3.42% | $309.7M / $42.7M | 2.97% | Passes capacity and exit tests. |
| LBTC | 8.13% | $1.8M / $0.13M | 0.13% | Fails the $1M ticket's exit-coverage requirement. |

The base objective is to deploy the full $100M and maximize post-impact native
Morpho interest without weakening eligibility or exposure limits. If hard
capacity is insufficient, the residual remains idle. The snapshot has
no active rewards. The code can include API reward APR with an explicit
`reward_weight`, but keeps native and incentive attribution separate and uses
zero until token liquidity, claimability, and expiry are reviewed.

### Sizing across markets

Adding supply lowers utilization and can reduce the APR earned by capital
already in that market. The allocator therefore compares the change in total
annual interest, not the APR displayed after the deposit. For example, suppose
a $10M position earns 4.00%, or $400k annually. If another $250k lowers the
whole position to 3.95%, projected revenue becomes $404,875. The next $250k has
added only $4,875, equivalent to a 1.95% marginal return—not 3.95%.

For allocation `a`, projected annual revenue is `a × projected APR(a)`. The
marginal return on an additional amount `Δ` is:

```text
[revenue(a + Δ) − revenue(a)] / Δ
```

The algorithm starts with no positions and repeatedly assigns the next
admissible amount to the market with the highest marginal return. It uses a $1M
step to open a position and $250k steps thereafter, while enforcing every
market, family, ownership, and liquidity constraint. After the initial fill, it
tests whether moving $1M can profitably open an unfunded market, then tests
$250k moves between funded markets.

### Portfolio constraints

| constraint | reason | present effect |
|---|---|---|
| 50% per market | No immutable market may hold a majority of NAV. | Non-binding; cbBTC is 48.25%. |
| 67.5% BTC family | Aggregates cbBTC and WBTC because wrapper diversity does not remove BTC price/liquidation correlation. It is the lowest tested 2.5-point cap that deploys the full ten-market snapshot NAV. | Binds at $67.5M. |
| 25% ETH/LST/LRT family | Aggregates WETH, both wstETH markets, and weETH; provides operating headroom without permitting an ETH-majority book. | Non-binding at 9.0%. |
| 5% Sky family | Limits stUSDS risk-capital, SKY-backed borrower, governance, and conversion exposure. | Non-binding at 4.25%; aggregate non-blue binds first. |
| 10% Re-credit family | Bounds shared reUSD/reinsurance, NAV, redemption and maturity risk across direct or PT forms. | PT-reUSD is 9.25%. |
| 5% FalconX credit family | Limits one permissioned borrower, lending-cycle, NAV and legal-enforcement exposure. | Binds AA_FalconXUSDC at $5M. |
| 5% COMP family | Limits volatile COMP collateral plus dCOMP wrapper-administration and delegation risk. | Binds dCOMP at $5M. |
| 25% non-blue collateral | Keeps at least 75% of NAV in the selected blue-chip tier. | Binds at 25.0%. |
| 35% post-deposit ownership | Prevents the vault from becoming the majority or dominant supplier. | Non-binding; funded markets are 9–27%. |
| 50% position exit coverage | Requires pre-existing unborrowed liquidity equal to at least half of each position. | Nearly binds PT-reUSD and sizes smaller ETH venues. |
| 60% portfolio stressed-withdrawable | Requires vault idle plus pre-deposit market cash to cover at least 60% of NAV. | $82.2M currently. |
| $1M minimum ticket | Excludes positions too small to justify execution and monitoring. | Binds WETH at $1M. |
| 100% deployment goal | Seek full use of NAV only after all hard constraints; infeasible residual stays idle. | All $100M deploys across ten markets. |

These are proposed governance limits to provide a balance between max allocation, desired APR, and asset diversity.

## 3. Selected universe and target allocation

### Economic characteristics and target

The allocation inputs below are from the committed Morpho API snapshot observed
at 2026-08-01 23:36:11 UTC. `main.py allocate` fetches a new snapshot on every
live run; the committed state is retained to make the reported target
reproducible.

`Unborrowed liquidity` is `supplied USDC − borrowed USDC`: USDC currently held
in the Morpho market and available collectively to suppliers who withdraw.
`Exit coverage` is `min(our target, pre-deposit unborrowed liquidity) / our
target`. `Cash ratio` is unborrowed liquidity divided by market supply. All
selected markets use the AdaptiveCurveIRM, whose utilization target is 90%.

The selected markets balance capacity for a large supply addition, persistent
borrower demand, post-allocation yield, withdrawal liquidity, and distinct risk
factors. The first table reports observed market state before the deposit; the
second reports the modeled target and resulting portfolio exposures.

#### Observed pre-deposit market state

| market | supply / borrow / cash | cash ratio | util. / target | supply / borrow APY | 1d / 30d supply APY | 32h Δ supply / borrow |
|---|---:|---:|---:|---:|---:|---:|
| cbBTC `0x64d6…` | $309.7M / $267.0M / $42.7M | 13.8% | 86.2% / 90% | 3.42% / 3.98% | 3.45% / 3.73% | −$2.15M / +$0.14M |
| WBTC `0x3a85…` | $123.8M / $106.9M / $16.9M | 13.7% | 86.3% / 90% | 3.42% / 3.97% | 3.43% / 3.72% | −$0.75M / +$0.15M |
| PT-reUSD `0x1e9d…` | $43.4M / $38.7M / $4.7M | 10.8% | 89.2% / 90% | 7.21% / 8.11% | 7.36% / 8.35% | +$0.04M / +$0.25M |
| AA_FalconXUSDC `0xe83d…` | $49.2M / $44.3M / $4.9M | 9.9% | 90.1% / 90% | 5.55% / 6.18% | 5.17% / 5.67% | +$5.04M / +$0.01M |
| dCOMP `0x2485…` | $13.7M / $10.8M / $2.9M | 21.2% | 78.8% / 90% | 8.87% / 11.38% | 9.06% / 11.90% | −$0.05M / +$0.00M |
| wstETH `0xb323…` | $23.4M / $20.3M / $3.2M | 13.6% | 86.4% / 90% | 3.42% / 3.97% | 3.42% / 3.72% | −$0.04M / +$0.11M |
| stUSDS `0xd570…` | $18.6M / $14.3M / $4.4M | 23.4% | 76.6% / 90% | 3.97% / 5.21% | 3.93% / 5.66% | −$0.59M / +$0.00M |
| wstETH `0x7e58…` | $9.1M / $7.8M / $1.3M | 13.8% | 86.2% / 90% | 3.42% / 3.98% | 3.42% / 3.73% | +$0.20M / +$0.55M |
| weETH `0x3437…` | $7.0M / $6.1M / $0.9M | 13.3% | 86.7% / 90% | 3.94% / 4.56% | 4.03% / 4.26% | −$0.07M / +$0.00M |
| WETH `0x94b8…` | $4.4M / $3.8M / $0.6M | 13.7% | 86.3% / 90% | 3.42% / 3.97% | 3.43% / 3.72% | −$0.06M / −$0.01M |

#### Modeled allocation and risk fields

| market | LLTV | oracle/pricing construction | target | post-util. | projected APR | ownership | exit coverage | observed curated-vault share |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| cbBTC `0x64d6…` | 86% | ChainlinkOracleV2; direct BTC/USD | $48.25M | 74.6% | 2.23% | 13.5% | 88.4% | 41.4% |
| WBTC `0x3a85…` | 86% | WBTC/BTC × BTC/USD ÷ USDC/USD | $19.25M | 74.7% | 2.24% | 13.5% | 87.9% | 13.0% |
| PT-reUSD `0x1e9d…` | 91.5% | Pendle PT pricing over reUSD NAV/redemption value | $9.25M | 73.5% | 4.21% | 17.6% | 50.6% | 3.7% |
| AA_FalconXUSDC `0xe83d…` | 77% | FalconX Credit Vault LP-token NAV feed | $5.00M | 81.8% | 4.05% | 9.2% | 97.2% | 33.6% |
| dCOMP `0x2485…` | 62.5% | two-feed COMP/USDC route; one-for-one dCOMP wrapper | $5.00M | 57.8% | 3.64% | 26.7% | 58.1% | n/a |
| wstETH `0xb323…` | 86% | wstETH/stETH conversion × ETH/USD | $4.75M | 71.9% | 2.03% | 16.9% | 66.9% | 38.1% |
| stUSDS `0xd570…` | 86% | stUSDS conversion × USDS/USD ÷ USDC/USD | $4.25M | 62.4% | 2.08% | 18.6% | 100.0% | n/a |
| wstETH `0x7e58…` | 86% | separate wstETH/stETH × ETH/USD route | $1.75M | 72.2% | 2.06% | 16.2% | 71.6% | 47.8% |
| weETH `0x3437…` | 77% | weETH/ETH conversion × ETH/USD | $1.50M | 71.4% | 2.28% | 17.7% | 62.1% | 30.9% |
| WETH `0x94b8…` | 86% | direct ETH/USD | $1.00M | 70.2% | 1.92% | 18.6% | 60.1% | 15.4% |

Note: The curated-vault share is a best-effort sum across the 200 largest listed
vaults queried during snapshot enrichment. `n/a` means the enrichment produced
no value for that market.

Full market IDs are defined in `curator/mandate.py`; the prefixes above
distinguish the exact markets in this memo.

### Market-by-market selection rationale and risk

**cbBTC/USDC — BTC core.** [cbBTC](https://help.coinbase.com/en-gb/coinbase/trading-and-funding/sending-or-receiving-cryptocurrency/coinbase-wrapped-btc)
is a Coinbase-custodied BTC claim. Its $267.0M borrowing and $42.7M cash provide
the strongest selected-market capacity. The direct BTC/USD oracle does not observe a
cbBTC/BTC discount; the 86% LLTV, custody, redemption, and BTC liquidation risks
therefore remain subject to market and BTC-family caps.

**WBTC/USDC — BTC core.** [WBTC](https://docs.wbtc.network/) is a custodial,
tokenized-BTC claim with a different custody system from cbBTC. Its $106.9M
borrowing and $16.9M cash support a second core position. The oracle observes
WBTC/BTC basis through a composed route, but adds feed dependencies. Its 86%
LLTV and common BTC liquidation exposure remain inside the BTC-family cap.

**wstETH/USDC (`0xb323…`) — primary LST market.** [wstETH](https://docs.lido.fi/contracts/wsteth/)
is the non-rebasing wrapper of Lido stETH, a claim on pooled staked ETH and
rewards. It is the largest selected non-BTC venue with $20.3M borrowed. Its 86%
LLTV and wstETH/stETH × ETH/USD route leave Lido governance, validator,
withdrawal, basis, and liquidation-liquidity risks under the ETH-family cap.

**stUSDS/USDC — Sky risk-capital token.** [Sky describes stUSDS](https://developers.skyeco.com/protocol/tokens/stusds/)
as an ERC-4626 risk-capital token funding SKY-backed borrowing, not the sUSDS
savings token. Its $14.3M borrowing and $4.4M cash provide capacity, while
borrower/system loss, governance, conversion, redemption, and USDS-basis risks
justify the 5% Sky cap and aggregate non-blue limit.

**wstETH/USDC (`0x7e58…`) — secondary LST market.** The collateral claim is the
same as the primary market, but the oracle contract and cash pool differ. Its
$7.8M borrowing supports a minimum ticket and adds venue capacity, not
independent asset risk; both wstETH positions share the ETH-family cap.

**weETH/USDC — LRT market.** [weETH](https://help.ether.fi/en/articles/595737-weeth)
is ether.fi's liquid-restaking token. The selected 77% LLTV is preferable to
the reviewed 86% alternative because restaking, accounting, redemption, and
weETH/ETH basis risks exceed those of WETH. Its $6.1M borrowing adds a small ETH
venue, while $0.9M cash and the non-blue cap limit size.

**PT-reUSD/USDC — fixed-maturity reinsurance claim.** A [Pendle PT](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/PT)
is redeemable for its accounting asset at maturity; this contract expires 10
December 2026. [reUSD](https://docs.re.xyz/protocol/how-the-re-protocol-works)
is a reinsurance-capital claim senior to a separate first-loss layer. Strong
borrowing supports the highest selected post-impact APR, but the 91.5% LLTV,
NAV, redemption, PT-liquidity, and roll risks require a 10% family cap and 50%
exit coverage.

**AA_FalconXUSDC/USDC — private-credit vault LP token.** The collateral address
is [Pareto's listed FalconX Credit Vault LP token](https://docs.pareto.credit/developers/addresses/product/credit-vaults).
[Pareto's Credit Vault design](https://docs.pareto.credit/product) sends
deposited assets to a whitelisted borrower and processes exits through lending
cycles. Its $44.3M borrower demand and cash support a position, but `AA_` is not
treated as a rating. FalconX default, NAV, legal-enforcement, and delayed-exit
risks remain despite the 77% LLTV, so the 5% single-counterparty cap binds.

**dCOMP/USDC — enhanced governance-token satellite.** [Api3 describes dCOMP](https://docs.api3.org/curation/)
as an ownable one-for-one COMP wrapper with configurable delegation and deposit
permissions. Its $10.8M borrowing and 62.5% LLTV offer yield with a larger
nominal liquidation buffer, but COMP volatility, wrapper administration,
oracle, and liquidation-depth risks require a 5% COMP cap.

**WETH/USDC — funded ETH market.** WETH is the canonical ERC-20
wrapper of ETH, with a direct ETH/USD oracle and no staking or custody wrapper.
Only $3.8M borrowing and $0.6M cash limit capacity; the $1M position contributes
to full deployment while remaining inside the ETH cap.

### Why the $100M projected APR is ~ 2.56%

Spot rates apply to current market supply. The modeled deposit increases
supplied USDC without increasing borrowed USDC, reducing utilization and the
supplier rate. While utilization remains below the AdaptiveCurveIRM's 90%
target, `rateAtTarget` also declines. Integrating this path over 14 days gives
a 2.56% portfolio APR.

This scale effect also appears historically. On the same hourly October
allocation path, treating the vault as a price taker produces 2.79% versus
2.27% after including its own utilization impact. The daily June–July
comparison is 3.16% versus 2.32%.

### Can a $100M vault reach prime lending rates?

Using approximately 3.5% as the target, not under current conditions and the
base assumption that borrowers do not respond to our deposit. The selected
portfolio projects 2.56% because deploying $100M reduces utilization across the
available markets. Even an optimistic, non-investable experiment that treats
all 46 mechanical scan passes as blue-chip reaches only 3.14% native APR, or
3.25% if every current incentive is valued fully. That experiment ignores
collateral and oracle exclusions, so it is a capacity ceiling rather than a
candidate portfolio. Reaching prime rates at this size requires more borrower
demand, durable incentives, or additional screened market capacity.

## 4. Monitoring and rebalancing

### Response to a material market change

`allocate` calculates a desired state. `rebalance` additionally accepts current
positions, fetches live state by default, removes our supply from the indexed
market totals, recomputes the target, and emits proposed moves. It does not
submit transactions. The same planner drives the historical strategy.

The planner first exits a manually disabled, mechanically ineligible, or
T−30 PT market, limited by cash currently withdrawable from that market. It
then withdraws enough to restore market, ownership, family, non-blue, and
portfolio-liquidity constraints. These defensive reductions bypass economic
gates. If the current book is compliant, it considers target-directed moves
subject to the routine execution gates below.

| failure mode or signal | response |
|---|---|
| API/indexer is stale or disagrees with RPC state | Fail closed for new supply; retain the last verified target and reconcile against chain state. |
| External supply rises without matching borrow growth | Recompute the rate curve and target; trade only if the economic gates pass. |
| Market cash or portfolio stressed-withdrawable liquidity breaches its floor | Stop additions and deallocate available USDC without waiting for the yield gate. |
| Oracle heartbeat/deviation, collateral redemption, NAV, or bad-debt incident | Disable new supply, set target to zero, and record any liquidity-constrained residual. |
| PT enters the T−60 review or T−30 exit window | Approve a successor through governance, then target the old market to zero and roll only withdrawable cash. |
| Execution reverts, gas spikes, or quoted cash disappears | Do not assume the move occurred; refresh state and recompute before retrying. |

The code derives activity, maturity, rate, concentration, and liquidity signals
from its inputs. Oracle, redemption, NAV, bad-debt, and legal incidents require
an external monitor or curator decision; `--disable-market` passes that decision
to the planner. An API failure stops the live command rather than silently using
the committed snapshot.

### Response when a market becomes crowded

External supply inflows reduce utilization unless matched by borrow growth.
They can also increase competition for withdrawals. The strategy therefore:

- recompute post-deposit and marginal APR after external supply inflows;
- stop new allocation when another market offers better marginal revenue;
- reduce the target only when the gain survives execution gates; and
- continue enforcing ownership and exit-liquidity limits despite a high spot
  APY.

### Guardrails against excessive churn

I would monitor safety-critical state every block or few minutes and recalculate
the target hourly. Recalculation does not automatically cause a trade. Collateral
eligibility and risk caps receive a separate weekly human review.

For an ordinary yield reallocation, both the source's excess and the
destination's shortfall must exceed $1M, or 1% of NAV. This matches the minimum
position size. A $3M threshold sometimes left cash idle because the desired
deposits were divided into several changes smaller than $3M. Reducing the
threshold to $1M increased average deployment by 0.5–4.1 percentage points
across the three tests, while changing total trading by only −$1M to +$4M.
The move must also improve
projected annual return on moved capital by at least 15 bp and cover transaction
cost over the 14-day rate horizon. The 15 bp threshold is an untuned noise
buffer. It was non-binding from 0–30 bp in the tested tapes. I use $60 per
withdrawal or supply leg, while a live system would use current gas.

Routine turnover is limited to $10M of gross flows in any seven days. Because a
market-to-market reallocation has a withdrawal and a supply leg, moving $5M uses
the full $10M allowance. Raising the cap to $20M did not materially improve
return in the three tested tapes, so I retain the more conservative setting.
Initial vault construction is not a rotation and follows the full feasible
target outside this rolling limit.
A disabled market or hard-limit breach is different: reduce it immediately as
far as available cash permits, without applying the yield or turnover tests.

## 5. Proposed Morpho vault configuration

| parameter | proposed setting |
|---|---|
| asset | canonical Ethereum USDC |
| selected allocation universe | ten exact IDs in `curator/mandate.py`; all ten start funded in the snapshot target |
| market caps | absolute caps derived from market weight, ownership, and exit-liquidity limits |
| target computation | hourly and after material state changes |
| supply routing | highest admissible post-impact marginal revenue |
| withdrawal routing | idle/adapter first, then unborrowed liquidity in overweight markets |
| curator | risk-committee multisig for adapters, markets, caps, roles, and other risk parameters |
| sentinel | independent risk multisig for cap reductions, deallocation, and pending-action revocation |
| timelock | 72 hours for risk-increasing changes; fastest supported path for risk reduction |
| neutral idle target | 0%; idle appears when capacity binds or risk is reduced |

Morpho market parameters are immutable, so a PT roll requires adding a successor
market through the timelock. Review it by T−60, target the old market to zero at
T−30, and withdraw only as market cash becomes available; collateral maturity
does not itself repay USDC suppliers.

## 6. Historical validation

All returns use the full $100M NAV denominator; idle earns 0%.

| window | grid | constrained strategy | static | spot chaser | avg. deployed | liquidations / repaid | supplier loss |
|---|---|---:|---:|---:|---:|---:|---:|
| Oct 10–16 cascade (four available IDs) | hourly + exact events | 2.76% | 2.93% | 1.95% | 76.7% | 27 / $7.69M | $0 |
| Oct 10–Dec 25 (four available IDs) | hourly + exact events | 2.27% | 2.44% | 1.76% | 74.3% | 128 / $41.61M | <$0.01 |
| Apr 21–May 20 (six available IDs) | daily + exact events | 2.05% | 2.09% | 1.04% | 80.9% | 7 / <$0.01M | $0 |
| Jun 25–Jul 24 (eight available IDs) | daily + exact events | 2.32% | 2.35% | 0.86% | 84.8% | 13 / $0.07M | $0 |

`Liquidations` counts on-chain liquidation logs, not distinct borrowers or
vault-level events. The selected markets recorded no bad debt during the
October cascade week. Liquidation volume is not supplier revenue.

The active book trails static in all four windows after enforcing live-style
constraint repair and execution gates, but it materially outperforms the
spot-APY rule with far less turnover. The result does not establish rebalancing
alpha; it tests whether the operating policy behaves coherently across a
liquidation event and quieter tapes.
Competitor attribution would require matched NAV, dates, flows, fees, and risk
constraints. Historical universes are point-in-time: only four of the current
ten IDs existed on 10 October 2025, so that replay tests the allocation rule,
not today's ten-market composition.

## 7. Limitations

- The counterfactual vault changes within-period utilization but does not alter
  the next external historical observation; borrower and competing-supplier
  responses are not reconstructed.
- Historical oracle prices, borrower health, transaction ordering, MEV,
  rewards, vault user flows, and complete underlying action flow are absent.
- The replay uses current selected IDs that existed at each historical start;
  it does not reconstruct the discovery and selection decisions available
  at that date and therefore retains survivorship bias.
- The public API is an indexer without an SLA. `main.py allocate` fetches fresh
  API state on every run and fails instead of silently using the committed
  snapshot. Production should additionally enforce data-age limits and
  reconcile critical state with RPC reads.
