"""Rainfall Data Ingestion and Normalization Module for KWRIS."""

from __future__ import annotations
import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from src.reference_data import lookup_station_coordinates


# Common missing indicators in Indian meteorological and water resource datasets
DEFAULT_MISSING_CODES = [-99, -99.0, -999, -999.0, -9999, 9999, "NA", "NaN", "null", "NULL", "-", "--", "NR"]


def detect_file_sheets(file_or_path: Any) -> List[str]:
    """Detect available sheet names for Excel files or return empty list for CSV."""
    if isinstance(file_or_path, str) and file_or_path.lower().endswith(".csv"):
        return []
    try:
        xl = pd.ExcelFile(file_or_path)
        return xl.sheet_names
    except Exception:
        return []


def read_raw_dataset(
    file_or_path: Any,
    sheet_name: Optional[Union[str, int]] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Read raw Excel or CSV into a DataFrame and return file metadata.
    Preserves exact raw contents without modification.
    """
    meta: Dict[str, Any] = {"format": "unknown"}
    
    # Check if string path
    if isinstance(file_or_path, str):
        meta["file_name"] = file_or_path.split("/")[-1].split("\\")[-1]
        if file_or_path.lower().endswith(".csv"):
            meta["format"] = "csv"
            df = pd.read_csv(file_or_path)
        else:
            meta["format"] = "excel"
            xl = pd.ExcelFile(file_or_path)
            meta["sheet_names"] = xl.sheet_names
            target_sheet = sheet_name if sheet_name is not None else xl.sheet_names[0]
            meta["selected_sheet"] = target_sheet
            df = pd.read_excel(file_or_path, sheet_name=target_sheet)
    else:
        # Streamlit UploadedFile or BytesIO
        file_name = getattr(file_or_path, "name", "uploaded_data")
        meta["file_name"] = file_name
        if file_name.lower().endswith(".csv"):
            meta["format"] = "csv"
            df = pd.read_csv(file_or_path)
        else:
            meta["format"] = "excel"
            xl = pd.ExcelFile(file_or_path)
            meta["sheet_names"] = xl.sheet_names
            target_sheet = sheet_name if sheet_name is not None else xl.sheet_names[0]
            meta["selected_sheet"] = target_sheet
            df = pd.read_excel(file_or_path, sheet_name=target_sheet)
            
    meta["raw_rows"] = len(df)
    meta["raw_cols"] = len(df.columns)
    meta["columns"] = df.columns.tolist()
    return df, meta


def detect_data_layout(df: pd.DataFrame) -> str:
    """
    Detect whether DataFrame is in 'long' format (station, date, rainfall columns)
    or 'wide' format (date column + station columns).
    """
    col_names = [str(c).lower().strip() for c in df.columns]
    
    # Check for long-format keywords
    has_rf_col = any(any(k in c for k in ["rf", "rain", "precip", "value", "rainfall"]) for c in col_names)
    has_station_col = any(any(k in c for k in ["station", "location", "wims", "site", "gauge"]) for c in col_names)
    
    if has_rf_col and has_station_col:
        return "long"
        
    # Check if there is a date column and multiple numeric columns
    date_col_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["date", "day", "time", "timestamp"])]
    if date_col_candidates:
        other_cols = [c for c in df.columns if c != date_col_candidates[0]]
        # If there are many other columns (>= 3) and mostly numeric
        numeric_count = sum(pd.api.types.is_numeric_dtype(df[c]) for c in other_cols)
        if len(other_cols) >= 2 and numeric_count / max(1, len(other_cols)) >= 0.5:
            return "wide"
            
    return "long" if has_rf_col else "wide"


def suggest_column_mappings(df: pd.DataFrame, layout: str = "long") -> Dict[str, Optional[str]]:
    """
    Suggest intelligent column mappings based on common KWRIS and hydrological naming conventions.
    """
    mapping: Dict[str, Optional[str]] = {
        "station_id": None,
        "station_name": None,
        "date": None,
        "rainfall": None,
        "unit": None,
        "gauge_type": None,
        "latitude": None,
        "longitude": None,
        "basin": None,
        "subbasin": None
    }
    
    cols = df.columns.tolist()
    cols_lower = {str(c).lower().strip(): c for c in cols}
    
    # Date mapping
    for pat in ["day", "date", "timestamp", "obs_date", "reading_date", "datetime"]:
        for cl, orig in cols_lower.items():
            if pat == cl or pat in cl:
                mapping["date"] = orig
                break
        if mapping["date"]:
            break
            
    if layout == "long":
        # Station ID (e.g. WIMS Code, Station_ID, StnID)
        for pat in ["wims code", "wims_code", "station_id", "stn_id", "station code", "stationid", "id"]:
            for cl, orig in cols_lower.items():
                if pat == cl or pat in cl:
                    mapping["station_id"] = orig
                    break
            if mapping["station_id"]:
                break
                
        # Station Name (e.g. LocationName, StationName, Station)
        for pat in ["locationname", "stationname", "location_name", "station_name", "location", "station", "stn_name"]:
            for cl, orig in cols_lower.items():
                if pat == cl or pat in cl:
                    mapping["station_name"] = orig
                    break
            if mapping["station_name"]:
                break
                
        # Rainfall value (e.g. RF(mm), Rainfall, Rain_mm, Precip)
        for pat in ["rf(mm)", "rf (mm)", "rf_mm", "rainfall(mm)", "rainfall", "rf", "precipitation", "precip", "value"]:
            for cl, orig in cols_lower.items():
                if pat == cl or pat in cl:
                    mapping["rainfall"] = orig
                    break
            if mapping["rainfall"]:
                break

    # Basin / Subbasin
    for pat in ["basinname", "basin_name", "basin"]:
        for cl, orig in cols_lower.items():
            if pat == cl or pat in cl:
                mapping["basin"] = orig
                break
        if mapping["basin"]:
            break

    for pat in ["subbasinname", "subbasin_name", "subbasin", "sub_basin"]:
        for cl, orig in cols_lower.items():
            if pat == cl or pat in cl:
                mapping["subbasin"] = orig
                break
        if mapping["subbasin"]:
            break

    # Latitude / Longitude
    for pat in ["latitude", "lat", "y"]:
        for cl, orig in cols_lower.items():
            if pat == cl or cl.startswith("lat"):
                mapping["latitude"] = orig
                break
        if mapping["latitude"]:
            break

    for pat in ["longitude", "lon", "long", "x"]:
        for cl, orig in cols_lower.items():
            if pat == cl or cl.startswith("lon") or cl.startswith("long"):
                mapping["longitude"] = orig
                break
        if mapping["longitude"]:
            break

    # Gauge type
    for pat in ["gauge_type", "gaugetype", "gauge", "instrument", "type"]:
        for cl, orig in cols_lower.items():
            if pat == cl or pat in cl:
                mapping["gauge_type"] = orig
                break
        if mapping["gauge_type"]:
            break

    return mapping


def normalize_dataset(
    df_raw: pd.DataFrame,
    layout: str,
    mapping: Dict[str, Optional[str]],
    missing_codes: Optional[List[Any]] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Normalize raw DataFrame into standard long format schema:
    [original_row_id, station_id, station_name, date, rainfall_mm, gauge_type, latitude, longitude, basin, subbasin]
    """
    if missing_codes is None:
        missing_codes = DEFAULT_MISSING_CODES
        
    audit_meta: Dict[str, Any] = {
        "layout": layout,
        "input_rows": len(df_raw),
        "missing_codes_used": missing_codes,
        "warnings": []
    }
    
    if layout == "wide":
        # Date column
        date_col = mapping.get("date")
        if not date_col or date_col not in df_raw.columns:
            # Fallback to first column
            date_col = df_raw.columns[0]
            
        station_cols = [c for c in df_raw.columns if c != date_col]
        
        # Melt wide into long
        melted = df_raw.melt(
            id_vars=[date_col],
            value_vars=station_cols,
            var_name="station_name",
            value_name="rainfall_raw"
        )
        melted["station_id"] = melted["station_name"]
        melted["date_raw"] = melted[date_col]
        melted["gauge_type"] = "manual"
        melted["basin"] = None
        melted["subbasin"] = None
        melted["latitude"] = np.nan
        melted["longitude"] = np.nan
        melted["original_row_id"] = melted.index
        df_work = melted
        
    else:  # long layout
        df_work = pd.DataFrame()
        df_work["original_row_id"] = df_raw.index
        
        # Date
        date_col = mapping.get("date")
        if date_col and date_col in df_raw.columns:
            df_work["date_raw"] = df_raw[date_col]
        else:
            raise ValueError("Observation date column is required and could not be identified.")
            
        # Station Name / ID
        stn_name_col = mapping.get("station_name")
        stn_id_col = mapping.get("station_id")
        
        if stn_name_col and stn_name_col in df_raw.columns:
            df_work["station_name"] = df_raw[stn_name_col].astype(str).str.strip()
        elif stn_id_col and stn_id_col in df_raw.columns:
            df_work["station_name"] = df_raw[stn_id_col].astype(str).str.strip()
        else:
            df_work["station_name"] = "STATION_1"
            audit_meta["warnings"].append("No station name column found; assigned default 'STATION_1'.")
            
        if stn_id_col and stn_id_col in df_raw.columns:
            df_work["station_id"] = df_raw[stn_id_col].astype(str).str.strip()
        else:
            df_work["station_id"] = df_work["station_name"]
            
        # Rainfall
        rf_col = mapping.get("rainfall")
        if rf_col and rf_col in df_raw.columns:
            df_work["rainfall_raw"] = df_raw[rf_col]
        else:
            raise ValueError("Rainfall value column is required and could not be identified.")
            
        # Gauge type
        gt_col = mapping.get("gauge_type")
        if gt_col and gt_col in df_raw.columns:
            df_work["gauge_type"] = df_raw[gt_col].astype(str).str.lower().str.strip()
        else:
            df_work["gauge_type"] = "manual"
            
        # Basin / Subbasin
        basin_col = mapping.get("basin")
        df_work["basin"] = df_raw[basin_col] if basin_col and basin_col in df_raw.columns else None
        
        subbasin_col = mapping.get("subbasin")
        df_work["subbasin"] = df_raw[subbasin_col] if subbasin_col and subbasin_col in df_raw.columns else None
        
        # Coordinates
        lat_col = mapping.get("latitude")
        df_work["latitude"] = pd.to_numeric(df_raw[lat_col], errors="coerce") if lat_col and lat_col in df_raw.columns else np.nan
        
        lon_col = mapping.get("longitude")
        df_work["longitude"] = pd.to_numeric(df_raw[lon_col], errors="coerce") if lon_col and lon_col in df_raw.columns else np.nan

    # Parse Dates safely
    df_work["date"] = pd.to_datetime(df_work["date_raw"], errors="coerce")
    invalid_dates_count = df_work["date"].isna().sum()
    if invalid_dates_count > 0:
        audit_meta["warnings"].append(f"Detected {invalid_dates_count} invalid or unparseable dates.")

    # Process Rainfall values and missing codes
    # Keep zero distinct from missing
    clean_rf = df_work["rainfall_raw"].copy()
    
    # Mask known missing codes
    for mc in missing_codes:
        try:
            clean_rf = clean_rf.replace(mc, np.nan)
        except Exception:
            pass
            
    # Convert string numbers to float, invalid strings to NaN
    df_work["rainfall_mm"] = pd.to_numeric(clean_rf, errors="coerce")

    # If coordinates are missing, attempt lookup from built-in catalog
    missing_coords_mask = df_work["latitude"].isna() | df_work["longitude"].isna()
    if missing_coords_mask.any():
        for stn in df_work.loc[missing_coords_mask, "station_name"].unique():
            coords = lookup_station_coordinates(stn)
            if coords:
                lat, lon = coords
                stn_mask = df_work["station_name"] == stn
                df_work.loc[stn_mask & df_work["latitude"].isna(), "latitude"] = lat
                df_work.loc[stn_mask & df_work["longitude"].isna(), "longitude"] = lon

    audit_meta["output_rows"] = len(df_work)
    audit_meta["stations_found"] = df_work["station_name"].nunique()
    audit_meta["valid_rainfall_rows"] = df_work["rainfall_mm"].notna().sum()
    audit_meta["missing_rainfall_rows"] = df_work["rainfall_mm"].isna().sum()
    
    final_cols = [
        "original_row_id", "station_id", "station_name", "date", 
        "rainfall_mm", "gauge_type", "latitude", "longitude", "basin", "subbasin"
    ]
    return df_work[final_cols].copy(), audit_meta
