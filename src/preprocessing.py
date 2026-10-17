"""Data Profiling and Preprocessing Engine for KWRIS Rainfall Data."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from src.models import DatasetProfile


def profile_raw_and_normalized_data(
    df_raw: pd.DataFrame,
    df_norm: pd.DataFrame,
    file_name: str,
    file_size_bytes: int,
    layout: str
) -> DatasetProfile:
    """
    Generate comprehensive profile of the uploaded and normalized dataset.
    """
    stn_ids = [str(x) for x in df_norm["station_id"].dropna().unique().tolist()]
    stn_names = [str(x) for x in df_norm["station_name"].dropna().unique().tolist()]
    
    valid_dates = df_norm["date"].dropna()
    min_date = valid_dates.min() if not valid_dates.empty else None
    max_date = valid_dates.max() if not valid_dates.empty else None
    
    # Calculate expected dates if date range is valid
    if min_date and max_date:
        total_unique_dates = df_norm["date"].nunique()
    else:
        total_unique_dates = 0
        
    # Duplicates check
    dup_rows = df_raw.duplicated().sum()
    dup_station_dates = df_norm.duplicated(subset=["station_id", "date"]).sum()
    
    # Missing cells
    missing_rf = df_norm["rainfall_mm"].isna().sum()
    
    # Negatives (< 0)
    negative_rf = (df_norm["rainfall_mm"] < 0).sum()
    
    # Placeholder values (-99, etc.)
    # In normalized data, these were converted to NaN, but let's check raw
    placeholder_count = 0
    for val in [-99, -99.0, -999, -999.0, -9999, 9999]:
        try:
            placeholder_count += (df_raw == val).sum().sum()
        except Exception:
            pass
            
    # Completeness percentage: (total valid observations / total expected records)
    total_records = len(df_norm)
    valid_records = df_norm["rainfall_mm"].notna().sum()
    completeness = (valid_records / total_records * 100.0) if total_records > 0 else 0.0
    
    has_coords = df_norm["latitude"].notna().any() and df_norm["longitude"].notna().any()
    
    return DatasetProfile(
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        row_count=len(df_raw),
        column_count=len(df_raw.columns),
        stations_count=len(stn_names),
        station_ids=stn_ids,
        station_names=stn_names,
        min_date=min_date,
        max_date=max_date,
        total_dates=total_unique_dates,
        detected_format=layout,
        duplicate_rows_count=int(dup_rows),
        duplicate_station_dates_count=int(dup_station_dates),
        missing_cells_count=int(missing_rf),
        negative_values_count=int(negative_rf),
        placeholder_values_count=int(placeholder_count),
        completeness_pct=round(completeness, 2),
        units_detected="mm",
        has_coordinates=bool(has_coords)
    )


def detect_date_gaps(df_norm: pd.DataFrame) -> pd.DataFrame:
    """
    Detect missing observation dates per station assuming daily records.
    Returns DataFrame of missing dates per station.
    """
    gap_records = []
    
    for stn, stn_df in df_norm.groupby("station_name"):
        valid_dates = stn_df["date"].dropna().sort_values()
        if len(valid_dates) < 2:
            continue
        min_d = valid_dates.min()
        max_d = valid_dates.max()
        full_date_range = pd.date_range(min_d, max_d, freq="D")
        actual_dates = set(valid_dates.dt.normalize())
        missing_dates = [d for d in full_date_range if d not in actual_dates]
        
        for md in missing_dates:
            gap_records.append({
                "station_name": stn,
                "station_id": stn_df["station_id"].iloc[0],
                "missing_date": md,
                "reason": "Missing date in time sequence"
            })
            
    return pd.DataFrame(gap_records)
