"""Tests for Automated Data Quality Validation."""

import pytest
import pandas as pd
import numpy as np
from src.configuration import ValidationThresholds, IssueSeverity
from src.data_validation import DataQualityValidator


def test_validator_detects_negatives():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-06-01", "2024-06-02"]),
        "station_id": ["STN_A", "STN_A"],
        "rainfall": [15.0, -5.5],
        "original_rainfall": [15.0, -5.5]
    })
    validator = DataQualityValidator()
    issues_df, summary = validator.validate(df)

    assert summary["negative_count"] == 1
    neg_issue = issues_df[issues_df["issue_type"] == "Negative Rainfall"].iloc[0]
    assert neg_issue["severity"] == IssueSeverity.CRITICAL.value
    assert neg_issue["validation_rule"] == "V_NEGATIVE_VALUE"


def test_validator_detects_missing_values():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-06-01", "2024-06-02", "2024-06-03"]),
        "station_id": ["STN_A", "STN_A", "STN_A"],
        "rainfall": [10.0, np.nan, 5.0],
        "original_rainfall": [10.0, -99, 5.0]
    })
    validator = DataQualityValidator()
    issues_df, summary = validator.validate(df)

    assert summary["missing_count"] == 1
    miss_issue = issues_df[issues_df["issue_type"] == "Missing Rainfall"].iloc[0]
    assert miss_issue["validation_rule"] == "V_MISSING_VALUE"


def test_validator_detects_duplicates():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-06-01", "2024-06-01"]),
        "station_id": ["STN_A", "STN_A"],
        "rainfall": [12.0, 18.0],
        "original_rainfall": [12.0, 18.0]
    })
    validator = DataQualityValidator()
    issues_df, summary = validator.validate(df)

    assert summary["duplicate_count"] >= 1
    dup_issue = issues_df[issues_df["validation_rule"] == "V_DUPLICATE_RECORD"].iloc[0]
    assert dup_issue["issue_type"] == "Conflicting Duplicate"


def test_validator_detects_date_sequence_gap():
    # Gap of 5 days between June 1 and June 7
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-06-01", "2024-06-07"]),
        "station_id": ["STN_A", "STN_A"],
        "rainfall": [5.0, 10.0],
        "original_rainfall": [5.0, 10.0]
    })
    validator = DataQualityValidator()
    issues_df, summary = validator.validate(df)

    assert summary["date_gap_count"] >= 1
    gap_issue = issues_df[issues_df["validation_rule"] == "V_MISSING_DATE_GAP"].iloc[0]
    assert "Missing continuous time series sequence of 5 days" in gap_issue["explanation"]
