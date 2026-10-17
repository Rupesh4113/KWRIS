"""Tests for Secondary Validation Rules S1 through S8."""

import pandas as pd
import numpy as np
import pytest
from src.secondary_validation import (
    run_s1_neighbour_selection,
    run_s2_neighbour_estimate_test,
    run_s3_wrong_day_check,
    run_s4_accumulated_totals_check,
    run_s5_missed_entries_check,
    run_s6_rainy_days_check,
    run_s7_monthly_yearly_totals,
    run_s8_double_mass_check,
    calculate_idw_estimate
)


def test_idw_estimate_math():
    # 2 neighbours: 10 km away with 20 mm, 20 km away with 40 mm
    # weights: 1/100 = 0.01, 1/400 = 0.0025
    # total weight: 0.0125
    # estimate: (0.01*20 + 0.0025*40) / 0.0125 = (0.2 + 0.1) / 0.0125 = 0.3 / 0.0125 = 24.0 mm
    est, std = calculate_idw_estimate([20.0, 40.0], [10.0, 20.0], power=2.0)
    assert round(est, 1) == 24.0


def test_s1_neighbour_selection_quadrants():
    # Target station at (13.0, 77.0)
    # Create 3 NE candidates, 1 SE candidate
    coords_map = {
        "Target": (13.0, 77.0),
        "NE_Close": (13.05, 77.05),     # dist ~ 7.6 km, NE
        "NE_Mid": (13.10, 77.10),       # dist ~ 15.3 km, NE
        "NE_Far": (13.15, 77.15),       # dist ~ 23.0 km, NE
        "SE_Station": (12.90, 77.10),   # dist ~ 15.5 km, SE
        "Outside": (15.0, 78.0)         # > 200 km away
    }
    all_stns = list(coords_map.keys())
    selected = run_s1_neighbour_selection("Target", all_stns, coords_map, {
        "max_neighbours": 8, "max_per_quadrant": 2, "search_radius_km": 35.0
    })
    
    # NE has 3 candidates within radius, but max 2 per quadrant allowed
    ne_selected = [s for s in selected if s["quadrant"] == "NE"]
    assert len(ne_selected) == 2
    assert "NE_Close" in [s["station"] for s in ne_selected]
    assert "NE_Mid" in [s["station"] for s in ne_selected]
    # Outside station must not be selected
    assert "Outside" not in [s["station"] for s in selected]


def test_s2_neighbour_estimate_discrepancy():
    coords_map = {
        "Stn_Target": (13.0, 77.0),
        "Stn_Neigh1": (13.05, 77.05),
        "Stn_Neigh2": (13.05, 76.95),
    }
    date = pd.Timestamp("2024-05-15")
    df = pd.DataFrame([
        # Neighbours have 10 mm and 12 mm rain
        {"station_name": "Stn_Neigh1", "date": date, "rainfall_mm": 10.0},
        {"station_name": "Stn_Neigh2", "date": date, "rainfall_mm": 12.0},
        # Target station has 85 mm rain (discrepancy > 45 mm)
        {"station_name": "Stn_Target", "date": date, "rainfall_mm": 85.0},
    ])
    
    flags, est_df = run_s2_neighbour_estimate_test(df, coords_map, {"absolute_diff_limit_mm": 45.0, "std_multiplier": 2.0})
    target_flags = [f for f in flags if f.station_name == "Stn_Target"]
    assert len(target_flags) == 1
    assert target_flags[0].rule_id == "S2"
    assert target_flags[0].flag_direction == "+"
    assert target_flags[0].original_value == 85.0


def test_s4_accumulated_totals():
    coords_map = {
        "Target": (13.0, 77.0),
        "Neigh": (13.05, 77.05),
    }
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    records = []
    # 5 dry days, then 3 rainy days where neighbour had rain and Target had 0, then Target spiked to 65 mm on day 9
    for i, d in enumerate(dates):
        if i in [5, 6, 7]:
            records.append({"station_name": "Neigh", "date": d, "rainfall_mm": 20.0})
            records.append({"station_name": "Target", "date": d, "rainfall_mm": 0.0})
        elif i == 8:
            records.append({"station_name": "Neigh", "date": d, "rainfall_mm": 5.0})
            records.append({"station_name": "Target", "date": d, "rainfall_mm": 65.0}) # Spike
        else:
            records.append({"station_name": "Neigh", "date": d, "rainfall_mm": 0.0})
            records.append({"station_name": "Target", "date": d, "rainfall_mm": 0.0})
            
    df = pd.DataFrame(records)
    flags = run_s4_accumulated_totals_check(df, [], coords_map, {})
    assert len(flags) == 1
    assert flags[0].rule_id == "S4"
    assert flags[0].date == dates[8]
    assert flags[0].original_value == 65.0


def test_s6_rainy_days_check():
    coords_map = {
        "Target": (13.0, 77.0),
        "Neigh1": (13.05, 77.05),
        "Neigh2": (13.05, 76.95),
    }
    dates = pd.date_range("2024-07-01", periods=31, freq="D")
    records = []
    for d in dates:
        # Neighbours had 15 rainy days
        is_rainy = (d.day % 2 == 0)
        records.append({"station_name": "Neigh1", "date": d, "rainfall_mm": 10.0 if is_rainy else 0.0})
        records.append({"station_name": "Neigh2", "date": d, "rainfall_mm": 12.0 if is_rainy else 0.0})
        # Target recorded rain on only 2 days (skipping light rain)
        records.append({"station_name": "Target", "date": d, "rainfall_mm": 25.0 if d.day in [10, 20] else 0.0})
        
    df = pd.DataFrame(records)
    flags = run_s6_rainy_days_check(df, coords_map, {"min_rain_threshold_mm": 0.1, "tolerance_ratio": 0.5})
    assert len(flags) == 1
    assert flags[0].rule_id == "S6"
    assert flags[0].flag_direction == "-"
