"""Primary Validation Module: P1 to P5.
Checks one station's records on its own to catch observer, instrument, and data entry errors.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from src.models import ValidationFlag, ValidationStatus


def run_p1_entry_check(df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationFlag]:
    """
    P1 - Entry Check:
    Detect non-numeric entries, invalid dates, duplicate station-date records,
    and missing value codes (-99, etc.).
    Preserves valid zero rainfall as legitimate observation.
    """
    flags: List[ValidationFlag] = []
    
    # 1. Check for duplicate station-date combinations
    dup_mask = df.duplicated(subset=["station_id", "date"], keep=False)
    dup_df = df[dup_mask & df["date"].notna()]
    for idx, row in dup_df.iterrows():
        flags.append(ValidationFlag(
            station_id=str(row["station_id"]),
            station_name=str(row["station_name"]),
            date=row["date"],
            rule_id="P1",
            severity="warning",
            message=f"Duplicate observation record detected for station '{row['station_name']}' on {row['date'].strftime('%Y-%m-%d')}.",
            original_value=row["rainfall_mm"],
            details={"type": "duplicate_date", "row_id": int(row.get("original_row_id", idx))}
        ))
        
    # 2. Check for invalid or missing dates
    invalid_dates = df[df["date"].isna()]
    for idx, row in invalid_dates.iterrows():
        flags.append(ValidationFlag(
            station_id=str(row.get("station_id", "UNKNOWN")),
            station_name=str(row.get("station_name", "UNKNOWN")),
            date=pd.Timestamp("1900-01-01"),
            rule_id="P1",
            severity="critical",
            message="Invalid or unparseable observation date.",
            original_value=row.get("rainfall_mm", np.nan),
            details={"type": "invalid_date", "row_id": int(row.get("original_row_id", idx))}
        ))
        
    # 3. Check for missing rainfall values
    missing_rf = df[df["rainfall_mm"].isna() & df["date"].notna()]
    for idx, row in missing_rf.iterrows():
        flags.append(ValidationFlag(
            station_id=str(row["station_id"]),
            station_name=str(row["station_name"]),
            date=row["date"],
            rule_id="P1",
            severity="info",
            message=f"Missing rainfall value / placeholder code detected at station '{row['station_name']}'.",
            original_value=np.nan,
            details={"type": "missing_value", "row_id": int(row.get("original_row_id", idx))}
        ))
        
    return flags


def run_p2_min_limit(df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationFlag]:
    """
    P2 - Minimum Limit:
    Flag rainfall values below 0.0 mm. Never automatically turn negative into zero.
    """
    flags: List[ValidationFlag] = []
    min_limit = float(config.get("min_rainfall_mm", 0.0))
    
    neg_records = df[df["rainfall_mm"] < min_limit]
    for idx, row in neg_records.iterrows():
        flags.append(ValidationFlag(
            station_id=str(row["station_id"]),
            station_name=str(row["station_name"]),
            date=row["date"],
            rule_id="P2",
            flag_direction="-",
            severity="critical",
            message=f"Physically impossible negative rainfall ({row['rainfall_mm']:.1f} mm < {min_limit} mm).",
            original_value=float(row["rainfall_mm"]),
            expected_value=0.0,
            details={"type": "negative_value", "limit": min_limit, "row_id": int(row.get("original_row_id", idx))}
        ))
        
    return flags


def run_p3_max_limit(
    df: pd.DataFrame, 
    config: Dict[str, Any],
    station_ceilings: Optional[Dict[str, float]] = None
) -> List[ValidationFlag]:
    """
    P3 - Maximum Limit:
    Daily ceiling based on 1-day Probable Maximum Precipitation (PMP) or highest recorded.
    Flag readings exceeding ceiling as doubtful.
    """
    flags: List[ValidationFlag] = []
    default_ceiling = float(config.get("default_daily_max_mm", 350.0))
    
    if station_ceilings is None:
        station_ceilings = {}
        
    for stn, stn_df in df.groupby("station_name"):
        ceiling = station_ceilings.get(stn, default_ceiling)
        exceeded = stn_df[stn_df["rainfall_mm"] > ceiling]
        for idx, row in exceeded.iterrows():
            flags.append(ValidationFlag(
                station_id=str(row["station_id"]),
                station_name=str(row["station_name"]),
                date=row["date"],
                rule_id="P3",
                flag_direction="+",
                severity="critical",
                message=f"Rainfall reading ({row['rainfall_mm']:.1f} mm) exceeds daily maximum ceiling ({ceiling:.1f} mm).",
                original_value=float(row["rainfall_mm"]),
                expected_value=ceiling,
                details={"type": "exceeds_ceiling", "ceiling_mm": ceiling, "row_id": int(row.get("original_row_id", idx))}
            ))
            
    return flags


def run_p4_upper_warning(df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationFlag]:
    """
    P4 - Upper Warning Level:
    For each calendar month, compute warning level = mean + 1.96 * std (or 98th percentile)
    using daily data including dry days. Flag values exceeding level as doubtful.
    """
    flags: List[ValidationFlag] = []
    method = config.get("method", "normal_multiplier")
    multiplier = float(config.get("multiplier", 1.96))
    percentile_val = float(config.get("percentile", 98.0))
    min_sample = int(config.get("min_sample_size", 15))
    
    valid_data = df[df["rainfall_mm"].notna() & df["date"].notna()].copy()
    if valid_data.empty:
        return flags
        
    valid_data["month"] = valid_data["date"].dt.month
    
    for (stn, month), group in valid_data.groupby(["station_name", "month"]):
        rf_vals = group["rainfall_mm"].values
        if len(rf_vals) < min_sample:
            continue
            
        if method == "normal_multiplier":
            mean_val = np.mean(rf_vals)
            std_val = np.std(rf_vals, ddof=1)
            warning_level = mean_val + (multiplier * std_val)
        else:
            warning_level = np.percentile(rf_vals, percentile_val)
            
        # Ensure warning level is above sensible threshold (at least 20mm)
        warning_level = max(warning_level, 20.0)
        
        flagged = group[group["rainfall_mm"] > warning_level]
        for idx, row in flagged.iterrows():
            flags.append(ValidationFlag(
                station_id=str(row["station_id"]),
                station_name=str(row["station_name"]),
                date=row["date"],
                rule_id="P4",
                flag_direction="+",
                severity="warning",
                message=f"Rainfall ({row['rainfall_mm']:.1f} mm) exceeds Month {month} upper warning level ({warning_level:.1f} mm).",
                original_value=float(row["rainfall_mm"]),
                expected_value=round(warning_level, 1),
                details={
                    "month": month,
                    "warning_level_mm": round(warning_level, 2),
                    "mean_mm": round(float(np.mean(rf_vals)), 2),
                    "std_mm": round(float(np.std(rf_vals, ddof=1)), 2),
                    "row_id": int(row.get("original_row_id", idx))
                }
            ))
            
    return flags


def run_p5_dual_gauge_comparison(df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationFlag]:
    """
    P5 - Two Gauges at One Station (Manual vs Automatic):
    Compare daily manual gauge vs daily aggregated automatic gauge.
    Ignore differences below 5%. Flag larger differences with pattern diagnostics.
    """
    flags: List[ValidationFlag] = []
    tolerance_pct = float(config.get("tolerance_pct", 5.0))
    
    # Check if dataset has gauge_type column with both manual and automatic
    if "gauge_type" not in df.columns or df["gauge_type"].nunique() < 2:
        return flags
        
    for stn, stn_df in df.groupby("station_name"):
        piv = stn_df.pivot_table(index="date", columns="gauge_type", values="rainfall_mm", aggfunc="first")
        if "manual" not in piv.columns or "automatic" not in piv.columns:
            continue
            
        both_present = piv.dropna(subset=["manual", "automatic"])
        if both_present.empty:
            continue
            
        # Check identical records over long periods (pattern 5)
        identical_diff = np.abs(both_present["manual"] - both_present["automatic"])
        identical_days = (identical_diff < 0.001) & (both_present["manual"] > 0)
        if identical_days.sum() > 30:
            flags.append(ValidationFlag(
                station_id=stn,
                station_name=stn,
                date=both_present.index[0],
                rule_id="P5",
                severity="warning",
                message="Suspiciously identical values between manual and automatic gauges across >30 rainy days. Possible data fabrication or copy.",
                details={"pattern": "identical_long_period", "count": int(identical_days.sum())}
            ))
            
        # Compare daily discrepancies
        for date, row in both_present.iterrows():
            m_val = float(row["manual"])
            a_val = float(row["automatic"])
            max_val = max(m_val, a_val)
            
            if max_val < 1.0:  # Ignore negligible readings
                continue
                
            abs_diff = abs(m_val - a_val)
            pct_diff = (abs_diff / max_val) * 100.0
            
            if pct_diff > tolerance_pct:
                # Diagnose diagnostic pattern
                if max_val > 50.0 and abs_diff > 20.0:
                    pattern = "Gap grows during heavy rain (likely bucket double-count or chart crowd; trust manual)"
                    rec_trust = "manual"
                elif a_val > m_val * 1.5:
                    pattern = "Automatic gauge consistently higher (calibration drift; trust manual)"
                    rec_trust = "manual"
                elif m_val > a_val * 1.5:
                    pattern = "Manual gauge higher (calibration error or bucket blockage; verify)"
                    rec_trust = "automatic"
                else:
                    pattern = "Dual-gauge reading discrepancy exceeding 5% tolerance"
                    rec_trust = "manual"
                    
                flags.append(ValidationFlag(
                    station_id=stn,
                    station_name=stn,
                    date=date,
                    rule_id="P5",
                    flag_direction="+" if a_val > m_val else "-",
                    severity="warning",
                    message=f"Gauge discrepancy: Manual={m_val:.1f} mm, Auto={a_val:.1f} mm (diff: {abs_diff:.1f} mm, {pct_diff:.1f}%). {pattern}.",
                    original_value=m_val,
                    expected_value=a_val,
                    details={
                        "manual_mm": m_val,
                        "automatic_mm": a_val,
                        "pct_diff": round(pct_diff, 1),
                        "recommended_gauge": rec_trust
                    }
                ))
                
    return flags


def run_all_primary_validations(
    df: pd.DataFrame, 
    config: Dict[str, Any],
    station_ceilings: Optional[Dict[str, float]] = None
) -> Tuple[List[ValidationFlag], pd.DataFrame]:
    """
    Execute all Primary Validation rules P1 to P5 and tag dataset.
    Returns (flags_list, annotated_dataframe).
    """
    flags: List[ValidationFlag] = []
    
    p1_cfg = config.get("p1_entry_check", {})
    if p1_cfg.get("enabled", True):
        flags.extend(run_p1_entry_check(df, p1_cfg))
        
    p2_cfg = config.get("p2_min_limit", {})
    if p2_cfg.get("enabled", True):
        flags.extend(run_p2_min_limit(df, p2_cfg))
        
    p3_cfg = config.get("p3_max_limit", {})
    if p3_cfg.get("enabled", True):
        flags.extend(run_p3_max_limit(df, p3_cfg, station_ceilings))
        
    p4_cfg = config.get("p4_upper_warning", {})
    if p4_cfg.get("enabled", True):
        flags.extend(run_p4_upper_warning(df, p4_cfg))
        
    p5_cfg = config.get("p5_dual_gauge", {})
    if p5_cfg.get("enabled", True):
        flags.extend(run_p5_dual_gauge_comparison(df, p5_cfg))
        
    # Annotate DataFrame with status and primary flags
    df_out = df.copy()
    if "validation_status" not in df_out.columns:
        df_out["validation_status"] = ValidationStatus.VALID.value
    if "flagged_rules" not in df_out.columns:
        df_out["flagged_rules"] = ""
    if "issue_description" not in df_out.columns:
        df_out["issue_description"] = ""
        
    # Mark missing rows as missing status
    missing_mask = df_out["rainfall_mm"].isna()
    df_out.loc[missing_mask, "validation_status"] = ValidationStatus.MISSING.value
    
    # Apply flags
    for flag in flags:
        if flag.details.get("row_id") is not None:
            r_idx = flag.details["row_id"]
            if r_idx in df_out.index:
                if df_out.at[r_idx, "validation_status"] != ValidationStatus.MISSING.value:
                    df_out.at[r_idx, "validation_status"] = ValidationStatus.DOUBTFUL.value
                current_rules = df_out.at[r_idx, "flagged_rules"]
                df_out.at[r_idx, "flagged_rules"] = f"{current_rules};{flag.rule_id}".strip(";")
                df_out.at[r_idx, "issue_description"] = flag.message
        else:
            match_mask = (df_out["station_name"] == flag.station_name) & (df_out["date"] == flag.date)
            if match_mask.any():
                df_out.loc[match_mask & (df_out["validation_status"] != ValidationStatus.MISSING.value), "validation_status"] = ValidationStatus.DOUBTFUL.value
                for m_idx in df_out[match_mask].index:
                    curr = df_out.at[m_idx, "flagged_rules"]
                    df_out.at[m_idx, "flagged_rules"] = f"{curr};{flag.rule_id}".strip(";")
                    df_out.at[m_idx, "issue_description"] = flag.message

    return flags, df_out
