import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from optionchain import core


def make_df(rows):
    """rows: list of dict with Strike, CE_LTP, PE_LTP, CE_OI, PE_OI (others default NaN)."""
    cols = ["Strike", "CE_LTP", "CE_OI", "CE_Vol", "CE_IV", "CE_Delta", "CE_Theta", "CE_Gamma", "CE_Vega", "CE_PoP",
            "PE_LTP", "PE_OI", "PE_Vol", "PE_IV", "PE_Delta", "PE_Theta", "PE_Gamma", "PE_Vega", "PE_PoP"]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    df["Total_OI"] = df["CE_OI"].fillna(0) + df["PE_OI"].fillna(0)
    return df.sort_values("Strike").reset_index(drop=True)


# --------------------------------------------------------------------------- #
# parse_chain
# --------------------------------------------------------------------------- #

def test_parse_chain_basic():
    raw = {
        "strategyChainData": {
            "strikeMap": {
                "24500": {
                    "callOptionData": {"marketData": {"ltp": 120.5, "oi": 1000, "volume": 500},
                                        "analytics": {"iv": 15.2, "delta": 0.55}},
                    "putOptionData": {"marketData": {"ltp": 90.0, "oi": 800, "volume": 400},
                                       "analytics": {"iv": 14.8, "delta": -0.45}},
                },
                "24600": {
                    "callOptionData": {"marketData": {"ltp": 80.0, "oi": 1200},
                                        "analytics": {"iv": 15.0}},
                    "putOptionData": {"marketData": {"ltp": 130.0, "oi": 900},
                                       "analytics": {"iv": 15.1}},
                },
            }
        }
    }
    df = core.parse_chain(raw)
    assert list(df["Strike"]) == [24500.0, 24600.0]
    assert df.loc[0, "CE_LTP"] == 120.5
    assert df.loc[0, "PE_OI"] == 800
    assert df.loc[1, "CE_IV"] == 15.0
    assert df["Total_OI"].tolist() == [1800.0, 2100.0]


def test_parse_chain_missing_fields_become_nan():
    raw = {"strategyChainData": {"strikeMap": {"100": {"callOptionData": {}, "putOptionData": {}}}}}
    df = core.parse_chain(raw)
    assert pd.isna(df.loc[0, "CE_LTP"])
    assert pd.isna(df.loc[0, "PE_OI"])


def test_parse_chain_empty():
    df = core.parse_chain({"strategyChainData": {"strikeMap": {}}})
    assert df.empty


# --------------------------------------------------------------------------- #
# spot estimate — this is the bug the user reported (max-OI guess landing on
# a round number instead of tracking real spot)
# --------------------------------------------------------------------------- #

def test_spot_manual_override_wins():
    df = make_df([{"Strike": 100, "CE_LTP": 5, "PE_LTP": 5, "CE_OI": 1, "PE_OI": 1}])
    est = core.estimate_spot({}, df, manual=99999)
    assert est.value == 99999
    assert est.source == "manual override"


def test_spot_api_field_detected():
    chain = {"strategyChainData": {"underlyingSpotPrice": 24123.45, "strikeMap": {}}}
    df = make_df([{"Strike": 100, "CE_LTP": 5, "PE_LTP": 5}])
    est = core.estimate_spot(chain, df)
    assert est.source == "API field"
    assert est.value == pytest.approx(24123.45)


def test_spot_call_put_parity_tracks_real_spot_not_max_oi_strike():
    """
    Regression test for the reported bug: spot must follow put-call parity,
    not just the strike with the largest total OI (which is often a round
    number far from the real underlying price).
    """
    true_spot = 22930.0
    rows = []
    for k in range(22500, 23500, 50):
        intrinsic_c = max(true_spot - k, 0)
        intrinsic_p = max(k - true_spot, 0)
        time_value = 25 * math.exp(-((k - true_spot) / 300) ** 2)
        ce_ltp = intrinsic_c + time_value
        pe_ltp = intrinsic_p + time_value
        # Deliberately put the *largest* OI at a far, round strike (24000) —
        # the old max-OI heuristic would report 24000 here.
        ce_oi = 5_000_000 if k == 24000 else 10_000
        pe_oi = 5_000_000 if k == 24000 else 10_000
        rows.append({"Strike": k, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, "CE_OI": ce_oi, "PE_OI": pe_oi})
    # extend range so 24000 actually exists in the strike list
    for k in range(23500, 24050, 50):
        rows.append({"Strike": k, "CE_LTP": 0.05, "PE_LTP": max(k - true_spot, 0.05),
                     "CE_OI": (5_000_000 if k == 24000 else 10_000),
                     "PE_OI": (5_000_000 if k == 24000 else 10_000)})
    df = make_df(rows)
    est = core.estimate_spot({}, df, years=0.0)
    assert est.source == "call-put parity"
    assert est.value == pytest.approx(true_spot, abs=100)
    assert abs(est.value - 24000) > 500   # must NOT collapse to the big-OI round strike


def test_spot_falls_back_to_max_oi_when_no_prices():
    rows = [{"Strike": k, "CE_OI": (100 if k != 24000 else 99999), "PE_OI": 10} for k in range(23800, 24200, 50)]
    df = make_df(rows)
    est = core.estimate_spot({}, df)
    assert est.source == "max-OI guess"
    assert est.value == 24000


