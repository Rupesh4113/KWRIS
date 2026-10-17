"""Station Quality Priority Ranking Engine.
Computes an operational priority score to direct engineers to the most critical
and urgent rainfall station issues first, with full breakdown and explanation.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from src.models import ValidationFlag


def compute_station_priority_ranking(
    df: pd.DataFrame,
    flags: List[ValidationFlag],
    coords_map: Dict[str, Any],
    weights_config: Optional[Dict[str, float]] = None
) -> pd.DataFrame:
    """
    Calculate transparent station priority ranking scores (0-100 scale, higher = more urgent).
    Factors:
    - Missing % (weight ~ 0.30)
    - Doubtful % (weight ~ 0.25)
    - Critical flag count: P2 negative, P3 ceiling (weight ~ 0.20)
    - Recency of latest problem (weight ~ 0.15)
    - Neighbour density / lack of coverage (weight ~ 0.10)
    """
    if weights_config is None:
        weights_config = {
            "missing_pct": 0.30,
            "doubtful_pct": 0.25,
            "critical_flags": 0.20,
            "recency": 0.15,
            "neighbour_coverage": 0.10
        }
        
    records = []
    flags_by_stn: Dict[str, List[ValidationFlag]] = {}
    for f in flags:
        flags_by_stn.setdefault(f.station_name, []).append(f)
        
    max_date_global = df["date"].max() if not df["date"].dropna().empty else pd.Timestamp.now()
    
    for stn, stn_df in df.groupby("station_name"):
        stn_id = str(stn_df["station_id"].iloc[0]) if "station_id" in stn_df.columns else stn
        total_obs = len(stn_df)
        stn_flags = flags_by_stn.get(stn, [])
        
        # 1. Missing rate
        missing_count = stn_df["rainfall_mm"].isna().sum()
        missing_pct = (missing_count / max(1, total_obs)) * 100.0
        score_missing = min(100.0, missing_pct * 2.0)  # 50% missing -> 100 score
        
        # 2. Doubtful rate
        doubtful_count = len(stn_flags)
        doubtful_pct = (doubtful_count / max(1, total_obs)) * 100.0
        score_doubtful = min(100.0, doubtful_pct * 4.0)
        
        # 3. Critical flags (P2 negative, P3 ceiling exceeded)
        crit_flags = [f for f in stn_flags if f.rule_id in ["P2", "P3"] or f.severity == "critical"]
        score_crit = min(100.0, len(crit_flags) * 20.0)
        
        # 4. Recency of problem
        if stn_flags:
            latest_flag_date = max(f.date for f in stn_flags)
            days_ago = max(0, (max_date_global - latest_flag_date).days)
            score_recency = max(0.0, 100.0 - (days_ago / 30.0 * 20.0))  # within last month = 100
            latest_issue_str = f"{stn_flags[-1].rule_id} on {latest_flag_date.strftime('%Y-%m-%d')}"
        elif missing_count > 0:
            score_recency = 50.0
            latest_issue_str = f"Missing data ({missing_count} records)"
        else:
            score_recency = 0.0
            latest_issue_str = "None (Station data healthy)"
            
        # 5. Neighbour availability
        has_coords = stn in coords_map
        score_coverage = 40.0 if not has_coords else 0.0
        
        # Combined weighted score
        priority_score = (
            weights_config.get("missing_pct", 0.30) * score_missing +
            weights_config.get("doubtful_pct", 0.25) * score_doubtful +
            weights_config.get("critical_flags", 0.20) * score_crit +
            weights_config.get("recency", 0.15) * score_recency +
            weights_config.get("neighbour_coverage", 0.10) * score_coverage
        )
        priority_score = round(min(100.0, max(0.0, priority_score)), 1)
        
        # Determine urgency category and recommended action
        if priority_score >= 70.0:
            urgency = "CRITICAL"
            recommended_action = "Immediate field inspection or high-priority correction required."
        elif priority_score >= 40.0:
            urgency = "HIGH"
            recommended_action = "Review flagged anomalies and propose neighbour-based gap estimates."
        elif priority_score >= 20.0:
            urgency = "MODERATE"
            recommended_action = "Routine quality validation and secondary neighbour cross-check."
        else:
            urgency = "LOW"
            recommended_action = "Station record validated; ready for hydrological modeling."
            
        explanation = (
            f"Missing: {missing_pct:.1f}%, Flagged anomalies: {doubtful_count} "
            f"(Critical: {len(crit_flags)}). Latest: {latest_issue_str}."
        )
        
        records.append({
            "station_id": stn_id,
            "station_name": stn,
            "priority_score": priority_score,
            "urgency": urgency,
            "total_records": total_obs,
            "missing_records": int(missing_count),
            "missing_pct": round(missing_pct, 1),
            "doubtful_flags_count": doubtful_count,
            "critical_flags_count": len(crit_flags),
            "latest_issue": latest_issue_str,
            "recommended_action": recommended_action,
            "score_explanation": explanation
        })
        
    df_ranked = pd.DataFrame(records)
    if not df_ranked.empty:
        df_ranked = df_ranked.sort_values(by="priority_score", ascending=False).reset_index(drop=True)
        df_ranked.index = df_ranked.index + 1
        df_ranked.index.name = "rank"
        
    return df_ranked
