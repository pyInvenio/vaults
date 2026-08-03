"""Curator-assigned collateral, oracle, and maturity metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import CollateralTier


@dataclass
class MarketMeta:
    tier: CollateralTier = CollateralTier.EXOTIC
    oracle_note: str = ""
    pt_maturity_days: Optional[float] = None
    pt_maturity_timestamp: Optional[int] = None
    notes: str = ""


METADATA: dict = {
    # Exact market overrides
    "0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="ChainlinkOracleV2 0xA6D6…; direct BTC/USD feed",
        notes="core cbBTC/USDC 86% market in the 2026-08-01 reviewed universe",
    ),
    "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="Chainlink oracle 0xDddd…; WBTC/BTC, BTC/USD and USDC/USD route",
        notes="core WBTC/USDC 86% market in the 2026-08-01 reviewed universe",
    ),
    "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="Chainlink oracle 0x48F7…; wstETH/stETH and ETH/USD route",
        notes="core wstETH/USDC 86% market in the 2026-08-01 reviewed universe",
    ),
    "0xd570c19c0dc0fbe4ab7faf4a37c4150e1c141c8aada8ca3e1b4b6c1b712af93d": MarketMeta(
        CollateralTier.YIELD_STABLE,
        oracle_note="ChainlinkOracleV2 0xba3D…; stUSDS vault conversion and market feeds",
        notes="satellite stUSDS/USDC 86% market; ERC-4626 risk-capital token "
        "funding SKY-backed borrowing, not the sUSDS savings token",
    ),
    "0x7e585a933ffe8443c371b4f8cfeb4430f5f6a14c2f32a898c26662c67a1cb8b8": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="ChainlinkOracleV2 0xe087…; wstETH/stETH and ETH/USD route",
        notes="satellite wstETH/USDC 86% market with distinct oracle contract",
    ),
    "0x34377fc4f617c51818e92c79df31ff270c6a91bc94ad32e367fdf59b9f4ac5dd": MarketMeta(
        CollateralTier.LST_LRT_MINOR,
        oracle_note="ChainlinkOracleV2 0xa3A7…; weETH/ETH and ETH/USD route",
        notes="satellite weETH/USDC market; conservative 77% LLTV",
    ),
    "0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="ChainlinkOracleV2 0x0F94…; ETH/USD route",
        notes="satellite WETH/USDC 86% market; thin capacity",
    ),
    "0x0a15460ad263c2186fe0b5df20a8cf71d55f3cfa06de15edcf6138f6b8edd8bf": MarketMeta(
        CollateralTier.LST_LRT_MINOR,
        oracle_note="ChainlinkOracleV2 0x36Cb…; rETH/ETH and ETH/USD route",
        notes="monitor-only rETH/USDC 86% market; thin and above tier LLTV comfort",
    ),
    "0xbf02d6c6852fa0b8247d5514d0c91e6c1fbde9a168ac3fd2033028b5ee5ce6d0": MarketMeta(
        CollateralTier.LST_LRT_MINOR,
        oracle_note="ChainlinkOracleV2 0xDCc0…; LBTC/BTC and BTC/USD route",
        notes="monitor-only LBTC/USDC 86% market; thin and crowded",
    ),
    "0xe83d72fa5b00dcd46d9e0e860d95aa540d5ec106da5833108a9f826f21f36f52": MarketMeta(
        CollateralTier.PRIVATE_CREDIT,
        oracle_note="ChainlinkOracleV2 feed for Pareto FalconX Credit Vault LP token NAV",
        notes="77% LLTV; direct permissioned FalconX Credit Vault LP exposure "
        "with borrower-default, NAV, lending-cycle and redemption risk",
    ),
    "0x1e9d614631a7df0ec07fb05b2c8cb2491575fd1a63a33bf187a6afb295a4fc64": MarketMeta(
        CollateralTier.PT_FIXED,
        oracle_note="Pendle PT route over reUSD; maturity convergence plus underlying NAV pricing",
        # Verified from the PT contract's expiry().
        pt_maturity_timestamp=1796860800,
        notes="10-Dec-2026 maturity; 91.5% LLTV and reinsurance-credit/redemption "
        "risk require a small family cap and pre-maturity exit plan",
    ),
    "0x24852d8d7464402ddcd717415e009d42bf7427d6a8893487f83c75ee0f4a0ea6": MarketMeta(
        CollateralTier.GOVERNANCE_TOKEN,
        oracle_note="ChainlinkOracleV2 0x0798…; two-feed COMP/USDC pricing route",
        notes="62.5% LLTV dCOMP market; dCOMP is an ownable one-for-one COMP "
        "wrapper with configurable delegation and depositor whitelist; "
        "COMP volatility, wrapper administration and liquidation depth "
        "require a separate 5% family cap",
    ),
    # Blue-chip collateral
    "wstETH": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="Lido exchange rate composed with ETH/USD Chainlink; deep DEX+withdrawal exit",
        notes="largest LST; liquidations proven through multiple drawdowns",
    ),
    "WBTC": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="Chainlink BTC/USD (WBTC/BTC basis monitored)",
        notes="custodial (BitGo) wrapper risk accepted; deepest BTC collateral on mainnet",
    ),
    "cbBTC": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="Chainlink BTC/USD; Coinbase custody",
        notes="fast-growing WBTC alternative; custody concentration with Coinbase",
    ),
    "WETH": MarketMeta(
        CollateralTier.BLUE_CHIP,
        oracle_note="Chainlink ETH/USD",
        notes="fine collateral, but mainnet WETH/USDC borrow demand is thin - "
        "ETH borrowing happens against LSTs instead",
    ),
    # Yield-bearing stable collateral
    "sUSDe": MarketMeta(
        CollateralTier.YIELD_STABLE,
        oracle_note="typically hardcoded/exchange-rate pricing - liquidations lag a true depeg",
        notes="Ethena staked USDe; funding-rate + custodian risk; large organic borrow demand for leverage looping",
    ),
    "USDe": MarketMeta(
        CollateralTier.YIELD_STABLE,
        oracle_note="hardcoded 1:1 in the flagship market - explicit no-liquidation-on-depeg stance",
        notes="unstaked Ethena; similar risk to sUSDe without staking yield",
    ),
    "sUSDS": MarketMeta(
        CollateralTier.YIELD_STABLE,
        oracle_note="sky savings rate accrual oracle",
        notes="Sky (Maker) savings USDS",
    ),
    "stUSDS": MarketMeta(
        CollateralTier.YIELD_STABLE,
        oracle_note="stUSDS ERC-4626 conversion composed with USDS/USD and USDC/USD",
        notes="Sky risk-capital collateral; SKY-backed borrower, governance, "
        "vault conversion, redemption and loss-absorption risk",
    ),
    "sDAI": MarketMeta(CollateralTier.YIELD_STABLE, oracle_note="DSR accrual oracle"),
    # Pendle PTs
    "PT-sUSDe": MarketMeta(
        CollateralTier.PT_FIXED,
        oracle_note="Pendle PT oracle (TWAP of implied yield) -> converges to par at maturity",
        notes="fixed-maturity; must roll at expiry",
    ),
    "PT-USDe": MarketMeta(
        CollateralTier.PT_FIXED, oracle_note="Pendle PT oracle; converges to par"
    ),
    # Smaller LST/LRT collateral
    "weETH": MarketMeta(
        CollateralTier.LST_LRT_MINOR,
        oracle_note="ether.fi exchange rate x ETH/USD",
        notes="restaking wrapper; exit depends on EigenLayer withdrawal path + DEX depth",
    ),
    "rETH": MarketMeta(
        CollateralTier.LST_LRT_MINOR, oracle_note="Rocket Pool exchange rate x ETH/USD"
    ),
    "cbETH": MarketMeta(CollateralTier.LST_LRT_MINOR),
    "rsETH": MarketMeta(CollateralTier.LST_LRT_MINOR),
    "ezETH": MarketMeta(CollateralTier.LST_LRT_MINOR),
    "LBTC": MarketMeta(
        CollateralTier.LST_LRT_MINOR,
        oracle_note="BTC/USD feed + LBTC/BTC ratio; Lombard consortium security model",
        notes="yield-bearing BTC wrapper, younger than WBTC/cbBTC; sized as minor tier",
    ),
    # RWA collateral
    "wbIB01": MarketMeta(
        CollateralTier.RWA,
        oracle_note="NAV oracle; T-bill ETF wrapper (Backed)",
        notes="asset quality high, on-chain exit liquidity ~nil; sized accordingly",
    ),
    # Explicit exclusions
    "mF-ONE": MarketMeta(
        CollateralTier.EXOTIC,
        oracle_note="Midas NAV oracle for Fasanara private-credit fund",
        notes="EXCLUDED by judgment: gated off-chain redemption, whitelisted-borrower "
        "market, lender base ~one curator; wrong shape for a liquid meta-vault",
    ),
    "OETH": MarketMeta(
        CollateralTier.EXOTIC,
        oracle_note="reviewed market uses an ETH/USD feed without a visible OETH/ETH leg",
        notes="EXCLUDED: apparent 1:1 OETH/ETH treatment can lag a wrapper depeg",
    ),
    "wstUSR": MarketMeta(
        CollateralTier.EXOTIC,
        notes="EXCLUDED: attack market of the Mar-2026 Resolv USR exploit (hardcoded "
        "oracle + donation attack); liquidity gone",
    ),
    "sdeUSD": MarketMeta(
        CollateralTier.EXOTIC,
        notes="EXCLUDED: Elixir collapse Nov-2025, realized bad debt, delisted",
    ),
}


def lookup(unique_key: str, symbol: str) -> MarketMeta:
    """Match market ID, exact symbol, then the longest symbol prefix."""
    if unique_key in METADATA:
        return METADATA[unique_key]
    if symbol in METADATA:
        return METADATA[symbol]
    best = None
    for key, meta in METADATA.items():
        if symbol.startswith(key) and (best is None or len(key) > best[0]):
            best = (len(key), meta)
    meta = best[1] if best else MarketMeta()
    if meta.tier == CollateralTier.PT_FIXED and symbol in PT_MATURITY_DAYS:
        from dataclasses import replace

        meta = replace(meta, pt_maturity_days=PT_MATURITY_DAYS[symbol])
    return meta


# Snapshot-relative fallback for PTs without exact-market metadata.
PT_MATURITY_DAYS = {
    "PT-sUSDe-25SEP2026": 57.0,
    "PT-USDe-26NOV2026": 119.0,
}
