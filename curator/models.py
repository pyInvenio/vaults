"""Core dataclasses. Rates are decimal annual rates; notionals are USD."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CollateralTier(Enum):
    """Human-assigned collateral buckets used for concentration limits."""

    BLUE_CHIP = 1
    YIELD_STABLE = 2
    PT_FIXED = 3
    LST_LRT_MINOR = 4
    RWA = 5
    PRIVATE_CREDIT = 6
    GOVERNANCE_TOKEN = 7
    EXOTIC = 8


@dataclass
class MarketState:
    """Point-in-time observable state of one Morpho Blue market."""

    supply_assets: float
    borrow_assets: float
    supply_apy: float
    borrow_apy: float
    utilization: float
    rate_at_target: float | None = None
    fee: float = 0.0
    reward_supply_apr: float = 0.0
    timestamp: int | None = None
    curated_vault_share: float | None = None

    @property
    def liquidity(self) -> float:
        """Instantly withdrawable USD (idle liquidity in the market)."""
        return max(0.0, self.supply_assets - self.borrow_assets)


@dataclass
class RateHistory:
    """Trailing averages of native supply APY, as reported by the API."""

    daily: float | None = None
    weekly: float | None = None
    monthly: float | None = None
    quarterly: float | None = None


@dataclass
class Market:
    """One Morpho Blue market plus curator-assigned risk metadata."""

    unique_key: str
    collateral_symbol: str
    loan_symbol: str
    lltv: float
    state: MarketState
    history: RateHistory = field(default_factory=RateHistory)
    tier: CollateralTier = CollateralTier.EXOTIC
    oracle_note: str = ""
    whitelisted: bool = True
    pt_maturity_days: float | None = None
    notes: str = ""

    @property
    def label(self) -> str:
        return f"{self.collateral_symbol}/{self.loan_symbol}@{self.lltv:.3g}"


@dataclass
class VaultConfig:
    """Market-level sizing and rebalance parameters."""

    total_usd: float = 100_000_000.0

    horizon_days: float = 14.0

    max_weight: dict[CollateralTier, float] = field(
        default_factory=lambda: {
            CollateralTier.BLUE_CHIP: 0.50,
            CollateralTier.YIELD_STABLE: 0.12,
            CollateralTier.PT_FIXED: 0.10,
            CollateralTier.LST_LRT_MINOR: 0.05,
            CollateralTier.RWA: 0.05,
            CollateralTier.PRIVATE_CREDIT: 0.05,
            CollateralTier.GOVERNANCE_TOKEN: 0.05,
            CollateralTier.EXOTIC: 0.0,
        }
    )
    max_ownership_share: float = 0.35
    min_ticket: float = 1_000_000.0
    idle_buffer_weight: float = 0.0
    idle_parking_apr: float = 0.0

    min_move_usd: float = 1_000_000.0
    min_gain_bps: float = 15.0
    gas_cost_per_move_usd: float = 60.0
    drift_band_abs: float = 0.01
    max_weekly_turnover: float = 0.10

    market_bad_debt_kill_usd: float = 100_000.0
    vault_loss_kill_bps: float = 1.0


@dataclass
class Allocation:
    """Target allocation produced by the allocator."""

    weights: dict[str, float]
    amounts: dict[str, float]
    projected_apr: float
    projected_risk_adj_apr: float | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
