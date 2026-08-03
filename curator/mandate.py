"""Human-reviewed Ethereum USDC markets, keyed by immutable market ID."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewedMarket:
    market_id: str
    symbol: str
    role: str
    rationale: str


REVIEWED_MARKETS = (
    ReviewedMarket(
        "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64",
        "cbBTC",
        "core",
        "deepest reviewed USDC market; ChainlinkOracleV2 BTC/USD feed",
    ),
    ReviewedMarket(
        "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49",
        "WBTC",
        "core",
        "deep reviewed BTC venue; independent wrapper and Chainlink route",
    ),
    ReviewedMarket(
        "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc",
        "wstETH",
        "core",
        "largest reviewed LST venue; composed market-price oracle",
    ),
    ReviewedMarket(
        "0xd570c19c0dc0fbe4ab7faf4a37c4150e1c141c8aada8ca3e1b4b6c1b712af93d",
        "stUSDS",
        "satellite",
        "Sky risk-capital token; ERC-4626 conversion plus market-price feeds",
    ),
    ReviewedMarket(
        "0x7e585a933ffe8443c371b4f8cfeb4430f5f6a14c2f32a898c26662c67a1cb8b8",
        "wstETH",
        "satellite",
        "second real wstETH venue with a distinct ChainlinkOracleV2 route",
    ),
    ReviewedMarket(
        "0x34377fc4f617c51818e92c79df31ff270c6a91bc94ad32e367fdf59b9f4ac5dd",
        "weETH",
        "satellite",
        "77% LLTV restaking venue; market-price feeds and conservative sizing",
    ),
    ReviewedMarket(
        "0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd",
        "WETH",
        "satellite",
        "plain ETH collateral with ChainlinkOracleV2 pricing; limited capacity",
    ),
    ReviewedMarket(
        "0xe83d72fa5b00dcd46d9e0e860d95aa540d5ec106da5833108a9f826f21f36f52",
        "AA_FalconXUSDC",
        "credit satellite",
        "77% LLTV FalconX Credit Vault LP token; separate 5% counterparty cap",
    ),
    ReviewedMarket(
        "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64",
        "PT-reUSD-10DEC2026",
        "term satellite",
        "fixed-maturity reUSD claim; 91.5% LLTV and reinsurance family capped at 10%",
    ),
    ReviewedMarket(
        "0x24852d8d7464402ddcd717415e009d42bf7427d6a8893487f83c75ee0f4a0ea6",
        "dCOMP",
        "enhanced satellite",
        "one-for-one COMP wrapper; 62.5% LLTV and separate 5% governance-token cap",
    ),
)

REVIEWED_MARKET_IDS = frozenset(m.market_id for m in REVIEWED_MARKETS)

# Scan passage does not imply approval.
SCAN_FILTERS = {
    "allowed_market_ids": None,
    "allowed_loan_symbols": ("USDC",),
    "banned_tiers": (),
    "min_supply_usd": 1_000_000,
    "min_borrow_usd": 500_000,
    "max_utilization": 0.995,
}

SELECTION_FILTERS = {
    "allowed_market_ids": REVIEWED_MARKET_IDS,
    "min_supply_usd": 1_000_000,
    "min_borrow_usd": 500_000,
}


def selection_filters() -> dict:
    return dict(SELECTION_FILTERS)


def scan_filters() -> dict:
    return dict(SCAN_FILTERS)


# Compatibility aliases for older notebooks and tests.
ApprovedMarket = ReviewedMarket
APPROVED_MARKETS = REVIEWED_MARKETS
APPROVED_MARKET_IDS = REVIEWED_MARKET_IDS
