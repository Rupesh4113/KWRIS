"""Time-Aware Model Evaluation Engine for Hydrological Predictions."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any, Callable
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, precision_score, recall_score, accuracy_score


def evaluate_predictions(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    y_lower: Optional[np.ndarray | pd.Series] = None,
    y_upper: Optional[np.ndarray | pd.Series] = None
) -> Dict[str, float]:
    """
    Compute time-aware hydrological validation metrics:
    - MAE: Mean Absolute Error (mm)
    - RMSE: Root Mean Squared Error (mm)
    - Bias: Mean error (mean(y_pred - y_true)) (mm)
    - Rain Occur Accuracy: Correctly identifying wet vs dry days (threshold 0.1 mm)
    - Wet Day MAE: MAE computed solely on days when it actually rained
    - Interval Coverage: Percentage of actual values falling inside [y_lower, y_upper]
    """
    y_t = np.array(y_true, dtype=float)
    y_p = np.array(y_pred, dtype=float)

    # Clean NaNs
    valid_mask = ~np.isnan(y_t) & ~np.isnan(y_p)
    if valid_mask.sum() == 0:
        return {
            "mae": 0.0, "rmse": 0.0, "bias": 0.0,
            "rain_accuracy": 0.0, "wet_mae": 0.0, "coverage_pct": 0.0
        }

    y_t = y_t[valid_mask]
    y_p = y_p[valid_mask]

    # Non-negative clipping for physical realism
    y_p = np.clip(y_p, 0.0, None)

    mae = float(mean_absolute_error(y_t, y_p))
    rmse = float(np.sqrt(mean_squared_error(y_t, y_p)))
    bias = float(np.mean(y_p - y_t))

    # Wet vs dry classification
    wet_true = (y_t >= 0.1).astype(int)
    wet_pred = (y_p >= 0.1).astype(int)
    rain_acc = float(accuracy_score(wet_true, wet_pred))

    # Wet-day conditional MAE
    wet_mask = y_t >= 0.1
    wet_mae = float(mean_absolute_error(y_t[wet_mask], y_p[wet_mask])) if wet_mask.sum() > 0 else 0.0

    # Interval coverage
    coverage_pct = 0.0
    if y_lower is not None and y_upper is not None:
        y_l = np.array(y_lower, dtype=float)[valid_mask]
        y_u = np.array(y_upper, dtype=float)[valid_mask]
        covered = (y_t >= y_l) & (y_t <= y_u)
        coverage_pct = float(np.mean(covered) * 100.0)

    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "rain_accuracy": round(rain_acc * 100.0, 1),
        "wet_mae": round(wet_mae, 2),
        "coverage_pct": round(coverage_pct, 1)
    }


def temporal_train_test_split(
    df: pd.DataFrame,
    date_col: str = "date",
    test_ratio: float = 0.20
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split time series sequentially without future leakage.
    Earliest (1 - test_ratio) goes to train, latest test_ratio goes to test.
    """
    sorted_df = df.sort_values(date_col).copy()
    split_idx = int(len(sorted_df) * (1.0 - test_ratio))
    train_df = sorted_df.iloc[:split_idx]
    test_df = sorted_df.iloc[split_idx:]
    return train_df, test_df
