"""Tests for Station Prioritization and Quality Scoring."""

import pytest
import pandas as pd
import numpy as np
from src.configuration import IssueSeverity
from src.prioritization import StationPrioritizer


def test_quality_score_calculation():
    prioritizer = StationPrioritizer()
    issues = pd.DataFrame([
        {"severity": IssueSeverity.CRITICAL.value},
        {"severity": IssueSeverity.HIGH.value},
        {"severity": IssueSeverity.MEDIUM.value}
    ])
    score, expl = prioritizer.calculate_overall_quality_score(100, issues)
    assert 0.0 <= score <= 100.0
    assert "Quality Score Formula:" in expl


def test_station_prioritization_ranking():
    prioritizer = StationPrioritizer()

    # Station A: Has critical issues and high missingness
    # Station B: Perfectly healthy
    dates = pd.date_range("2024-06-01", periods=10, freq="D")
    df_a = pd.DataFrame({
        "date": dates,
        "station_id": ["STN_A"] * 10,
        "station_name": ["Station A"] * 10,
        "rainfall": [np.nan] * 5 + [10.0] * 5
    })
    df_b = pd.DataFrame({
        "date": dates,
        "station_id": ["STN_B"] * 10,
        "station_name": ["Station B"] * 10,
        "rainfall": [5.0] * 10
    })
    df = pd.concat([df_a, df_b], ignore_index=True)

    issues = pd.DataFrame([
        {"station_id": "STN_A", "severity": IssueSeverity.CRITICAL.value, "issue_type": "Negative Rainfall"}
    ])

    priorities = prioritizer.prioritize_stations(df, issues)
    assert not priorities.empty
    # STN_A should be ranked first with higher priority
    assert priorities.iloc[0]["station_id"] == "STN_A"
    assert priorities.iloc[0]["priority_category"] in ["Critical", "High"]
    assert priorities.iloc[1]["station_id"] == "STN_B"
    assert priorities.iloc[1]["priority_category"] == "Low"
