# Curator memo: $100M USDC vault on Morpho Blue

## Executive summary

I propose ten exact Morpho markets spanning BTC, ETH/LST/LRT, Sky risk capital,
fixed-maturity reinsurance credit, private credit, and a governance-token
wrapper. Eligibility follows collateral, oracle, LLTV, liquidation,
redemption, incident, and capacity review.
The allocator maximizes projected native interest after deposit impact subject
to market, risk-family, ownership, and withdrawal-liquidity limits.

The snapshot target deploys $100M across all ten markets: $48.25M cbBTC,
$19.25M WBTC, $9.25M PT-reUSD, $6.50M across two wstETH markets, $5.00M each
in AA_FalconXUSDC and dCOMP, $4.25M stUSDS, $1.50M weETH, and $1.00M WETH.
The portfolio has no idle USDC and $82.2M of stressed-withdrawable market
liquidity.

The projected 14-day whole-vault native APR is 2.56% under zero borrower
response. The main constraint is capacity: adding $100M pushes the principal
markets below their starting utilization, reducing the immediate supplier rate
and the subsequent AdaptiveCurveIRM path. In historical replay, the constrained
strategy remains close to a matched static allocation and materially
outperforms a high-turnover spot-APY ranking rule.

## 1. Allocation universe: which markets and why?

### Market discovery

