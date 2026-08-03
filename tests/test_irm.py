import math

import pytest

from curator import irm


def test_err_boundaries():
    assert irm.err(0.9) == 0.0
    assert irm.err(1.0) == 1.0
    assert irm.err(0.0) == -1.0
    assert irm.err(0.95) == pytest.approx(0.5)
    assert irm.err(0.45) == pytest.approx(-0.5)


def test_curve_endpoints():
    r = 0.04
    assert irm.borrow_rate(r, 0.90) == pytest.approx(r)
    assert irm.borrow_rate(r, 1.0) == pytest.approx(4 * r)  # steepness x
    assert irm.borrow_rate(r, 0.0) == pytest.approx(r / 4)  # steepness /


def test_supply_rate_is_borrow_times_util():
    assert irm.supply_rate(0.04, 0.9) == pytest.approx(0.04 * 0.9)
    assert irm.supply_rate(0.04, 0.9, fee=0.1) == pytest.approx(0.04 * 0.9 * 0.9)


def test_implied_rate_at_target_inverts_curve():
    for u in (0.3, 0.7, 0.9, 0.97):
        r_t = 0.05
        b = irm.borrow_rate(r_t, u)
        assert irm.implied_rate_at_target(b, u) == pytest.approx(r_t, rel=1e-9)


def test_adaptation_halving_time():
    # at err=-0.5 (u=0.45), rateAtTarget halves in ln2/(50*0.5) years ~ 5.06 days
    r0 = 0.04
    days = math.log(2) / (irm.ADJUSTMENT_SPEED * 0.5) * 365
    r1 = irm.evolve_rate_at_target(r0, 0.45, days / 365)
    assert r1 == pytest.approx(r0 / 2, rel=1e-6)


def test_adaptation_clamped():
    assert irm.evolve_rate_at_target(0.04, 0.0, 10.0) == irm.MIN_RATE_AT_TARGET
    assert irm.evolve_rate_at_target(0.04, 1.0, 10.0) == irm.MAX_RATE_AT_TARGET


def test_interval_rate_matches_contract_n2_average():
    start, u, dt = 0.04, 0.72, 1.0 / 365.0
    end = irm.evolve_rate_at_target(start, u, dt)
    mid = irm.evolve_rate_at_target(start, u, dt / 2.0)
    expected = irm.borrow_rate((start + end + 2 * mid) / 4, u)

    actual, actual_end = irm.interval_borrow_rate(start, u, dt)

    assert actual == pytest.approx(expected)
    assert actual_end == pytest.approx(end)


def test_zero_response_still_accrues_debt_and_raises_utilization():
    sim = irm.MarketSim(200e6, 140e6, 0.04, demand_elasticity=0.0)
    before = sim.utilization

    interval_return = sim.step(1.0)

    assert interval_return > 0
    assert sim.borrow > 140e6
    assert sim.supply > 200e6
    assert sim.utilization > before


def test_projected_apr_decreasing_in_deposit_size():
    s, b, r_t = 200e6, 180e6, 0.05
    aprs = [
        irm.projected_supply_apr(s, b, r_t, extra, horizon_days=14)
        for extra in (0.0, 10e6, 30e6, 60e6)
    ]
    assert aprs == sorted(aprs, reverse=True)
    # depositing 30% of the market must cost real yield, not epsilon
    assert aprs[0] - aprs[3] > 0.005


def test_projection_below_spot_when_diluting():
    s, b, r_t = 200e6, 180e6, 0.05  # u = 0.9 exactly
    spot = irm.supply_rate(r_t, 0.9)
    proj = irm.projected_supply_apr(s, b, r_t, 40e6, horizon_days=14)
    assert proj < spot


def test_borrower_elasticity_softens_impact():
    s, b, r_t = 200e6, 180e6, 0.05
    rigid = irm.projected_supply_apr(s, b, r_t, 40e6, demand_elasticity=0.0)
    elastic = irm.projected_supply_apr(s, b, r_t, 40e6, demand_elasticity=0.6)
    assert elastic > rigid


def test_withdrawal_raises_projected_rate():
    s, b, r_t = 200e6, 170e6, 0.05
    base = irm.projected_supply_apr(s, b, r_t, 0.0)
    after = irm.projected_supply_apr(s, b, r_t, -30e6)
    assert after > base


def test_apy_apr_roundtrip():
    for x in (0.01, 0.05, 0.2):
        assert irm.apy_to_apr(irm.apr_to_apy(x)) == pytest.approx(x)
