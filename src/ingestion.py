"""Robust File Ingestion and Dataset Normalization for RainfallIQ."""

from __future__ import annotations
import io
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import pandas as pd
import numpy as np

from src.configuration import APP_CONFIG
from src.schema_detection import (
    detect_columns,
    detect_dataset_format,
    convert_wide_to_long,
    detect_observation_frequency,
    detect_unit_from_headers_or_values
)


def get_excel_sheet_names(file_or_path: Union[str, Path, io.BytesIO]) -> List[str]:
    """Retrieve all sheet names from an Excel file safely."""
    try:
        excel_file = pd.ExcelFile(file_or_path)
        return excel_file.sheet_names
    except Exception as e:
        return ["Default"]


def read_raw_data(
    file_or_path: Union[str, Path, io.BytesIO],
    filename: str,
    sheet_name: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Read CSV or Excel file into a raw DataFrame with metadata.
    Handles encoding fallback, header cleaning, and sheet selection.
    """
    ext = Path(filename).suffix.lower()
    df = pd.DataFrame()
    metadata: Dict[str, Any] = {
        "filename": filename,
        "extension": ext,
        "sheet_name": sheet_name,
        "encoding": "utf-8",
        "raw_rows": 0,
        "raw_cols": 0
    }

    if ext in [".xlsx", ".xls"]:
        sheets = get_excel_sheet_names(file_or_path)
        metadata["available_sheets"] = sheets
        selected_sheet = sheet_name if sheet_name in sheets else sheets[0]
        metadata["sheet_name"] = selected_sheet
        df = pd.read_excel(file_or_path, sheet_name=selected_sheet)
    elif ext == ".csv":
        # Encoding fallbacks
        encodings = ["utf-8", "latin-1", "cp1252"]
        success = False
        for enc in encodings:
            try:
                if hasattr(file_or_path, "seek"):
                    file_or_path.seek(0)
                df = pd.read_csv(file_or_path, encoding=enc, low_memory=False)
                metadata["encoding"] = enc
                success = True
                break
            except (UnicodeDecodeError, Exception):
                continue
        if not success:
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(0)
            df = pd.read_csv(file_or_path, encoding="utf-8", errors="replace", low_memory=False)
            metadata["encoding"] = "utf-8 (lossy)"
    else:
        raise ValueError(f"Unsupported file format: {ext}. Please upload a .csv or .xlsx file.")

    # Drop completely empty rows and columns
    df.dropna(how="all", inplace=True)
    df.dropna(how="all", axis=1, inplace=True)

    metadata["raw_rows"] = len(df)
    metadata["raw_cols"] = len(df.columns)
    metadata["raw_columns"] = list(df.columns)

    return df, metadata


def clean_missing_codes(series: pd.Series) -> pd.Series:
    """Replace configured missing value codes (-99, -999, 'NA', etc.) with NaN."""
    s = series.copy()
    missing_codes = APP_CONFIG.get("missing_codes", [])
    
    # Direct replacement
    s = s.replace(missing_codes, np.nan)
    
    # String pattern matching for string objects
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        s = s.apply(
            lambda x: np.nan if str(x).strip().upper() in ["NA", "NAN", "NULL", "-", "--", "NR", "NONE"] else x
        )
    return s


def normalize_rainfall_dataset(
    df: pd.DataFrame,
    column_mapping: Dict[str, Optional[str]],
    unit: str = "mm",
    format_type: str = "long"
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Standardize DataFrame into a unified schema:
    [date, station_id, station_name, rainfall, district, state, latitude, longitude, unit]
    Preserves original values in 'original_rainfall'.
    """
    date_col = column_mapping.get("date")
    if not date_col or date_col not in df.columns:
        raise ValueError("A valid 'date' column must be identified.")

    work_df = df.copy()

    # Handle wide format transformation if applicable
    if format_type == "wide":
        station_cols = [c for c in df.columns if c != date_col]
        work_df = convert_wide_to_long(work_df, date_col, station_cols, unit=unit)
        station_id_col = "station_id"
        station_name_col = "station_name"
        rainfall_col = "rainfall"
    else:
        station_id_col = column_mapping.get("station_id")
        station_name_col = column_mapping.get("station_name")
        rainfall_col = column_mapping.get("rainfall")

        if not rainfall_col or rainfall_col not in work_df.columns:
            raise ValueError("A valid 'rainfall' column must be identified.")

    # Create standardized dataframe
    norm_df = pd.DataFrame()
    
    # 1. Date parsing
    norm_df["date"] = pd.to_datetime(work_df[date_col], errors="coerce")
    
    # 2. Station ID and Name
    if station_id_col and station_id_col in work_df.columns:
        norm_df["station_id"] = work_df[station_id_col].astype(str).str.strip()
    else:
        norm_df["station_id"] = "STN_DEFAULT"

    if station_name_col and station_name_col in work_df.columns:
        norm_df["station_name"] = work_df[station_name_col].astype(str).str.strip()
    else:
        norm_df["station_name"] = norm_df["station_id"]

    # 3. Rainfall processing
    raw_rf_series = work_df[rainfall_col]
    norm_df["original_rainfall"] = raw_rf_series  # Exact original preservation
    
    cleaned_rf = clean_missing_codes(raw_rf_series)
    norm_df["rainfall"] = pd.to_numeric(cleaned_rf, errors="coerce")

    # Unit conversion to mm if needed
    unit_multiplier = APP_CONFIG["unit_conversion_to_mm"].get(unit.lower(), 1.0)
    if unit_multiplier != 1.0:
        norm_df["rainfall"] = norm_df["rainfall"] * unit_multiplier
        norm_df["unit"] = "mm"
        norm_df["original_unit"] = unit
    else:
        norm_df["unit"] = unit
        norm_df["original_unit"] = unit

    # 4. Optional Metadata Columns
    opt_cols = ["district", "state", "latitude", "longitude", "gauge_type"]
    for opt in opt_cols:
        mapped_col = column_mapping.get(opt)
        if mapped_col and mapped_col in work_df.columns:
            if opt in ["latitude", "longitude"]:
                norm_df[opt] = pd.to_numeric(work_df[mapped_col], errors="coerce")
            else:
                norm_df[opt] = work_df[mapped_col].astype(str).str.strip()
        else:
            norm_df[opt] = np.nan

    # Calculate dataset summary metrics
    valid_dates = norm_df["date"].dropna()
    summary: Dict[str, Any] = {
        "total_records": len(norm_df),
        "total_stations": norm_df["station_id"].nunique(),
        "start_date": valid_dates.min().strftime("%Y-%m-%d") if not valid_dates.empty else "N/A",
        "end_date": valid_dates.max().strftime("%Y-%m-%d") if not valid_dates.empty else "N/A",
        "frequency": detect_observation_frequency(norm_df["date"]),
        "missing_rainfall_count": int(norm_df["rainfall"].isna().sum()),
        "valid_rainfall_count": int(norm_df["rainfall"].notna().sum()),
        "zero_rainfall_count": int((norm_df["rainfall"] == 0.0).sum()),
        "max_rainfall_mm": float(norm_df["rainfall"].max()) if norm_df["rainfall"].notna().any() else 0.0,
        "mean_rainfall_mm": float(norm_df["rainfall"].mean()) if norm_df["rainfall"].notna().any() else 0.0
    }

    return norm_df, summary
