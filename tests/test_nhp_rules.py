"""Automated Unit & Integration Tests for NHP Rainfall Validation Rules (P1-P5, S1-S8, G1-G6).

Verifies implementation against the National Hydrology Project (NHP, May 2019) Manual:
- P1-P5: Primary data validation
- S1-S8: Secondary spatial and consistency validation
- G1-G6: Missing-data estimation hierarchy and guardrails
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime

from src.configuration import ValidationThresholds, IssueSeverity
from src.data_validation import DataQualityValidator
from src.anomaly_detection import AnomalyDetector
from src.secondary_validation import (
    SecondaryQualityValidator,
    select_quadrant_neighbours,
    calculate_bearing_degrees,
    assign_quadrant,
    haversine_km
)
from src.missing_value_prediction import (
    MissingRainfallPredictor,
    estimate_annual_normals
)


# =============================================================================
# 1. PRIMARY VALIDATION TESTS (P1 - P5)
# =============================================================================

def test_p1_entry_and_date_check():
    """Verify Rule P1: Detects invalid/missing dates and duplicate records."""
    df = pd.DataFrame({
        "station_id": ["STN_01", "STN_01", "STN_01"],
        "date": [pd.NaT, pd.Timestamp("2024-07-01"), pd.Timestamp("2024-07-01")],
        "rainfall": [10.0, 15.0, 25.0],
        "original_rainfall": ["10.0", "15.0", "25.0"]
    })
    validator = DataQualityValidator()
    issues, _ = validator.validate(df)

    assert not issues.empty
    rules = issues["validation_rule"].values
    assert "V_INVALID_DATE" in rules
    assert "V_DUPLICATE_RECORD" in rules


def test_p2_minimum_limit_check():
    """Verify Rule P2: Flags negative rainfall (< 0.0 mm) as Critical."""
    df = pd.DataFrame({
        "station_id": ["STN_01"],
        "date": [pd.Timestamp("2024-07-01")],
        "rainfall": [-15.0],
        "original_rainfall": ["-15.0"]
    })
    validator = DataQualityValidator()
    issues, _ = validator.validate(df)

    assert not issues.empty
    row = issues.iloc[0]
    assert row["validation_rule"] == "V_NEGATIVE_VALUE"
    assert row["severity"] == IssueSeverity.CRITICAL.value


def test_p3_maximum_limit_ceiling():
    """Verify Rule P3: Flags values exceeding regional physical ceiling (400 mm)."""
    df = pd.DataFrame({
        "station_id": ["STN_01"],
        "date": [pd.Timestamp("2024-07-01")],
        "rainfall": [485.0],
        "original_rainfall": [485.0]
    })
    detector = AnomalyDetector()
    issues, summary = detector.detect_anomalies(df)

    assert not issues.empty
    row = issues.iloc[0]
    assert row["validation_rule"] == "A_DOMAIN_CEILING"
    assert row["severity"] == IssueSeverity.CRITICAL.value
    assert summary["extreme_ceilings"] == 1


def test_p4_upper_warning_level_preservation():
    """Verify Rule P4: Extreme values (200-400 mm) flagged as Warning, not deleted."""
    df = pd.DataFrame({
        "station_id": ["STN_01"],
        "date": [pd.Timestamp("2024-07-01")],
        "rainfall": [275.0],
        "original_rainfall": [275.0]
    })
    detector = AnomalyDetector()
    issues, summary = detector.detect_anomalies(df)

    assert not issues.empty
    row = issues.iloc[0]
    assert row["validation_rule"] == "A_DAILY_WARNING"
    assert row["severity"] == IssueSeverity.MEDIUM.value
    assert row["anomaly_type"] == "Potential Extreme Weather Event"


def test_p5_dual_gauge_comparison():
    """Verify Rule P5: Flags discrepancy between co-located SRG and ARG."""
    df = pd.DataFrame({
        "station_id": ["STN_SITE1", "STN_SITE1"],
        "date": [pd.Timestamp("2024-07-01"), pd.Timestamp("2024-07-02")],
        "rainfall": [50.0, 30.0],
        "rainfall_srg": [50.0, 30.0],
        "rainfall_arg": [20.0, 28.0]  # First day diff = 30 mm (> 5mm threshold)
    })
    sec_validator = SecondaryQualityValidator()
    issues = sec_validator.check_dual_gauge(df, "Dual_Gauge_Test")

    assert len(issues) >= 1
    assert issues[0]["validation_rule"] == "P5_DUAL_GAUGE"
    assert "Discrepancy" in issues[0]["explanation"]


# =============================================================================
# 2. SECONDARY SPATIAL VALIDATION TESTS (S1 - S8)
# =============================================================================

def test_s1_quadrant_neighbour_selection():
    """Verify Rule S1: Selects up to 2 stations per quadrant within 25 km."""
    # Test station at (12.97, 77.59)
    test_lat, test_lon = 12.97, 77.59

    # Candidates in different directions (bearing) and distances
    candidates = pd.DataFrame({
        "station_id": ["NE1", "NE2", "NE3", "SE1", "SW1", "NW1", "FAR1"],
        "latitude": [
            test_lat + 0.05, test_lat + 0.08, test_lat + 0.10,  # Quadrant 1 (NE)
            test_lat - 0.05,                                    # Quadrant 2 (SE)
            test_lat - 0.06,                                    # Quadrant 3 (SW)
            test_lat + 0.05,                                    # Quadrant 4 (NW)
            test_lat + 1.0                                      # Far (> 100 km)
        ],
        "longitude": [
            test_lon + 0.05, test_lon + 0.08, test_lon + 0.10,
            test_lon + 0.05,
            test_lon - 0.06,
            test_lon - 0.05,
            test_lon + 1.0
        ]
    })

    selected = select_quadrant_neighbours(test_lat, test_lon, candidates, max_radius_km=25.0, max_per_quadrant=2)

    assert not selected.empty
    assert len(selected) <= 8
    assert "FAR1" not in selected["station_id"].values
    # Quadrant 1 should have exactly 2 stations (NE1, NE2), NE3 dropped due to max_per_quadrant=2
    q1_count = (selected["quadrant"] == 1).sum()
    assert q1_count == 2


def test_s2_spatial_homogeneity_departure():
    """Verify Rule S2: Departure flags (+) and (-) when exceeding Xabs and Xrel*StDev."""
    # 4 stations: STN_A has 120 mm, while neighbours have 10, 12, 11 mm
    dates = [pd.Timestamp("2024-07-01")] * 4
    df = pd.DataFrame({
        "station_id": ["STN_A", "STN_B", "STN_C", "STN_D"],
        "date": dates,
        "rainfall": [120.0, 10.0, 12.0, 11.0],
        "latitude": [12.97, 12.98, 12.96, 12.97],
        "longitude": [77.59, 77.60, 77.58, 77.61]
    })
    sec_validator = SecondaryQualityValidator()
    issues, summary = sec_validator.validate_dataset(df, "Spatial_Test")

    assert not issues.empty
    rules = issues["validation_rule"].values
    # STN_A should trigger S2 positive departure
    assert any("S2_SPATIAL_ANOMALY_+" in r for r in rules)


def test_s3_shifted_date_detection():
    """Verify Rule S3: Detects 1-day observer lag/lead."""
    # Network has rain on July 10, STN_A records 0 on July 10 and 60 mm on July 11
    d1 = pd.Timestamp("2024-07-10")
    d2 = pd.Timestamp("2024-07-11")

    records = [
        # Day 1: Neighbours heavy rain, STN_A 0
        {"date": d1, "station_id": "STN_A", "rainfall": 0.0},
        {"date": d1, "station_id": "STN_B", "rainfall": 55.0},
        {"date": d1, "station_id": "STN_C", "rainfall": 60.0},
        {"date": d1, "station_id": "STN_D", "rainfall": 58.0},
        # Day 2: Neighbours dry, STN_A spikes to 60
        {"date": d2, "station_id": "STN_A", "rainfall": 60.0},
        {"date": d2, "station_id": "STN_B", "rainfall": 1.0},
        {"date": d2, "station_id": "STN_C", "rainfall": 0.5},
        {"date": d2, "station_id": "STN_D", "rainfall": 0.0},
    ]
    df = pd.DataFrame(records)
    sec_validator = SecondaryQualityValidator()
    issues = sec_validator.check_shifted_dates(df, "Shift_Test")

    assert len(issues) >= 1
    assert issues[0]["validation_rule"] == "S3_SHIFTED_DATE"
    assert issues[0]["station_id"] == "STN_A"


def test_s4_accumulation_detection():
    """Verify Rule S4: Detects dry days followed by surge matching neighbour cumulative sum."""
    dates = pd.date_range("2024-07-01", periods=6, freq="D")
    records = []
    # STN_A has 0 for 4 days, then 70 mm on day 5
    stn_a_rfs = [0.0, 0.0, 0.0, 0.0, 70.0, 5.0]
    # Neighbours had 15, 20, 18, 17 mm across those 4 days (sum = 70 mm)
    oth_rfs = [15.0, 20.0, 18.0, 17.0, 2.0, 5.0]

    for i, d in enumerate(dates):
        records.append({"date": d, "station_id": "STN_A", "rainfall": stn_a_rfs[i]})
        records.append({"date": d, "station_id": "STN_B", "rainfall": oth_rfs[i]})
        records.append({"date": d, "station_id": "STN_C", "rainfall": oth_rfs[i]})

    df = pd.DataFrame(records)
    sec_validator = SecondaryQualityValidator()
    issues = sec_validator.check_accumulations(df, "Accum_Test")

    assert len(issues) >= 1
    assert issues[0]["validation_rule"] == "S4_ACCUMULATED_TOTAL"
    assert issues[0]["station_id"] == "STN_A"


def test_s5_missed_deluge_false_zero():
    """Verify Rule S5: Flags 0.0 mm when surrounding stations report deluge > 50 mm."""
    df = pd.DataFrame({
        "date": [pd.Timestamp("2024-07-15")] * 4,
        "station_id": ["STN_A", "STN_B", "STN_C", "STN_D"],
        "rainfall": [0.0, 75.0, 80.0, 68.0]
    })
    sec_validator = SecondaryQualityValidator()
    issues = sec_validator.check_missed_deluges(df, "Deluge_Test")

    assert len(issues) >= 1
    assert issues[0]["validation_rule"] == "S5_MISSED_OBSERVATION"
    assert issues[0]["station_id"] == "STN_A"


def test_s6_rainy_days_frequency_consistency():
    """Verify Rule S6: Flags monthly deficit in rainy days (>= 0.1 mm) vs neighbours."""
    dates = pd.date_range("2024-07-01", periods=30, freq="D")
    records = []

    for d in dates:
        # STN_A has rain only on 2 days
        records.append({"date": d, "station_id": "STN_A", "rainfall": 20.0 if d.day in [5, 20] else 0.0})
        # STN_B, STN_C, STN_D have 18 rainy days with small rain (0.5 mm)
        records.append({"date": d, "station_id": "STN_B", "rainfall": 1.0 if d.day <= 18 else 0.0})
        records.append({"date": d, "station_id": "STN_C", "rainfall": 1.0 if d.day <= 18 else 0.0})
        records.append({"date": d, "station_id": "STN_D", "rainfall": 1.0 if d.day <= 18 else 0.0})

    df = pd.DataFrame(records)
    sec_validator = SecondaryQualityValidator()
    issues = sec_validator.check_rainy_days_frequency(df, "Rainy_Days_Test")

    assert len(issues) >= 1
    assert issues[0]["validation_rule"] == "S6_RAINY_DAYS"
    assert issues[0]["station_id"] == "STN_A"


def test_s8_double_mass_trend_analysis():
    """Verify Rule S8: Detects significant slope break (> 25%) in multi-year double-mass curve."""
    # Generate 36 months of data
    dates = pd.date_range("2021-01-01", periods=1095, freq="D")
    records = []

    for d in dates:
        # Base stations have steady rainfall (10 mm every 5 days)
        base_rf = 10.0 if d.day % 5 == 0 else 0.0
        # Target station has steady rainfall until month 18, then changes slope by 50%
        if d < pd.Timestamp("2022-07-01"):
            target_rf = base_rf
        else:
            target_rf = base_rf * 1.6  # 60% slope increase

        records.append({"date": d, "station_id": "STN_TARGET", "rainfall": target_rf})
        records.append({"date": d, "station_id": "BASE_1", "rainfall": base_rf})
        records.append({"date": d, "station_id": "BASE_2", "rainfall": base_rf})
        records.append({"date": d, "station_id": "BASE_3", "rainfall": base_rf})

    df = pd.DataFrame(records)
    sec_validator = SecondaryQualityValidator()
    issues = sec_validator.check_double_mass_systematic_shift(df, "Double_Mass_Test")

    assert len(issues) >= 1
    assert issues[0]["validation_rule"] == "S8_DOUBLE_MASS"
    assert issues[0]["station_id"] == "STN_TARGET"


# =============================================================================
# 3. MISSING-VALUE ESTIMATION HIERARCHY TESTS (G1 - G6)
# =============================================================================

def test_g1_alternate_gauge_completion():
    """Verify Rule G1: In-fills missing daily value from co-located alternate gauge."""
    dates = pd.date_range("2024-07-01", periods=3, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "station_id": ["STN_A"] * 3,
        "rainfall": [10.0, np.nan, 20.0],
        "rainfall_arg": [10.0, 14.5, 20.0]  # Alternate gauge has 14.5 mm on July 2
    })
    predictor = MissingRainfallPredictor()
    preds = predictor.predict_gap_series(df, "STN_A", preferred_method="G1: Co-located Alternate Gauge")

    assert not preds.empty
    pred_row = preds.iloc[0]
    assert pred_row["predicted_value_mm"] == pytest.approx(14.5, abs=0.1)
    assert "G1" in pred_row["prediction_method"]
    assert bool(pred_row["is_estimated"]) is True


def test_g2_arithmetic_average_completion():
    """Verify Rule G2: Arithmetic average applied when annual normals within +-10%."""
    d = pd.Timestamp("2024-07-05")
    df = pd.DataFrame({
        "date": [d, d, d, d],
        "station_id": ["TARGET", "BASE_1", "BASE_2", "BASE_3"],
        "rainfall": [np.nan, 25.0, 35.0, 30.0]
    })
    # Target normal = 800 mm, base normals = 810, 790, 820 mm (all within 5%)
    normals = {"TARGET": 800.0, "BASE_1": 810.0, "BASE_2": 790.0, "BASE_3": 820.0}

    predictor = MissingRainfallPredictor()
    preds = predictor.predict_gap_series(df, "TARGET", station_normals=normals)

    assert not preds.empty
    pred_row = preds.iloc[0]
    # Expected: (25 + 35 + 30) / 3 = 30.0 mm
    assert pred_row["predicted_value_mm"] == pytest.approx(30.0, abs=0.1)
    assert "G2: Arithmetic Average" in pred_row["prediction_method"]


def test_g3_normal_ratio_completion():
    """Verify Rule G3: Normal-ratio method applied when annual normals differ > 10%."""
    d = pd.Timestamp("2024-07-05")
    df = pd.DataFrame({
        "date": [d, d, d, d],
        "station_id": ["TARGET", "BASE_1", "BASE_2", "BASE_3"],
        "rainfall": [np.nan, 20.0, 30.0, 40.0]
    })
    # Target normal = 700 mm, base normals differ by 20%
    normals = {"TARGET": 700.0, "BASE_1": 900.0, "BASE_2": 850.0, "BASE_3": 1000.0}

    predictor = MissingRainfallPredictor()
    preds = predictor.predict_gap_series(df, "TARGET", station_normals=normals)

    assert not preds.empty
    pred_row = preds.iloc[0]
    # Px = (700/3) * (20/900 + 30/850 + 40/1000) = 233.33 * (0.0222 + 0.0353 + 0.040) = 22.75 mm
    expected = (700.0 / 3.0) * (20.0 / 900.0 + 30.0 / 850.0 + 40.0 / 1000.0)
    assert pred_row["predicted_value_mm"] == pytest.approx(expected, abs=0.2)
    assert "G3: Normal-Ratio" in pred_row["prediction_method"]


def test_g4_distance_power_idw():
    """Verify Rule G4: Inverse Distance Weighting with power b=2."""
    d = pd.Timestamp("2024-07-05")
    # TARGET at (12.97, 77.59)
    # BASE_1 at dist ~10km with 50 mm, BASE_2 at dist ~20km with 10 mm
    df = pd.DataFrame({
        "date": [d, d, d],
        "station_id": ["TARGET", "BASE_1", "BASE_2"],
        "rainfall": [np.nan, 50.0, 10.0],
        "latitude": [12.97, 13.06, 13.15],
        "longitude": [77.59, 77.59, 77.59]
    })
    predictor = MissingRainfallPredictor()
    preds = predictor.predict_gap_series(df, "TARGET", preferred_method="G4: Distance Power Method (IDW)")

    assert not preds.empty
    pred_row = preds.iloc[0]
    assert "G4" in pred_row["prediction_method"]
    # Closer station (50 mm) should receive higher weight, so estimate > 30 mm
    assert pred_row["predicted_value_mm"] > 35.0


def test_g5_linear_regression_relation_curve():
    """Verify Rule G5: Paired linear regression with R^2 >= 0.70 and N >= 30."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    base_vals = np.linspace(5.0, 50.0, 50)
    # Target is strictly linear: y = 2.0 * x + 1.0 (R^2 = 1.0)
    target_vals = 2.0 * base_vals + 1.0
    # Make last day missing
    target_vals[-1] = np.nan

    records = []
    for i in range(50):
        records.append({"date": dates[i], "station_id": "TARGET", "rainfall": target_vals[i]})
        records.append({"date": dates[i], "station_id": "BASE_PARTNER", "rainfall": base_vals[i]})

    df = pd.DataFrame(records)
    predictor = MissingRainfallPredictor()
    preds = predictor.predict_gap_series(df, "TARGET", preferred_method="G5: Validated Linear Regression")

    assert not preds.empty
    pred_row = preds.iloc[0]
    expected_val = 2.0 * base_vals[-1] + 1.0
    assert pred_row["predicted_value_mm"] == pytest.approx(expected_val, abs=0.5)
    assert "G5: Validated Linear Regression" in pred_row["prediction_method"]


