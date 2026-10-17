"""Automated Data Quality Validation Engine for Rainfall Datasets."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np

from src.configuration import ValidationThresholds, IssueSeverity, ReviewStatus


class DataQualityValidator:
    """Configurable hydrological data quality validation engine."""

    def __init__(self, thresholds: Optional[ValidationThresholds] = None):
        self.thresholds = thresholds or ValidationThresholds()

    def validate(
        self,
        df: pd.DataFrame,
        dataset_name: str = "Uploaded Dataset"
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Execute comprehensive validation checks on normalized dataframe.
        Returns:
            issues_df: DataFrame of detected data issues.
            summary: Aggregated validation metrics.
        """
        issues: List[Dict[str, Any]] = []

        if df.empty:
            return pd.DataFrame(), {"total_issues": 0}

        # 1. Invalid or Missing Dates
        invalid_dates = df[df["date"].isna()]
        for idx, row in invalid_dates.iterrows():
            issues.append({
                "dataset_name": dataset_name,
                "station_id": str(row.get("station_id", "Unknown")),
                "observation_date": "NaT",
                "original_value": str(row.get("original_rainfall", "")),
                "issue_type": "Invalid Date",
                "severity": IssueSeverity.CRITICAL.value,
                "validation_rule": "V_INVALID_DATE",
                "explanation": "Observation date could not be parsed or is completely missing.",
                "recommended_action": "Verify and provide valid ISO YYYY-MM-DD date in source record.",
                "review_status": ReviewStatus.PENDING.value
            })

        # Filter to records with valid dates for subsequent checks
        valid_df = df[df["date"].notna()].copy()

        # 2. Duplicate Station-Date Records
        duplicates = valid_df[valid_df.duplicated(subset=["station_id", "date"], keep=False)]
        if not duplicates.empty:
            grouped = duplicates.groupby(["station_id", "date"])
            for (stn_id, obs_date), group in grouped:
                unique_vals = group["rainfall"].unique()
                is_conflicting = len(unique_vals) > 1
                date_str = pd.to_datetime(obs_date).strftime("%Y-%m-%d")
                
                issues.append({
                    "dataset_name": dataset_name,
                    "station_id": str(stn_id),
                    "observation_date": date_str,
                    "original_value": str(list(group["original_rainfall"].values)),
                    "issue_type": "Conflicting Duplicate" if is_conflicting else "Exact Duplicate",
                    "severity": IssueSeverity.HIGH.value if is_conflicting else IssueSeverity.MEDIUM.value,
                    "validation_rule": "V_DUPLICATE_RECORD",
                    "explanation": f"Found {len(group)} observations on the same date with values: {list(unique_vals)} mm.",
                    "recommended_action": "Consolidate duplicate records; check gauge logs for genuine multi-entry.",
                    "review_status": ReviewStatus.PENDING.value
                })

        # 3. Negative Rainfall Values
        negative_records = valid_df[valid_df["rainfall"] < self.thresholds.min_rainfall_mm]
        for idx, row in negative_records.iterrows():
            date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            issues.append({
                "dataset_name": dataset_name,
                "station_id": str(row["station_id"]),
                "observation_date": date_str,
                "original_value": str(row["original_rainfall"]),
                "issue_type": "Negative Rainfall",
                "severity": IssueSeverity.CRITICAL.value,
                "validation_rule": "V_NEGATIVE_VALUE",
                "explanation": f"Rainfall value ({row['rainfall']} mm) is below theoretical minimum of 0.0 mm.",
                "recommended_action": "Investigate gauge calibration error or missing code interpreted as negative; set to 0.0 mm or flag as missing.",
                "review_status": ReviewStatus.PENDING.value
            })

        # 4. Missing Rainfall Observations (NaN / Null / Missing Codes)
        missing_records = valid_df[valid_df["rainfall"].isna()]
        for idx, row in missing_records.iterrows():
            date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            orig_val = str(row["original_rainfall"]) if pd.notna(row["original_rainfall"]) else "NULL"
            issues.append({
                "dataset_name": dataset_name,
                "station_id": str(row["station_id"]),
                "observation_date": date_str,
                "original_value": orig_val,
                "issue_type": "Missing Rainfall",
                "severity": IssueSeverity.HIGH.value,
                "validation_rule": "V_MISSING_VALUE",
                "explanation": f"Rainfall observation is missing (recorded original code: '{orig_val}').",
                "recommended_action": "Apply AI missing value prediction using historical patterns or spatial estimation.",
                "review_status": ReviewStatus.PENDING.value
            })

        # 5. Station Time Series Completeness & Internal Date Gaps
        stations = valid_df["station_id"].unique()
        for stn in stations:
            stn_data = valid_df[valid_df["station_id"] == stn].sort_values("date")
            if len(stn_data) < 2:
                continue

            min_date = stn_data["date"].min()
            max_date = stn_data["date"].max()
            full_date_range = pd.date_range(start=min_date, end=max_date, freq="D")
            existing_dates = set(stn_data["date"].dt.date)

            missing_dates = [d for d in full_date_range if d.date() not in existing_dates]
            
            # Detect consecutive date gaps
            if missing_dates:
                gap_start = missing_dates[0]
                gap_count = 1
                for i in range(1, len(missing_dates)):
                    if (missing_dates[i] - missing_dates[i-1]).days == 1:
                        gap_count += 1
                    else:
                        severity = IssueSeverity.HIGH.value if gap_count > 3 else IssueSeverity.MEDIUM.value
                        issues.append({
                            "dataset_name": dataset_name,
                            "station_id": str(stn),
                            "observation_date": f"{gap_start.strftime('%Y-%m-%d')} to {missing_dates[i-1].strftime('%Y-%m-%d')}",
                            "original_value": "NO_RECORD",
                            "issue_type": "Missing Date Gap",
                            "severity": severity,
                            "validation_rule": "V_MISSING_DATE_GAP",
                            "explanation": f"Missing continuous time series sequence of {gap_count} days between {gap_start.strftime('%Y-%m-%d')} and {missing_dates[i-1].strftime('%Y-%m-%d')}.",
                            "recommended_action": "Check station transmission log; apply time series or spatial gap estimation if < 4 days, else historical baseline.",
                            "review_status": ReviewStatus.PENDING.value
                        })
                        gap_start = missing_dates[i]
                        gap_count = 1

                # Last group
                severity = IssueSeverity.HIGH.value if gap_count > 3 else IssueSeverity.MEDIUM.value
                issues.append({
                    "dataset_name": dataset_name,
                    "station_id": str(stn),
                    "observation_date": f"{gap_start.strftime('%Y-%m-%d')} to {missing_dates[-1].strftime('%Y-%m-%d')}",
                    "original_value": "NO_RECORD",
                    "issue_type": "Missing Date Gap",
                    "severity": severity,
                    "validation_rule": "V_MISSING_DATE_GAP",
                    "explanation": f"Missing continuous time series sequence of {gap_count} days between {gap_start.strftime('%Y-%m-%d')} and {missing_dates[-1].strftime('%Y-%m-%d')}.",
                    "recommended_action": "Check station transmission log; apply time series or spatial gap estimation if < 4 days, else historical baseline.",
                    "review_status": ReviewStatus.PENDING.value
                })

        issues_df = pd.DataFrame(issues)
        if issues_df.empty:
            issues_df = pd.DataFrame(columns=[
                "dataset_name", "station_id", "observation_date", "original_value",
                "issue_type", "severity", "validation_rule", "explanation",
                "recommended_action", "review_status"
            ])

        # Aggregate summary
        summary = {
            "total_issues": len(issues_df),
            "critical_count": int((issues_df["severity"] == IssueSeverity.CRITICAL.value).sum()) if not issues_df.empty else 0,
            "high_count": int((issues_df["severity"] == IssueSeverity.HIGH.value).sum()) if not issues_df.empty else 0,
            "medium_count": int((issues_df["severity"] == IssueSeverity.MEDIUM.value).sum()) if not issues_df.empty else 0,
            "low_count": int((issues_df["severity"] == IssueSeverity.LOW.value).sum()) if not issues_df.empty else 0,
            "missing_count": int((issues_df["issue_type"] == "Missing Rainfall").sum()) if not issues_df.empty else 0,
            "negative_count": int((issues_df["issue_type"] == "Negative Rainfall").sum()) if not issues_df.empty else 0,
            "duplicate_count": int(issues_df["issue_type"].str.contains("Duplicate").sum()) if not issues_df.empty else 0,
            "date_gap_count": int((issues_df["issue_type"] == "Missing Date Gap").sum()) if not issues_df.empty else 0,
        }

        return issues_df, summary