At startup, the program paginates [Morpho's public GraphQL API](https://docs.morpho.org/developers/api/morpho/)
for listed Ethereum mainnet markets (`chainId = 1`) whose loan asset is
canonical USDC (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`). For every
result it retains the exact market ID, collateral, oracle and IRM addresses,
LLTV, fee, rewards,
supply, borrowing, unborrowed liquidity, utilization, rates, and recent APY
history.

### Scan and selection criteria

The snapshot contains 118 collateralized USDC markets. Discovery, mechanical
screening, underwriting, and allocation are separate stages.

| stage | criterion | treatment and reason |
|---|---|---|
| discovery | Ethereum mainnet (`chainId = 1`) | Hard scope boundary; no bridge or cross-chain risk. |
| discovery | canonical USDC is the loan asset | Hard scope boundary; the vault supplies its existing asset without a swap or PYUSD/USDT basis exposure. |
| discovery | listed market with non-null collateral | Hard requirement; excludes idle markets and unlisted records. |
| mechanical scan | at least $1M supplied | Removes markets too small to support the operating ticket or meaningful capacity analysis. |
| mechanical scan | at least $0.5M borrowed | Requires evidence of borrower-paid demand; zero-demand headline rates are not scalable. |
| mechanical scan | utilization no higher than 99.5% | Removes effectively cashless markets where entry and withdrawal are already impaired. |
| underwriting | exact collateral claim and redemption path understood | Identify issuer, custody, legal/counterparty dependencies, loss waterfall, maturity, gates, and depeg mechanisms. Unknown is excluded pending review. |
| underwriting | oracle path reconstructed and appropriate | Review every feed, conversion ratio, vault/NAV component, heartbeat, and hardcoded-peg assumption for that exact market ID. |
| underwriting | LLTV defensible against collateral volatility and executable liquidation depth | Assess collateral value at the liquidation trigger, liquidation incentive, oracle latency, and executable sale/redemption value. |
| underwriting | verified PT maturity at least 30 days away | The exact contract expiry—not the ticker alone—is recorded; stop eligibility early enough to execute a governed exit or roll. |
| underwriting | incidents, bad debt, governance and contract dependencies reviewed | A known unresolved exploit, impaired redemption, or unexplained bad debt is a hard exclusion. |
| capacity rank | projected native APR after a common $10M deposit | Uses the AdaptiveCurveIRM and our own dilution; spot APY is not a ranking objective. |
| allocation | ownership, family concentration and pre-deposit cash | Size within 35% post-deposit ownership, factor caps, 50% position exit coverage, and 60% portfolio stressed-withdrawable liquidity. |

The activity floors reduce 118 discoveries to 46 scan passes; ten exact IDs
complete underwriting. Asset category alone does not establish eligibility.

`main.py allocate --show-shortlist` ranks the top 15 mechanical passes by
projected APR after a common $10M deposit and labels each `reviewed`,
`excluded`, or `diligence`. Ranking prioritizes underwriting work; it does not
approve collateral. This makes the 118 → 46 → 10 funnel reproducible without
delegating collateral judgment to spot yield.

Every reviewed market lends canonical USDC and uses Morpho's
[AdaptiveCurveIRM](https://docs.morpho.org/get-started/resources/contracts/irm/),
zero market fees, and zero active rewards in the snapshot. The projection is
therefore native borrower-paid interest after utilization impact.

### Economic characteristics and target

The allocation inputs below are from the committed Morpho API snapshot observed
at 2026-08-01 23:36:11 UTC. `main.py allocate` fetches a new snapshot on every
live run; the committed state is retained to make the reported target
reproducible.

`Unborrowed liquidity` is `supplied USDC − borrowed USDC`: USDC currently held
in the Morpho market and available collectively to suppliers who withdraw.
`Exit coverage` is `min(our target, pre-deposit unborrowed liquidity) / our
target`. `Cash ratio` is unborrowed liquidity divided by market supply. All
reviewed markets use the AdaptiveCurveIRM with 90% target utilization. Supply
and borrow APYs are API spot values before the modeled deposit.

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

The flow columns compare the allocation snapshot at 2026-08-01 23:36 UTC
with a live API fetch at 2026-08-03 08:01 UTC. They are short-window
diagnostics, not fitted forecasts or direct optimizer signals.

For dCOMP, the snapshot's indexed `rateAtTarget` reproduces the displayed
borrow APY with a 1.5 bp discrepancy, consistent with fields sampled at nearby
blocks. The curve constructor therefore uses its documented fallback: invert
the observed borrow APY and utilization to a state-consistent `rateAtTarget`.
The other reviewed snapshot rows use the indexed value directly. This changes
calibration of the current curve, not the zero-borrower-response assumption.

| market | LLTV | oracle/pricing construction | target | post-util. | projected APR | ownership | exit coverage | curated-vault share |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| cbBTC `0x64d6…` | 86% | ChainlinkOracleV2; direct BTC/USD | $48.25M | 74.6% | 2.23% | 13.5% | 88.4% | 41.4% |
| WBTC `0x3a85…` | 86% | WBTC/BTC × BTC/USD ÷ USDC/USD | $19.25M | 74.7% | 2.24% | 13.5% | 87.9% | 13.0% |
| PT-reUSD `0x1e9d…` | 91.5% | Pendle PT pricing over reUSD NAV/redemption value | $9.25M | 73.5% | 4.21% | 17.6% | 50.6% | 3.7% |
| AA_FalconXUSDC `0xe83d…` | 77% | FalconX Credit Vault LP-token NAV feed | $5.00M | 81.8% | 4.05% | 9.2% | 97.2% | 33.6% |
| dCOMP `0x2485…` | 62.5% | two-feed COMP/USDC route; one-for-one dCOMP wrapper | $5.00M | 57.8% | 3.64% | 26.7% | 58.1% | n/a |
| wstETH `0xb323…` | 86% | wstETH/stETH conversion × ETH/USD | $4.75M | 71.9% | 2.03% | 16.9% | 66.9% | 38.1% |
| stUSDS `0xd570…` | 86% | stUSDS conversion × USDS/USD ÷ USDC/USD | $4.25M | 62.4% | 2.08% | 18.6% | 100.0% | 0.0% |
| wstETH `0x7e58…` | 86% | separate wstETH/stETH × ETH/USD route | $1.75M | 72.2% | 2.06% | 16.2% | 71.6% | 47.8% |
| weETH `0x3437…` | 77% | weETH/ETH conversion × ETH/USD | $1.50M | 71.4% | 2.28% | 17.7% | 62.1% | 30.9% |
| WETH `0x94b8…` | 86% | direct ETH/USD | $1.00M | 70.2% | 1.92% | 18.6% | 60.1% | 15.4% |

| collateral | exact Morpho market ID |
|---|---|
| cbBTC | `0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64` |
| WBTC | `0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49` |
| PT-reUSD-10DEC2026 | `0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64` |
| AA_FalconXUSDC | `0xe83d72fa5b00dcd46d9e0e860d95aa540d5ec106da5833108a9f826f21f36f52` |
| dCOMP | `0x24852d8d7464402ddcd717415e009d42bf7427d6a8893487f83c75ee0f4a0ea6` |
| wstETH (primary) | `0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc` |
| stUSDS | `0xd570c19c0dc0fbe4ab7faf4a37c4150e1c141c8aada8ca3e1b4b6c1b712af93d` |
| wstETH (secondary) | `0x7e585a933ffe8443c371b4f8cfeb4430f5f6a14c2f32a898c26662c67a1cb8b8` |
| weETH | `0x34377fc4f617c51818e92c79df31ff270c6a91bc94ad32e367fdf59b9f4ac5dd` |
| WETH | `0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd` |

### Market-by-market underwriting

**cbBTC/USDC — BTC core.** [cbBTC](https://help.coinbase.com/en-gb/coinbase/trading-and-funding/sending-or-receiving-cryptocurrency/coinbase-wrapped-btc)
is a Coinbase-custodied tokenized claim backed one-for-one by BTC.
The market's direct BTC/USD oracle treats one cbBTC as one BTC and therefore
does not independently observe a cbBTC/BTC discount. The 86% LLTV leaves 14%
collateral-value margin before liquidation; custody or redemption impairment,
oracle latency, and BTC sale slippage can consume that margin. The market is
included because $267.0M of borrowing demonstrates demand and $42.7M of cash is
the largest reviewed exit pool. The $48.25M target
produces 13.5% ownership, 88.4% exit coverage, 74.6% utilization, and 2.23%
projected APR. Issuer and BTC-factor caps contain risks that market depth does
not remove.

**WBTC/USDC — BTC core.** [WBTC](https://docs.wbtc.network/) is a custodial,
one-for-one tokenized-BTC claim with a
different custody and redemption system from cbBTC. Its oracle composes
WBTC/BTC, BTC/USD, and USDC/USD feeds, so the route can observe wrapper basis
but adds feed and composition dependencies. The 86% LLTV again leaves 14%
collateral-value margin before liquidation. The market is included because
$106.9M of borrowing and $16.9M of cash support a material position and because
it avoids concentrating all BTC-wrapper exposure in cbBTC. A $19.25M target
produces 13.5% ownership, 87.9% exit coverage, 74.7% utilization, and 2.24%
projected APR. Both wrappers remain aggregated under the BTC-factor cap.

**wstETH/USDC (`0xb323…`) — primary LST market.** [wstETH](https://docs.lido.fi/contracts/wsteth/)
is the non-rebasing wrapper of Lido stETH, a claim on pooled staked ETH and
accrued staking rewards.
The oracle composes the wstETH/stETH conversion with ETH/USD. At 86% LLTV, the
liquidation design depends on the conversion feed and on executable stETH/ETH
liquidity during an ETH drawdown. Other risks are Lido governance, validator
performance, and withdrawal or basis dislocation. The market is included as
the largest reviewed non-BTC venue with $20.3M borrowed. A $4.75M target
produces 66.9% exit coverage, 71.9% utilization, and 2.03% projected APR.

**stUSDS/USDC — Sky risk-capital token.** [Sky describes stUSDS](https://developers.skyeco.com/protocol/tokens/stusds/)
as an ERC-4626 risk-capital token that funds SKY-backed borrowing and is
structured to absorb more system risk in return for greater rewards. It is not
the sUSDS savings token. The oracle composes the stUSDS vault conversion with
USDS/USD and USDC/USD feeds. At 86% LLTV, the important tails are borrower or
system loss, governance changes, stale conversion value, redemption capacity,
and USDS/USDC basis—not ordinary stablecoin volatility alone. The market is
included because $14.3M borrowing and $4.4M cash provide usable capacity, but
the corrected underwriting limits the Sky family to 5% of NAV. The $4.25M
target has 100% pre-deposit cash coverage, lowers utilization from 76.6% to
62.4%, and projects 2.08% APR; the aggregate non-blue limit prevents the Sky
family ceiling from filling.

**wstETH/USDC (`0x7e58…`) — secondary LST market.** The collateral claim is the
same wstETH described above, but this immutable Morpho market has a different
oracle contract and liquidity pool. Its 86% LLTV therefore adds venue and
oracle capacity, not asset-factor diversification. The market is included
because $7.8M of borrowing supports a valid $1M minimum ticket and the exact
route passed review. The $1.3M cash pool supports a $1.75M target, producing
71.6% exit coverage, 72.2% utilization, and 2.06% projected APR. Both wstETH
positions count against one ETH/LST family limit.

**weETH/USDC — LRT market.** [weETH](https://help.ether.fi/en/articles/595737-weeth)
is ether.fi's non-rebasing liquid-restaking token: its value depends on staked
ETH, protocol accounting, restaking rewards
and penalties, and redemption or secondary-market liquidity. The oracle
combines weETH/ETH with ETH/USD. The selected 77% LLTV leaves 23% margin before
liquidation and is preferred to the reviewed 86% alternative because LRT basis
and dependency risk are greater than for WETH. The market is included as a
small, separately governed ETH-yield venue with $6.1M borrowed. A $1.50M target
produces 62.1% exit coverage, 71.4% utilization, and 2.28% projected APR; its
$0.9M cash pool and the non-blue cap prevent larger sizing.

**PT-reUSD/USDC — fixed-maturity reinsurance claim.** A [Pendle PT](https://docs.pendle.finance/pendle-v2/ProtocolMechanics/YieldTokenization/PT)
represents the principal component of a yield-bearing asset and becomes
redeemable for its accounting asset at maturity. The exact collateral
contract's `expiry()` is 10 December 2026. [Re describes reUSD](https://docs.re.xyz/protocol/how-the-re-protocol-works)
as its principal-protected, low-volatility reinsurance-capital token, senior to
the reUSDe first-loss layer. The Pendle/reUSD
pricing route must represent both PT discount convergence and underlying NAV.
The 91.5% LLTV leaves only 8.5% collateral-value margin, making stale NAV,
redemption impairment, PT liquidity, and liquidation execution particularly
important. The market is included because $38.7M of borrowing supports a high
native rate and the verified maturity permits a governed roll. A $9.25M target
produces 50.6% exit coverage, 73.5% utilization, and 4.21% projected APR. The
10% Re-credit cap and 50% exit rule bind the exposure independently of yield.

**AA_FalconXUSDC/USDC — private-credit vault LP token.** The collateral address
is [Pareto's listed FalconX Credit Vault LP token](https://docs.pareto.credit/developers/addresses/product/credit-vaults).
[Pareto's Credit Vault design](https://docs.pareto.credit/product) sends
deposited assets to a whitelisted borrower and processes exits through lending
cycles. The `AA_` symbol is not treated as evidence of a rated or protected
senior tranche. Its NAV feed and 77% LLTV provide 23% nominal collateral-value
margin, but that margin depends on current valuation and realizability.
FalconX default, repayment-cycle, NAV, contract, legal-enforcement, and delayed-
redemption risks remain. The market is included for its $44.3M borrower demand
and strong position exit coverage, but the $5.0M single-counterparty cap is
binding. That target produces
97.2% exit coverage, 81.8% utilization, and 4.05% projected APR. The subsequent
$5.04M supply inflow with negligible borrow growth compressed live spot APY
from 5.55% to 4.47%. The allocator therefore recomputes from current state; it
does not extrapolate this short flow window.

**dCOMP/USDC — enhanced governance-token satellite.** [Api3 describes dCOMP](https://docs.api3.org/curation/)
as a lightweight, ownable wrapper that holds COMP one-for-one while allowing
the owner to change the delegated voting address. The wrapper contract also
controls who may deposit COMP; those administrative controls and the wrapper's
redemption code are additional dependencies beyond COMP itself. The market's
two-feed oracle route prices the COMP wrapper against USDC. Its 62.5% LLTV
leaves 37.5% nominal collateral-value margin, materially more than the 86–91.5%
markets, but suppliers still depend on timely oracle updates and executable
COMP liquidation through a volatile governance-token market. The snapshot has
$13.7M supplied, $10.8M borrowed, and $2.9M cash. A separately capped $5.0M
target produces 26.7% ownership, 58.1% exit coverage, 57.8% post-deposit
utilization, and 3.64% projected APR. It raises the portfolio's modeled return
without being classified as blue-chip; the 5% COMP-family and 25% aggregate
non-blue limits both bind.

**WETH/USDC — funded ETH market.** WETH is the canonical ERC-20
wrapper of native ETH and can be unwrapped one-for-one; it has no separate
staking, restaking, or custodial-BTC claim. The direct ETH/USD oracle avoids a
wrapper-conversion leg. The 86% LLTV nevertheless exposes suppliers to oracle
latency and ETH liquidation slippage. The exact market passes collateral and
oracle review, but $3.8M borrowing and only $0.6M cash provide limited capacity.
The $1.0M target has 60.1% exit coverage, 70.2% utilization, and 1.92%
projected APR. It is funded because the tighter BTC and single-market caps make
its capacity useful to the 100% deployment objective.

Over the 30-hour comparison, cbBTC and WBTC supply declined while borrowing was
approximately flat, and PT-reUSD borrowing grew slightly faster than supply.
Those moves support utilization over that short interval but do not establish
a persistent trend. FalconX experienced the only large relative supply inflow.

### Risk disposition: excluded, capped, and retained

No lending portfolio is risk-free. Here, “risk excluded” means the vault does
not knowingly take a particular risk configuration; it does not mean the
remaining markets cannot lose principal. The mandate separates risks into
three treatments:

| disposition | risk configuration | implementation |
|---|---|---|
| excluded | Another chain or a non-USDC loan asset | Ethereum and canonical-USDC discovery filters avoid bridge, foreign-loan-asset, swap, and additional stablecoin-accounting risk. |
| excluded | Collateral whose issuer, legal claim, loss waterfall, redemption mechanism, or maturity cannot be verified | The exact market ID remains in the diligence queue regardless of APY. A familiar symbol is insufficient. |
| excluded | Oracle construction that is unresolved, omits a material wrapper-basis risk, depends on an unjustified fixed peg, or cannot be reconciled to realizable collateral value | Reject the exact ID; a cap cannot repair a liquidation oracle that may price the wrong economic claim. |
| excluded | Unresolved exploit, unexplained bad debt, impaired redemption, or delisting | Disable new supply and target zero; do not trade higher yield against a known unresolved principal-loss mechanism. |
| excluded | LLTV that is not defensible against oracle latency, collateral volatility, and executable liquidation or redemption depth | Reject the exact LLTV/oracle configuration even if another market using the same collateral is acceptable. |
| excluded or deferred | Insufficient borrow demand, market cash, or maturity runway | Mechanical activity floors remove negligible demand; the $1M ticket, exit-coverage rules, and 30-day PT cutoff prevent economically or operationally unusable positions. |
| accepted and capped | cbBTC/WBTC custody, redemption, and BTC-basis risk | Exact-ID review plus market caps and one aggregate BTC-factor cap. Wrapper diversification does not eliminate BTC correlation. |
| accepted and capped | Lido, ether.fi, staking/restaking, and LST/LRT basis risk | ETH/LST aggregation, lower 77% LLTV for weETH, non-blue exposure limits, and liquidity-based sizing. |
| accepted and capped | stUSDS SKY-backed borrower, loss-absorption, governance, conversion, redemption, and USDS-basis risk | 5% Sky-family ceiling and exact conversion-oracle review. |
| accepted and tightly capped | Direct FalconX borrower default, lending-cycle, NAV, legal-enforcement, and delayed-redemption risk | 5% FalconX-family ceiling plus position exit coverage. |
| accepted and tightly capped | reUSD reinsurance-credit, NAV, PT pricing, maturity, and roll risk | 10% Re-credit ceiling, 50% position exit coverage, verified maturity, and a T−60/T−30 roll process. |
| accepted and tightly capped | dCOMP wrapper administration, COMP volatility, governance concentration, oracle, and liquidation-depth risk | 62.5% LLTV market only; 5% COMP-family ceiling, 35% ownership cap, and 50% position exit coverage. |
| retained common risk | Morpho and vault smart contracts, Ethereum execution, canonical USDC, oracle infrastructure, governance, liquidation, and residual borrower-default risk | These cannot be diversified away inside this strategy; monitor them, use role separation and timelocks, and disclose them as portfolio-level residual risks. |

Hard exclusions apply before optimization. Accepted risks remain subject to
exact-market, family, ownership, and liquidity limits; return ranking cannot
override either treatment.

### Examples of excluded and deferred candidates

Mechanical scan passage is not approval. The following examples show how the
rules reject or defer a market after discovery:

| candidate | decision | controlling reason |
|---|---|---|
| PRIME/PYUSD | out of scope | PYUSD is the loan asset; a USDC vault would need a swap or cross-asset adapter and would add PYUSD basis and execution risk. |
| mF-ONE/USDC | excluded | Gated off-chain redemption, whitelisted borrower structure, and concentrated lender base are inconsistent with the vault's withdrawal objective. |
| OETH/USDC reviewed route | excluded | The observed ETH/USD route did not expose a separate OETH/ETH basis leg; a wrapper impairment could therefore be reflected too slowly. |
| wstUSR/USDC | excluded | The reviewed market was associated with the 2026 Resolv exploit path and no longer supplied usable exit liquidity. |
| sdeUSD/USDC | excluded | Realized collateral impairment, bad debt, and delisting fail the incident and redemption tests. |
| rETH/USDC `0x0a15…` | deferred | 86% LLTV is aggressive for the smaller LST venue and available cash does not support the required ticket with the desired exit margin. |
| LBTC/USDC `0xbf02…` | deferred | The yield-bearing BTC wrapper adds consortium, redemption, and basis risks; only $0.13M cash made the $1M ticket fail exit coverage. |
| alternate IDs for approved symbols | not automatically eligible | A symbol match does not validate a market's oracle, LLTV, IRM, fee, or liquidity. Only the exact IDs above completed review. |

Other PTs, credit claims, RWAs, and yield-bearing stablecoins remain in the
diligence queue until the same exact-ID review is complete. The reproducible
$10M-probe shortlist begins PT-reUSD, AA_FalconXUSDC, cbBTC, WBTC, dCOMP, USD3,
wFalconX, reUSD, mF-ONE, PST, and PT-USD3. The first five completed review;
mF-ONE is excluded; the remainder require claim, waterfall, redemption, oracle,
and LLTV diligence.

## 2. What market and collateral features matter most?

Eligibility is determined before return ranking. A market with an unresolved
principal-loss or exit mechanism is excluded regardless of its supply rate.

| feature | question answered | use in the strategy |
|---|---|---|
| collateral and redemption | What claim do liquidators receive, and how can it fail or depeg? | Human exact-ID approval plus issuer/factor caps; not reduced to a scalar score. |
| oracle path | What is priced, through which feeds and conversions, and how can it become stale or wrong? | Human exact-ID approval; an unresolved path is excluded. |
| LLTV and liquidation depth | How much adverse value movement can occur before liquidation, and can liquidators realize the oracle value? | Exact-market approval and tier/family caps; prefer lower LLTV for less liquid or more complex collateral. |
| supplied TVL | Is the venue large enough, and how much of it would the vault own? | $1M scan floor, 35% post-deposit ownership cap, and the denominator for utilization. |
| borrowed TVL | Is there material borrower-paid demand? | $0.5M scan floor and the numerator held fixed in the primary post-deposit projection. |
| unborrowed liquidity (`supply − borrow`) | How much USDC can suppliers collectively withdraw before borrowers repay? | 50% per-position exit coverage and 60% portfolio stressed-withdrawable constraints. |
| utilization and 90% IRM target | Where is the market on the AdaptiveCurveIRM and how does our supply change it? | Direct inputs to the 14-day post-deposit rate path. |
| borrow APY and `rateAtTarget` | Does the reconstructed IRM state reproduce the API rate? | API `rateAtTarget` is used directly; borrow APY is the fallback calibration and a validation check. |
| supply APY and 1d/30d averages | Is the modeled spot rate consistent with the API, and has yield been persistent? | Reporting and validation; spot supply APY is not the allocation objective. |
| recent supply and borrow changes | Is crowding or demand changing the rate state? | Monitoring and event-triggered recomputation; no unvalidated trend coefficient. |
| ownership and curated-vault share | Could this vault dominate supply or face correlated curator exits? | Hard ownership ceiling; curated share is a crowding diagnostic. |
| fees and rewards | How much displayed yield is native and repeatable? | Market fees enter the rate. Incentives are attributed separately and enter the objective only after claimability, token liquidity, and expiry review; `reward_weight=0` is the base. |
| gas and reallocation friction | Is moving to a new target economically worthwhile and operationally possible? | Not part of the desired-state optimum; execution requires a $1M leg, 15 bp gain, drift threshold, and available market cash. |

The primary allocator does not use a composite risk score or subtract a
subjective APR premium. A comparable expected-loss estimate would require
default probabilities, loss-given-default, oracle/depeg frequencies,
liquidation price-impact curves, and cross-market dependence that are not
identified by the available history. Risk is represented through exact-ID
eligibility and exposure constraints.

## 3. Lower stable yield versus higher unstable yield

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
capacity is insufficient, the residual remains idle. The reviewed snapshot has
no active rewards. The code can include API reward APR with an explicit
`reward_weight`, but keeps native and incentive attribution separate and uses
zero until token liquidity, claimability, and expiry are reviewed.

## 4. How allocations are sized

For market `i`, let `R_i(a)` be its projected 14-day native APR after receiving
allocation `a`, `Q_i` its verified reward APR, and `w_Q` the approved reward
weight. Annual effective revenue and marginal revenue for the next chunk are:

```text
V_i(a) = a × [R_i(a) + w_Q × Q_i]
MR_i(a, Δ) = [V_i(a + Δ) − V_i(a)] / Δ
```

Marginal revenue includes interest on the incremental capital and the rate
dilution applied to the existing position. The allocator assigns $250k
increments to the admissible market with the highest marginal revenue, then
performs feasible pairwise $250k exchanges until no exchange increases annual
revenue. This second pass matters near IRM kinks and shared family constraints.
The algorithm does not require seven positive positions merely because the
universe contains ten.
The $250k increment is numerical resolution: a $50k run projects 2.5564% versus
2.5552% at $250k, a 0.12 basis-point difference. Atomic $1M ticket exchanges
are evaluated separately, so a finer chunk cannot strand an otherwise useful
new market outside a fully deployed book.

For markets with the same IRM, fee, and reward treatment, unconstrained
marginal allocation tends to equalize post-deposit utilization. Binding market,
family, ownership, exit-liquidity, and minimum-ticket constraints produce the
remaining differences.

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

These are initial governance limits, not fitted default probabilities or Morpho
protocol limits. The 50% market cap prevents one immutable market from holding
a majority of NAV. The 67.5% BTC cap is the lowest tested 2.5-point setting that
permits full deployment on this snapshot; the sensitivity table quantifies the
cost of tighter choices. The 25% ETH cap aggregates WETH, LSTs, and LRTs under
one liquidation factor and leaves headroom above the current 9% allocation.

The 5% Sky, FalconX, and COMP limits bound one risk-capital system, one
permissioned borrower, and one governance-token wrapper, respectively. The 10%
Re-credit limit permits a larger sleeve because reUSD is senior to a separate
first-loss layer, while retaining a small budget for NAV, redemption, and PT
maturity risk. The 25% aggregate non-blue cap prevents these individually small
sleeves from collectively dominating the portfolio.

The ownership and cash tests address capacity directly. A 35% post-deposit
ownership limit avoids majority-supplier status. The 50% position test requires
at least half of each allocation to be covered by cash observed before entry;
the 60% portfolio test applies the same measure across NAV. These are initial
liquidity thresholds, not estimated run percentiles, so the resulting 82.2%
coverage is disclosed for committee review. The $1M ticket equals 1% of NAV and
removes positions too small to justify separate execution and monitoring.

| policy sensitivity | projected APR | deployed | BTC | stressed-withdrawable |
|---|---:|---:|---:|---:|
| 70% BTC | 2.56% | 100.0% | 69.8% | 81.5% |
| base: 67.5% BTC | 2.56% | 100.0% | 67.5% | 82.2% |
| 65% BTC | 2.54% | 99.8% | 65.0% | 82.5% |
| 60% BTC | 2.46% | 94.8% | 60.0% | 87.5% |
| 50% BTC | 2.29% | 84.8% | 50.0% | 87.9% |
| 40% single-market cap | 2.53% | 100.0% | 67.0% | 79.6% |
| 7-day projection | 2.78% | 100.0% | 67.5% | 82.2% |
| 30-day projection | 2.13% | 100.0% | 67.5% | 82.2% |

`main.py sensitivity-snapshot` reproduces the table. The return/deployment
cost of tighter BTC limits is disclosed rather than used to weaken those
limits silently.

### Why the $100M projected APR is 2.56%

Spot rates apply to current market supply. The modeled deposit increases
supplied USDC without increasing borrowed USDC, reducing utilization and the
supplier rate. While utilization remains below the AdaptiveCurveIRM's 90%
target, `rateAtTarget` also declines. Integrating this path over 14 days gives
a 2.56% portfolio APR.

This scale effect also appears historically. On the same October allocation
path, treating the vault as a price taker produces 3.23% versus 2.54% after
including its own utilization impact. The June–July comparison is 3.13% versus
2.30%. Smaller live vaults can retain higher market utilization; their
dashboard APY is not directly scalable to $100M.

### Can the current market set reach 3.5% at $100M?

Not under the base zero-borrower-response assumptions. As an optimistic
capacity diagnostic, the code temporarily treats all 46 mechanical scan passes
as blue-chip collateral while retaining ownership and withdrawal constraints.
That non-investable portfolio projects 3.14% native APR, or 3.25% if every
current incentive is valued at 100%. Because this deliberately ignores the
collateral and oracle exclusions, it is a ceiling diagnostic rather than a
candidate allocation. Reaching 3.5% would currently require borrower growth,
durable rewards, additional underwritten capacity, a smaller NAV, or weaker
constraints; none is assumed in the headline.

### Zero-borrow-growth stress

Holding borrowed USDC and external supply fixed for 90 days while allowing the
IRM to adjust produces a 1.22% average annualized APR on the published target,
equivalent to approximately 0.30% earned over 90 days. This deterministic
sensitivity is not a probability-weighted forecast or principal-loss estimate.
Reoptimization over the same horizon should be reported separately from this
held-target stress.

## Proposed Morpho vault configuration

| parameter | proposed setting |
|---|---|
| asset | canonical Ethereum USDC |
| reviewed allocation universe | ten exact IDs above; all ten start funded in the snapshot target |
| market caps | absolute caps derived from market weight, ownership, and exit-liquidity limits |
| target computation | hourly and after material state changes |
| supply routing | highest admissible post-impact marginal revenue |
| withdrawal routing | idle/adapter first, then unborrowed liquidity in overweight markets |
| target calculator | fetches current state and computes the desired allocation among enabled markets; it does not submit transactions |
| production allocator role | may execute allocation and deallocation among enabled markets within on-chain caps after the execution controller accepts a move |
| curator | risk-committee multisig for adapters, markets, caps, roles, and other risk parameters |
| sentinel | independent risk multisig for cap reductions, deallocation, and pending-action revocation |
| owner | security-council multisig; no routine allocation role |
| timelock | 72 hours for risk-increasing changes; fastest supported path for risk reduction |
| neutral idle target | 0%; idle appears when capacity binds or risk is reduced |

The liquidity adapter routes user flows but does not make borrowed USDC
withdrawable. Setting a target to zero stops intended exposure; actual
deallocation remains limited by market liquidity and borrower repayment.

Morpho Blue market parameters are immutable; the vault migrates between market
IDs. In Vault V2, `MorphoMarketV1AdapterV2` can address a successor PT market.
The Curator submits absolute and relative cap increases for the new collateral
and market, waits for the configured timelock, and executes them. The Allocator
may then supply USDC within those caps. Reducing the old market's caps prevents
additional exposure; deallocation transfers only currently available USDC.

For PT-reUSD, the operating schedule is: review and submit the successor market
by T−60 days; make the old market ineligible and target zero at T−30 days; and
deallocate as liquidity becomes available. The vault supplies USDC rather than
holding the PT, so collateral maturity does not repay the vault. Borrowers may
remain outstanding after expiry, causing old and new vintages to coexist until
the old supply is withdrawable. Vault V1 implements the same migration using
timelocked `submitCap`/`acceptCap`, `reallocate`, and queue updates.

## 5. Response to a material market change

Economic changes and risk events use different execution gates.

The submitted `allocate` command is a desired-state calculator, consistent with
the assessment's statement that an execution engine is not required. It fetches
current market state but neither reads live vault positions nor submits a
transaction. A production controller would compare current positions with this
target and apply the gates below. `--compare-snapshot` reports changes in supply,
borrow, utilization, and rate state since a saved observation; those deltas are
monitoring inputs, not fitted forecasts.

**Economic change:** refresh supply, borrow, utilization, unborrowed liquidity,
and IRM state; recompute the post-impact target; then execute only if target drift exceeds
3 percentage points, the move is at least $1M, the gain exceeds 15 annual basis
points on moved notional, and rolling turnover capacity remains. A rate spike
alone is insufficient because the algorithm tests the rate after our move.

**Liquidity deterioration:** reduce a position that breaches the market or
portfolio exit rule. Yield and drift gates do not block this defensive action;
the executable withdrawal remains limited by unborrowed liquidity.

**Risk event:** an oracle failure, material bad debt, collateral redemption
impairment, delisting, or governance/security incident disables new supply and
sets the affected target to zero. The Sentinel deallocates available USDC and
records residual exposure. This control cannot force borrower repayment.

Safety signals are evaluated from block-level events or frequent indexed-state
updates. Targets are recomputed hourly and after material events; transactions
remain subject to the execution gates. New markets and cap increases require
explicit Curator action and the configured timelock.

| failure mode or signal | response |
|---|---|
| API/indexer is stale or disagrees with RPC state | Fail closed for new supply; retain the last verified target and reconcile against chain state. |
| External supply rises without matching borrow growth | Recompute the rate curve and target; trade only if the economic gates pass. |
| Market cash or portfolio stressed-withdrawable liquidity breaches its floor | Stop additions and deallocate available USDC without waiting for the yield gate. |
| Oracle heartbeat/deviation, collateral redemption, NAV, or bad-debt incident | Disable new supply, set target to zero, and record any liquidity-constrained residual. |
| PT enters the T−60 review or T−30 exit window | Approve a successor through governance, then target the old market to zero and roll only withdrawable cash. |
| Execution reverts, gas spikes, or quoted cash disappears | Do not assume the move occurred; refresh state and recompute before retrying. |

## 6. Response when a market becomes crowded

External supply inflows reduce utilization unless matched by borrow growth.
They can also increase competition for market cash during withdrawals. The
strategy therefore:

- recompute post-deposit and marginal APR after external supply inflows;
- stop new allocation when another market offers better marginal revenue;
- reduce the target when the gain survives execution gates;
- enforce ownership and pre-deposit-liquidity limits even when spot APY is high;
- monitor curated-vault share and common allocator behavior as an exit-risk
  diagnostic, without converting it into an uncalibrated APR penalty.

A supply inflow does not itself trigger removal. The target changes when the
updated borrow demand, projected marginal revenue, ownership, or exit capacity
changes the constrained optimum.

## 7. Guardrails against excessive churn

Monitoring, target calculation, and execution use separate cadences:

- block/minute safety monitoring;
- market-state refresh every 5–15 minutes in production;
- hourly target recomputation and event-triggered recomputation;
- conditional execution rather than scheduled trading;
- weekly human review of collateral eligibility and risk caps.

Routine execution requires 3 percentage points of target drift, a $1M minimum
leg, and at least 15 bp of projected annual gain on moved notional. For a $1M
leg, 15 bp equals $1,500 of annual modeled revenue versus the $60 transaction-
cost assumption. Two-sided turnover is limited to 10% of NAV per rolling seven
days; moving $5M between two markets consumes $10M of turnover.

The cadence sweep does not establish a general return advantage from faster
recomputation. Over October 10–December 25, hourly recomputation earned 2.57%,
versus 2.54% at seven days. In the cascade week, hourly recomputation earned
3.00% versus 2.93% at seven days. Frequent recomputation reduces detection
latency; the execution thresholds, not the observation schedule, control
turnover.

## Optional extension: historical validation

All returns use the full $100M NAV denominator; idle earns 0%.

| window | grid | constrained strategy | static | spot chaser | avg. deployed | liquidations / repaid | supplier loss |
|---|---|---:|---:|---:|---:|---:|---:|
| Oct 10–16 cascade (four available IDs) | hourly + exact events | 3.00% | 2.93% | 1.95% | 86.5% | 27 / $7.69M | $0 |
| Oct 10–Dec 25 (four available IDs) | hourly + exact events | 2.57% | 2.44% | 1.76% | 87.8% | 128 / $41.61M | <$0.01 |
| Apr 21–May 20 (six available IDs) | daily + exact events | 2.00% | 2.09% | 1.04% | 78.3% | 7 / <$0.01M | $0 |
| Jun 25–Jul 24 (eight available IDs) | daily + exact events | 2.30% | 2.35% | 0.86% | 83.7% | 13 / $0.07M | $0 |

`Liquidations` counts on-chain liquidation logs, not distinct borrowers or
vault-level events. The selected markets recorded no bad debt during the
October cascade week. Liquidation volume is not supplier revenue.

The hourly active book outperforms static in the two October windows; static
outperforms the daily active book in the two quiet windows.
The spot-APY rule underperforms both and incurs substantially more turnover.
Competitor attribution would require matched NAV, dates, flows, fees, and risk
constraints. Historical universes are point-in-time: only four of the current
ten IDs existed on 10 October 2025, so that replay tests the allocation rule,
not today's ten-market composition.

## Limitations

- The counterfactual vault changes within-period utilization but does not alter
  the next external historical observation; borrower and competing-supplier
  responses are not reconstructed.
- Historical oracle prices, borrower health, transaction ordering, MEV,
  rewards, vault user flows, and complete underlying action flow are absent.
- The replay uses current reviewed IDs that existed at each historical start;
  it does not reconstruct the discovery and underwriting decisions available
  at that date and therefore retains survivorship bias.
- The public API is an indexer without an SLA. `main.py allocate` fetches fresh
  API state on every run and fails instead of silently using the committed
  snapshot. Production should additionally enforce data-age limits and
  reconcile critical state with RPC reads.
