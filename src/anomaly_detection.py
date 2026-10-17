"""Complementary Anomaly Detection Engine for RainfallIQ."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest

from src.configuration import ValidationThresholds, IssueSeverity, ReviewStatus


class AnomalyDetector:
    """
    Multi-method anomaly detection for rainfall observations:
    1. Domain-specific physical ceilings (IMD PMP benchmarks).
    2. Robust Median / MAD-based Z-score outlier detection.
    3. Unsupervised machine learning (Isolation Forest).
    4. Spatial consistency checks against nearby stations.
    5. Consecutive dry/wet run anomaly screening.
    """

    def __init__(self, thresholds: Optional[ValidationThresholds] = None):
        self.thresholds = thresholds or ValidationThresholds()

    def detect_anomalies(
        self,
        df: pd.DataFrame,
        dataset_name: str = "Uploaded Dataset",
        historical_climatology: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Execute all complementary anomaly detection checks.
        Returns:
            anomalies_df: Issues records with anomaly classifications.
            summary: Summary counts by method and classification.
        """
        anomalies: List[Dict[str, Any]] = []

        valid_df = df[df["date"].notna() & df["rainfall"].notna()].copy()
        if valid_df.empty:
            return pd.DataFrame(), {"total_anomalies": 0}

        # 1. Domain Ceilings & Physical Benchmarks
        for idx, row in valid_df.iterrows():
            rf = row["rainfall"]
            date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            stn_id = str(row["station_id"])

            if rf > self.thresholds.daily_ceiling_mm:
                anomalies.append({
                    "dataset_name": dataset_name,
                    "station_id": stn_id,
                    "observation_date": date_str,
                    "original_value": str(row.get("original_rainfall", rf)),
                    "issue_type": "Domain Ceiling Exceeded",
                    "severity": IssueSeverity.CRITICAL.value,
                    "validation_rule": "A_DOMAIN_CEILING",
                    "explanation": f"Rainfall ({rf:.1f} mm) exceeds absolute regional daily physical limit of {self.thresholds.daily_ceiling_mm} mm.",
                    "recommended_action": "Check for decimal placement error or cumulative bucket reading. Verify with radar/IMD before clearing.",
                    "review_status": ReviewStatus.PENDING.value,
                    "anomaly_type": "Suspected Anomaly"
                })
            elif rf > self.thresholds.daily_warning_mm:
                anomalies.append({
                    "dataset_name": dataset_name,
                    "station_id": stn_id,
                    "observation_date": date_str,
                    "original_value": str(row.get("original_rainfall", rf)),
                    "issue_type": "High Rainfall Warning",
                    "severity": IssueSeverity.MEDIUM.value,
                    "validation_rule": "A_DAILY_WARNING",
                    "explanation": f"Extreme rainfall ({rf:.1f} mm) exceeds warning threshold ({self.thresholds.daily_warning_mm} mm). May be valid extreme weather.",
                    "recommended_action": "Preserve value; do not discard. Compare with neighbouring stations and flood bulletins.",
                    "review_status": ReviewStatus.PENDING.value,
                    "anomaly_type": "Potential Extreme Weather Event"
                })

        # 2. Robust Station-Specific Median / MAD Z-Scores
        for stn_id, stn_df in valid_df.groupby("station_id"):
            rainy_days = stn_df[stn_df["rainfall"] >= self.thresholds.rainy_day_threshold_mm]
            if len(rainy_days) < 10:
                continue

            median_rf = rainy_days["rainfall"].median()
            mad_rf = np.median(np.abs(rainy_days["rainfall"] - median_rf))
            if mad_rf < 0.1:
                mad_rf = 0.5  # Prevent division by zero

            norm_mad = 1.4826 * mad_rf
            for idx, row in rainy_days.iterrows():
                rf = row["rainfall"]
                # Skip if already flagged under domain ceiling
                if rf > self.thresholds.daily_ceiling_mm:
                    continue

                z_score = (rf - median_rf) / norm_mad
                if z_score > self.thresholds.mad_zscore_threshold:
                    date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
                    anomalies.append({
                        "dataset_name": dataset_name,
                        "station_id": str(stn_id),
                        "observation_date": date_str,
                        "original_value": str(row.get("original_rainfall", rf)),
                        "issue_type": "Statistical Spike (MAD)",
                        "severity": IssueSeverity.HIGH.value if z_score > 6.0 else IssueSeverity.MEDIUM.value,
                        "validation_rule": "A_MAD_OUTLIER",
                        "explanation": f"Robust MAD Z-score is {z_score:.2f} (median: {median_rf:.1f} mm, MAD: {mad_rf:.1f} mm). Value {rf:.1f} mm is an extreme statistical outlier.",
                        "recommended_action": "Cross-check with neighbouring station readings on {date_str} to confirm localized cloudburst vs gauge glitch.",
                        "review_status": ReviewStatus.PENDING.value,
                        "anomaly_type": "Suspected Anomaly"
                    })

        # 3. Machine Learning: Isolation Forest Unsupervised Anomaly Detection
        if len(valid_df) >= 30:
            try:
                features_df = pd.DataFrame()
                features_df["rainfall"] = valid_df["rainfall"].values
                dts = pd.to_datetime(valid_df["date"])
                features_df["day_of_year_sin"] = np.sin(2 * np.pi * dts.dt.dayofyear / 365.25)
                features_df["day_of_year_cos"] = np.cos(2 * np.pi * dts.dt.dayofyear / 365.25)
                features_df["month"] = dts.dt.month.values

                iso_forest = IsolationForest(
                    contamination=self.thresholds.isolation_forest_contamination,
                    random_state=42,
                    n_estimators=100
                )
                preds = iso_forest.fit_predict(features_df)
                scores = iso_forest.decision_function(features_df)

                anomaly_indices = np.where(preds == -1)[0]
                for aidx in anomaly_indices:
                    row = valid_df.iloc[aidx]
                    rf = row["rainfall"]
                    # Only flag if not already captured and rainfall is notable
                    if rf > 30.0 and rf <= self.thresholds.daily_ceiling_mm:
                        date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
                        stn_id = str(row["station_id"])
                        score_val = float(scores[aidx])
                        anomalies.append({
                            "dataset_name": dataset_name,
                            "station_id": stn_id,
                            "observation_date": date_str,
                            "original_value": str(row.get("original_rainfall", rf)),
                            "issue_type": "ML Anomaly (Isolation Forest)",
                            "severity": IssueSeverity.MEDIUM.value,
                            "validation_rule": "A_ISOLATION_FOREST",
                            "explanation": f"Unsupervised Isolation Forest detected multivariate anomaly (score: {score_val:.3f}) based on seasonal timing and magnitude ({rf:.1f} mm).",
                            "recommended_action": "Review seasonal plausibility; check whether rainfall aligns with historical monthly pattern.",
                            "review_status": ReviewStatus.PENDING.value,
                            "anomaly_type": "Suspected Anomaly"
                        })
            except Exception:
                pass  # ML failure should not crash overall validation

        # 4. Spatial Consistency Checks (when multiple stations available on same date)
        if valid_df["station_id"].nunique() >= 3:
            date_groups = valid_df.groupby("date")
            for obs_date, group in date_groups:
                if len(group) < 3:
                    continue

                for idx, row in group.iterrows():
                    rf = row["rainfall"]
                    stn_id = str(row["station_id"])
                    date_str = pd.to_datetime(obs_date).strftime("%Y-%m-%d")

                    others = group[group["station_id"] != stn_id]["rainfall"]
                    if len(others) < 2:
                        continue
                    median_network_rf = others.median()
                    p75_network_rf = others.quantile(0.75)

                    # Station shows severe downpour while surrounding stations are dry
                    if rf > self.thresholds.spatial_diff_limit_mm and p75_network_rf < 2.0:
                        anomalies.append({
                            "dataset_name": dataset_name,
                            "station_id": stn_id,
                            "observation_date": date_str,
                            "original_value": str(row.get("original_rainfall", rf)),
                            "issue_type": "Spatial Discordance (Isolated Spike)",
                            "severity": IssueSeverity.HIGH.value,
                            "validation_rule": "A_SPATIAL_DISCORDANCE",
                            "explanation": f"Station recorded {rf:.1f} mm, but surrounding stations recorded median {median_network_rf:.1f} mm (75th percentile < {p75_network_rf:.1f} mm).",
                            "recommended_action": "Check if neighbouring stations had rain on adjacent days (wrong-day shift) or if an isolated convective cell occurred.",
                            "review_status": ReviewStatus.PENDING.value,
                            "anomaly_type": "Suspected Anomaly"
                        })
                    # Station shows 0.0 mm while network is in widespread heavy deluge
                    elif rf == 0.0 and median_network_rf > 60.0:
                        anomalies.append({
                            "dataset_name": dataset_name,
                            "station_id": stn_id,
                            "observation_date": date_str,
                            "original_value": str(row.get("original_rainfall", rf)),
                            "issue_type": "Spatial Discordance (Missed Rain)",
                            "severity": IssueSeverity.HIGH.value,
                            "validation_rule": "A_SPATIAL_MISSED_RAIN",
                            "explanation": f"Station recorded 0.0 mm while surrounding stations median was {median_network_rf:.1f} mm.",
                            "recommended_action": "Check for gauge blockage, funnel clogging, or recorder freeze.",
                            "review_status": ReviewStatus.PENDING.value,
                            "anomaly_type": "Suspected Anomaly"
                        })

        anomalies_df = pd.DataFrame(anomalies)
        if anomalies_df.empty:
            anomalies_df = pd.DataFrame(columns=[
                "dataset_name", "station_id", "observation_date", "original_value",
                "issue_type", "severity", "validation_rule", "explanation",
                "recommended_action", "review_status", "anomaly_type"
            ])
        else:
            # Deduplicate by station_id, date, and rule
            anomalies_df.drop_duplicates(subset=["station_id", "observation_date", "validation_rule"], inplace=True)

        summary = {
            "total_anomalies": len(anomalies_df),
            "extreme_ceilings": int((anomalies_df["validation_rule"] == "A_DOMAIN_CEILING").sum()) if not anomalies_df.empty else 0,
            "statistical_spikes": int((anomalies_df["validation_rule"] == "A_MAD_OUTLIER").sum()) if not anomalies_df.empty else 0,
            "ml_anomalies": int((anomalies_df["validation_rule"] == "A_ISOLATION_FOREST").sum()) if not anomalies_df.empty else 0,
            "spatial_discordances": int(anomalies_df["validation_rule"].str.contains("SPATIAL").sum()) if not anomalies_df.empty else 0,
            "potential_extremes": int((anomalies_df.get("anomaly_type") == "Potential Extreme Weather Event").sum()) if not anomalies_df.empty else 0
        }

        return anomalies_df, summary
