"""Morpho GraphQL client and verified snapshot loader."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from .market_metadata import MarketMeta, lookup
from .models import Market, MarketState, RateHistory

API_URL = "https://api.morpho.org/graphql"
USDC_MAINNET = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
SECONDS_PER_YEAR = 365 * 24 * 60 * 60

MARKETS_QUERY = (
    """
query UsdcMarkets($first: Int!, $skip: Int!) {
  markets(
    first: $first
    skip: $skip
    orderBy: SupplyAssetsUsd
    orderDirection: Desc
    where: { chainId_in: [1], loanAssetAddress_in: ["%s"], listed: true }
  ) {
    items {
      uniqueKey: marketId
      lltv
      whitelisted: listed
      loanAsset { symbol decimals }
      collateralAsset { symbol address }
      irmAddress
      oracle {
        address
        type
        data {
          ... on MorphoChainlinkOracleData {
            baseFeedOne { address }
            baseFeedTwo { address }
            baseOracleVault { address }
            quoteFeedOne { address }
            quoteFeedTwo { address }
            scaleFactor
            vaultConversionSample
          }
          ... on MorphoChainlinkOracleV2Data {
            baseFeedOne { address }
            baseFeedTwo { address }
            baseOracleVault { address }
            baseVaultConversionSample
            quoteFeedOne { address }
            quoteFeedTwo { address }
            quoteOracleVault { address }
            quoteVaultConversionSample
            scaleFactor
          }
        }
      }
      state {
        supplyAssetsUsd
        borrowAssetsUsd
        liquidityAssetsUsd
        supplyApy
        borrowApy
        utilization
        fee
        rateAtUTarget: rateAtTarget
        timestamp
        rewards { supplyApr }
      }
      dailyApys { supplyApy }
      monthlyApys { supplyApy }
    }
    pageInfo { count countTotal }
  }
}
"""
    % USDC_MAINNET
)


def _post(query: str, variables: dict[str, object], timeout: float = 30.0) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "curator-takehome/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read())
    if "errors" in out:
        raise RuntimeError(f"GraphQL errors: {out['errors']}")
    return out["data"]


VAULT_ALLOCATIONS_QUERY = """
query VaultAllocations($first: Int!, $skip: Int!) {
  vaults(
    first: $first
    skip: $skip
    orderBy: TotalAssetsUsd
    orderDirection: Desc
    where: { chainId_in: [1], listed: true }
  ) {
    items {
      address
      name
      state {
        totalAssetsUsd
        allocation { market { marketId } supplyAssetsUsd }
      }
    }
    pageInfo { count countTotal }
  }
}
"""


def fetch_usdc_markets(
    max_pages: int | None = None, page_size: int = 100
) -> list[dict]:
    """Fetch all listed mainnet USDC-loan markets, largest first."""
    items: list[dict] = []
    page = 0
    while max_pages is None or page < max_pages:
        data = _post(MARKETS_QUERY, {"first": page_size, "skip": page * page_size})
        chunk = data["markets"]["items"]
        items.extend(chunk)
        total = int(data["markets"]["pageInfo"]["countTotal"])
        if len(items) >= total or len(chunk) < page_size:
            break
        page += 1
    return items


def attach_curated_shares(
    items: list[dict],
    max_pages: int = 2,
    page_size: int = 100,
    exclude_vaults: tuple[str, ...] = (),
) -> list[dict]:
    """Add each market's curated-vault supply share on a best-effort basis."""
    try:
        curated: dict[str, float] = {}
        excluded = {address.lower() for address in exclude_vaults}
        for page in range(max_pages):
            data = _post(
                VAULT_ALLOCATIONS_QUERY,
                {"first": page_size, "skip": page * page_size},
            )
            vaults = data["vaults"]["items"]
            for vault in vaults:
                if (vault.get("address") or "").lower() in excluded:
                    continue
                allocations = (vault.get("state") or {}).get("allocation") or []
                for alloc in allocations:
                    market = alloc.get("market") or {}
                    key = market.get("marketId") or market.get("uniqueKey")
                    usd = float(alloc.get("supplyAssetsUsd") or 0.0)
                    if key and usd > 0:
                        curated[key] = curated.get(key, 0.0) + usd
            if len(vaults) < page_size:
                break
        for item in items:
            supply = float((item.get("state") or {}).get("supplyAssetsUsd") or 0.0)
            if supply > 0 and item["uniqueKey"] in curated:
                item["curatedVaultShare"] = min(
                    curated[item["uniqueKey"]] / supply,
                    1.0,
                )
    except Exception:
        pass
    return items


