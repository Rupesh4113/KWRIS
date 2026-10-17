"""Intelligent Station Prioritization and Quality Scoring Engine."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np

from src.configuration import PrioritizationWeights, IssueSeverity


class StationPrioritizer:
    """
    Computes transparent, explainable priority scores (0 to 100) and tiers
    (Critical, High, Medium, Low) for stations needing engineer attention.
    """

    def __init__(self, weights: Optional[PrioritizationWeights] = None):
        self.weights = weights or PrioritizationWeights()

    def calculate_overall_quality_score(
        self,
        total_records: int,
        issues_df: pd.DataFrame
    ) -> Tuple[float, str]:
        """
        Calculate transparent overall data quality score (0 - 100).
        Formula:
            Base = 100.0
            Penalty = (Critical * 6.0 + High * 2.5 + Medium * 0.8 + Low * 0.2) / max(total_records / 100, 1)
            Score = max(0.0, min(100.0, 100.0 - Penalty))
        """
        if total_records == 0:
            return 100.0, "No records present."

        crit = int((issues_df["severity"] == IssueSeverity.CRITICAL.value).sum()) if not issues_df.empty else 0
        high = int((issues_df["severity"] == IssueSeverity.HIGH.value).sum()) if not issues_df.empty else 0
        med = int((issues_df["severity"] == IssueSeverity.MEDIUM.value).sum()) if not issues_df.empty else 0
        low = int((issues_df["severity"] == IssueSeverity.LOW.value).sum()) if not issues_df.empty else 0

        penalty_scale = max(total_records / 100.0, 1.0)
        penalty = (crit * 6.0 + high * 2.5 + med * 0.8 + low * 0.2) / penalty_scale
        score = max(0.0, min(100.0, 100.0 - penalty))

        formula_explanation = (
            f"Quality Score Formula: 100 - [({crit} Critical × 6.0 + {high} High × 2.5 + "
            f"{med} Medium × 0.8 + {low} Low × 0.2) / ({total_records} records / 100)] = {score:.1f}%"
        )
        return round(score, 1), formula_explanation

    def prioritize_stations(
        self,
        df: pd.DataFrame,
        issues_df: pd.DataFrame,
        coverage_df: Optional[pd.DataFrame] = None,
        critical_station_ids: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Prioritize all stations in the dataset and return a ranked table.
        """
        if df.empty:
            return pd.DataFrame()

        critical_stations_set = set(critical_station_ids or [])
        stations = df["station_id"].unique()
        priorities: List[Dict[str, Any]] = []

        coverage_dict = {}
        if coverage_df is not None and not coverage_df.empty:
            for idx, r in coverage_df.iterrows():
                coverage_dict[str(r["station_id"])] = {
                    "coverage_years": r.get("coverage_years", 0),
                    "completeness_pct": r.get("completeness_pct", 0.0)
                }

        for stn_id in stations:
            stn_records = df[df["station_id"] == stn_id].sort_values("date")
            stn_name = stn_records["station_name"].iloc[0] if "station_name" in stn_records.columns else stn_id
            total_obs = len(stn_records)
            
            missing_obs = int(stn_records["rainfall"].isna().sum())
            missing_pct = (missing_obs / total_obs) if total_obs > 0 else 0.0

            # Find longest consecutive missing run
            is_na_seq = stn_records["rainfall"].isna().astype(int)
            gap_lengths = is_na_seq.groupby((~is_na_seq.astype(bool)).cumsum()).sum()
            max_gap_days = int(gap_lengths.max()) if not gap_lengths.empty else 0

            # Issues for this station
            stn_issues = issues_df[issues_df["station_id"] == str(stn_id)] if not issues_df.empty else pd.DataFrame()
            crit_count = int((stn_issues["severity"] == IssueSeverity.CRITICAL.value).sum()) if not stn_issues.empty else 0
            high_count = int((stn_issues["severity"] == IssueSeverity.HIGH.value).sum()) if not stn_issues.empty else 0
            med_count = int((stn_issues["severity"] == IssueSeverity.MEDIUM.value).sum()) if not stn_issues.empty else 0

            # Component sub-scores (0.0 to 1.0)
            score_missing = min(1.0, missing_pct * 2.0)
            score_gap = min(1.0, max_gap_days / 15.0)
            score_anomaly = min(1.0, (crit_count * 0.5 + high_count * 0.25 + med_count * 0.1))
            
            # Historical unreliability
            hist_meta = coverage_dict.get(str(stn_id), {"coverage_years": 0})
            hist_years = hist_meta.get("coverage_years", 0)
            score_hist_unreliable = max(0.0, (5 - hist_years) / 5.0) if hist_years < 5 else 0.0

            # Network criticality
            is_crit_net = str(stn_id) in critical_stations_set or "dam" in str(stn_name).lower() or "reservoir" in str(stn_name).lower()
            score_network = 1.0 if is_crit_net else 0.2

            # Weighted priority calculation (0 to 100)
            w = self.weights
            composite_score = 100.0 * (
                w.missing_pct * score_missing +
                w.gap_duration * score_gap +
                w.anomaly_severity * score_anomaly +
                w.historical_unreliability * score_hist_unreliable +
                w.network_criticality * score_network
            )
            composite_score = round(max(0.0, min(100.0, composite_score)), 1)

            # Assign Priority Category
            if composite_score >= 70.0 or crit_count > 0 or max_gap_days >= 14:
                category = "Critical"
            elif composite_score >= 45.0 or high_count > 0 or max_gap_days >= 7:
                category = "High"
            elif composite_score >= 20.0 or med_count > 0:
                category = "Medium"
            else:
                category = "Low"

            # Primary Reason & Concrete Action
            reasons = []
            actions = []
            if crit_count > 0:
                reasons.append(f"{crit_count} critical issues (e.g. negative readings or ceiling exceedance)")
                actions.append("Audit raw field register immediately to rectify calibration or entry corruption.")
            if max_gap_days >= 7:
                reasons.append(f"Extended transmission blackout of {max_gap_days} consecutive days")
                actions.append("Inspect gauge hardware and run AI missing value imputation.")
            elif missing_obs > 0:
                reasons.append(f"{missing_obs} missing records ({missing_pct:.1%})")
                actions.append("Estimate missing observations using seasonal baseline or spatial IDW.")
            if high_count > 0:
                reasons.append(f"{high_count} suspicious statistical/spatial anomalies")
                actions.append("Verify extreme rainfall spikes with neighbouring telemetry before approval.")
            if hist_years < 3:
                reasons.append(f"Limited historical baseline ({hist_years} yrs)")
                actions.append("Import additional historical records to enable multi-year machine learning.")

            if not reasons:
                primary_reason = "Healthy station: records intact with no severe anomalies detected."
                recommended_action = "Routine monitoring and periodic archive."
            else:
                primary_reason = "; ".join(reasons)
                recommended_action = " ".join(actions)

            priorities.append({
                "station_id": str(stn_id),
                "station_name": str(stn_name),
                "priority_category": category,
                "priority_score": composite_score,
                "total_records": total_obs,
                "missing_records": missing_obs,
                "completeness_pct": round((1.0 - missing_pct) * 100.0, 1),
                "max_gap_days": max_gap_days,
                "critical_issues": crit_count,
                "high_issues": high_count,
                "medium_issues": med_count,
                "historical_years": hist_years,
                "is_critical_network": is_crit_net,
                "primary_reason": primary_reason,
                "recommended_action": recommended_action,
                "latest_date": stn_records["date"].max().strftime("%Y-%m-%d") if pd.notna(stn_records["date"].max()) else "N/A"
            })

        p_df = pd.DataFrame(priorities)
        if not p_df.empty:
            p_df.sort_values(by=["priority_score"], ascending=False, inplace=True)
            p_df.reset_index(drop=True, inplace=True)
        return p_df