# --------------------------------------------------------------------------- #
# nearest_strike / strike_step
# --------------------------------------------------------------------------- #

def test_nearest_strike():
    df = make_df([{"Strike": k} for k in (24000, 24050, 24100)])
    assert core.nearest_strike(df, 24063) == 24050

def test_strike_step():
    df = make_df([{"Strike": k} for k in (100, 150, 200, 250)])
    assert core.strike_step(df) == 50


# --------------------------------------------------------------------------- #
# pcr
# --------------------------------------------------------------------------- #

def test_pcr_basic():
    df = make_df([{"Strike": 1, "CE_OI": 100, "PE_OI": 150}, {"Strike": 2, "CE_OI": 100, "PE_OI": 50}])
    assert core.pcr(df) == pytest.approx(1.0)

def test_pcr_no_call_oi_is_nan():
    df = make_df([{"Strike": 1, "CE_OI": 0, "PE_OI": 50}])
    assert math.isnan(core.pcr(df))


# --------------------------------------------------------------------------- #
# max_pain
# --------------------------------------------------------------------------- #

def test_max_pain_single_dominant_strike():
    # All OI concentrated at strike 200 -> max pain must be 200
    rows = [{"Strike": k, "CE_OI": 0, "PE_OI": 0} for k in (100, 150, 200, 250, 300)]
    rows[2]["CE_OI"] = 1000
    rows[2]["PE_OI"] = 1000
    df = make_df(rows)
    strike, table = core.max_pain(df)
    assert strike == 200
    assert len(table) == 5

def test_max_pain_symmetric_two_strikes():
    rows = [{"Strike": 100, "CE_OI": 100, "PE_OI": 0}, {"Strike": 200, "CE_OI": 0, "PE_OI": 100}]
    df = make_df(rows)
    strike, _ = core.max_pain(df)
    assert strike in (100, 200)  # symmetric payoff -> pain equal at both ends by construction


# --------------------------------------------------------------------------- #
# support_resistance
# --------------------------------------------------------------------------- #

def test_support_resistance():
    rows = [{"Strike": 100, "CE_OI": 50, "PE_OI": 500}, {"Strike": 200, "CE_OI": 900, "PE_OI": 20},
            {"Strike": 300, "CE_OI": 10, "PE_OI": 10}]
    df = make_df(rows)
    sup, res = core.support_resistance(df, n=1)
    assert sup == [(100.0, 500.0)]
    assert res == [(200.0, 900.0)]


# --------------------------------------------------------------------------- #
# straddle / IV
# --------------------------------------------------------------------------- #

def test_atm_straddle():
    df = make_df([{"Strike": 100, "CE_LTP": 10, "PE_LTP": 8}])
    r = core.atm_straddle(df, atm=100, spot=100)
    assert r["straddle"] == 18
    assert r["lower"] == 82
    assert r["upper"] == 118

def test_atm_straddle_missing_prices_returns_none():
    df = make_df([{"Strike": 100, "CE_LTP": np.nan, "PE_LTP": 8}])
    assert core.atm_straddle(df, atm=100, spot=100) is None

def test_atm_iv_average():
    df = make_df([{"Strike": 100, "CE_IV": 15, "PE_IV": 17}])
    assert core.atm_iv(df, 100) == pytest.approx(16.0)


# --------------------------------------------------------------------------- #
# formatting — prices must stay full precision, only OI/volume compacts
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("x,expected", [
    (500, "500.00"), (1500, "1.5K"), (150000, "1.50L"), (25000000, "2.50Cr"), (None, "—"),
])
def test_fmt_compact(x, expected):
    assert core.fmt_compact(x) == expected

def test_fmt_price_never_abbreviates():
    assert core.fmt_price(1234567.891) == "1,234,567.89"

def test_fmt_price_nan():
    assert core.fmt_price(float("nan")) == "—"


# --------------------------------------------------------------------------- #
# years_to_expiry
# --------------------------------------------------------------------------- #

def test_years_to_expiry_future():
    from datetime import datetime
    now = datetime(2026, 1, 1, 10, 0, tzinfo=core.IST)
    y = core.years_to_expiry("08-01-2026", now=now)
    assert 0 < y < 0.03

def test_years_to_expiry_past_clips_to_zero():
    from datetime import datetime
    now = datetime(2026, 1, 10, 10, 0, tzinfo=core.IST)
    y = core.years_to_expiry("01-01-2026", now=now)
    assert y == 0.0

def test_years_to_expiry_bad_format():
    assert core.years_to_expiry("not-a-date") is None


# --------------------------------------------------------------------------- #
# fallback_expiries
# --------------------------------------------------------------------------- #

def test_fallback_expiries_are_tuesdays():
    from datetime import date
    exps = core.fallback_expiries(today=date(2026, 1, 1), n=4)  # Jan 1 2026 is a Thursday
    assert len(exps) == 4
    from datetime import datetime
    for e in exps:
        d = datetime.strptime(e, "%d-%m-%Y").date()
        assert d.weekday() == 1
