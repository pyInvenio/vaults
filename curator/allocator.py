"""Capacity-aware allocation with explicit portfolio constraints."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Allocation, CollateralTier, Market, VaultConfig
from .rates import MarketCurve

EPSILON = 1e-6
MAX_SWAP_ITERATIONS = 10_000


@dataclass(frozen=True)
class AllocationPolicy:
    """Product and portfolio constraints expressed as fractions of NAV."""

    max_market_weight: float = 0.50
    max_non_blue_weight: float = 0.25
    family_caps: dict[str, float] = field(
        default_factory=lambda: {
            "btc": 0.675,
            "eth": 0.25,
            "sky": 0.05,
            "re_credit": 0.10,
            "falconx_credit": 0.05,
            "comp": 0.05,
        }
    )
    min_funded_markets: int = 0
    min_deployed_weight: float = 1.0
    min_market_exit_coverage: float = 0.50
    min_stressed_liquidity_weight: float = 0.60
    reward_weight: float = 0.0

    def __post_init__(self) -> None:
        fractions = {
            "max_market_weight": self.max_market_weight,
            "max_non_blue_weight": self.max_non_blue_weight,
            "min_deployed_weight": self.min_deployed_weight,
            "min_market_exit_coverage": self.min_market_exit_coverage,
            "min_stressed_liquidity_weight": self.min_stressed_liquidity_weight,
            "reward_weight": self.reward_weight,
            **{f"family:{name}": value for name, value in self.family_caps.items()},
        }
        for name, value in fractions.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1: {value}")
        if self.min_funded_markets < 0:
            raise ValueError("min_funded_markets cannot be negative")


def risk_family(market: Market) -> str | None:
    symbol = market.collateral_symbol.upper()
    if symbol in {"CBBTC", "WBTC", "LBTC"}:
        return "btc"
    if symbol in {"WETH", "WSTETH", "WEETH", "RETH"}:
        return "eth"
    if symbol == "STUSDS":
        return "sky"
    if symbol.startswith("PT-REUSD") or symbol == "REUSD":
        return "re_credit"
    if "FALCONX" in symbol:
        return "falconx_credit"
    if symbol in {"COMP", "DCOMP"}:
        return "comp"
    return None


def allocate(
    markets: list[Market],
    cfg: VaultConfig,
    budget: AllocationPolicy | None = None,
    chunk: float | None = None,
) -> Allocation:
    """Maximize post-impact native yield subject to hard constraints."""
    if budget is None:
        budget = AllocationPolicy()
    if chunk is None:
        chunk = max(cfg.total_usd / 400.0, 100_000.0)
    if chunk <= 0:
        raise ValueError("chunk must be positive")
    deployable = cfg.total_usd * (1.0 - cfg.idle_buffer_weight)
    curves = {m.unique_key: MarketCurve(m, cfg) for m in markets}
    amounts = {k: 0.0 for k in curves}
    by_key = {m.unique_key: m for m in markets}

    def local_cap(curve: MarketCurve) -> float:
        liquidity_cap = float("inf")
        if budget.min_market_exit_coverage > 0:
            liquidity_cap = (
                curve.market.state.liquidity / budget.min_market_exit_coverage
            )
        return min(
            curve.cap,
            budget.max_market_weight * cfg.total_usd,
            liquidity_cap,
        )

    local_caps = {key: local_cap(curve) for key, curve in curves.items()}
    family_amounts = {name: 0.0 for name in budget.family_caps}
    non_blue = 0.0
    remaining = deployable

    def position_revenue(k: str, amount: float) -> float:
        native = curves[k].revenue(amount)
        rewards = amount * by_key[k].state.reward_supply_apr * budget.reward_weight
        return native + rewards

    def marginal_revenue(k: str, amount: float, step: float) -> float:
        return (position_revenue(k, amount + step) - position_revenue(k, amount)) / step

    def stressed_liquidity(changes: dict[str, float] | None = None) -> float:
        """Idle plus positions covered by cash that preceded our deposit."""
        changes = changes or {}
        deployed_after = sum(amounts[k] + changes.get(k, 0.0) for k in amounts)
        total = cfg.total_usd - deployed_after
        for key, amount in amounts.items():
            amount += changes.get(key, 0.0)
            total += min(amount, by_key[key].state.liquidity)
        return total

    def admissible(k: str, step: float) -> bool:
        if amounts[k] + step > local_caps[k] + EPSILON:
            return False
        market = by_key[k]
        if market.tier != CollateralTier.BLUE_CHIP:
            if non_blue + step > budget.max_non_blue_weight * cfg.total_usd + EPSILON:
                return False
        family = risk_family(market)
        if family in budget.family_caps:
            if (
                family_amounts[family] + step
                > budget.family_caps[family] * cfg.total_usd + EPSILON
            ):
                return False
        if stressed_liquidity({k: step}) + EPSILON < (
            budget.min_stressed_liquidity_weight * cfg.total_usd
        ):
            return False
        return True

    def adjust(k: str, delta: float) -> None:
        nonlocal non_blue, remaining
        amounts[k] += delta
        remaining -= delta
        market = by_key[k]
        if market.tier != CollateralTier.BLUE_CHIP:
            non_blue += delta
        family = risk_family(market)
        if family in family_amounts:
            family_amounts[family] += delta

    def fill() -> None:
        while remaining > EPSILON:
            deployed = sum(amounts.values())
            required = min(budget.min_deployed_weight * cfg.total_usd, deployable)
            hurdle = (
                -float("inf") if deployed + EPSILON < required else cfg.idle_parking_apr
            )
            best_key, best_step, best_mr = None, 0.0, hurdle
            for k in curves:
                step = min(chunk, remaining) if amounts[k] > 0 else cfg.min_ticket
                if step > remaining + EPSILON or not admissible(k, step):
                    continue
                mr = marginal_revenue(k, amounts[k], step)
                if mr > best_mr:
                    best_key, best_step, best_mr = k, step, mr
            if best_key is None:
                break
            adjust(best_key, best_step)

    while sum(amount > 0 for amount in amounts.values()) < budget.min_funded_markets:
        candidates = []
        for k in curves:
            if amounts[k] > 0 or remaining + EPSILON < cfg.min_ticket:
                continue
            if not admissible(k, cfg.min_ticket):
                continue
            candidates.append((marginal_revenue(k, 0.0, cfg.min_ticket), k))
        if not candidates:
            break
        _, seed_key = max(candidates)
        adjust(seed_key, cfg.min_ticket)

    fill()

    # Refine the greedy fill across non-smooth minimum-ticket constraints.
    def swap_admissible(
        source: str,
        destination: str,
        step: float,
        *,
        allow_new: bool = False,
    ) -> bool:
        if source == destination or amounts[source] + EPSILON < step:
            return False
        source_after = amounts[source] - step
        if 0 < source_after < cfg.min_ticket - EPSILON:
            return False
        if amounts[destination] <= 0 and (
            not allow_new or step + EPSILON < cfg.min_ticket
        ):
            return False
        if amounts[destination] + step > local_caps[destination] + EPSILON:
            return False

        source_market = by_key[source]
        destination_market = by_key[destination]
        non_blue_after = non_blue
        if source_market.tier != CollateralTier.BLUE_CHIP:
            non_blue_after -= step
        if destination_market.tier != CollateralTier.BLUE_CHIP:
            non_blue_after += step
        if non_blue_after > budget.max_non_blue_weight * cfg.total_usd + EPSILON:
            return False

        family_after = dict(family_amounts)
        source_family = risk_family(source_market)
        destination_family = risk_family(destination_market)
        if source_family in family_after:
            family_after[source_family] -= step
        if destination_family in family_after:
            family_after[destination_family] += step
        for family, amount in family_after.items():
            if amount > budget.family_caps[family] * cfg.total_usd + EPSILON:
                return False

        stressed_after = stressed_liquidity({source: -step, destination: step})
        return stressed_after + EPSILON >= (
            budget.min_stressed_liquidity_weight * cfg.total_usd
        )

    def execute_swap(source: str, destination: str, step: float) -> None:
        adjust(source, -step)
        adjust(destination, step)

    for _ in range(len(amounts)):
        best_open: tuple[str, str] | None = None
        best_open_gain = EPSILON
        for destination, destination_amount in amounts.items():
            if destination_amount > 0:
                continue
            step = cfg.min_ticket
            for source, source_amount in amounts.items():
                if not swap_admissible(source, destination, step, allow_new=True):
                    continue
                gain = (
                    position_revenue(destination, step)
                    - position_revenue(destination, 0.0)
                    - position_revenue(source, source_amount)
                    + position_revenue(source, source_amount - step)
                )
                if gain > best_open_gain:
                    best_open_gain = gain
                    best_open = (source, destination)
        if best_open is None:
            break
        execute_swap(*best_open, cfg.min_ticket)

    for _ in range(MAX_SWAP_ITERATIONS):
        best_swap: tuple[str, str] | None = None
        best_revenue_gain = EPSILON
        for source, source_amount in amounts.items():
            if source_amount + EPSILON < chunk:
                continue
            source_loss = position_revenue(source, source_amount) - position_revenue(
                source, source_amount - chunk
            )
            for destination, destination_amount in amounts.items():
                if not swap_admissible(source, destination, chunk):
                    continue
                destination_gain = position_revenue(
                    destination, destination_amount + chunk
                ) - position_revenue(destination, destination_amount)
                gain = destination_gain - source_loss
                if gain > best_revenue_gain:
                    best_revenue_gain = gain
                    best_swap = (source, destination)
        if best_swap is None:
            break
        execute_swap(*best_swap, chunk)

    deployed = sum(amounts.values())
    native_revenue = sum(curves[k].revenue(a) for k, a in amounts.items())
    reward_revenue = sum(
        a * by_key[k].state.reward_supply_apr * budget.reward_weight
        for k, a in amounts.items()
    )
    gross_revenue = native_revenue + reward_revenue
    final_stressed_liquidity = stressed_liquidity()

    def binding_constraints(k: str, amount: float) -> list[str]:
        """Return constraints that block another allocation chunk."""
        if amount <= 0:
            return []
        market = by_key[k]
        constraints: list[str] = []
        if amount >= local_caps[k] - chunk:
            constraints.append("market")
        family = risk_family(market)
        if (
            family in budget.family_caps
            and family_amounts[family]
            >= budget.family_caps[family] * cfg.total_usd - chunk
        ):
            constraints.append(f"family:{family}")
        if (
            market.tier != CollateralTier.BLUE_CHIP
            and non_blue >= budget.max_non_blue_weight * cfg.total_usd - chunk
        ):
            constraints.append("non_blue")
        if (
            final_stressed_liquidity
            <= budget.min_stressed_liquidity_weight * cfg.total_usd + chunk
            and amount + chunk > market.state.liquidity
        ):
            constraints.append("portfolio_liquidity")
        return constraints

    diagnostics: dict[str, object] = {}
    for k, a in amounts.items():
        bindings = binding_constraints(k, a)
        diagnostics[k] = {
            "label": by_key[k].label,
            "amount_usd": a,
            "weight": a / cfg.total_usd,
            "projected_apr": curves[k].projected_apr(a),
            "reward_apr": by_key[k].state.reward_supply_apr * budget.reward_weight,
            "effective_projected_apr": (
                curves[k].projected_apr(a)
                + by_key[k].state.reward_supply_apr * budget.reward_weight
            ),
            "spot_supply_apy": by_key[k].state.supply_apy,
            "rate_calibration_source": curves[k].rate_calibration_source,
            "marginal_revenue": marginal_revenue(k, a, chunk),
            "risk_family": risk_family(by_key[k]),
            "binding_constraints": bindings,
            "capped": bool(bindings),
            "ownership_share": (
                a / (by_key[k].state.supply_assets + a) if a > 0 else 0.0
            ),
            "post_utilization": (
                by_key[k].state.borrow_assets
                / max(by_key[k].state.supply_assets + a, 1.0)
            ),
            "stressed_withdrawable_usd": min(a, by_key[k].state.liquidity),
            "exit_coverage": (min(a, by_key[k].state.liquidity) / a if a > 0 else 1.0),
            "hard_cap_usd": local_caps[k],
        }
    diagnostics.update(
        {
            "_idle_usd": cfg.total_usd - deployed,
            "_deployed_apr": gross_revenue / max(deployed, 1.0),
            "_native_projected_apr": native_revenue / cfg.total_usd,
            "_reward_projected_apr": reward_revenue / cfg.total_usd,
            "_non_blue_weight": non_blue / cfg.total_usd,
            "_family_weights": {
                name: amount / cfg.total_usd for name, amount in family_amounts.items()
            },
            "_stressed_liquidity_usd": final_stressed_liquidity,
            "_stressed_liquidity_weight": final_stressed_liquidity / cfg.total_usd,
            "_deployed_weight": deployed / cfg.total_usd,
        }
    )
    idle_income = (cfg.total_usd - deployed) * cfg.idle_parking_apr
    return Allocation(
        weights={k: a / cfg.total_usd for k, a in amounts.items()},
        amounts=amounts,
        projected_apr=(gross_revenue + idle_income) / cfg.total_usd,
        diagnostics=diagnostics,
    )
