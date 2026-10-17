"""Tests for Statistical Analysis and Aggregation Rules A1 through A6."""

import pandas as pd
import numpy as np
import pytest
from src.statistics import (
    aggregate_weekly_standard,
    aggregate_ten_daily_dekad,
    compute_station_monthly_statistics,
    compute_station_yearly_statistics,
    perform_a5_consistency_tests
)


def test_a1_weekly_standard_leap_and_non_leap():
    # 2024 is a leap year (366 days)
    leap_dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    df_leap = pd.DataFrame({"date": leap_dates, "rainfall_mm": [2.0]*len(leap_dates)})
    w_leap = aggregate_weekly_standard(df_leap)
    assert len(w_leap) == 52
    assert w_leap.iloc[0]["expected_days"] == 7
    # Week 52 in a leap year must have 9 days
    assert w_leap.iloc[51]["expected_days"] == 9
    
    # 2023 is a non-leap year (365 days)
    non_leap_dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    df_non_leap = pd.DataFrame({"date": non_leap_dates, "rainfall_mm": [2.0]*len(non_leap_dates)})
    w_non_leap = aggregate_weekly_standard(df_non_leap)
    assert len(w_non_leap) == 52
    # Week 52 in non-leap year must have 8 days
    assert w_non_leap.iloc[51]["expected_days"] == 8


def test_a1_ten_daily_dekad_lengths():
    # Test January (31 days) and February 2024 (29 days)
    dates = pd.date_range("2024-01-01", "2024-02-29", freq="D")
    df = pd.DataFrame({"date": dates, "rainfall_mm": [5.0]*len(dates)})
    dekads = aggregate_ten_daily_dekad(df)
    
    # Jan Dekad 1: 10 days, Dekad 2: 10 days, Dekad 3: 11 days (31 - 20)
    jan_d = dekads[dekads["month"] == 1]
    assert jan_d.iloc[0]["days_in_dekad"] == 10
    assert jan_d.iloc[1]["days_in_dekad"] == 10
    assert jan_d.iloc[2]["days_in_dekad"] == 11
    
    # Feb 2024 Dekad 3: 9 days (29 - 20)
    feb_d = dekads[dekads["month"] == 2]
    assert feb_d.iloc[2]["days_in_dekad"] == 9


def test_a3_completeness_rule_flagging():
    # Month with 31 days, but only 20 days measured (64.5% complete < 90%)
    dates = pd.date_range("2024-01-01", periods=31, freq="D")
    rf_vals = [10.0]*20 + [np.nan]*11
    df = pd.DataFrame({
        "station_name": ["Stn1"]*31,
        "date": dates,
        "rainfall_mm": rf_vals
    })
    
    m_stats = compute_station_monthly_statistics(df, completeness_min_pct=90.0)
    assert len(m_stats) == 1
    assert m_stats.iloc[0]["is_complete"] == False
    assert m_stats.iloc[0]["completeness_pct"] < 90.0


def test_a5_consistency_tests():
    # 20 years of data: first 10 years around 1000 mm, next 10 years around 500 mm (abrupt shift)
    years = list(range(2000, 2020))
    ann_vals = [1000.0 + np.random.normal(0, 50) for _ in range(10)] + [500.0 + np.random.normal(0, 50) for _ in range(10)]
    series = pd.Series(ann_vals, index=years)
    
    res = perform_a5_consistency_tests(series)
    assert res["status"] == "tested"
    assert res["is_statistically_significant_shift"] == True
    assert res["mann_whitney_pvalue"] < 0.05
