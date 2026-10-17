"""Unit and Integration Tests for Station Timeline Validation (Checkpoint 1)."""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.station_timeline_validation import (
    Checkpoint1Thresholds,
    normalize_column_names,
    match_checkpoint1_columns,
    validate_required_columns,
    parse_observation_dates,
    identify_invalid_records,
    detect_duplicate_station_dates,
    calculate_consecutive_missing_gaps,
    assign_station_priority,
    calculate_station_timeline_summary,
    identify_missing_station_dates,
    generate_checkpoint1_report
)


def test_column_normalization_and_matching():
    # Arkavathi style headers with trailing space on 'Station Code '
    df = pd.DataFrame(columns=["BasinName", "SubBasinName", "Station Code ", "LocationName", "Day", "RF(mm)"])
    col_map = match_checkpoint1_columns(df)
    assert col_map["date"] == "Day"
    assert col_map["station_code"] == "Station Code "
    assert col_map["station_name"] == "LocationName"
    assert col_map["rainfall"] == "RF(mm)"

    is_valid, missing = validate_required_columns(df, col_map)
    assert is_valid is True
    assert len(missing) == 0


def test_wims_code_matching():
    # WIMS Code matching
    df = pd.DataFrame(columns=["WIMS Code", "LocationName", "Day", "RF(mm)"])
    col_map = match_checkpoint1_columns(df)
    assert col_map["station_code"] == "WIMS Code"
    assert col_map["station_name"] == "LocationName"
    assert col_map["date"] == "Day"


def test_date_parsing_formats():
    # ISO, Indian DD-MM-YYYY, slashed DD/MM/YYYY
    df = pd.DataFrame({
        "Day": ["2024-01-01", "02-01-2024", "03/01/2024", "corrupted_date", None]
    })
    parsed = parse_observation_dates(df, "Day")
    assert parsed.iloc[0] == pd.Timestamp("2024-01-01")
    assert parsed.iloc[1] == pd.Timestamp("2024-01-02")
    assert pd.isna(parsed.iloc[3])
    assert pd.isna(parsed.iloc[4])


def test_missing_days_calculation_hand_crafted():
    # Station A: Starts 2024-06-01, ends 2024-06-10 (Expected: 10 days)
    # Recorded: June 1, 2, 4, 5, 8, 10 (6 unique days) -> Missing: 4 days (June 3, 6, 7, 9)
    # Expected: 10, Unique: 6, Missing: 4, Completeness: 60.0%
    dates = pd.to_datetime(["2024-06-01", "2024-06-02", "2024-06-04", "2024-06-05", "2024-06-08", "2024-06-10"])
    df = pd.DataFrame({
        "Day": dates,
        "Station Code ": ["STN_A"] * 6,
        "LocationName": ["Station Alpha"] * 6,
        "RF(mm)": [0.0, 5.0, 10.0, 2.0, 0.0, 15.0]
    })
    col_map = {"date": "Day", "station_code": "Station Code ", "station_name": "LocationName", "rainfall": "RF(mm)"}
    
    summary = calculate_station_timeline_summary(df, col_map)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["expected_calendar_days"] == 10
    assert row["unique_recorded_dates"] == 6
    assert row["missing_calendar_days"] == 4
    assert row["data_completeness_pct"] == 60.0

    # Missing dates detail
    missing_df = identify_missing_station_dates(df, col_map)
    assert len(missing_df) == 4
    assert set(missing_df["missing_date"]) == {"2024-06-03", "2024-06-06", "2024-06-07", "2024-06-09"}


def test_duplicate_records_do_not_inflate_completeness():
    # 5 total rows, but June 1 is recorded 3 times with duplicates!
    # Expected: June 1 to June 3 = 3 days
    # Recorded unique days: June 1, June 2 (2 unique days) -> Missing: 1 day (June 3)
    # Completeness must be (2 / 3) * 100 = 66.7%, NOT (5 / 3) * 100!
    df = pd.DataFrame({
        "Day": pd.to_datetime(["2024-06-01", "2024-06-01", "2024-06-01", "2024-06-02", "2024-06-02"]),
        "Station Code ": ["STN_DUP"] * 5,
        "LocationName": ["Duplicate Test Stn"] * 5,
        "RF(mm)": [10.0, 10.0, 15.0, 0.0, 0.0]
    })
    col_map = {"date": "Day", "station_code": "Station Code ", "station_name": "LocationName", "rainfall": "RF(mm)"}

    summary = calculate_station_timeline_summary(df, col_map)
    row = summary.iloc[0]
    assert row["expected_calendar_days"] == 2
    assert row["unique_recorded_dates"] == 2
    assert row["missing_calendar_days"] == 0
    assert row["data_completeness_pct"] == 100.0
    assert row["duplicate_records"] == 3  # (3 - 1) on June 1 + (2 - 1) on June 2 = 3 duplicate records

    dup_df = detect_duplicate_station_dates(df, col_map)
    assert len(dup_df) == 2  # June 1 and June 2
    june1_dup = dup_df[dup_df["observation_date"] == "2024-06-01"].iloc[0]
    assert june1_dup["duplicate_type"] == "Conflicting Duplicate"


