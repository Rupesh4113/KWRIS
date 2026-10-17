"""Tests for Primary Validation Rules P1 through P5."""

import pandas as pd
import numpy as np
import pytest
from src.primary_validation import (
    run_p1_entry_check,
    run_p2_min_limit,
    run_p3_max_limit,
    run_p4_upper_warning,
    run_p5_dual_gauge_comparison,
    run_all_primary_validations
)


def test_p1_entry_check_duplicates_and_missing():
    data = [
        {"original_row_id": 0, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-01"), "rainfall_mm": 10.0},
        {"original_row_id": 1, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-01"), "rainfall_mm": 15.0}, # Duplicate date
        {"original_row_id": 2, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-02"), "rainfall_mm": np.nan}, # Missing
        {"original_row_id": 3, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-03"), "rainfall_mm": 0.0}, # Valid 0.0
    ]
    df = pd.DataFrame(data)
    flags = run_p1_entry_check(df, {})
    
    # Check duplicate flags and missing flag raised
    rule_ids = [f.rule_id for f in flags]
    assert all(r == "P1" for r in rule_ids)
    flag_types = [f.details.get("type") for f in flags]
    assert "duplicate_date" in flag_types
    assert "missing_value" in flag_types
    
    # Crucial test: Valid 0.0 mm must NOT raise a missing flag!
    zero_flags = [f for f in flags if f.date == pd.Timestamp("2024-01-03")]
    assert len(zero_flags) == 0


def test_p2_min_limit_negative_rainfall():
    data = [
        {"original_row_id": 0, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-01"), "rainfall_mm": -5.2},
        {"original_row_id": 1, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-02"), "rainfall_mm": 0.0},
        {"original_row_id": 2, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-03"), "rainfall_mm": 12.0},
    ]
    df = pd.DataFrame(data)
    flags = run_p2_min_limit(df, {"min_rainfall_mm": 0.0})
    
    assert len(flags) == 1
    assert flags[0].rule_id == "P2"
    assert flags[0].flag_direction == "-"
    assert flags[0].original_value == -5.2
    assert flags[0].severity == "critical"


def test_p3_max_limit_ceiling_exceeded():
    data = [
        {"original_row_id": 0, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-01"), "rainfall_mm": 250.0},
        {"original_row_id": 1, "station_id": "S1", "station_name": "Station 1", "date": pd.Timestamp("2024-01-02"), "rainfall_mm": 420.0}, # Exceeds 350 ceiling
    ]
    df = pd.DataFrame(data)
    flags = run_p3_max_limit(df, {"default_daily_max_mm": 350.0})
    
    assert len(flags) == 1
    assert flags[0].rule_id == "P3"
    assert flags[0].flag_direction == "+"
    assert flags[0].original_value == 420.0


def test_p4_upper_warning_level():
    # Create 30 days of synthetic rainfall in January
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    # 29 days with typical rainfall (0 to 15 mm), 1 day with 95 mm (spike below 350 ceiling but above warning level)
    rf_values = [0.0]*20 + [5.0, 10.0, 2.0, 8.0, 12.0, 4.0, 6.0, 15.0, 0.0] + [95.0]
    df = pd.DataFrame({
        "original_row_id": range(30),
        "station_id": ["S1"]*30,
        "station_name": ["Station 1"]*30,
        "date": dates,
        "rainfall_mm": rf_values
    })
    
    flags = run_p4_upper_warning(df, {"method": "normal_multiplier", "multiplier": 1.96, "min_sample_size": 15})
    assert len(flags) >= 1
    assert flags[0].rule_id == "P4"
    assert flags[0].flag_direction == "+"
    assert flags[0].original_value == 95.0


def test_p5_dual_gauge_comparison():
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    df = pd.DataFrame([
        # Day 1: 20 mm vs 20.5 mm (< 5% discrepancy -> should be ignored)
        {"station_name": "S1", "date": dates[0], "gauge_type": "manual", "rainfall_mm": 20.0},
        {"station_name": "S1", "date": dates[0], "gauge_type": "automatic", "rainfall_mm": 20.5},
        # Day 2: 10 mm vs 35 mm (> 5% discrepancy -> calibration or double count)
        {"station_name": "S1", "date": dates[1], "gauge_type": "manual", "rainfall_mm": 10.0},
        {"station_name": "S1", "date": dates[1], "gauge_type": "automatic", "rainfall_mm": 35.0},
        # Day 3: 50 mm vs 51 mm (< 5% discrepancy -> ignored)
        {"station_name": "S1", "date": dates[2], "gauge_type": "manual", "rainfall_mm": 50.0},
        {"station_name": "S1", "date": dates[2], "gauge_type": "automatic", "rainfall_mm": 51.0},
    ])
    
    flags = run_p5_dual_gauge_comparison(df, {"tolerance_pct": 5.0})
    assert len(flags) == 1
    assert flags[0].rule_id == "P5"
    assert flags[0].date == dates[1]
