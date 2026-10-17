"""Automatic Schema and Column Detection for Rainfall Datasets."""

from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np


# Candidate keyword patterns for automatic detection (case-insensitive)
COLUMN_PATTERNS = {
    "date": [
        r"^date$", r"^datetime$", r"^timestamp$", r"^time$", r"^dt$",
        r"obs.*date", r"reading.*date", r"rf.*date", r"rain.*date",
        r"^day$", r"^dates$"
    ],
    "station_id": [
        r"^station_?id$", r"^stn_?id$", r"^stationid$", r"^stnid$",
        r"^station_?code$", r"^stn_?code$", r"^id$", r"^code$",
        r"^site_?id$", r"^gauge_?id$"
    ],
    "station_name": [
        r"^station_?name$", r"^stn_?name$", r"^stationname$",
        r"^station$", r"^stn$", r"^place$", r"^location$", r"^site_?name$"
    ],
    "rainfall": [
        r"^rainfall", r"^rain", r"^rf$", r"^rf_.*", r"^precip",
        r"^precipitation", r"^value$", r"^reading$", r"^val$",
        r"^amount$", r"^daily_?rf", r"^daily_?rain"
    ],
    "latitude": [
        r"^lat$", r"^latitude$", r"^lat_dec$", r"^y$"
    ],
    "longitude": [
        r"^lon$", r"^long$", r"^longitude$", r"^lon_dec$", r"^lng$", r"^x$"
    ],
    "district": [
        r"^district$", r"^dist$", r"^taluk$", r"^taluka$", r"^region$"
    ],
    "state": [
        r"^state$", r"^province$"
    ],
    "gauge_type": [
        r"^gauge_?type$", r"^type$", r"^instrument$"
    ]
}


def match_column(col_name: str, patterns: List[str]) -> bool:
    """Check if column name matches any of regex patterns."""
    clean = str(col_name).strip().lower().replace(" ", "_")
    for pat in patterns:
        if re.search(pat, clean):
            return True
    return False


def detect_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """Automatically map standard fields to uploaded dataset columns."""
    mapping: Dict[str, Optional[str]] = {
        "date": None,
        "station_id": None,
        "station_name": None,
        "rainfall": None,
        "latitude": None,
        "longitude": None,
        "district": None,
        "state": None,
        "gauge_type": None
    }

    used_cols = set()

    # Priority order for detection
    priority_order = [
        "date", "rainfall", "station_id", "station_name",
        "latitude", "longitude", "district", "state", "gauge_type"
    ]

    for field_key in priority_order:
        patterns = COLUMN_PATTERNS.get(field_key, [])
        for col in columns:
            if col in used_cols:
                continue
            if match_column(col, patterns):
                mapping[field_key] = col
                used_cols.add(col)
                break

    return mapping


def detect_dataset_format(df: pd.DataFrame, date_col: Optional[str]) -> str:
    """
    Determine if dataframe is in 'long' format (station_id, date, rainfall rows)
    or 'wide' format (date rows with each column as a station).
    """
    if df.empty:
        return "unknown"

    cols = [c for c in df.columns if c != date_col]
    
    # If there are many numeric columns and a date column, it's likely wide format
    numeric_cols = df[cols].select_dtypes(include=[np.number]).columns
    if len(numeric_cols) >= 3 and len(numeric_cols) / max(len(cols), 1) > 0.6:
        return "wide"
    
    return "long"


def convert_wide_to_long(
    df: pd.DataFrame,
    date_col: str,
    station_cols: List[str],
    unit: str = "mm"
) -> pd.DataFrame:
    """Melt wide matrix (dates as rows, stations as columns) to standardized long format."""
    melted = df.melt(
        id_vars=[date_col],
        value_vars=station_cols,
        var_name="station_id",
        value_name="rainfall"
    )
    melted["station_name"] = melted["station_id"]
    melted.rename(columns={date_col: "date"}, inplace=True)
    return melted


def detect_observation_frequency(dates: pd.Series) -> str:
    """Infer frequency (Daily, Hourly, Monthly) from timestamp sequence."""
    clean_dates = pd.to_datetime(dates.dropna(), errors="coerce").drop_duplicates().sort_values()
    if len(clean_dates) < 3:
        return "Daily"

    deltas = clean_dates.diff().dropna()
    median_seconds = deltas.dt.total_seconds().median()

    if median_seconds <= 3600:
        return "Hourly"
    elif 80000 <= median_seconds <= 95000:
        return "Daily"
    elif 27 * 86400 <= median_seconds <= 32 * 86400:
        return "Monthly"
    else:
        return "Daily"


def detect_unit_from_headers_or_values(
    col_name: Optional[str],
    values: Optional[pd.Series] = None
) -> str:
    """Detect measurement unit ('mm', 'cm', or 'inches') from header or magnitude."""
    if col_name:
        clean = col_name.lower()
        if "cm" in clean:
            return "cm"
        if "inch" in clean or "_in" in clean:
            return "inches"
        if "mm" in clean:
            return "mm"

    if values is not None:
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if not numeric.empty:
            p99 = numeric.quantile(0.99)
            # If 99th percentile is < 10, could be cm or inches, but standard is mm unless stated
            if p99 > 30:
                return "mm"

    return "mm"
