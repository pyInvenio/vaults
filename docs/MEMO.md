# Curator memo: $100M USDC vault on Morpho Blue

## Executive summary

I propose a hybrid universe of ten exact Morpho markets spanning BTC,
ETH/LST/LRT, Sky risk capital, fixed-maturity reinsurance credit, private
credit, and a governance-token wrapper.

- **Allocation:** deploy all $100M, led by $48.25M in cbBTC and $19.25M in
  WBTC, with the remaining $32.5M diversified across eight capped positions.
- **Projected return:** 2.56% native APR over 14 days, assuming borrowing does
  not respond to our deposit.
- **Withdrawal capacity:** existing market cash, measured before our deposit,
  covers $82.2M of the proposed positions.
- **Rebalancing:** recalculate hourly, but trade only after risk, drift,
  expected-return, gas, liquidity, and turnover checks.

The central constraint is scale. Adding $100M lowers utilization and therefore
the supplier rate in the principal markets. In historical replay, this approach
earned close to leaving the initial allocation alone and materially more than
chasing the highest displayed APY. I do not interpret that result as evidence
of rebalancing alpha; it mainly shows that accounting for capacity avoids a
costly mistake.

## 1. Building the investable universe

We start with every listed Morpho market on Ethereum whose loan asset is
canonical USDC. The API pull records the exact market ID and the fields needed
to evaluate it: collateral, oracle, IRM, LLTV, fees, rewards, supply, borrowing,
cash, utilization, rates, and recent APY history. Starting from the full set
avoids choosing familiar collateral symbols first and looking for evidence
afterward.

The snapshot contains 118 collateralized USDC markets. Discovery, mechanical
screening, preliminary desk review, and allocation are separate stages.

| stage | criterion | treatment and reason |
|---|---|---|
| discovery | Ethereum mainnet (`chainId = 1`) | Keeps the portfolio within the assignment and avoids adding bridge or cross-chain risk. |
| discovery | canonical USDC is the loan asset | The vault can supply its existing asset without a swap or PYUSD/USDT basis exposure. |
| discovery | listed market with non-null collateral | Excludes idle markets and unlisted records. |
| mechanical scan | at least $1M supplied | Removes markets too small to support the operating ticket or meaningful capacity analysis. |
| mechanical scan | at least $0.5M borrowed | Requires evidence of borrower-paid demand; zero-demand headline rates are not scalable. |
| mechanical scan | utilization no higher than 99.5% | Removes effectively cashless markets where entry and withdrawal are already impaired. |
| desk review | collateral, oracle, LLTV, maturity, and known incidents | Select exact IDs only after the preliminary review described below; unresolved structures and incidents remain outside the universe. |
| capacity rank | projected native APR after a common $10M deposit | Uses the AdaptiveCurveIRM and our own dilution; spot APY is not a ranking objective. |
| allocation | ownership, family concentration and pre-deposit cash | Size within 35% post-deposit ownership, factor caps, 50% position cash coverage, and 60% portfolio cash coverage. |

The two activity floors reduce 118 discoveries to 46 candidates. I then review
the collateral, oracle, LLTV, incidents, and usable liquidity of each exact
market ID and select ten. All ten use Morpho's AdaptiveCurveIRM. At the
snapshot, they also have zero market fees and no active rewards, so the return
projection is entirely borrower-paid interest after accounting for our own
deposit.

### Underwriting

