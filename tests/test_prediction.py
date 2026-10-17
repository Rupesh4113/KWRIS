"""Tests for Missing Value Prediction Hierarchy and Evaluation."""

import pytest
import pandas as pd
import numpy as np
from src.missing_value_prediction import MissingRainfallPredictor, haversine_distance_km
from src.model_evaluation import evaluate_predictions, temporal_train_test_split
from src.historical_data import HistoricalDataManager


def test_haversine_distance():
    # Bangalore (12.9716, 77.5946) to Mysuru (12.2958, 76.6394) is approx 128-140 km
    dist = haversine_distance_km(12.9716, 77.5946, 12.2958, 76.6394)
    assert 120.0 < dist < 150.0


def test_evaluate_predictions_metrics():
    y_true = np.array([0.0, 5.0, 10.0, 0.0, 20.0])
    y_pred = np.array([0.0, 4.0, 12.0, 1.0, 18.0])
    y_lower = y_pred - 3.0
    y_upper = y_pred + 3.0

    metrics = evaluate_predictions(y_true, y_pred, y_lower, y_upper)
    assert metrics["mae"] > 0
    assert metrics["rmse"] > 0
    assert metrics["rain_accuracy"] >= 80.0
    assert metrics["coverage_pct"] >= 80.0


def test_temporal_train_test_split_no_leakage():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame({"date": dates, "rainfall": np.random.rand(100)})
    train, test = temporal_train_test_split(df, test_ratio=0.20)

    assert len(train) == 80
    assert len(test) == 20
    # No future dates in train set
    assert train["date"].max() < test["date"].min()


def test_prediction_short_gap_interpolation():
    # Missing 1 day between 10.0 mm and 20.0 mm -> Method 2
    dates = pd.date_range("2024-06-01", periods=5, freq="D")
    rfs = [5.0, 10.0, np.nan, 20.0, 15.0]
    df = pd.DataFrame({
        "date": dates,
        "station_id": ["STN_A"] * 5,
        "station_name": ["Station A"] * 5,
        "rainfall": rfs,
        "original_rainfall": rfs
    })

    predictor = MissingRainfallPredictor()
    preds = predictor.predict_gap_series(df, "STN_A")

    assert not preds.empty
    pred_row = preds.iloc[0]
    assert pred_row["date"] == "2024-06-03"
    assert pred_row["predicted_value_mm"] == pytest.approx(15.0, abs=0.1)
    assert "Method 2" in pred_row["prediction_method"]
    assert bool(pred_row["is_estimated"]) is True  # ESTIMATED — NOT OBSERVED