def test_linear_interpolation_not_default_when_spatial_available():
    """Verify Guardrail: Linear interpolation is NOT the default when spatial neighbours exist."""
    d1 = pd.Timestamp("2024-07-01")
    d2 = pd.Timestamp("2024-07-02")
    d3 = pd.Timestamp("2024-07-03")

    records = [
        {"date": d1, "station_id": "TARGET", "rainfall": 10.0},
        {"date": d2, "station_id": "TARGET", "rainfall": np.nan},  # Gap = 1 day
        {"date": d3, "station_id": "TARGET", "rainfall": 20.0},
        # 3 neighbours reporting on d2 with 40 mm
        {"date": d2, "station_id": "BASE_1", "rainfall": 40.0},
        {"date": d2, "station_id": "BASE_2", "rainfall": 42.0},
        {"date": d2, "station_id": "BASE_3", "rainfall": 38.0},
    ]
    df = pd.DataFrame(records)
    normals = {"TARGET": 800.0, "BASE_1": 800.0, "BASE_2": 800.0, "BASE_3": 800.0}

    predictor = MissingRainfallPredictor()
    # Call with auto hierarchy (preferred_method=None)
    preds = predictor.predict_gap_series(df, "TARGET", station_normals=normals)

    assert not preds.empty
    pred_row = preds.iloc[0]
    # Spatial method (G2 Arithmetic Average = ~40 mm) MUST be selected over linear interpolation (15 mm)
    assert "G2" in pred_row["prediction_method"]
    assert pred_row["predicted_value_mm"] == pytest.approx(40.0, abs=1.0)
