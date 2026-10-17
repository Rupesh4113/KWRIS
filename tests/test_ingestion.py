"""Tests for Data Ingestion, Column Mapping, and Normalization."""

import io
import pandas as pd
import numpy as np
import pytest
from src.ingestion import (
    read_raw_dataset,
    detect_data_layout,
    suggest_column_mappings,
    normalize_dataset,
    DEFAULT_MISSING_CODES
)
from src.preprocessing import profile_raw_and_normalized_data


def test_ingest_long_format_csv():
    csv_data = """BasinName,SubBasinName,WIMS Code,LocationName,Day,RF(mm)
Cauvery,Arkavati,KC3GBNG771,Adankuppe,2024-01-01,0.0
Cauvery,Arkavati,KC3GBNG771,Adankuppe,2024-01-02,15.5
Cauvery,Arkavati,KC3GBNG771,Adankuppe,2024-01-03,-99
Cauvery,Arkavati,KC3GBNG771,Adankuppe,2024-01-04,0.0
"""
    df_raw = pd.read_csv(io.StringIO(csv_data))
    layout = detect_data_layout(df_raw)
    assert layout == "long"
    
    mapping = suggest_column_mappings(df_raw, layout=layout)
    assert mapping["station_name"] == "LocationName"
    assert mapping["date"] == "Day"
    assert mapping["rainfall"] == "RF(mm)"
    
    df_norm, meta = normalize_dataset(df_raw, layout=layout, mapping=mapping)
    assert len(df_norm) == 4
    # Zero must be preserved as 0.0, NOT NaN
    assert df_norm.loc[0, "rainfall_mm"] == 0.0
    assert df_norm.loc[1, "rainfall_mm"] == 15.5
    # -99 code must be converted to NaN
    assert np.isnan(df_norm.loc[2, "rainfall_mm"])
    assert df_norm.loc[3, "rainfall_mm"] == 0.0
    # Coordinates looked up from catalog for Adankuppe
    assert not np.isnan(df_norm.loc[0, "latitude"])
    assert not np.isnan(df_norm.loc[0, "longitude"])


def test_ingest_wide_format_spreadsheet():
    wide_data = """Date,StationA,StationB,StationC
2024-01-01,0,12.0,5.5
2024-01-02,-99,0.0,8.2
2024-01-03,25.0,-99,0.0
"""
    df_raw = pd.read_csv(io.StringIO(wide_data))
    layout = detect_data_layout(df_raw)
    assert layout == "wide"
    
    mapping = suggest_column_mappings(df_raw, layout=layout)
    assert mapping["date"] == "Date"
    
    df_norm, meta = normalize_dataset(df_raw, layout=layout, mapping=mapping)
    assert len(df_norm) == 9  # 3 dates x 3 stations
    assert df_norm["station_name"].nunique() == 3
    # Check -99 converted to NaN
    assert df_norm[df_norm["rainfall_mm"].isna()].shape[0] == 2


def test_preservation_of_original_data_integrity():
    csv_data = """Date,Station,Rainfall
2024-01-01,Stn1,10.0
2024-01-02,Stn1,0.0
"""
    df_raw = pd.read_csv(io.StringIO(csv_data))
    df_raw_copy = df_raw.copy(deep=True)
    mapping = {"date": "Date", "station_name": "Station", "rainfall": "Rainfall"}
    
    df_norm, meta = normalize_dataset(df_raw, layout="long", mapping=mapping)
    
    # Original raw DataFrame must not be altered in any way
    pd.testing.assert_frame_equal(df_raw, df_raw_copy)
    assert "original_row_id" in df_norm.columns
