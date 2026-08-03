import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from curator.models import CollateralTier, Market, MarketState, RateHistory


def make_market(
    key="m1",
    coll="wstETH",
    supply=200e6,
    utilization=0.90,
    borrow_apy=0.055,
    tier=CollateralTier.BLUE_CHIP,
    lltv=0.86,
    reward_apr=0.0,
    pt_maturity_days=None,
):
    borrow = supply * utilization
    supply_apy = borrow_apy * utilization
    return Market(
        unique_key=key,
        collateral_symbol=coll,
        loan_symbol="USDC",
        lltv=lltv,
        state=MarketState(
            supply_assets=supply,
            borrow_assets=borrow,
            supply_apy=supply_apy,
            borrow_apy=borrow_apy,
            utilization=utilization,
            reward_supply_apr=reward_apr,
        ),
        history=RateHistory(daily=supply_apy, weekly=supply_apy, monthly=supply_apy),
        tier=tier,
        pt_maturity_days=pt_maturity_days,
    )


@pytest.fixture
def sample_universe():
    return [
        make_market(
            "wsteth", "wstETH", supply=300e6, utilization=0.90, borrow_apy=0.052
        ),
        make_market("wbtc", "WBTC", supply=400e6, utilization=0.88, borrow_apy=0.048),
        make_market("cbbtc", "cbBTC", supply=250e6, utilization=0.91, borrow_apy=0.050),
        make_market(
            "susde",
            "sUSDe",
            supply=150e6,
            utilization=0.92,
            borrow_apy=0.085,
            tier=CollateralTier.YIELD_STABLE,
            lltv=0.915,
        ),
        make_market(
            "ptsusde",
            "PT-sUSDe",
            supply=120e6,
            utilization=0.93,
            borrow_apy=0.078,
            tier=CollateralTier.PT_FIXED,
            lltv=0.915,
            pt_maturity_days=90,
        ),
        make_market(
            "weeth",
            "weETH",
            supply=60e6,
            utilization=0.85,
            borrow_apy=0.045,
            tier=CollateralTier.LST_LRT_MINOR,
            lltv=0.77,
        ),
        make_market(
            "rwa",
            "wbIB01",
            supply=40e6,
            utilization=0.80,
            borrow_apy=0.060,
            tier=CollateralTier.RWA,
        ),
    ]
