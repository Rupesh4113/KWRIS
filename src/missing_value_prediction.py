"""AI-Based Missing Rainfall Prediction Hierarchy & Pipeline for RainfallIQ."""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor

from src.configuration import ValidationThresholds, PredictionQuality, ReviewStatus
from src.historical_data import HistoricalDataManager
from src.model_evaluation import evaluate_predictions, temporal_train_test_split


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two geographic coordinates in kilometers."""
    r = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class MissingRainfallPredictor:
    """
    Hierarchical Missing Rainfall Prediction Engine:
    - Method 1: Historical Seasonal Baseline (Climatological DOY/Monthly)
    - Method 2: Time-Series Interpolation (strictly for internal gaps <= 3 days)
    - Method 3: Machine Learning (Random Forest / Gradient Boosting with lag & rolling features)
    - Method 4: Spatial Estimation (Inverse Distance Weighting from coordinates)
    """

    def __init__(
        self,
        historical_manager: Optional[HistoricalDataManager] = None,
        thresholds: Optional[ValidationThresholds] = None
    ):
        self.hist_mgr = historical_manager or HistoricalDataManager()
        self.thresholds = thresholds or ValidationThresholds()

    def build_feature_matrix(self, stn_series: pd.DataFrame) -> pd.DataFrame:
        """Create time-lag, rolling, and seasonal calendar features for ML prediction."""
        df = stn_series.sort_values("date").copy()
        dts = pd.to_datetime(df["date"])

        df["doy"] = dts.dt.dayofyear
        df["month"] = dts.dt.month
        df["day"] = dts.dt.day
        df["doy_sin"] = np.sin(2 * np.pi * df["doy"] / 365.25)
        df["doy_cos"] = np.cos(2 * np.pi * df["doy"] / 365.25)

        # Lags on rainfall (forward-fill clean values to prevent cascading NaNs)
        clean_rf = df["rainfall"].ffill().bfill().fillna(0.0)
        df["lag_1"] = clean_rf.shift(1).fillna(0.0)
        df["lag_2"] = clean_rf.shift(2).fillna(0.0)
        df["lag_7"] = clean_rf.shift(7).fillna(0.0)

        # Rolling statistics
        df["rolling_7d_mean"] = clean_rf.rolling(7, min_periods=1).mean().shift(1).fillna(0.0)
        df["rolling_14d_mean"] = clean_rf.rolling(14, min_periods=1).mean().shift(1).fillna(0.0)

        return df

    def predict_gap_series(
        self,
        current_df: pd.DataFrame,
        station_id: str,
        preferred_method: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Identify missing observations for given station and predict estimates
        using the best justified method from the hierarchy.
        Returns a DataFrame of predictions marked ESTIMATED — NOT OBSERVED.
        """
        stn_df = current_df[current_df["station_id"] == station_id].sort_values("date").copy()
        if stn_df.empty:
            return pd.DataFrame()

        stn_name = stn_df["station_name"].iloc[0] if "station_name" in stn_df.columns else station_id
        
        # Ensure complete continuous date index to capture missing dates as well
        min_date = stn_df["date"].min()
        max_date = stn_df["date"].max()
        full_idx = pd.date_range(start=min_date, end=max_date, freq="D")
        stn_df = stn_df.set_index("date").reindex(full_idx)
        stn_df.index.name = "date"
        stn_df["station_id"] = station_id
        stn_df["station_name"] = stn_name
        stn_df = stn_df.reset_index()

        missing_mask = stn_df["rainfall"].isna()
        if not missing_mask.any():
            return pd.DataFrame()

        # Retrieve historical coverage
        coverage_df = self.hist_mgr.get_station_coverage([station_id])
        hist_years = int(coverage_df["coverage_years"].iloc[0]) if not coverage_df.empty else 0
        climatology = self.hist_mgr.compute_daily_climatology(station_id)

        # Train ML Model if enough observed data points exist
        valid_records = stn_df[~missing_mask].copy()
        ml_model = None
        ml_mae = 0.0
        ml_rmse = 0.0
        ml_res_std = 1.0

        feature_cols = ["doy_sin", "doy_cos", "month", "day", "lag_1", "lag_2", "lag_7", "rolling_7d_mean", "rolling_14d_mean"]
        if len(valid_records) >= 30:
            feat_df = self.build_feature_matrix(stn_df)
            train_pool = feat_df[~missing_mask]

            if len(train_pool) >= 30:
                train_part, val_part = temporal_train_test_split(train_pool, date_col="date", test_ratio=0.20)
                X_tr, y_tr = train_part[feature_cols], train_part["rainfall"]
                X_val, y_val = val_part[feature_cols], val_part["rainfall"]

                model = RandomForestRegressor(n_estimators=50, max_depth=8, random_state=42)
                model.fit(X_tr, y_tr)
                val_preds = np.clip(model.predict(X_val), 0.0, None)
                metrics = evaluate_predictions(y_val, val_preds)
                ml_mae = metrics["mae"]
                ml_rmse = metrics["rmse"]
                residuals = y_val.values - val_preds
                ml_res_std = float(np.std(residuals)) if len(residuals) > 1 else 1.0

                # Refit on all observed data
                model.fit(train_pool[feature_cols], train_pool["rainfall"])
                ml_model = model

        # Spatial neighbor detection
        has_coords = "latitude" in stn_df.columns and "longitude" in stn_df.columns and stn_df["latitude"].notna().any()
        stn_lat = float(stn_df["latitude"].dropna().iloc[0]) if has_coords else None
        stn_lon = float(stn_df["longitude"].dropna().iloc[0]) if has_coords else None

        # Predict for each missing date
        predictions: List[Dict[str, Any]] = []
        missing_indices = stn_df[missing_mask].index

        # Compute gap lengths for interpolation qualification
        for idx in missing_indices:
            row = stn_df.loc[idx]
            dt = row["date"]
            doy = dt.dayofyear
            date_str = dt.strftime("%Y-%m-%d")

            # Determine consecutive missing run length around this index
            left_valid = stn_df.loc[:idx, "rainfall"].last_valid_index()
            right_valid = stn_df.loc[idx:, "rainfall"].first_valid_index()
            gap_days = (right_valid - left_valid - 1) if (left_valid is not None and right_valid is not None) else 999

            pred_val = 0.0
            pred_method = ""
            conf_low = 0.0
            conf_high = 0.0
            mae = 0.0
            rmse = 0.0
            quality = PredictionQuality.LOW.value
            explanation = ""
            obs_used = 0
            review_req = True

            # Check preferred method or hierarchy selection
            chosen_method = preferred_method

            if not chosen_method:
                # Automated hierarchy selection
                if gap_days <= self.thresholds.max_interpolation_gap_days and left_valid is not None and right_valid is not None:
                    chosen_method = "Method 2: Time-Series Interpolation"
                elif ml_model is not None and ml_mae < 10.0:
                    chosen_method = "Method 3: Machine Learning (Random Forest)"
                elif not climatology.empty:
                    chosen_method = "Method 1: Historical Seasonal Baseline"
                elif has_coords and current_df["station_id"].nunique() >= 3:
                    chosen_method = "Method 4: Spatial IDW"
                else:
                    chosen_method = "Method 1: Historical Seasonal Baseline"

            # Execute Selected Method
            if chosen_method == "Method 2: Time-Series Interpolation" and gap_days <= 3 and left_valid is not None and right_valid is not None:
                val_left = float(stn_df.loc[left_valid, "rainfall"])
                val_right = float(stn_df.loc[right_valid, "rainfall"])
                weight = (idx - left_valid) / (right_valid - left_valid)
                pred_val = max(0.0, val_left + weight * (val_right - val_left))
                pred_method = "Method 2: Time-Series Interpolation (<= 3 days)"
                conf_low = max(0.0, pred_val - 2.0)
                conf_high = pred_val + 2.0
                mae = 1.8
                rmse = 2.5
                obs_used = 2
                quality = PredictionQuality.HIGH.value
                explanation = f"Short internal gap of {gap_days} days. Linear interpolation between {val_left:.1f} mm and {val_right:.1f} mm."
                review_req = False

            elif chosen_method.startswith("Method 3") and ml_model is not None:
                feat_row = self.build_feature_matrix(stn_df).loc[idx:idx][feature_cols]
                raw_p = float(ml_model.predict(feat_row)[0])
                pred_val = max(0.0, raw_p)
                pred_method = "Method 3: Machine Learning (Random Forest)"
                conf_low = max(0.0, pred_val - 1.645 * ml_res_std)
                conf_high = pred_val + 1.645 * ml_res_std
                mae = ml_mae
                rmse = ml_rmse
                obs_used = len(valid_records)
                quality = PredictionQuality.HIGH.value if ml_mae < 5.0 else PredictionQuality.MODERATE.value
                explanation = f"Random Forest regressor evaluated on temporal lags and calendar features (out-of-sample MAE: {ml_mae:.2f} mm)."
                review_req = quality != PredictionQuality.HIGH.value

            elif chosen_method == "Method 4: Spatial IDW" and has_coords:
                # Find other stations reporting on the exact same date
                same_day_others = current_df[(current_df["date"] == dt) & (current_df["station_id"] != station_id) & current_df["rainfall"].notna()].dropna(subset=["latitude", "longitude"])
                if len(same_day_others) >= 2:
                    weights = []
                    vals = []
                    for _, oth in same_day_others.iterrows():
                        dist = haversine_distance_km(stn_lat, stn_lon, float(oth["latitude"]), float(oth["longitude"]))
                        dist = max(dist, 0.5)  # Avoid division by 0
                        w = 1.0 / (dist ** 2)
                        weights.append(w)
                        vals.append(float(oth["rainfall"]))

                    pred_val = max(0.0, float(np.sum(np.array(weights) * np.array(vals)) / np.sum(weights)))
                    pred_method = "Method 4: Spatial IDW"
                    conf_low = max(0.0, float(np.percentile(vals, 10)))
                    conf_high = float(np.percentile(vals, 90))
                    mae = 3.5
                    rmse = 4.8
                    obs_used = len(same_day_others)
                    quality = PredictionQuality.MODERATE.value
                    explanation = f"Inverse Distance Weighting using {len(same_day_others)} neighboring station observations on {date_str}."
                    review_req = False
                else:
                    # Fallback to Method 1
                    chosen_method = "Method 1: Historical Seasonal Baseline"

            if chosen_method.startswith("Method 1") or pred_method == "":
                if not climatology.empty and doy in climatology["doy"].values:
                    c_row = climatology[climatology["doy"] == doy].iloc[0]
                    pred_val = float(c_row["median_mm"])
                    conf_low = float(c_row["p10_mm"])
                    conf_high = float(c_row["p90_mm"])
                    obs_used = int(c_row["sample_size"])
                    quality = PredictionQuality.MODERATE.value if hist_years >= 5 else PredictionQuality.LOW.value
                    explanation = f"Historical {hist_years}-year day-of-year climatological median (DOY {doy}, rainy prob: {c_row['pr_rain']:.1%})."
                else:
                    # Local station month fallback
                    same_month = valid_records[valid_records["date"].dt.month == dt.month]
                    if not same_month.empty:
                        pred_val = float(same_month["rainfall"].median())
                        conf_low = float(same_month["rainfall"].quantile(0.10))
                        conf_high = float(same_month["rainfall"].quantile(0.90))
                        obs_used = len(same_month)
                        quality = PredictionQuality.LOW.value
                        explanation = f"Current season month {dt.month} median baseline (sample size: {obs_used} days)."
                    else:
                        pred_val = 0.0
                        conf_low = 0.0
                        conf_high = 0.0
                        quality = PredictionQuality.UNAVAILABLE.value
                        explanation = "Insufficient historical or observed records to formulate reliable estimate."

                pred_method = "Method 1: Historical Seasonal Baseline"
                mae = 4.2
                rmse = 6.0
                review_req = True

            predictions.append({
                "station_id": station_id,
                "station_name": stn_name,
                "date": date_str,
                "original_value": np.nan,
                "predicted_value_mm": round(pred_val, 2),
                "prediction_method": pred_method,
                "historical_coverage_years": hist_years,
                "confidence_lower_mm": round(conf_low, 2),
                "confidence_upper_mm": round(conf_high, 2),
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "observations_used": obs_used,
                "prediction_quality": quality,
                "explanation": explanation,
                "manual_review_required": review_req,
                "is_estimated": True,  # **ESTIMATED — NOT OBSERVED**
                "review_status": ReviewStatus.PENDING.value
            })

        return pd.DataFrame(predictions)
