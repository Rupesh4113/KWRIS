"""Tests for Gap Filling and Correction Engine Rules G1 through G8."""

import pandas as pd
import numpy as np
import pytest
from src.gap_filling import (
    propose_g4_split_accumulated_corrections,
    propose_g5_fill_from_neighbours,
    apply_approved_corrections
)
from src.models import ValidationFlag, CorrectionProposal, ReviewStatus


def test_g1_keep_missing_as_missing():
    # When no neighbours exist, a gap must remain NaN and NEVER be filled with 0.0
    df = pd.DataFrame([
        {"station_name": "Isolated_Stn", "date": pd.Timestamp("2024-01-01"), "rainfall_mm": np.nan}
    ])
    proposals = propose_g5_fill_from_neighbours(df, coords_map={}, config={})
    assert len(proposals) == 0  # No estimate can be generated


def test_g4_split_accumulated_totals_proportions_and_sum():
    coords_map = {
        "Target": (13.0, 77.0),
        "Neigh": (13.05, 77.05),
    }
    dates = [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    # Neighbours had 10 mm, 20 mm, 30 mm (sum = 60 mm)
    # Target had 0, 0, and accumulated spike of 120 mm
    df = pd.DataFrame([
        {"station_name": "Neigh", "date": dates[0], "rainfall_mm": 10.0},
        {"station_name": "Target", "date": dates[0], "rainfall_mm": 0.0},
        {"station_name": "Neigh", "date": dates[1], "rainfall_mm": 20.0},
        {"station_name": "Target", "date": dates[1], "rainfall_mm": 0.0},
        {"station_name": "Neigh", "date": dates[2], "rainfall_mm": 30.0},
        {"station_name": "Target", "date": dates[2], "rainfall_mm": 120.0},
    ])
    s4_flag = ValidationFlag(
        station_id="Target",
        station_name="Target",
        date=dates[2],
        rule_id="S4",
        original_value=120.0,
        details={"zero_period_dates": [dates[0], dates[1]]}
    )
    
    proposals = propose_g4_split_accumulated_corrections(df, [s4_flag], coords_map, {})
    assert len(proposals) == 3
    # Proportions: 10/60 = 1/6 (20 mm), 20/60 = 2/6 (40 mm), 30/60 = 3/6 (60 mm)
    vals = [p.proposed_value for p in proposals]
    assert vals[0] == 20.0
    assert vals[1] == 40.0
    assert vals[2] == 60.0
    # Crucial scientific criterion: Sum of split shares must equal original total exactly (120.0 mm)
    assert round(sum(vals), 2) == 120.0


def test_g5_fill_from_neighbours_normal_ratio():
    coords_map = {
        "Target": (13.0, 77.0),
        "Neigh1": (13.05, 77.05),
        "Neigh2": (13.05, 76.95),
        "Neigh3": (12.95, 77.00),
    }
    date = pd.Timestamp("2024-08-10")
    # Target normal ~ 800 mm, Neigh normal ~ 1200 mm (> 10% difference -> normal ratio)
    records = []
    # Seed historical years to establish normals
    for yr in [2021, 2022, 2023]:
        records.append({"station_name": "Target", "date": pd.Timestamp(f"{yr}-01-01"), "rainfall_mm": 800.0})
        for n in ["Neigh1", "Neigh2", "Neigh3"]:
            records.append({"station_name": n, "date": pd.Timestamp(f"{yr}-01-01"), "rainfall_mm": 1200.0})
            
    # The gap date
    records.append({"station_name": "Target", "date": date, "rainfall_mm": np.nan})
    records.append({"station_name": "Neigh1", "date": date, "rainfall_mm": 30.0})
    records.append({"station_name": "Neigh2", "date": date, "rainfall_mm": 30.0})
    records.append({"station_name": "Neigh3", "date": date, "rainfall_mm": 30.0})
    
    df = pd.DataFrame(records)
    proposals = propose_g5_fill_from_neighbours(df, coords_map, {"normal_diff_threshold_pct": 10.0})
    
    # Gap on target date should be filled via normal ratio:
    # 30 * (800 / 1200) = 30 * 2/3 = 20.0 mm
    target_prop = [p for p in proposals if p.station_name == "Target" and p.date == date]
    assert len(target_prop) == 1
    assert target_prop[0].proposed_value == 20.0
    assert "Normal-Ratio" in target_prop[0].method


def test_apply_approved_corrections_workflow():
    df = pd.DataFrame([
        {"station_name": "S1", "date": pd.Timestamp("2024-01-01"), "rainfall_mm": 50.0},
        {"station_name": "S1", "date": pd.Timestamp("2024-01-02"), "rainfall_mm": np.nan},
    ])
    proposals = [
        CorrectionProposal(
            proposal_id="P1",
            station_id="S1",
            station_name="S1",
            date=pd.Timestamp("2024-01-01"),
            original_value=50.0,
            proposed_value=25.0,
            rule_id="G3",
            method="Date Shift",
            reason="Corrected date lag",
            review_status=ReviewStatus.APPROVED
        ),
        CorrectionProposal(
            proposal_id="P2",
            station_id="S1",
            station_name="S1",
            date=pd.Timestamp("2024-01-02"),
            original_value=np.nan,
            proposed_value=18.5,
            rule_id="G5",
            method="IDW",
            reason="Filled from neighbours",
            review_status=ReviewStatus.PENDING # Still pending, should not be applied!
        )
    ]
    
    df_out = apply_approved_corrections(df, proposals)
    
    # Proposal 1 is approved -> corrected value 25.0, status 'corrected', original preserved as 50.0
    assert df_out.loc[0, "validated_rainfall_mm"] == 25.0
    assert df_out.loc[0, "rainfall_mm"] == 50.0
    assert df_out.loc[0, "is_corrected"] == True
    
    # Proposal 2 is pending -> remains NaN, NOT applied silently!
    assert np.isnan(df_out.loc[1, "validated_rainfall_mm"])
    assert df_out.loc[1, "is_completed"] == False