| feature | how it was assessed | how it affects the decision |
|---|---|---|
| protocol and configuration | Confirmed Morpho Blue, canonical USDC, and the exact market ID, oracle, IRM, LLTV, fee, and collateral returned by the API. | Eligibility is by exact ID, not ticker. Morpho contract and governance risk is common to the whole portfolio and cannot be diversified inside this mandate. |
| collateral and redemption | Reviewed the claim, custodian or borrower, redemption path, maturity, and loss-bearing role using issuer and protocol documentation. | Exclude unresolved structures; cap distinct custody, credit, redemption, and maturity risks. Legal enforceability and complete admin controls were not independently verified. |
| oracle path | Inspected each oracle address, type, and available feed or vault-conversion components. | Prefer routes that observe wrapper basis. Heartbeats, deviation thresholds, historical accuracy, and executable-price comparisons were not tested. |
| LLTV and liquidation depth | Compared `1 − LLTV` with collateral and oracle complexity; preferred lower LLTV for more complex claims. | LLTV and oracle construction inform eligibility and caps. Borrower health and liquidation-sized market depth were not reconstructed. |
| supplied TVL and ownership | Pulled supply and calculated post-deposit ownership as `allocation / (existing supply + allocation)`. | Require at least $1M supplied and cap the vault at 35% of post-deposit market supply. |
| borrowed TVL and demand | Pulled borrowing, utilization, recent supply/borrow changes, and available historical states. | Require at least $0.5M borrowed. Hold borrowing fixed in the projection; borrower concentration and elasticity are not estimated. |
| withdrawal risk | Calculated cash as `supply − borrow` before our deposit and reviewed any gated redemption mechanics. | Require 50% cash coverage per position and 60% across the portfolio. Live withdrawals remain bounded by actual market cash. |
| utilization, rates, and IRM state | Recalculated utilization after each proposed deposit and integrated the AdaptiveCurveIRM path over 14 days. Compared spot, 1-day, and 30-day rates. | Rank post-impact and marginal APR rather than displayed APY. Treat supply growth without borrow growth as crowding, not durable demand. |
| concentration | Mapped markets to shared BTC, ETH/LST/LRT, Sky, FalconX, re-credit, and COMP factors. Estimated curated-vault share where available. | Enforce market, ownership, family, and aggregate non-blue caps. Report curated-vault share without hard-gating an incomplete estimate. |
| fees, rewards, and execution | Pulled fees and rewards separately. The rebalance planner checks cash, minimum size, expected gain, gas, and rolling turnover. | Include fees; give rewards zero base weight. Require 14-day modeled benefit to cover $60 per leg plus a 15 bp annual gain hurdle. Production would use live gas and account for adapters, reverts, and delay. |

I do not compress these risks into one score or subtract an invented "risk
premium" from APR. Doing that credibly would require default probabilities,
loss-given-default, oracle and depeg frequencies, liquidation price-impact
curves, and cross-market dependence that this dataset cannot identify. Instead,
I make risk visible through exact-ID approval and explicit exposure limits.

### What I excluded or deferred

Passing the scan is not approval. The examples below show where I stopped after
underwriting, before yield optimization could influence the decision.

| candidate | decision | controlling reason |
|---|---|---|
| PRIME/PYUSD | out of scope | PYUSD is the loan asset; a USDC vault would need a swap or cross-asset adapter and would add PYUSD basis and execution risk. |
| mF-ONE/USDC | excluded | Gated off-chain redemption, whitelisted borrower structure, and concentrated lender base are inconsistent with the vault's withdrawal objective. |
| OETH/USDC reviewed route | excluded | The observed ETH/USD route did not expose a separate OETH/ETH basis leg; a wrapper impairment could therefore be reflected too slowly. |
| wstUSR/USDC | excluded | The reviewed market was associated with the 2026 Resolv exploit path and no longer supplied usable exit liquidity. |
| sdeUSD/USDC | excluded | Realized collateral impairment, bad debt, and delisting fail the incident and redemption tests. |
| rETH/USDC `0x0a15…` | deferred | 86% LLTV is aggressive for the smaller LST venue and available cash does not support the required ticket with the desired exit margin. |
| LBTC/USDC `0xbf02…` | deferred | The yield-bearing BTC wrapper adds consortium, redemption, and basis risks; only $0.13M cash made the $1M ticket fail exit coverage. |
| alternate IDs for selected symbols | not automatically eligible | A symbol match does not validate a market's oracle, LLTV, IRM, fee, or liquidity. Only the exact IDs in Section 3 were selected. |

## 2. Allocating $100M

### Stable yield versus headline yield

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

My objective is to deploy the full $100M at the highest post-impact native
return the approved markets can support. I would rather leave a residual idle
than weaken the eligibility or exposure limits to force deployment. There are
no active rewards in this snapshot. If incentives appear, I would value them
separately and only after reviewing the token's liquidity, claimability, and
expiry; the base case gives them no credit.

### Allocate on marginal return

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

### Portfolio guardrails

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
| 60% portfolio cash coverage | Requires vault idle plus pre-deposit market cash to cover at least 60% of NAV. | $82.2M currently. |
| $1M minimum ticket | Excludes positions too small to justify execution and monitoring. | Binds WETH at $1M. |
| 100% deployment goal | Seek full use of NAV only after all hard constraints; infeasible residual stays idle. | All $100M deploys across ten markets. |

These are proposed governance limits, not estimated default probabilities or
Morpho protocol constraints. They trade some projected yield for diversification
and withdrawal capacity while still allowing full deployment in the snapshot.