def test_invalid_records_identification():
    # Records with missing date, missing code, missing name
    df = pd.DataFrame({
        "Day": ["2024-06-01", "not_a_date", "2024-06-03", None],
        "Station Code ": ["S1", "S1", "   ", "S2"],
        "LocationName": ["Stn 1", "Stn 1", "Stn 1", None],
        "RF(mm)": [5.0, 10.0, 0.0, 0.0]
    })
    col_map = {"date": "Day", "station_code": "Station Code ", "station_name": "LocationName", "rainfall": "RF(mm)"}

    invalid_df = identify_invalid_records(df, col_map)
    assert len(invalid_df) == 3
    # Original data must remain completely unchanged
    assert len(df) == 4


def test_single_date_station():
    # Station with exactly 1 observation date
    df = pd.DataFrame({
        "Day": pd.to_datetime(["2024-06-01"]),
        "Station Code ": ["STN_SINGLE"],
        "LocationName": ["Single Date Station"],
        "RF(mm)": [12.0]
    })
    col_map = {"date": "Day", "station_code": "Station Code ", "station_name": "LocationName", "rainfall": "RF(mm)"}

    summary = calculate_station_timeline_summary(df, col_map)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["expected_calendar_days"] == 1
    assert row["unique_recorded_dates"] == 1
    assert row["missing_calendar_days"] == 0
    assert row["data_completeness_pct"] == 100.0


def test_consecutive_missing_gap_calculation():
    # Existing dates: June 1, June 10 -> Gap between June 2 and June 9 = 8 days
    existing = {pd.to_datetime("2024-06-01").date(), pd.to_datetime("2024-06-10").date()}
    max_gap, gaps = calculate_consecutive_missing_gaps(
        existing, pd.to_datetime("2024-06-01"), pd.to_datetime("2024-06-10")
    )
    assert max_gap == 8
    assert len(gaps) == 1
    assert gaps[0]["gap_start"] == "2024-06-02"
    assert gaps[0]["gap_end"] == "2024-06-09"
    assert gaps[0]["gap_days"] == 8


def test_priority_assignment_thresholds():
    thresh = Checkpoint1Thresholds(
        critical_completeness_pct=70.0,
        critical_consecutive_gap_days=30
    )
    # 1. Critical: completeness < 70%
    prio, reason, _ = assign_station_priority(
        completeness_pct=65.0, missing_days=50, max_consecutive_gap=10,
        duplicate_count=0, invalid_date_count=0, thresholds=thresh
    )
    assert prio == "Critical"
    assert "Severe data deficit" in reason

    # 2. Critical: gap >= 30 days
    prio, reason, _ = assign_station_priority(
        completeness_pct=92.0, missing_days=35, max_consecutive_gap=35,
        duplicate_count=0, invalid_date_count=0, thresholds=thresh
    )
    assert prio == "Critical"
    assert "Extended transmission blackout" in reason


def test_generate_checkpoint1_report_end_to_end():
    df = pd.DataFrame({
        "Day": ["2024-06-01", "2024-06-02", "2024-06-04", "invalid_dt"],
        "Station Code ": ["S01", "S01", "S01", "S01"],
        "LocationName": ["Station 1", "Station 1", "Station 1", "Station 1"],
        "RF(mm)": [0.0, 10.0, -99.0, 5.0]
    })
    rep = generate_checkpoint1_report(df)
    assert rep["is_valid_schema"] is True
    assert len(rep["station_summary"]) == 1
    assert len(rep["invalid_records"]) == 1
    assert rep["metrics"]["total_stations"] == 1
    assert rep["metrics"]["total_missing_days"] == 1  # 2024-06-03
