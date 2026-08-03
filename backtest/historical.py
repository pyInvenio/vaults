"""Counterfactual replay of allocation policies on Morpho daily history.

The historical tape is never shuffled.  On each UTC day the replay replaces
the external market state with the observation stored in SQLite, adds the
strategy's hypothetical position, and recomputes its post-deposit rate from
the AdaptiveCurve IRM.  The hypothetical position does not alter the next
day's historical observation.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from curator import irm, universe
from curator.mandate import selection_filters
from curator.models import CollateralTier, Market, MarketState, RateHistory, VaultConfig
from curator.strategy import SpotApyChaser, Strategy

from .history_db import connect, event_window_covered
from .pull_history import DEFAULT_DB, timestamp
from .strategy import ConstrainedYieldStrategy, StaticConstrainedStrategy

DAY_SECONDS = 86_400


@dataclass(frozen=True)
class HistoricalWindow:
    name: str
    start: int
    end: int

    @property
    def days(self) -> int:
        """Number of daily observations; both endpoints are inclusive."""
        return (self.end - self.start) // DAY_SECONDS + 1


@dataclass(frozen=True)
class BacktestSpec:
    """Reusable replay request: a UTC start, duration, and observation grid."""

    name: str
    start: int
    days: int
    resolution: str = "DAY"
    require_events: bool = True

    @property
    def step_seconds(self) -> int:
        if self.resolution == "DAY":
            return DAY_SECONDS
        if self.resolution == "HOUR":
            return 3_600
        raise ValueError(f"unsupported resolution: {self.resolution}")

    @property
    def observations(self) -> int:
        if self.days <= 0:
            raise ValueError("backtest days must be positive")
        return self.days * DAY_SECONDS // self.step_seconds

    @property
    def end_exclusive(self) -> int:
        return self.start + self.days * DAY_SECONDS


@dataclass(frozen=True)
class HistoricalResult:
    window: str
    start: str
    end: str
    strategy: str
    resolution: str
    pricing_model: str
    cadence_days: float | None
    universe_size: int
    universe: str
    observations: int
    initial_nav_usd: float
    ending_nav_usd: float
    gross_interest_usd: float
    net_apr: float
    gross_apr: float
    gas_usd: float
    turnover_nav: float
    moves: int
    liquidation_count: int
    liquidation_repaid_usd: float
    bad_debt_event_count: int
    material_incident_count: int
    principal_loss_usd: float
    max_concentration: float
    max_liquidity_shortfall: float
    average_deployed_weight: float
    minimum_deployed_weight: float
    maximum_deployed_weight: float
    final_idle_weight: float
    daily_apr_volatility: float


def iso_day(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


class HistoryStore:
    """Point-in-time reads over the local Morpho history database."""

    def __init__(self, path: str | Path = DEFAULT_DB) -> None:
        self.db = connect(path, read_only=True)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "HistoryStore":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    @staticmethod
    def _state_table(resolution: str) -> str:
        if resolution == "DAY":
            return "market_states"
        if resolution == "HOUR":
            return "market_states_hourly"
        raise ValueError(f"unsupported resolution: {resolution}")

    def markets_at(self, ts: int, resolution: str = "DAY") -> list[Market]:
        table = self._state_table(resolution)
        rows = self.db.execute(
            f"""
            SELECT m.*, s.timestamp, s.supply_assets_usd, s.borrow_assets_usd,
                   s.supply_apy, s.borrow_apy, s.utilization,
                   (SELECT AVG(h.supply_apy) FROM market_states h
                    WHERE h.market_id=s.market_id
                      AND h.timestamp BETWEEN ? AND s.timestamp) AS weekly_apy,
                   (SELECT AVG(h.supply_apy) FROM market_states h
                    WHERE h.market_id=s.market_id
                      AND h.timestamp BETWEEN ? AND s.timestamp) AS monthly_apy,
                   (SELECT AVG(h.supply_apy) FROM market_states h
                    WHERE h.market_id=s.market_id
                      AND h.timestamp BETWEEN ? AND s.timestamp) AS quarterly_apy
            FROM {table} s
            JOIN markets m ON m.market_id=s.market_id
            WHERE s.timestamp=?
            ORDER BY m.market_id
            """,
            (ts - 6 * DAY_SECONDS, ts - 29 * DAY_SECONDS, ts - 89 * DAY_SECONDS, ts),
        ).fetchall()
        return [self._market(row) for row in rows]

    def states_at(
        self, ts: int, market_ids: Iterable[str], resolution: str = "DAY"
    ) -> dict[str, object]:
        ids = tuple(market_ids)
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        table = self._state_table(resolution)
        rows = self.db.execute(
            f"""
            SELECT s.*,
                   (SELECT AVG(h.supply_apy) FROM market_states h
                    WHERE h.market_id=s.market_id
                      AND h.timestamp BETWEEN ? AND s.timestamp) AS weekly_apy,
                   (SELECT AVG(h.supply_apy) FROM market_states h
                    WHERE h.market_id=s.market_id
                      AND h.timestamp BETWEEN ? AND s.timestamp) AS monthly_apy,
                   (SELECT AVG(h.supply_apy) FROM market_states h
                    WHERE h.market_id=s.market_id
                      AND h.timestamp BETWEEN ? AND s.timestamp) AS quarterly_apy
            FROM {table} s
            WHERE s.timestamp=? AND s.market_id IN ({placeholders})
            """,
            (
                ts - 6 * DAY_SECONDS,
                ts - 29 * DAY_SECONDS,
                ts - 89 * DAY_SECONDS,
                ts,
                *ids,
            ),
        ).fetchall()
        return {row["market_id"]: row for row in rows}

    def liquidations_between(
        self, start: int, end: int, market_ids: Iterable[str]
    ) -> list[object]:
        ids = tuple(market_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        return self.db.execute(
            f"""
            SELECT * FROM liquidation_events
            WHERE timestamp>=? AND timestamp<?
              AND market_id IN ({placeholders})
            ORDER BY timestamp, block_number, log_index
            """,
            (start, end, *ids),
        ).fetchall()

    def events_covered(self, start: int, end: int, market_ids: Iterable[str]) -> bool:
        return event_window_covered(self.db, tuple(market_ids), start, end)

    def candidate_start_dates(self, days: int) -> list[int]:
        last_allowed = self.db.execute(
            "SELECT MAX(timestamp)-? FROM market_states", (days * DAY_SECONDS,)
        ).fetchone()[0]
        if last_allowed is None:
            return []
        return [
            row[0]
            for row in self.db.execute(
                """
                SELECT s.timestamp
                FROM market_states s JOIN markets m USING(market_id)
                WHERE s.timestamp<=? AND m.tier!='EXOTIC'
                  AND s.supply_assets_usd>=30000000
                  AND s.borrow_assets_usd>=5000000
                  AND s.utilization<=0.995
                GROUP BY s.timestamp
                HAVING COUNT(*)>=3
                ORDER BY s.timestamp
                """,
                (last_allowed,),
            )
        ]

    def is_quiet_window(
        self,
        start: int,
        days: int,
        market_ids: Iterable[str],
        max_daily_change: float = 0.15,
        max_utilization: float = 0.97,
        max_supply_apy: float = 0.15,
    ) -> bool:
        ids = tuple(market_ids)
        placeholders = ",".join("?" for _ in ids)
        rows = self.db.execute(
            f"""
            SELECT * FROM market_states
            WHERE timestamp>=? AND timestamp<? AND market_id IN ({placeholders})
            ORDER BY market_id, timestamp
            """,
            (start, start + days * DAY_SECONDS, *ids),
        ).fetchall()
        if len(rows) != days * len(ids):
            return False
        previous: dict[str, object] = {}
        for row in rows:
            if (
                row["utilization"] > max_utilization
                or row["supply_apy"] > max_supply_apy
            ):
                return False
            prior = previous.get(row["market_id"])
            if prior is not None:
                for field in ("supply_assets_usd", "borrow_assets_usd"):
                    base = prior[field]
                    if base <= 0 or abs(row[field] / base - 1.0) > max_daily_change:
                        return False
            previous[row["market_id"]] = row
        return True

    @staticmethod
    def _market(row) -> Market:
        return Market(
            unique_key=row["market_id"],
            collateral_symbol=row["collateral_symbol"],
            loan_symbol=row["loan_symbol"],
            lltv=row["lltv"],
            state=MarketState(
                supply_assets=row["supply_assets_usd"],
                borrow_assets=row["borrow_assets_usd"],
                supply_apy=row["supply_apy"],
                borrow_apy=row["borrow_apy"],
                utilization=row["utilization"],
                timestamp=row["timestamp"],
            ),
            history=RateHistory(
                daily=row["supply_apy"],
                weekly=row["weekly_apy"],
                monthly=row["monthly_apy"],
                quarterly=row["quarterly_apy"],
            ),
            tier=CollateralTier[row["tier"]],
            # Today's listed flag is not historical eligibility evidence.
            whitelisted=True,
            oracle_note=row["oracle_note"],
            pt_maturity_days=row["pt_maturity_days"],
            notes=row["notes"],
        )


@dataclass
class HistoricalMarket:
    market: Market
    supply_ext: float
    borrow: float
    rate_at_target: float
    fee: float
    our_position: float = 0.0

    @property
    def total_supply(self) -> float:
        return self.supply_ext + self.our_position

    @property
    def utilization(self) -> float:
        return min(self.borrow / self.total_supply, 1.0) if self.total_supply else 0.0

    def supply_rate(self, market_impact: bool = True) -> float:
        utilization = self.utilization
        if not market_impact and self.supply_ext > 0:
            utilization = min(self.borrow / self.supply_ext, 1.0)
        return irm.supply_rate(self.rate_at_target, utilization, self.fee)

    def update(self, row) -> None:
        state = self.market.state
        self.supply_ext = row["supply_assets_usd"]
        self.borrow = min(row["borrow_assets_usd"], self.supply_ext)
        observed_u = row["utilization"]
        self.rate_at_target = irm.rate_at_target_from(row["borrow_apy"], observed_u)
        borrow_apr = irm.apy_to_apr(row["borrow_apy"])
        supply_apr = irm.apy_to_apr(row["supply_apy"])
        gross_supply_apr = borrow_apr * observed_u
        self.fee = (
            min(max(1.0 - supply_apr / gross_supply_apr, 0.0), 1.0)
            if gross_supply_apr > 1e-12
            else 0.0
        )
        state.supply_assets = self.supply_ext
        state.borrow_assets = self.borrow
        state.supply_apy = row["supply_apy"]
        state.borrow_apy = row["borrow_apy"]
        state.utilization = observed_u
        state.rate_at_target = self.rate_at_target
        state.timestamp = row["timestamp"]
        self.market.history = RateHistory(
            daily=row["supply_apy"],
            weekly=row["weekly_apy"],
            monthly=row["monthly_apy"],
            quarterly=row["quarterly_apy"],
        )


def _historical_market(market: Market) -> HistoricalMarket:
    world_market = HistoricalMarket(
        market=market,
        supply_ext=market.state.supply_assets,
        borrow=market.state.borrow_assets,
        rate_at_target=irm.rate_at_target_from(
            market.state.borrow_apy, market.state.utilization
        ),
        fee=0.0,
    )

    class Row(dict):
        __getattr__ = dict.__getitem__

    world_market.update(
        Row(
            supply_assets_usd=market.state.supply_assets,
            borrow_assets_usd=market.state.borrow_assets,
            supply_apy=market.state.supply_apy,
            borrow_apy=market.state.borrow_apy,
            utilization=market.state.utilization,
            timestamp=market.state.timestamp,
            weekly_apy=market.history.weekly,
            monthly_apy=market.history.monthly,
            quarterly_apy=market.history.quarterly,
        )
    )
    return world_market


def _observable_snapshot(
    world: dict[str, HistoricalMarket], cfg: VaultConfig
) -> tuple[float, float]:
    """Return concentration and liquidity shortfall from observed state.

    Scenario-loss haircuts belong in the experimental evaluator. Historical
    headline metrics are limited to quantities observable on the replay tape.
    """
    positions = {key: sm.our_position for key, sm in world.items()}
    concentration = max(positions.values(), default=0.0) / cfg.total_usd
    liquidity_gap = (
        sum(
            # Do not count our deposit as exit liquidity.
            max(sm.our_position - max(sm.supply_ext - sm.borrow, 0.0), 0.0)
            for sm in world.values()
        )
        / cfg.total_usd
    )
    return concentration, liquidity_gap


def replay_spec(
    store: HistoryStore,
    spec: BacktestSpec,
    strategy: Strategy,
    cfg: VaultConfig | None = None,
    filters: dict | None = None,
    apply_market_impact: bool = True,
) -> HistoricalResult:
    """Replay one policy with sampled states plus exact-block liquidation events."""
    cfg = cfg or VaultConfig()
    observations = spec.observations
    report = universe.select(
        store.markets_at(spec.start, spec.resolution),
        cfg,
        filters=filters,
    )
    selected = report.universe
    if not selected:
        raise ValueError(f"no eligible markets at {iso_day(spec.start)}")
    world = {m.unique_key: _historical_market(m) for m in selected}
    if spec.require_events and not store.events_covered(
        spec.start, spec.end_exclusive, world
    ):
        raise ValueError(
            "liquidation event coverage is missing for this exact market/date scope; "
            "run backtest.pull_events before treating absent events as zero"
        )

    cash = cfg.total_usd
    interest = gas = turnover = principal_loss = 0.0
    moves = 0
    liquidation_count = 0
    liquidation_repaid = 0.0
    bad_debt_event_count = 0
    material_incident_count = 0
    blocked_markets: set[str] = set()
    daily_aprs: list[float] = []
    day_interest = 0.0
    elapsed_in_day = 0
    concentration_trace: list[float] = []
    liquidity_trace: list[float] = []
    deployed_trace: list[float] = []

    for observation in range(observations):
        ts = spec.start + observation * spec.step_seconds
        rows = store.states_at(ts, world, spec.resolution)
        missing = set(world) - set(rows)
        if missing:
            labels = ", ".join(world[key].market.collateral_symbol for key in missing)
            stamp = datetime.fromtimestamp(ts, timezone.utc).isoformat()
            raise ValueError(f"missing {stamp} {spec.resolution} history for {labels}")
        for key, row in rows.items():
            world[key].update(row)

        elapsed_days = observation * spec.step_seconds / DAY_SECONDS
        target = strategy.target(world, elapsed_days, cfg)
        for key in blocked_markets:
            target[key] = 0.0
        for key, sm in world.items():
            delta = target.get(key, 0.0) - sm.our_position
            if delta <= -cfg.min_move_usd:
                liquidity = max(sm.total_supply - sm.borrow, 0.0)
                take = min(-delta, liquidity, sm.our_position)
                if take >= cfg.min_move_usd:
                    sm.our_position -= take
                    cash += take
                    turnover += take
                    gas += cfg.gas_cost_per_move_usd
                    moves += 1
        deposits = sorted(
            (
                (key, target.get(key, 0.0) - sm.our_position)
                for key, sm in world.items()
            ),
            key=lambda item: -item[1],
        )
        for key, delta in deposits:
            put = min(delta, cash)
            if put < cfg.min_move_usd:
                continue
            world[key].our_position += put
            cash -= put
            turnover += put
            gas += cfg.gas_cost_per_move_usd
            moves += 1

        # Preserve exact event order between sampled market states.
        events = store.liquidations_between(ts, ts + spec.step_seconds, world)
        for event in events:
            liquidation_count += 1
            liquidation_repaid += event["repaid_assets_usd"]
            bad_debt = event["bad_debt_assets_usd"]
            if bad_debt <= 0:
                continue
            bad_debt_event_count += 1
            sm = world[event["market_id"]]
            share = sm.our_position / max(sm.total_supply, 1.0)
            loss = min(sm.our_position, bad_debt * share)
            sm.our_position -= loss
            principal_loss += loss
            material = (
                bad_debt >= cfg.market_bad_debt_kill_usd
                or loss >= cfg.total_usd * cfg.vault_loss_kill_bps / 10_000
            )
            if not material:
                continue
            material_incident_count += 1
            blocked_markets.add(event["market_id"])
            liquidity = max(sm.total_supply - sm.borrow, 0.0)
            take = min(sm.our_position, liquidity)
            if take >= cfg.min_move_usd:
                sm.our_position -= take
                cash += take
                turnover += take
                gas += cfg.gas_cost_per_move_usd
                moves += 1

        step_interest = sum(
            sm.our_position
            * sm.supply_rate(apply_market_impact)
            * spec.step_seconds
            / (365 * DAY_SECONDS)
            for sm in world.values()
        )
        interest += step_interest
        day_interest += step_interest
        elapsed_in_day += spec.step_seconds
        if elapsed_in_day == DAY_SECONDS:
            daily_aprs.append(day_interest / cfg.total_usd * 365.0)
            day_interest = 0.0
            elapsed_in_day = 0
        concentration, liquidity_gap = _observable_snapshot(world, cfg)
        concentration_trace.append(concentration)
        liquidity_trace.append(liquidity_gap)
        deployed_trace.append(
            sum(sm.our_position for sm in world.values()) / cfg.total_usd
        )

    gross_apr = interest / cfg.total_usd * 365.0 / spec.days
    return HistoricalResult(
        window=spec.name,
        start=iso_day(spec.start),
        end=iso_day(spec.end_exclusive - spec.step_seconds),
        strategy=strategy.name,
        resolution=spec.resolution,
        pricing_model="post-impact" if apply_market_impact else "price-taker",
        cadence_days=getattr(strategy, "period_days", None),
        universe_size=len(world),
        universe=", ".join(
            sorted(sm.market.collateral_symbol for sm in world.values())
        ),
        observations=observations,
        initial_nav_usd=cfg.total_usd,
        ending_nav_usd=cfg.total_usd + interest - gas - principal_loss,
        gross_interest_usd=interest,
        net_apr=(interest - gas - principal_loss) / cfg.total_usd * 365.0 / spec.days,
        gross_apr=gross_apr,
        gas_usd=gas,
        turnover_nav=turnover / cfg.total_usd,
        moves=moves,
        liquidation_count=liquidation_count,
        liquidation_repaid_usd=liquidation_repaid,
        bad_debt_event_count=bad_debt_event_count,
        material_incident_count=material_incident_count,
        principal_loss_usd=principal_loss,
        max_concentration=max(concentration_trace),
        max_liquidity_shortfall=max(liquidity_trace),
        average_deployed_weight=statistics.fmean(deployed_trace),
        minimum_deployed_weight=min(deployed_trace),
        maximum_deployed_weight=max(deployed_trace),
        final_idle_weight=cash / cfg.total_usd,
        daily_apr_volatility=statistics.pstdev(daily_aprs),
    )


def replay(
    store: HistoryStore,
    window: HistoricalWindow,
    strategy: Strategy,
    cfg: VaultConfig | None = None,
) -> HistoricalResult:
    """Backward-compatible daily replay with inclusive date endpoints."""
    if window.end < window.start:
        raise ValueError("historical window must contain at least one day")
    return replay_spec(
        store,
        BacktestSpec(window.name, window.start, window.days, "DAY", False),
        strategy,
        cfg,
        filters=None,
        apply_market_impact=True,
    )


def requested_windows() -> list[HistoricalWindow]:
    return [
        HistoricalWindow(
            "oct10-dec25", timestamp("2025-10-10"), timestamp("2025-12-25")
        ),
        HistoricalWindow(
            "oct25-dec25", timestamp("2025-10-25"), timestamp("2025-12-25")
        ),
    ]


def strategy_factories(cadences: Iterable[float]) -> list[Callable[[], Strategy]]:
    return [
        StaticConstrainedStrategy,
        lambda: SpotApyChaser(top_n=2, period_days=1.0),
        *(
            lambda period=period: ConstrainedYieldStrategy(period_days=period)
            for period in cadences
        ),
    ]


class HistoricalBacktester(ABC):
    """Backend-independent date-plus-duration backtest interface."""

    @abstractmethod
    def run(
        self,
        start_date: str,
        days: int,
        strategy: Strategy,
        resolution: str = "DAY",
        name: str | None = None,
    ) -> HistoricalResult:
        raise NotImplementedError


class MorphoHistoricalBacktester(HistoricalBacktester):
    """Replay Morpho policies from the local sampled-state + exact-event tape."""

    def __init__(
        self,
        database: str | Path = DEFAULT_DB,
        cfg: VaultConfig | None = None,
        filters: dict | None = None,
    ) -> None:
        self.database = Path(database)
        self.cfg = cfg or VaultConfig()
        self.filters = selection_filters() if filters is None else filters

    def run(
        self,
        start_date: str,
        days: int,
        strategy: Strategy,
        resolution: str = "DAY",
        name: str | None = None,
    ) -> HistoricalResult:
        spec = BacktestSpec(
            name or f"{start_date}-{days}d",
            timestamp(start_date),
            days,
            resolution,
        )
        with HistoryStore(self.database) as store:
            return replay_spec(store, spec, strategy, self.cfg, self.filters)

    def run_suite(
        self,
        start_date: str,
        days: int,
        cadences: Iterable[float] = (1, 3, 7, 14, 28),
        resolution: str = "DAY",
        name: str | None = None,
    ) -> list[HistoricalResult]:
        return [
            self.run(start_date, days, factory(), resolution, name)
            for factory in strategy_factories(cadences)
        ]

    def sample_normal_periods(
        self,
        days: int,
        count: int,
        seed: int = 7,
        exclude: Iterable[tuple[str, str]] = (),
    ) -> list[BacktestSpec]:
        """Seeded random contiguous windows that pass a transparent quiet-tape filter.

        Randomness chooses start dates only; observations inside each selected
        window remain in their original order. Full-window filtering is for
        scenario labeling, never supplied to the strategy.
        """
        excluded = tuple((timestamp(start), timestamp(end)) for start, end in exclude)
        with HistoryStore(self.database) as store:
            candidates = store.candidate_start_dates(days)
            random.Random(seed).shuffle(candidates)
            selected_specs: list[BacktestSpec] = []
            for start in candidates:
                end = start + days * DAY_SECONDS
                if any(
                    start < blocked_end and end > blocked_start
                    for blocked_start, blocked_end in excluded
                ):
                    continue
                if any(
                    start < spec.end_exclusive and end > spec.start
                    for spec in selected_specs
                ):
                    continue
                report = universe.select(
                    store.markets_at(start), self.cfg, filters=self.filters
                )
                # Exclude tiny venues only from quiet-period labeling.
                quiet_ids = [
                    market.unique_key
                    for market in report.universe
                    if market.state.supply_assets >= 10_000_000
                    and market.state.borrow_assets >= 5_000_000
                ]
                if len(quiet_ids) < 2 or not store.is_quiet_window(
                    start, days, quiet_ids
                ):
                    continue
                selected_specs.append(
                    BacktestSpec(f"normal-{iso_day(start)}-{days}d", start, days, "DAY")
                )
                if len(selected_specs) == count:
                    return selected_specs
        raise ValueError(
            f"found only {len(selected_specs)} quiet windows; requested {count}"
        )


def evaluate(
    database: str | Path = DEFAULT_DB,
    windows: Iterable[HistoricalWindow] | None = None,
    cadences: Iterable[float] = (1, 3, 7, 14, 28),
) -> list[HistoricalResult]:
    results: list[HistoricalResult] = []
    with HistoryStore(database) as store:
        for window in windows or requested_windows():
            for factory in strategy_factories(cadences):
                results.append(replay(store, window, factory()))
    return results


def write_csv(results: Iterable[HistoricalResult], path: str | Path) -> None:
    rows = list(results)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(HistoricalResult.__dataclass_fields__),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def print_results(results: Iterable[HistoricalResult]) -> None:
    rows = list(results)
    print(
        f"{'window':<24}{'grid':>6} {'pricing':<12}{'strategy':<27}"
        f"{'net APR':>10}{'gross':>9}"
        f"{'turn':>8}{'moves':>7}{'liqs':>6}{'repaid':>10}{'bad debt':>11}"
        f"{'max pos':>9}{'liq gap':>9}{'idle':>8}"
    )
    for row in rows:
        print(
            f"{row.window:<24}{row.resolution:>6} {row.pricing_model:<12}"
            f"{row.strategy:<27}{row.net_apr:>10.2%}"
            f"{row.gross_apr:>9.2%}{row.turnover_nav:>7.2f}x{row.moves:>7}"
            f"{row.liquidation_count:>6}{row.liquidation_repaid_usd / 1e6:>9.2f}M"
            f"{row.principal_loss_usd / 1e6:>10.2f}M{row.max_concentration:>9.1%}"
            f"{row.max_liquidity_shortfall:>9.1%}{row.final_idle_weight:>8.1%}"
        )
    print("\nPoint-in-time universes")
    seen = set()
    for row in rows:
        if row.window in seen:
            continue
        seen.add(row.window)
        print(f"  {row.window}: {row.universe}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=str(DEFAULT_DB))
    parser.add_argument("--cadences", default="1,3,7,14,28")
    parser.add_argument("--start", help="custom inclusive UTC start date")
    parser.add_argument("--end", help="custom inclusive UTC end date (legacy form)")
    parser.add_argument("--days", type=int, help="duration from --start")
    parser.add_argument("--resolution", choices=("DAY", "HOUR"), default="DAY")
    parser.add_argument("--output", help="optional result CSV path")
    args = parser.parse_args()
    cadences = tuple(float(value) for value in args.cadences.split(","))
    if args.days and not args.start:
        parser.error("--days requires --start")
    if args.start and not (args.days or args.end):
        parser.error("--start requires --days or --end")
    if args.days and args.end:
        parser.error("use either --days or --end, not both")
    windows = None
    if args.start and args.days:
        backtester = MorphoHistoricalBacktester(args.database)
        results = backtester.run_suite(args.start, args.days, cadences, args.resolution)
    elif args.start:
        windows = [
            HistoricalWindow(
                f"{args.start}-{args.end}", timestamp(args.start), timestamp(args.end)
            )
        ]
        results = evaluate(args.database, windows, cadences)
    else:
        results = evaluate(args.database, windows, cadences)
    print_results(results)
    if args.output:
        write_csv(results, args.output)


if __name__ == "__main__":
    main()