## 3. Proposed portfolio

### Market data and target allocation

The allocation below uses a Morpho API snapshot observed at 2026-08-01 23:36:11
UTC. I commit that snapshot so the result can be reproduced, but every live
allocation run fetches current data rather than treating these numbers as
current indefinitely.

The tables use three liquidity measures:

- **Unborrowed liquidity:** supplied USDC minus borrowed USDC—the cash currently
  available to all suppliers.
- **Cash ratio:** unborrowed liquidity divided by total market supply.
- **Exit coverage:** the share of our target covered by cash that existed before
  our deposit. Our deposit is not counted as its own exit liquidity.

All selected markets use the AdaptiveCurveIRM with a 90% target utilization.

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
is a Coinbase-custodied BTC claim. **Why included:** $267.0M borrowed and $42.7M
cash provide the strongest capacity in the selected set. **Principal risks:**
the direct BTC/USD oracle does not observe a cbBTC/BTC discount, while the 86%
LLTV leaves custody, redemption, and BTC-liquidation exposure. The market and
BTC-family caps limit those risks.

**WBTC/USDC — BTC core.** [WBTC](https://docs.wbtc.network/) is a custodial,
tokenized-BTC claim with a different custody system from cbBTC. **Why included:**
$106.9M borrowed and $16.9M cash support a second large position, and the oracle
observes WBTC/BTC basis. **Principal risks:** the composed oracle adds feed
dependencies, and the 86% LLTV retains the same BTC liquidation factor as
cbBTC. Both positions share the BTC-family cap.

**wstETH/USDC (`0xb323…`) — primary LST market.** [wstETH](https://docs.lido.fi/contracts/wsteth/)
is the non-rebasing wrapper of Lido stETH, a claim on pooled staked ETH and
rewards. **Why included:** it is the largest selected non-BTC venue, with
$20.3M borrowed. **Principal risks:** the 86% LLTV and wstETH/stETH × ETH/USD
route retain Lido governance, validator, withdrawal, basis, and liquidation
risks. The ETH-family cap aggregates these exposures.

**stUSDS/USDC — Sky risk-capital token.** [Sky describes stUSDS](https://developers.skyeco.com/protocol/tokens/stusds/)
as an ERC-4626 risk-capital token funding SKY-backed borrowing, not the sUSDS
savings token. **Why included:** $14.3M borrowed and $4.4M cash provide useful
non-BTC capacity. **Principal risks:** borrower or system losses, governance,
conversion, redemption, and USDS basis. The 5% Sky cap and aggregate non-blue
limit control the position.

**wstETH/USDC (`0x7e58…`) — secondary LST market.** The collateral claim is the
same as in the primary market, but the oracle and cash pool differ. **Why
included:** $7.8M borrowed supports a second venue and a minimum ticket.
**Principal risk:** this adds market capacity, not independent collateral
diversification, so both wstETH positions share the ETH-family cap.

**weETH/USDC — LRT market.** [weETH](https://help.ether.fi/en/articles/595737-weeth)
is ether.fi's liquid-restaking token. **Why included:** $6.1M borrowed adds a
small ETH venue, and the selected 77% LLTV is preferable to the reviewed 86%
alternative. **Principal risks:** restaking, accounting, redemption, and
weETH/ETH basis. Only $0.9M cash and the non-blue cap keep the position small.

**PT-reUSD/USDC — fixed-maturity reinsurance claim.** A [Pendle PT](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/PT)
is redeemable for its accounting asset at maturity; this contract expires 10
December 2026. [reUSD](https://docs.re.xyz/protocol/how-the-re-protocol-works)
is a reinsurance-capital claim senior to a separate first-loss layer. **Why
included:** strong borrowing produces the highest selected post-impact APR.
**Principal risks:** 91.5% LLTV, NAV accuracy, redemption, PT liquidity, and the
required pre-maturity roll. A 10% family cap and 50% exit coverage limit it.

**AA_FalconXUSDC/USDC — private-credit vault LP token.** The collateral address
is [Pareto's listed FalconX Credit Vault LP token](https://docs.pareto.credit/developers/addresses/product/credit-vaults).
[Pareto's Credit Vault design](https://docs.pareto.credit/product) sends
deposited assets to a whitelisted borrower and processes exits through lending
cycles. **Why included:** $44.3M of borrower demand and available cash support a
position. `AA_` is not treated as a rating. **Principal risks:** FalconX default,
NAV, legal enforcement, and delayed exits remain despite the 77% LLTV. The 5%
single-counterparty cap binds.

**dCOMP/USDC — enhanced governance-token satellite.** [Api3 describes dCOMP](https://docs.api3.org/curation/)
as an ownable one-for-one COMP wrapper with configurable delegation and deposit
permissions. **Why included:** $10.8M borrowed supports yield, while the 62.5%
LLTV provides a larger nominal liquidation buffer. **Principal risks:** COMP
volatility, wrapper administration, oracle design, and liquidation depth. The
5% COMP cap binds.

**WETH/USDC — funded ETH market.** WETH is the canonical ERC-20
wrapper of ETH, with a direct ETH/USD oracle and no staking or custody wrapper.
**Why included:** it adds plain-ETH exposure and helps complete deployment.
**Principal risk:** only $3.8M borrowed and $0.6M cash support a $1M position,
so capacity—not collateral quality—is the binding concern.

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

## 4. Vault rebalancing

I would recalculate the portfolio every hour, but I would not trade every time
rates move. The live positions are compared with a fresh target, and only a
meaningful difference becomes a proposed trade. When calculating that target,
I first remove our positions from reported market supply so the same capital is
not counted twice. In the implementation, `allocate` produces the target and
`rebalance` proposes.

At each hourly or event-driven refresh, I ask three questions in order:

1. **Has a market become unacceptable?** An oracle, collateral, bad-debt,
   legal, or maturity signal sets its target to zero. I withdraw whatever USDC
   is available and report any balance that cannot yet exit.
2. **Are we outside a portfolio limit?** If a position breaches a market,
   ownership, family, non-blue, or liquidity cap, I reduce it toward compliance.
3. **Is an ordinary yield move worth making?** I rotate from an overweight
   market to an underweight one only when the move passes the tests below.

Only the third case is subject to the churn controls. After any execution, I
read positions and market cash again rather than assume that every proposed
transaction settled.

| routine rule | setting | rationale |
|---|---:|---|
| target drift and minimum move | $1M on both sides | Matches the 1% minimum position size. A $3M threshold left cash idle when the desired deposits were split across several smaller changes. |
| expected improvement | at least 15 bp annualized | Filters small differences in modeled rates; it was non-binding between 0 and 30 bp in the tested periods. |
| transaction-cost test | 14-day benefit must cover $60 per leg | Uses the same horizon as the rate projection. Production would replace $60 with live gas and execution estimates. |
| rolling turnover | $10M of gross flows per 7 days | A $5M market-to-market move counts as $10M: one withdrawal and one deposit. A $20M limit did not materially improve the tested returns. |

I treat the first $100M deployment differently from a rebalance: there is no
existing portfolio to churn, so the turnover limit does not apply. After
launch, I also separate risk trades from yield trades. If an oracle breaks or a
position breaches its cap, I withdraw as much as market cash permits even when
the move fails the return or gas hurdle. Those tests exist to prevent noisy
yield chasing, not to delay risk reduction.

For example, suppose third-party supply enters the FalconX market while
borrowing is unchanged. Its utilization and post-impact APR fall. If the new
target reduces our position from $5M to $3M and another market offers at least
15 bp more on the moved capital, the planner can propose the $2M rotation after
checking gas, available cash, and weekly turnover. If the advantage is only 5
bp, I leave the position alone. This is how the strategy reacts to crowding
without chasing every change in displayed APY.

I would refresh market data every 5–15 minutes and monitor urgent risk signals
at block level. The portfolio target updates hourly or immediately after a
material event, while collateral eligibility and risk caps receive a weekly
human review. An oracle, redemption, NAV, bad-debt, or legal alert can override
the yield model and disable a market. If the API is unavailable, the live run
stops rather than silently falling back to the committed snapshot.

## 5. My Morpho Vault Configuration

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

## 6. What the historical replay says

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

The active strategy trails the static portfolio in all four windows, but it
materially outperforms the rule that simply chases the highest spot APY and does
so with far less turnover. That is a useful but modest result: the policy
behaved sensibly through both the October liquidation cascade and quieter
periods, but the test does not show that frequent rebalancing adds alpha.

Competitor attribution would require matched NAV, dates, flows, fees, and risk
constraints. Historical universes are point-in-time: only four of the current
ten IDs existed on 10 October 2025, so that replay tests the allocation rule,
not today's ten-market composition.

## 7. What this analysis does not prove

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
