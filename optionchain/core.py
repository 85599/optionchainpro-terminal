"""
Option-chain data access + analytics.

Pure Python (no Streamlit import) so every function here can be unit-tested.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests

IST = timezone(timedelta(hours=5, minutes=30))

ASSET_KEY = "NSE_INDEX|Nifty 50"
CHAIN_URL = "https://service.upstox.com/option-analytics-tool/open/v1/strategy-chains"
EXPIRY_URL = "https://service.upstox.com/instrument/v1/open/fnOUnderlierSymbolsWithExpiry"

# Nifty 50 F&O lot size, revised by NSE effective the Jan-2026 series (was 75).
NIFTY_LOT_SIZE = 65

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://upstox.com/",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Net cost of carry (risk-free rate minus dividend yield) used to turn the
# forward implied by put-call parity back into a spot estimate.
CARRY = 0.05

# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #

def fetch_option_chain(expiry: str, asset_key: str = ASSET_KEY, timeout: int = 15):
    """Return (chain_data, error). `expiry` is DD-MM-YYYY."""
    params = {"assetKey": asset_key, "strategyChainType": "PC_CHAIN", "expiry": expiry}
    try:
        r = requests.get(CHAIN_URL, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if "data" not in data:
            return None, "Unexpected response structure"
        return data["data"], None
    except requests.exceptions.RequestException as e:
        return None, str(e)


def fallback_expiries(today: Optional[date] = None, n: int = 10) -> list[str]:
    """Next `n` Tuesdays (Nifty weekly expiry day) as DD-MM-YYYY."""
    d = today or date.today()
    out: list[str] = []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() == 1:
            out.append(d.strftime("%d-%m-%Y"))
    return out


def fetch_expiries() -> list[str]:
    """Try Upstox's expiry list first; fall back to generated Tuesdays."""
    try:
        r = requests.get(EXPIRY_URL, params={"name": "nifty"}, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            lst = r.json().get("data", {}).get("symbolExpiryDataList", [])
            if lst:
                return sorted(lst[0].get("expiries", []))
    except Exception:
        pass
    return fallback_expiries()


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

_SIDE_FIELDS = {
    "LTP": ("marketData", "ltp"),
    "OI": ("marketData", "oi"),
    "Vol": ("marketData", "volume"),
    "Bid": ("marketData", "bidPrice"),
    "Ask": ("marketData", "askPrice"),
    "IV": ("analytics", "iv"),
    "Delta": ("analytics", "delta"),
    "Theta": ("analytics", "theta"),
    "Gamma": ("analytics", "gamma"),
    "Vega": ("analytics", "vega"),
    "PoP": ("analytics", "pop"),
}


def parse_chain(chain_data: dict) -> pd.DataFrame:
    """strategyChainData.strikeMap -> tidy DataFrame (one row per strike)."""
    strike_map = (chain_data.get("strategyChainData") or {}).get("strikeMap") or {}
    rows = []
    for strike_str, side in strike_map.items():
        row = {"Strike": float(strike_str)}
        for prefix, key in (("CE", "callOptionData"), ("PE", "putOptionData")):
            leg = side.get(key) or {}
            for name, (group, field) in _SIDE_FIELDS.items():
                row[f"{prefix}_{name}"] = (leg.get(group) or {}).get(field)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("Strike").reset_index(drop=True)
    for col in df.columns:
        if col != "Strike":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Total_OI"] = df["CE_OI"].fillna(0) + df["PE_OI"].fillna(0)
    return df


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #

def years_to_expiry(expiry: str, now: Optional[datetime] = None) -> Optional[float]:
    """Years from `now` to 15:30 IST on the expiry date (None if unparseable)."""
    d = None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(str(expiry), fmt).date()
            break
        except ValueError:
            continue
    if d is None:
        return None
    end = datetime.combine(d, dtime(15, 30), tzinfo=IST)
    now = now or datetime.now(IST)
    return max((end - now).total_seconds(), 0.0) / (365 * 86400)


# --------------------------------------------------------------------------- #
# Spot estimate
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SpotEstimate:
    value: float
    source: str


def find_spot_field(chain_data: dict) -> Optional[float]:
    """Look for a numeric 'spot'-like field anywhere in the first few levels of the response."""
    def walk(node, depth=0):
        if not isinstance(node, dict) or depth > 3:
            return None
        for k, v in node.items():
            name = str(k).lower()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                if "spot" in name or name in {"underlyingltp", "underlyingprice", "underlying_price"}:
                    return float(v)
        for v in node.values():
            hit = walk(v, depth + 1)
            if hit:
                return hit
        return None

    return walk(chain_data)


def estimate_spot(
    chain_data: dict,
    df: pd.DataFrame,
    years: Optional[float] = None,
    manual: float = 0.0,
) -> SpotEstimate:
    """
    Best available spot, in priority order:
      1. manual override
      2. a spot field present in the API response
      3. call-put parity:  F = K + C - P  at the strikes where C ~ P,  spot = F * exp(-carry * T)
      4. last resort: strike with the highest total OI near the middle (rough guess)
    """
    if manual and manual > 0:
        return SpotEstimate(float(manual), "manual override")

    api = find_spot_field(chain_data)
    if api:
        return SpotEstimate(api, "API field")

    both = df.dropna(subset=["CE_LTP", "PE_LTP"])
    both = both[(both["CE_LTP"] > 0) & (both["PE_LTP"] > 0)]
    if not both.empty:
        diff = both["CE_LTP"] - both["PE_LTP"]
        idx = diff.abs().nsmallest(3).index
        forward = float((both.loc[idx, "Strike"] + diff.loc[idx]).median())
        return SpotEstimate(forward * math.exp(-CARRY * (years or 0.0)), "call-put parity")

    mid = len(df) // 2
    window = df.iloc[max(0, mid - 15): mid + 15]
    strike = df.loc[window["Total_OI"].idxmax(), "Strike"] if not window.empty else df["Strike"].median()
    return SpotEstimate(float(strike), "max-OI guess")


def nearest_strike(df: pd.DataFrame, spot: float) -> float:
    return float(df.loc[(df["Strike"] - spot).abs().idxmin(), "Strike"])


def strike_step(df: pd.DataFrame) -> float:
    diffs = np.diff(np.sort(df["Strike"].to_numpy()))
    return float(np.median(diffs)) if len(diffs) else 50.0


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #

def pcr(df: pd.DataFrame) -> float:
    """Put/Call ratio by open interest (NaN if there is no call OI)."""
    ce = df["CE_OI"].fillna(0).sum()
    pe = df["PE_OI"].fillna(0).sum()
    return float(pe / ce) if ce > 0 else float("nan")


def max_pain(df: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """
    Strike at which the total payout to option *buyers* is smallest if the index
    settles there. Returns (strike, table of payouts per candidate strike).
    """
    d = df[["Strike", "CE_OI", "PE_OI"]].fillna(0)
    s = d["Strike"].to_numpy(dtype=float)
    ce = d["CE_OI"].to_numpy(dtype=float)
    pe = d["PE_OI"].to_numpy(dtype=float)
    k = s[:, None]
    call_pain = (np.maximum(k - s[None, :], 0.0) * ce[None, :]).sum(axis=1)
    put_pain = (np.maximum(s[None, :] - k, 0.0) * pe[None, :]).sum(axis=1)
    total = call_pain + put_pain
    table = pd.DataFrame({"Strike": s, "CE_Pain": call_pain, "PE_Pain": put_pain, "Total_Pain": total})
    return float(s[int(np.argmin(total))]), table


def support_resistance(df: pd.DataFrame, n: int = 3):
    """Top-n strikes by put OI (support) and by call OI (resistance)."""
    sup = df.nlargest(n, "PE_OI")[["Strike", "PE_OI"]]
    res = df.nlargest(n, "CE_OI")[["Strike", "CE_OI"]]
    return (
        [(float(a), float(b)) for a, b in zip(sup["Strike"], sup["PE_OI"])],
        [(float(a), float(b)) for a, b in zip(res["Strike"], res["CE_OI"])],
    )


def atm_straddle(df: pd.DataFrame, atm: float, spot: float) -> Optional[dict]:
    """ATM straddle price and the +/- range it implies (a common expected-move proxy)."""
    row = df[df["Strike"] == atm]
    if row.empty:
        return None
    c, p = row.iloc[0]["CE_LTP"], row.iloc[0]["PE_LTP"]
    if pd.isna(c) or pd.isna(p) or c <= 0 or p <= 0:
        return None
    s = float(c + p)
    return {"call": float(c), "put": float(p), "straddle": s,
            "lower": spot - s, "upper": spot + s, "pct": s / spot * 100}


def atm_iv(df: pd.DataFrame, atm: float) -> Optional[float]:
    row = df[df["Strike"] == atm]
    if row.empty:
        return None
    vals = [v for v in (row.iloc[0]["CE_IV"], row.iloc[0]["PE_IV"]) if pd.notna(v) and v > 0]
    return float(np.mean(vals)) if vals else None


def iv_skew(df: pd.DataFrame, atm: float, k: int = 5) -> Optional[float]:
    """IV of the OTM put k strikes below ATM minus IV of the OTM call k strikes above."""
    step = strike_step(df)
    put = df[df["Strike"] == atm - k * step]
    call = df[df["Strike"] == atm + k * step]
    if put.empty or call.empty:
        return None
    p, c = put.iloc[0]["PE_IV"], call.iloc[0]["CE_IV"]
    if pd.isna(p) or pd.isna(c):
        return None
    return float(p - c)


# --------------------------------------------------------------------------- #
# Formatting (Indian units; prices are never abbreviated)
# --------------------------------------------------------------------------- #

def fmt_compact(x, decimals: int = 2) -> str:
    """Quantities such as OI / volume: 1.5K, 1.50L (lakh), 2.50Cr (crore)."""
    if x is None or pd.isna(x):
        return "—"
    a = abs(x)
    if a >= 1e7:
        return f"{x / 1e7:.2f}Cr"
    if a >= 1e5:
        return f"{x / 1e5:.2f}L"
    if a >= 1e3:
        return f"{x / 1e3:.1f}K"
    return f"{x:.{decimals}f}"


def fmt_price(x, decimals: int = 2) -> str:
    """Prices are shown in full, never abbreviated."""
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.{decimals}f}"


def fmt_num(x, decimals: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:.{decimals}f}"
