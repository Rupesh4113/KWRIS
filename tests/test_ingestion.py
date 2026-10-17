"""Tests for File Ingestion and Schema Detection."""

import io
import pytest
import pandas as pd
import numpy as np
from src.schema_detection import (
    detect_columns,
    detect_dataset_format,
    convert_wide_to_long,
    detect_observation_frequency,
    detect_unit_from_headers_or_values
)
from src.ingestion import (
    read_raw_data,
    clean_missing_codes,
    normalize_rainfall_dataset
)


def test_detect_columns_standard():
    cols = ["Obs_Date", "Station_ID", "Station_Name", "Rainfall_mm", "Latitude", "Longitude", "District"]
    mapping = detect_columns(cols)
    assert mapping["date"] == "Obs_Date"
    assert mapping["station_id"] == "Station_ID"
    assert mapping["station_name"] == "Station_Name"
    assert mapping["rainfall"] == "Rainfall_mm"
    assert mapping["latitude"] == "Latitude"
    assert mapping["longitude"] == "Longitude"
    assert mapping["district"] == "District"


def test_detect_dataset_format_and_melt():
    # Wide format dataframe
    df_wide = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "STN_A": [5.2, 12.0],
        "STN_B": [0.0, 4.5],
        "STN_C": [2.1, 0.0]
    })
    fmt = detect_dataset_format(df_wide, "date")
    assert fmt == "wide"

    long_df = convert_wide_to_long(df_wide, "date", ["STN_A", "STN_B", "STN_C"])
    assert len(long_df) == 6
    assert set(long_df.columns) >= {"date", "station_id", "rainfall"}


def test_clean_missing_codes():
    s = pd.Series([10.5, -99.0, -999, "NA", "NR", 0.0, -9999, "15.2"])
    cleaned = clean_missing_codes(s)
    assert cleaned.iloc[0] == 10.5
    assert np.isnan(cleaned.iloc[1])
    assert np.isnan(cleaned.iloc[2])
    assert np.isnan(cleaned.iloc[3])
    assert np.isnan(cleaned.iloc[4])
    assert cleaned.iloc[5] == 0.0  # Zero is not missing!


def test_normalize_rainfall_dataset():
    raw_df = pd.DataFrame({
        "date_col": ["2024-06-01", "2024-06-02", "2024-06-03"],
        "stn": ["S01", "S01", "S01"],
        "rain": [12.4, -99, 0.0]
    })
    mapping = {"date": "date_col", "station_id": "stn", "rainfall": "rain"}
    norm_df, summary = normalize_rainfall_dataset(raw_df, mapping, unit="mm")

    assert len(norm_df) == 3
    assert norm_df["rainfall"].iloc[0] == 12.4
    assert np.isnan(norm_df["rainfall"].iloc[1])
    assert norm_df["rainfall"].iloc[2] == 0.0  # Zero preserved
    assert norm_df["original_rainfall"].iloc[1] == -99  # Original preserved
    assert summary["zero_rainfall_count"] == 1
    assert summary["missing_rainfall_count"] == 1
