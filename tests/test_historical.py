from curator.models import CollateralTier, Market, MarketState
from curator.allocator import AllocationPolicy

from backtest.historical import (
    BacktestSpec,
    HistoricalWindow,
    HistoryStore,
    MorphoHistoricalBacktester,
    replay,
)
from backtest.history_db import (
    connect,
    event_scope_hash,
    record_event_window,
    upsert_liquidations,
    upsert_market,
    upsert_states,
)
from backtest.pull_history import timestamp
from backtest.strategy import ConstrainedYieldStrategy


def _database(path):
    db = connect(path)
    market = Market(
        unique_key="market-1",
        collateral_symbol="wstETH",
        loan_symbol="USDC",
        lltv=0.86,
        state=MarketState(200e6, 180e6, 0.045, 0.05, 0.90),
        tier=CollateralTier.BLUE_CHIP,
    )
    upsert_market(db, market)
    upsert_states(
        db,
        market.unique_key,
        [
            {
                "timestamp": timestamp("2024-12-31"),
                "supply_assets_usd": 200e6,
                "borrow_assets_usd": 180e6,
                "supply_apy": 0.02,
                "borrow_apy": 0.025,
                "utilization": 0.90,
            },
            {
                "timestamp": timestamp("2025-01-01"),
                "supply_assets_usd": 200e6,
                "borrow_assets_usd": 180e6,
                "supply_apy": 0.04,
                "borrow_apy": 0.045,
                "utilization": 0.90,
            },
            {
                "timestamp": timestamp("2025-01-02"),
                "supply_assets_usd": 200e6,
                "borrow_assets_usd": 180e6,
                "supply_apy": 0.99,
                "borrow_apy": 1.0,
                "utilization": 0.90,
            },
        ],
    )
    db.commit()
    db.close()


def test_history_store_trailing_averages_do_not_look_ahead(tmp_path):
    path = tmp_path / "history.sqlite3"
    _database(path)
    with HistoryStore(path) as store:
        (market,) = store.markets_at(timestamp("2025-01-01"))
    assert market.history.daily == 0.04
    assert market.history.weekly == 0.03


def test_replay_uses_inclusive_dates_and_historical_observations(tmp_path):
    path = tmp_path / "history.sqlite3"
    _database(path)
    window = HistoricalWindow(
        "two-days", timestamp("2025-01-01"), timestamp("2025-01-02")
    )
    with HistoryStore(path) as store:
        result = replay(store, window, ConstrainedYieldStrategy(period_days=1))
    assert result.observations == 2
    assert result.universe == "wstETH"
    assert result.moves == 1
    assert result.net_apr > 0


def test_date_duration_abstraction_counts_hourly_observations():
    spec = BacktestSpec("event", timestamp("2025-10-10"), 7, "HOUR")
    assert spec.observations == 7 * 24
    assert spec.end_exclusive == timestamp("2025-10-17")


def test_exact_event_bad_debt_is_charged_to_supplier_and_forces_exit(tmp_path):
    path = tmp_path / "history.sqlite3"
    _database(path)
    db = connect(path)
    upsert_liquidations(
        db,
        [
            {
                "tx_hash": "0xevent",
                "log_index": 1,
                "market_id": "market-1",
                "timestamp": timestamp("2025-01-01") + 3600,
                "block_number": 123,
                "repaid_assets_usd": 2e6,
                "bad_debt_assets_usd": 11e6,
                "seized_assets_raw": "1",
                "liquidator": "0xliquidator",
            }
        ],
    )
    record_event_window(
        db,
        event_scope_hash(["market-1"]),
        timestamp("2025-01-01"),
        timestamp("2025-01-02"),
        1,
        timestamp("2025-01-03"),
    )
    db.commit()
    db.close()

    backtester = MorphoHistoricalBacktester(
        path,
        filters={
            "allowed_market_ids": {"market-1"},
            "min_supply_usd": 1.0,
            "min_borrow_usd": 1.0,
        },
    )
    result = backtester.run(
        "2025-01-01",
        1,
        ConstrainedYieldStrategy(
            period_days=1,
            # Hold a deterministic $40M position so this test isolates the
            # supplier-loss calculation from changes to production caps.
            budget=AllocationPolicy(
                max_market_weight=0.40,
                family_caps={"eth": 1.0},
            ),
        ),
    )
    assert result.liquidation_count == 1
    assert result.liquidation_repaid_usd == 2e6
    # The live mandate sizes this one-market fixture to $40M: twice the $20M
    # pre-deposit exit liquidity. Supplier loss is charged pro rata.
    assert result.principal_loss_usd == 40e6 / 240e6 * 11e6
    assert result.bad_debt_event_count == 1
    assert result.material_incident_count == 1
    assert result.moves == 2  # deposit followed by exact-event forced exit
    assert result.net_apr < 0


def test_bad_debt_dust_is_recorded_without_forcing_exit(tmp_path):
    path = tmp_path / "history.sqlite3"
    _database(path)
    db = connect(path)
    upsert_liquidations(
        db,
        [
            {
                "tx_hash": "0xdust",
                "log_index": 1,
                "market_id": "market-1",
                "timestamp": timestamp("2025-01-01") + 3600,
                "block_number": 124,
                "repaid_assets_usd": 1.0,
                "bad_debt_assets_usd": 0.03,
                "seized_assets_raw": "1",
                "liquidator": "0xliquidator",
            }
        ],
    )
    record_event_window(
        db,
        event_scope_hash(["market-1"]),
        timestamp("2025-01-01"),
        timestamp("2025-01-02"),
        1,
        timestamp("2025-01-03"),
    )
    db.commit()
    db.close()

    backtester = MorphoHistoricalBacktester(
        path,
        filters={
            "allowed_market_ids": {"market-1"},
            "min_supply_usd": 1.0,
            "min_borrow_usd": 1.0,
        },
    )
    result = backtester.run("2025-01-01", 1, ConstrainedYieldStrategy(period_days=1))
    assert result.bad_debt_event_count == 1
    assert result.material_incident_count == 0
    assert result.principal_loss_usd > 0
    assert result.moves == 1
