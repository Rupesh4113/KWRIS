"""Tests for Anomaly Detection Engine."""

import pytest
import pandas as pd
import numpy as np
from src.configuration import ValidationThresholds, IssueSeverity
from src.anomaly_detection import AnomalyDetector


def test_detect_domain_ceiling_exceeded():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-07-15", "2024-07-16"]),
        "station_id": ["STN_A", "STN_A"],
        "rainfall": [25.0, 520.0],
        "original_rainfall": [25.0, 520.0]
    })
    detector = AnomalyDetector()
    anomalies_df, summary = detector.detect_anomalies(df)

    assert summary["extreme_ceilings"] == 1
    ceiling_issue = anomalies_df[anomalies_df["validation_rule"] == "A_DOMAIN_CEILING"].iloc[0]
    assert ceiling_issue["severity"] == IssueSeverity.CRITICAL.value
    assert ceiling_issue["anomaly_type"] == "Suspected Anomaly"


def test_detect_daily_warning_potential_extreme():
    # Value > 200 mm but <= 400 mm should be classified as Potential Extreme Weather Event, not deleted!
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-07-15"]),
        "station_id": ["STN_A"],
        "rainfall": [260.0],
        "original_rainfall": [260.0]
    })
    detector = AnomalyDetector()
    anomalies_df, summary = detector.detect_anomalies(df)

    assert summary["potential_extremes"] == 1
    warn_issue = anomalies_df[anomalies_df["validation_rule"] == "A_DAILY_WARNING"].iloc[0]
    assert warn_issue["anomaly_type"] == "Potential Extreme Weather Event"


def test_detect_statistical_mad_outliers():
    # 20 typical values (median around 5 mm) and one sudden spike to 120 mm
    dates = pd.date_range("2024-06-01", periods=25, freq="D")
    rfs = [4.0, 5.0, 6.0, 3.5, 4.5, 5.5, 4.8, 5.2, 6.1, 4.9,
           5.0, 4.2, 5.8, 3.9, 6.2, 5.1, 4.7, 5.3, 4.6, 5.4,
           120.0, 5.0, 4.8, 5.2, 4.9]
    df = pd.DataFrame({
        "date": dates,
        "station_id": ["STN_A"] * 25,
        "rainfall": rfs,
        "original_rainfall": rfs
    })
    detector = AnomalyDetector()
    anomalies_df, summary = detector.detect_anomalies(df)

    assert summary["statistical_spikes"] >= 1
    mad_issues = anomalies_df[anomalies_df["validation_rule"] == "A_MAD_OUTLIER"]
    assert not mad_issues.empty


def test_spatial_discordance():
    # On 2024-07-20: Station A has 110 mm while Stations B and C have 0.0 mm
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-07-20", "2024-07-20", "2024-07-20"]),
        "station_id": ["STN_A", "STN_B", "STN_C"],
        "rainfall": [110.0, 0.0, 0.5],
        "original_rainfall": [110.0, 0.0, 0.5]
    })
    detector = AnomalyDetector()
    anomalies_df, summary = detector.detect_anomalies(df)

    assert summary["spatial_discordances"] >= 1
    spatial_issue = anomalies_df[anomalies_df["validation_rule"] == "A_SPATIAL_DISCORDANCE"].iloc[0]
    assert spatial_issue["station_id"] == "STN_A"