def save_snapshot(items: list[dict], path: str | Path) -> None:
    payload = {
        "fetched_at": int(time.time()),
        "source": API_URL,
        "chain_id": 1,
        "loan_asset": USDC_MAINNET,
        "data_quality": "morpho_api",
        "items": items,
    }
    with open(path, "w", encoding="utf-8") as snapshot_file:
        json.dump(payload, snapshot_file, indent=1)


def load_snapshot(path: str | Path, require_verified: bool = True) -> list[dict]:
    with open(path, encoding="utf-8") as snapshot_file:
        payload = json.load(snapshot_file)
    if require_verified and payload.get("data_quality") != "morpho_api":
        raise ValueError(
            f"{path} is not a verified Morpho API snapshot; "
            "refusing reconstructed or estimated market data"
        )
    items = payload["items"]
    for item in items:
        market_id = item.get("uniqueKey", "")
        if (
            not market_id.startswith("0x")
            or len(market_id) != 66
            or item.get("_estimated")
        ):
            raise ValueError(f"unverified market record in {path}: {market_id!r}")
    return items


def _avg_apy(block: dict | None) -> float | None:
    if isinstance(block, dict):
        return block.get("supplyApy")
    return None


def _annual_rate_at_target(value: object) -> float | None:
    """Normalize the API's on-chain per-second WAD into annual APR.

    ``rateAtTarget`` is exposed as the raw AdaptiveCurveIRM value (WAD per
    second), unlike ``supplyApy`` and ``borrowApy`` which are annual decimal
    rates. Older cached fixtures used an annual decimal directly, so retain
    that representation when the value is already below one.
    """
    if value in (None, ""):
        return None
    rate = float(value)
    if rate >= 1.0:
        rate = rate * SECONDS_PER_YEAR / 1e18
    if not 0.0 < rate <= 2.0:
        raise ValueError(f"invalid annualized rateAtTarget: {rate}")
    return rate


def to_markets(items: list[dict]) -> list[Market]:
    """Raw API items -> Market objects with curator metadata attached."""
    markets: list[Market] = []
    for item in items:
        coll = (item.get("collateralAsset") or {}).get("symbol")
        if coll is None:
            continue
        st = item["state"]
        supply = float(st["supplyAssetsUsd"] or 0.0)
        borrow = float(st["borrowAssetsUsd"] or 0.0)
        meta: MarketMeta = lookup(item["uniqueKey"], coll)
        rewards = st.get("rewards") or []
        reward_apr = sum(float(r.get("supplyApr") or 0.0) for r in rewards)
        pt_maturity_days = meta.pt_maturity_days
        if meta.pt_maturity_timestamp is not None and st.get("timestamp") is not None:
            pt_maturity_days = max(
                0.0,
                (meta.pt_maturity_timestamp - int(st["timestamp"])) / 86_400.0,
            )
        market = Market(
            unique_key=item["uniqueKey"],
            collateral_symbol=coll,
            loan_symbol=item["loanAsset"]["symbol"],
            lltv=(
                float(item["lltv"]) / 1e18
                if float(item["lltv"]) > 10
                else float(item["lltv"])
            ),
            state=MarketState(
                supply_assets=supply,
                borrow_assets=borrow,
                supply_apy=float(st["supplyApy"] or 0.0),
                borrow_apy=float(st["borrowApy"] or 0.0),
                utilization=float(
                    st["utilization"] or (borrow / supply if supply else 0.0)
                ),
                rate_at_target=_annual_rate_at_target(
                    st.get("rateAtUTarget", st.get("rateAtTarget"))
                ),
                fee=float(st.get("fee") or 0.0),
                reward_supply_apr=reward_apr,
                timestamp=st.get("timestamp"),
                curated_vault_share=item.get("curatedVaultShare"),
            ),
            history=RateHistory(
                daily=_avg_apy(item.get("dailyApys")),
                weekly=_avg_apy(item.get("weeklyApys")),
                monthly=_avg_apy(item.get("monthlyApys")),
                quarterly=_avg_apy(item.get("quarterlyApys")),
            ),
            tier=meta.tier,
            oracle_note=meta.oracle_note,
            whitelisted=bool(item.get("whitelisted", True)),
            pt_maturity_days=pt_maturity_days,
            notes=meta.notes,
        )
        markets.append(market)
    return markets
