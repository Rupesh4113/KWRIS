"""Station Timeline and Missing-Day Validation (Checkpoint 1).

Implements mandatory Checkpoint 1 of RainfallIQ:
- Station timeline construction and observation window tracking
- Expected calendar days vs unique valid recorded dates
- Missing calendar days and consecutive gap analysis
- Duplicate station-date detection
- Invalid record triage (missing dates, station codes, or names)
- Non-destructive processing preserving raw data
- Configurable hydrological priority ranking
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd


@dataclass
class Checkpoint1Thresholds:
    """Configurable thresholds for Checkpoint 1 priority ranking."""
    critical_completeness_pct: float = 70.0    # Below 70% is Critical
    high_completeness_pct: float = 85.0        # Below 85% is High
    medium_completeness_pct: float = 95.0      # Below 95% is Medium
    critical_consecutive_gap_days: int = 30    # Continuous gap >= 30 days is Critical
    high_consecutive_gap_days: int = 14        # Continuous gap >= 14 days is High
    medium_consecutive_gap_days: int = 3       # Continuous gap >= 3 days is Medium
    critical_missing_days: int = 180           # Missing days >= 180 is Critical
    high_missing_days: int = 45                # Missing days >= 45 is High
    medium_missing_days: int = 5               # Missing days >= 5 is Medium


def normalize_column_names(df: pd.DataFrame) -> Dict[str, str]:
    """
    Map standardized/normalized column names to original column names.
    Strips leading/trailing whitespace, converts to lowercase, replaces multiple spaces.
    Example: 'Station Code ' -> 'station_code', 'LocationName' -> 'locationname'
    """
    mapping: Dict[str, str] = {}
    for col in df.columns:
        norm = " ".join(str(col).strip().lower().split())
        norm_key = norm.replace(" ", "_")
        mapping[norm_key] = col
        mapping[norm] = col
    return mapping


def match_checkpoint1_columns(
    df: pd.DataFrame,
    user_mapping: Optional[Dict[str, Optional[str]]] = None
) -> Dict[str, str]:
    """
    Identify physical column names for logical fields:
    - date: 'Day', 'Date', 'Observation Date', etc.
    - station_code: 'Station Code ', 'Station Code', 'WIMS Code', 'Station_ID', 'ID', etc.
    - station_name: 'LocationName', 'Station Name', 'StationName', 'Location', etc.
    - rainfall: 'RF(mm)', 'Rainfall', 'RF', 'Precipitation', etc.
    """
    normalized_map = normalize_column_names(df)
    actual_cols = list(df.columns)
    
    resolved: Dict[str, Optional[str]] = {
        "date": None,
        "station_code": None,
        "station_name": None,
        "rainfall": None
    }

    # If user provided explicit mapping, prioritize it
    if user_mapping:
        for logical_key in resolved.keys():
            user_val = user_mapping.get(logical_key)
            if user_val and user_val in actual_cols:
                resolved[logical_key] = user_val

    # Automatic detection candidates
    candidates = {
        "date": [
            "day", "date", "obs_date", "reading_date", "datetime",
            "timestamp", "dates", "rainfall_date"
        ],
        "station_code": [
            "station_code", "station code", "wims_code", "wims code",
            "station_id", "stationid", "stn_code", "stn_id", "id", "code"
        ],
        "station_name": [
            "locationname", "location_name", "location name",
            "station_name", "station name", "stationname", "stn_name", "station"
        ],
        "rainfall": [
            "rf(mm)", "rf_mm", "rf", "rainfall", "rain", "precipitation",
            "val", "value", "reading", "amount", "daily_rf"
        ]
    }

    for logical_key, pat_list in candidates.items():
        if resolved[logical_key] is None:
            # Check normalized keys
            for pat in pat_list:
                clean_pat = pat.replace(" ", "_")
                if clean_pat in normalized_map:
                    resolved[logical_key] = normalized_map[clean_pat]
                    break
                elif pat in normalized_map:
                    resolved[logical_key] = normalized_map[pat]
                    break

            # Fallback substring match across actual columns if still None
            if resolved[logical_key] is None:
                for col in actual_cols:
                    col_lower = str(col).strip().lower()
                    for pat in pat_list:
                        if pat in col_lower:
                            resolved[logical_key] = col
                            break
                    if resolved[logical_key]:
                        break

    return resolved


def validate_required_columns(
    df: pd.DataFrame,
    column_mapping: Dict[str, Optional[str]]
) -> Tuple[bool, List[str]]:
    """Verify that essential columns (date, station_code or station_name) are present."""
    missing: List[str] = []
    
    if not column_mapping.get("date") or column_mapping["date"] not in df.columns:
        missing.append("Observation Date ('Day' / 'Date')")
        
    has_code = column_mapping.get("station_code") and column_mapping["station_code"] in df.columns
    has_name = column_mapping.get("station_name") and column_mapping["station_name"] in df.columns
    
    if not has_code and not has_name:
        missing.append("Station Identifier ('Station Code ' / 'WIMS Code' / 'LocationName')")

    return (len(missing) == 0, missing)


def parse_observation_dates(df: pd.DataFrame, date_column: str) -> pd.Series:
    """
    Parse date column into standardized datetime format.
    Supports ISO (YYYY-MM-DD), Indian standard (DD-MM-YYYY, DD/MM/YYYY), timestamps, and mixed formats.
    Returns pd.Series of datetime64[ns] with NaT for unparseable dates.
    """
    raw_dates = df[date_column]
    if pd.api.types.is_datetime64_any_dtype(raw_dates):
        return pd.to_datetime(raw_dates)

    first_valid = raw_dates.dropna().astype(str).str.strip()
    if first_valid.empty:
        return pd.to_datetime(raw_dates, errors="coerce")

    # Fast vectorized check: if all non-empty sample strings start with 4-digit year, it's %Y-%m-%d
    sample = first_valid.iloc[:min(len(first_valid), 100)]
    if sample.str[:4].str.isdigit().all() and ("-" in sample.iloc[0] or "/" in sample.iloc[0]):
        return pd.to_datetime(raw_dates, errors="coerce")

    def _parse_val(x):
        if pd.isna(x):
            return pd.NaT
        s = str(x).strip()
        if not s or s.lower() in ["nan", "nat", "null", "none", "missing"]:
            return pd.NaT
        try:
            if len(s) >= 10 and s[:4].isdigit():
                return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")
            elif len(s) >= 10 and s[-4:].isdigit():
                if "-" in s:
                    return pd.to_datetime(s[:10], format="%d-%m-%Y", errors="coerce")
                elif "/" in s:
                    return pd.to_datetime(s[:10], format="%d/%m/%Y", errors="coerce")
            return pd.to_datetime(s, errors="coerce", format="mixed")
        except Exception:
            return pd.to_datetime(s, errors="coerce")

    return raw_dates.apply(_parse_val)


def identify_invalid_records(
    df: pd.DataFrame,
    column_mapping: Dict[str, Optional[str]],
    parsed_dates: Optional[pd.Series] = None
) -> pd.DataFrame:
    """
    Identify and flag records with missing or invalid dates, station codes, or station names.
    Does NOT discard records; creates an audit log of all invalid rows.
    """
    date_col = column_mapping.get("date")
    code_col = column_mapping.get("station_code")
    name_col = column_mapping.get("station_name")
    
    if parsed_dates is None and date_col:
        parsed_dates = parse_observation_dates(df, date_col)

    invalid_rows: List[Dict[str, Any]] = []

    # Vectorized condition masks
    date_invalid_mask = parsed_dates.isna() if parsed_dates is not None else pd.Series(True, index=df.index)
    
    code_missing_mask = (
        df[code_col].isna() | (df[code_col].astype(str).str.strip().isin(["", "nan", "None", "NULL", "NaT"]))
        if code_col and code_col in df.columns else pd.Series(False, index=df.index)
    )

    name_missing_mask = (
        df[name_col].isna() | (df[name_col].astype(str).str.strip().isin(["", "nan", "None", "NULL", "NaT"]))
        if name_col and name_col in df.columns else pd.Series(False, index=df.index)
    )

    # Any record with invalid date or both code and name missing
    flagged_mask = date_invalid_mask | (code_missing_mask & name_missing_mask) | code_missing_mask | name_missing_mask
    flagged_indices = df[flagged_mask].index

    for idx in flagged_indices:
        reasons = []
        if date_invalid_mask.loc[idx]:
            raw_d = str(df.loc[idx, date_col]) if date_col else "N/A"
            reasons.append(f"Invalid or unparseable date ('{raw_d}')")
        if code_missing_mask.loc[idx]:
            reasons.append("Missing or empty Station Code")
        if name_missing_mask.loc[idx]:
            reasons.append("Missing or empty Station Name (LocationName)")

        stn_code_val = str(df.loc[idx, code_col]).strip() if code_col and code_col in df.columns else "MISSING"
        stn_name_val = str(df.loc[idx, name_col]).strip() if name_col and name_col in df.columns else "MISSING"
        raw_date_val = str(df.loc[idx, date_col]) if date_col else "MISSING"

        invalid_rows.append({
            "row_index": int(idx),
            "station_code": stn_code_val,
            "station_name": stn_name_val,
            "raw_date": raw_date_val,
            "reason": "; ".join(reasons),
            "is_fatal_to_timeline": date_invalid_mask.loc[idx] or (code_missing_mask.loc[idx] and name_missing_mask.loc[idx]),
            "action_required": "Correct date or station identifier in source registry."
        })

    return pd.DataFrame(invalid_rows)


def detect_duplicate_station_dates(
    df: pd.DataFrame,
    column_mapping: Dict[str, Optional[str]],
    parsed_dates: Optional[pd.Series] = None
) -> pd.DataFrame:
    """
    Detect duplicate station-date observations.
    Categorizes duplicates into 'Exact Duplicate' (identical rainfall) or 'Conflicting Duplicate'.
    """
    date_col = column_mapping.get("date")
    code_col = column_mapping.get("station_code")
    name_col = column_mapping.get("station_name")
    rf_col = column_mapping.get("rainfall")

    if parsed_dates is None and date_col:
        parsed_dates = parse_observation_dates(df, date_col)

    # Build working grouping identifiers
    work = pd.DataFrame(index=df.index)
    work["_date"] = parsed_dates
    work["_code"] = df[code_col].astype(str).str.strip() if code_col and code_col in df.columns else (
        df[name_col].astype(str).str.strip() if name_col and name_col in df.columns else "DEFAULT"
    )
    work["_name"] = df[name_col].astype(str).str.strip() if name_col and name_col in df.columns else work["_code"]
    work["_rf"] = df[rf_col] if rf_col and rf_col in df.columns else np.nan
    work["_row_idx"] = df.index

    # Filter out records with invalid dates
    valid_work = work[work["_date"].notna()].copy()
    if valid_work.empty:
        return pd.DataFrame()

    # Find duplicates on (_code, _date)
    dup_mask = valid_work.duplicated(subset=["_code", "_date"], keep=False)
    if not dup_mask.any():
        return pd.DataFrame()

    dup_groups = valid_work[dup_mask].groupby(["_code", "_date"])
    dup_records: List[Dict[str, Any]] = []

    for (code_val, obs_date), group in dup_groups:
        unique_rfs = group["_rf"].dropna().unique()
        is_conflicting = len(unique_rfs) > 1
        stn_name = group["_name"].iloc[0]
        
        dup_records.append({
            "station_code": str(code_val),
            "station_name": str(stn_name),
            "observation_date": pd.to_datetime(obs_date).strftime("%Y-%m-%d"),
            "duplicate_count": len(group),
            "recorded_values": [float(x) for x in unique_rfs] if len(unique_rfs) > 0 else ["Missing"],
            "duplicate_type": "Conflicting Duplicate" if is_conflicting else "Exact Duplicate",
            "row_indices": group["_row_idx"].tolist(),
            "recommendation": "Consolidate duplicate records; check telemetry log for double submission."
        })

    return pd.DataFrame(dup_records)


def calculate_consecutive_missing_gaps(
    target: Any,
    second_arg: Any = None,
    third_arg: Any = None,
    frequency: str = "D"
) -> Any:
    """
    Calculate longest consecutive missing gap and list all continuous gap intervals.
    Supports two calling patterns:
    1. calculate_consecutive_missing_gaps(existing_dates_set, min_date, max_date, frequency='D')
       -> Returns Tuple[int, List[Dict[str, Any]]] (max_gap_days, list_of_gap_dicts)
    2. calculate_consecutive_missing_gaps(df, column_mapping, frequency='D')
       -> Returns pd.DataFrame of consecutive gaps across all stations
    """
    if isinstance(target, pd.DataFrame):
        df = target
        col_map = second_arg or match_checkpoint1_columns(df)
        date_col = col_map.get("date")
        code_col = col_map.get("station_code")
        name_col = col_map.get("station_name")
        freq = third_arg if isinstance(third_arg, str) else frequency

        parsed = parse_observation_dates(df, date_col) if date_col else pd.Series(dtype="datetime64[ns]")
        work = pd.DataFrame({
            "_date": parsed,
            "_code": df[code_col].astype(str).str.strip() if code_col and code_col in df.columns else (
                df[name_col].astype(str).str.strip() if name_col and name_col in df.columns else "DEFAULT"
            ),
            "_name": df[name_col].astype(str).str.strip() if name_col and name_col in df.columns else "DEFAULT"
        }).dropna(subset=["_date"])

        all_gaps = []
        for (stn_code, stn_name), group in work.groupby(["_code", "_name"]):
            dts = group["_date"].drop_duplicates().sort_values()
            if len(dts) < 2:
                continue
            min_d, max_d = dts.min(), dts.max()
            existing_set = set(dts.dt.date)
            _, gap_list = _calculate_gaps_from_set(existing_set, min_d, max_d, freq)
            for g in gap_list:
                all_gaps.append({
                    "station_code": str(stn_code),
                    "station_name": str(stn_name),
                    "gap_start": g["gap_start"],
                    "gap_end": g["gap_end"],
                    "gap_days": g["gap_days"]
                })
        return pd.DataFrame(all_gaps)

    # Calling pattern 1: existing_dates, min_date, max_date
    existing_dates = target
    min_date = second_arg
    max_date = third_arg
    return _calculate_gaps_from_set(existing_dates, min_date, max_date, frequency)


def _calculate_gaps_from_set(
    existing_dates: set,
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
    frequency: str = "D"
) -> Tuple[int, List[Dict[str, Any]]]:
    """Helper to calculate consecutive gap days from a date set."""
    if pd.isna(min_date) or pd.isna(max_date) or min_date > max_date:
        return 0, []

    full_range = pd.date_range(start=min_date, end=max_date, freq=frequency)
    missing_dates = [d.date() for d in full_range if d.date() not in existing_dates]

    if not missing_dates:
        return 0, []

    gaps: List[Dict[str, Any]] = []
    current_gap_start = missing_dates[0]
    current_length = 1

    for i in range(1, len(missing_dates)):
        diff_days = (missing_dates[i] - missing_dates[i - 1]).days
        if diff_days == 1:
            current_length += 1
        else:
            gaps.append({
                "gap_start": current_gap_start.strftime("%Y-%m-%d"),
                "gap_end": missing_dates[i - 1].strftime("%Y-%m-%d"),
                "gap_days": current_length
            })
            current_gap_start = missing_dates[i]
            current_length = 1

    gaps.append({
        "gap_start": current_gap_start.strftime("%Y-%m-%d"),
        "gap_end": missing_dates[-1].strftime("%Y-%m-%d"),
        "gap_days": current_length
    })

    max_gap = max(g["gap_days"] for g in gaps) if gaps else 0
    return max_gap, gaps


def assign_station_priority(
    summary: Any = None,
    thresholds: Any = None,
    *args,
    completeness_pct: Optional[float] = None,
    missing_days: Optional[int] = None,
    max_consecutive_gap: Optional[int] = None,
    duplicate_count: int = 0,
    invalid_date_count: int = 0,
    **kwargs
) -> Tuple[str, str, str]:
    """
    Assign priority (Critical, High, Medium, Low), concrete rationale, and recommended action.
    Supports:
    1. assign_station_priority(summary_dict_or_series, thresholds)
    2. assign_station_priority(completeness_pct=..., missing_days=..., thresholds=...)
    3. assign_station_priority(completeness_pct, missing_days, max_consecutive_gap, duplicate_count, invalid_date_count, thresholds)
    """
    if completeness_pct is not None:
        comp = float(completeness_pct)
        miss = int(missing_days) if missing_days is not None else 0
        gap = int(max_consecutive_gap) if max_consecutive_gap is not None else 0
        dup = int(duplicate_count)
        inv = int(invalid_date_count)
        thresh = thresholds if isinstance(thresholds, Checkpoint1Thresholds) else (
            kwargs.get("thresholds") if isinstance(kwargs.get("thresholds"), Checkpoint1Thresholds) else Checkpoint1Thresholds()
        )
    elif isinstance(summary, (dict, pd.Series)):
        data = summary
        thresh = thresholds if isinstance(thresholds, Checkpoint1Thresholds) else (
            kwargs.get("thresholds") if isinstance(kwargs.get("thresholds"), Checkpoint1Thresholds) else Checkpoint1Thresholds()
        )
        comp = float(data.get("data_completeness_pct", data.get("completeness_pct", 100.0)))
        miss = int(data.get("missing_calendar_days", data.get("missing_days", 0)))
        gap = int(data.get("max_consecutive_gap_days", data.get("max_consecutive_gap", 0)))
        dup = int(data.get("duplicate_records", data.get("duplicate_count", 0)))
        inv = int(data.get("invalid_date_records", data.get("invalid_date_count", 0)))
    else:
        comp = float(summary) if summary is not None else 100.0
        miss = int(thresholds) if thresholds is not None else 0
        gap = int(args[0]) if len(args) > 0 else 0
        dup = int(args[1]) if len(args) > 1 else 0
        inv = int(args[2]) if len(args) > 2 else 0
        thresh = args[3] if len(args) > 3 and isinstance(args[3], Checkpoint1Thresholds) else Checkpoint1Thresholds()

    reasons = []
    actions = []

    # Check Critical Conditions
    if comp < thresh.critical_completeness_pct:
        reasons.append(f"Severe data deficit (completeness {comp:.1f}% < {thresh.critical_completeness_pct}%)")
        actions.append("Audit station recording log and ingest supplemental historical records.")
    if gap >= thresh.critical_consecutive_gap_days:
        reasons.append(f"Extended transmission blackout of {gap} consecutive days")
        actions.append("Check station hardware / sensor continuity; apply multi-station spatial imputation.")
    if miss >= thresh.critical_missing_days:
        reasons.append(f"High cumulative missing volume ({miss} missing days)")

    if reasons:
        return "Critical", "; ".join(reasons), " ".join(actions) if actions else "Immediate station audit required."

    # Check High Conditions
    if comp < thresh.high_completeness_pct:
        reasons.append(f"Low completeness ({comp:.1f}% < {thresh.high_completeness_pct}%)")
    if gap >= thresh.high_consecutive_gap_days:
        reasons.append(f"Significant consecutive gap of {gap} days")
    if miss >= thresh.high_missing_days:
        reasons.append(f"{miss} missing days in observation window")
    if dup >= 10:
        reasons.append(f"Multiple duplicate records ({dup} duplicates)")
        actions.append("Investigate duplicate batch uploads and deduplicate station series.")

    if reasons:
        return "High", "; ".join(reasons), " ".join(actions) if actions else "Prioritize for historical missing-value estimation."

    # Check Medium Conditions
    if comp < thresh.medium_completeness_pct:
        reasons.append(f"Moderate missing observations ({comp:.1f}% completeness)")
    if gap >= thresh.medium_consecutive_gap_days:
        reasons.append(f"Moderate gap of {gap} consecutive days")
    if dup > 0:
        reasons.append(f"{dup} duplicate records detected")
    if inv > 0:
        reasons.append(f"{inv} records with unparseable dates")

    if reasons:
        return "Medium", "; ".join(reasons), "Routine verification and short-gap interpolation."

    # Low Priority (Healthy Station)
    if miss > 0:
        return "Low", f"Isolated {miss} missing days with {comp:.1f}% completeness.", "Apply short-gap interpolation or seasonal climatology."
    else:
        return "Low", "Complete continuous recording timeline with no missing days.", "Station records intact; proceed to Checkpoint 2."


def calculate_station_timeline_summary(
    df: pd.DataFrame,
    column_mapping: Dict[str, Optional[str]],
    frequency: str = "D",
    thresholds: Optional[Checkpoint1Thresholds] = None,
    parsed_dates: Optional[pd.Series] = None
) -> pd.DataFrame:
    """
    Calculate station-wise timeline summary metrics:
    - Station Code & Station Name
    - First & Last Recorded Dates
    - Expected Calendar Days = (Last - First).days + 1
    - Unique Valid Recorded Dates
    - Missing Calendar Days = Expected - Unique Valid Recorded Dates
    - Data Completeness (%) = (Unique Valid Recorded Dates / Expected) * 100
    - Duplicate Records Count
    - Invalid Date Records Count
    - Missing Rainfall Values Count
    - Longest Consecutive Missing Gap
    - Priority Level & Issue Description
    """
    thresholds = thresholds or Checkpoint1Thresholds()
    date_col = column_mapping.get("date")
    code_col = column_mapping.get("station_code")
    name_col = column_mapping.get("station_name")
    rf_col = column_mapping.get("rainfall")

    if parsed_dates is None and date_col:
        parsed_dates = parse_observation_dates(df, date_col)

    # Build working dataframe
    work = pd.DataFrame(index=df.index)
    work["_date"] = parsed_dates
    work["_code"] = (
        df[code_col].astype(str).str.strip()
        if code_col and code_col in df.columns
        else (df[name_col].astype(str).str.strip() if name_col and name_col in df.columns else "STN_DEFAULT")
    )
    work["_name"] = (
        df[name_col].astype(str).str.strip()
        if name_col and name_col in df.columns
        else work["_code"]
    )
    work["_rf"] = df[rf_col] if rf_col and rf_col in df.columns else np.nan

    # Identify invalid records count per station
    invalid_mask = work["_date"].isna()
    invalid_by_stn = work[invalid_mask].groupby(["_code", "_name"]).size().to_dict()

    # Filter to valid dates for station timeline calculation
    valid_work = work[~invalid_mask].copy()
    if valid_work.empty:
        return pd.DataFrame()

    # Detect duplicates
    dup_counts = (
        valid_work.groupby(["_code", "_name", "_date"]).size() - 1
    ).clip(lower=0).groupby(["_code", "_name"]).sum().to_dict()

    # Missing rainfall values on valid dates
    missing_rf_counts = (
        valid_work[valid_work["_rf"].isna() | valid_work["_rf"].isin([-99, -99.0, -999, -999.0])]
        .groupby(["_code", "_name"])
        .size()
        .to_dict()
    )

    summaries: List[Dict[str, Any]] = []

    # Group by both station code and station name
    station_groups = valid_work.groupby(["_code", "_name"])

    for (stn_code, stn_name), group in station_groups:
        unique_dates_series = group["_date"].dropna().drop_duplicates().sort_values()
        unique_valid_dates = len(unique_dates_series)
        
        if unique_valid_dates == 0:
            continue

        min_d = unique_dates_series.min()
        max_d = unique_dates_series.max()

        # Expected calendar days = (Last - First).days + 1
        expected_days = (max_d - min_d).days + 1 if frequency == "D" else unique_valid_dates
        expected_days = max(1, expected_days)

        missing_days = max(0, expected_days - unique_valid_dates)
        completeness_pct = (unique_valid_dates / expected_days) * 100.0

        existing_date_set = set(d.date() for d in unique_dates_series)
        max_gap, _ = calculate_consecutive_missing_gaps(existing_date_set, min_d, max_d, frequency=frequency)

        dup_cnt = int(dup_counts.get((stn_code, stn_name), 0))
        inv_cnt = int(invalid_by_stn.get((stn_code, stn_name), 0))
        miss_rf_cnt = int(missing_rf_counts.get((stn_code, stn_name), 0))

        priority, reason, action = assign_station_priority(
            completeness_pct=completeness_pct,
            missing_days=missing_days,
            max_consecutive_gap=max_gap,
            duplicate_count=dup_cnt,
            invalid_date_count=inv_cnt,
            thresholds=thresholds
        )

        summaries.append({
            "station_code": str(stn_code),
            "station_name": str(stn_name),
            "first_recorded_date": min_d.strftime("%Y-%m-%d"),
            "last_recorded_date": max_d.strftime("%Y-%m-%d"),
            "expected_calendar_days": int(expected_days),
            "unique_recorded_dates": int(unique_valid_dates),
            "missing_calendar_days": int(missing_days),
            "data_completeness_pct": round(completeness_pct, 2),
            "max_consecutive_gap_days": int(max_gap),
            "duplicate_records": dup_cnt,
            "invalid_date_records": inv_cnt,
            "missing_rainfall_values": miss_rf_cnt,
            "priority_level": priority,
            "issue_description": reason,
            "recommended_action": action
        })

    summary_df = pd.DataFrame(summaries)
    if not summary_df.empty:
        # Default sorting: highest missing calendar days first
        summary_df.sort_values(
            by=["missing_calendar_days", "data_completeness_pct"],
            ascending=[False, True],
            inplace=True
        )
        summary_df.reset_index(drop=True, inplace=True)

    return summary_df


def identify_missing_station_dates(
    df: pd.DataFrame,
    column_mapping: Dict[str, Optional[str]],
    frequency: str = "D",
    parsed_dates: Optional[pd.Series] = None
) -> pd.DataFrame:
    """
    Generate detailed line-item records for every specific calendar date
    missing from each station's continuous observation window.
    """
    date_col = column_mapping.get("date")
    code_col = column_mapping.get("station_code")
    name_col = column_mapping.get("station_name")

    if parsed_dates is None and date_col:
        parsed_dates = parse_observation_dates(df, date_col)

    work = pd.DataFrame(index=df.index)
    work["_date"] = parsed_dates
    work["_code"] = (
        df[code_col].astype(str).str.strip()
        if code_col and code_col in df.columns
        else (df[name_col].astype(str).str.strip() if name_col and name_col in df.columns else "DEFAULT")
    )
    work["_name"] = (
        df[name_col].astype(str).str.strip()
        if name_col and name_col in df.columns
        else work["_code"]
    )

    valid_work = work[work["_date"].notna()]
    if valid_work.empty:
        return pd.DataFrame()

    missing_items: List[Dict[str, Any]] = []

    for (stn_code, stn_name), group in valid_work.groupby(["_code", "_name"]):
        unique_dts = group["_date"].drop_duplicates().sort_values()
        if len(unique_dts) < 2:
            continue

        min_d = unique_dts.min()
        max_d = unique_dts.max()
        full_range = pd.date_range(start=min_d, end=max_d, freq=frequency)
        existing_set = set(unique_dts.dt.date)

        gap_id = 0
        in_gap = False
        consec_count = 0

        # Pass 1: detect gaps
        gap_blocks = []
        cur_block = []
        for dt_val in full_range:
            if dt_val.date() not in existing_set:
                cur_block.append(dt_val)
            else:
                if cur_block:
                    gap_blocks.append(cur_block)
                    cur_block = []
        if cur_block:
            gap_blocks.append(cur_block)

        # Build records
        for gid, block in enumerate(gap_blocks, 1):
            block_len = len(block)
            for dt_miss in block:
                missing_items.append({
                    "station_code": str(stn_code),
                    "station_name": str(stn_name),
                    "missing_date": dt_miss.strftime("%Y-%m-%d"),
                    "year": int(dt_miss.year),
                    "month": int(dt_miss.month),
                    "gap_id": gid,
                    "consecutive_gap_length": block_len,
                    "status": "Missing Observation Date",
                    "provenance": "Timeline Continuity Check"
                })

    return pd.DataFrame(missing_items)


def generate_checkpoint1_report(
    df: pd.DataFrame,
    column_mapping: Optional[Dict[str, Optional[str]]] = None,
    thresholds: Optional[Checkpoint1Thresholds] = None,
    frequency: str = "D"
) -> Dict[str, Any]:
    """
    Main entrypoint for Checkpoint 1: Station Timeline and Missing-Day Validation.
    Returns:
        station_summary: DataFrame
        missing_dates_detail: DataFrame
        invalid_records: DataFrame
        duplicate_records: DataFrame
        metrics: Dict[str, Any]
        column_mapping: Dict[str, str]
        warnings_and_errors: List[str]
    """
    thresholds = thresholds or Checkpoint1Thresholds()
    warnings: List[str] = []

    # 1. Column matching & schema validation
    resolved_mapping = match_checkpoint1_columns(df, column_mapping)
    is_valid_schema, missing_cols = validate_required_columns(df, resolved_mapping)

    if not is_valid_schema:
        return {
            "is_valid_schema": False,
            "station_summary": pd.DataFrame(),
            "missing_dates_detail": pd.DataFrame(),
            "invalid_records": pd.DataFrame(),
            "duplicate_records": pd.DataFrame(),
            "metrics": {},
            "column_mapping": resolved_mapping,
            "warnings_and_errors": [f"Missing required column: {c}" for c in missing_cols]
        }

    # 2. Parse dates non-destructively
    date_col = resolved_mapping["date"]
    parsed_dates = parse_observation_dates(df, date_col)

    # 3. Identify invalid records (without dropping them silently)
    invalid_df = identify_invalid_records(df, resolved_mapping, parsed_dates=parsed_dates)
    if not invalid_df.empty:
        warnings.append(f"Identified {len(invalid_df)} records with invalid or missing essential fields.")

    # 4. Duplicate station-dates
    duplicates_df = detect_duplicate_station_dates(df, resolved_mapping, parsed_dates=parsed_dates)
    if not duplicates_df.empty:
        warnings.append(f"Detected {len(duplicates_df)} duplicate station-date instances.")

    # 5. Station Timeline Summary
    summary_df = calculate_station_timeline_summary(
        df, resolved_mapping, frequency=frequency, thresholds=thresholds, parsed_dates=parsed_dates
    )

    # 6. Detailed missing dates
    missing_dates_df = identify_missing_station_dates(
        df, resolved_mapping, frequency=frequency, parsed_dates=parsed_dates
    )

    # 7. Overall Checkpoint 1 KPI Metrics
    total_stations = len(summary_df)
    total_valid_obs = int(summary_df["unique_recorded_dates"].sum()) if not summary_df.empty else 0
    total_expected_days = int(summary_df["expected_calendar_days"].sum()) if not summary_df.empty else 0
    total_missing_days = int(summary_df["missing_calendar_days"].sum()) if not summary_df.empty else 0
    overall_completeness = (
        round((total_valid_obs / total_expected_days) * 100.0, 2)
        if total_expected_days > 0 else 0.0
    )
    
    crit_stns = int((summary_df["priority_level"] == "Critical").sum()) if not summary_df.empty else 0
    high_stns = int((summary_df["priority_level"] == "High").sum()) if not summary_df.empty else 0
    med_stns = int((summary_df["priority_level"] == "Medium").sum()) if not summary_df.empty else 0
    low_stns = int((summary_df["priority_level"] == "Low").sum()) if not summary_df.empty else 0
    stations_attention = crit_stns + high_stns + med_stns

    metrics = {
        "total_stations": total_stations,
        "total_valid_obs": total_valid_obs,
        "total_expected_days": total_expected_days,
        "total_missing_days": total_missing_days,
        "overall_completeness_pct": overall_completeness,
        "duplicate_records_count": len(duplicates_df),
        "invalid_records_count": len(invalid_df),
        "stations_requiring_attention": stations_attention,
        "critical_stations_count": crit_stns,
        "high_stations_count": high_stns,
        "medium_stations_count": med_stns,
        "low_stations_count": low_stns,
        "execution_timestamp": datetime.now().isoformat()
    }

    return {
        "is_valid_schema": True,
        "station_summary": summary_df,
        "missing_dates_detail": missing_dates_df,
        "invalid_records": invalid_df,
        "duplicate_records": duplicates_df,
        "metrics": metrics,
        "column_mapping": resolved_mapping,
        "warnings_and_errors": warnings
    }
