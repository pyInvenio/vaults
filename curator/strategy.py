"""Minimal allocation-policy interface and historical comparison baselines."""

from __future__ import annotations

from .models import VaultConfig


class Strategy:
    """Given observable market state, return target USD amounts by market."""

    name = "base"

    def target(self, world: dict, day: float, cfg: VaultConfig) -> dict:
        raise NotImplementedError


class SpotApyChaser(Strategy):
    """Naive comparison: split NAV across the highest current supply rates."""

    def __init__(self, top_n: int = 2, period_days: float = 1.0):
        self.top_n, self.period_days = top_n, period_days
        self.name = f"spot-chaser(top{top_n})"
        self._last = -1e9
        self._target: dict = {}

    def target(self, world: dict, day: float, cfg: VaultConfig) -> dict:
        if day - self._last < self.period_days and self._target:
            return self._target
        self._last = day
        ranked = sorted(world, key=lambda key: world[key].supply_rate(), reverse=True)
        selected = ranked[: self.top_n]
        per_market = cfg.total_usd * (1 - cfg.idle_buffer_weight) / len(selected)
        self._target = {key: per_market if key in selected else 0.0 for key in world}
        return self._target
