"""Upload and Column Mapping Interface for KWRIS Rainfall Data."""

from __future__ import annotations
import os
import streamlit as st
import pandas as pd
from src.ingestion import (
    read_raw_dataset,
    detect_file_sheets,
    detect_data_layout,
    suggest_column_mappings,
    normalize_dataset
)
from src.preprocessing import profile_raw_and_normalized_data


def render_upload_page():
    st.markdown("## 📤 Upload Rainfall Data")
    st.markdown(
        "Upload raw KWRIS rainfall records in **Excel (.xlsx, .xls)** or **CSV (.csv)** format. "
        "Supports long-format records (Basin, Station, Date, RF) and wide-format spreadsheets."
    )
    
    col_up, col_sample = st.columns([3, 2])
    
    with col_up:
        uploaded_file = st.file_uploader(
            "Choose a rainfall data file",
            type=["xlsx", "xls", "csv"],
            help="Upload raw data. The original file is stored unmodified in memory for auditing."
        )
        
    with col_sample:
        st.markdown("#### Or select an existing KWRIS dataset:")
        sample_choice = st.selectbox(
            "Available repository datasets:",
            options=[
                "-- Select a sample dataset --",
                "ARKAVATHI RAINFALL.xlsx",
                "GHATAPRABHA RF KWRIS 1991-2025.xlsx",
                "K3_RF_filled_IDW_20km_3Nearest.xlsx",
                "K4_RF_filled_IDW_20km_3Nearest.xlsx"
            ]
        )
        
    target_file = None
    file_name = ""
    file_size = 0
    
    if uploaded_file is not None:
        target_file = uploaded_file
        file_name = uploaded_file.name
        file_size = uploaded_file.size
    elif sample_choice and sample_choice != "-- Select a sample dataset --":
        if os.path.exists(sample_choice):
            target_file = sample_choice
            file_name = sample_choice
            file_size = os.path.getsize(sample_choice)
            
    if target_file is None:
        st.info("👆 Please upload a file or select one of the built-in Karnataka basin datasets above.")
        return

    # Check for sheets if Excel
    sheets = detect_file_sheets(target_file)
    selected_sheet = None
    if sheets and len(sheets) > 1:
        selected_sheet = st.selectbox("Select Excel worksheet to load:", options=sheets, index=0)
    elif sheets:
        selected_sheet = sheets[0]
        
    # Read raw dataset
    try:
        with st.spinner(f"Reading {file_name}..."):
            df_raw, meta = read_raw_dataset(target_file, sheet_name=selected_sheet)
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return

    st.success(f"✓ Loaded **{file_name}** ({meta['raw_rows']:,} rows, {meta['raw_cols']} columns)")
    
    # Auto-detect layout
    detected_layout = detect_data_layout(df_raw)
    st.markdown("### 🔀 Layout and Column Mapping")
    
    col_layout, col_preview_btn = st.columns([2, 3])
    with col_layout:
        layout = st.radio(
            "Data Format Layout:",
            options=["long", "wide"],
            index=0 if detected_layout == "long" else 1,
            format_func=lambda x: "Long Format (Station, Date, RF columns)" if x == "long" else "Wide Format (Date col + Station cols)"
        )
        
    # Suggest mappings
    suggested = suggest_column_mappings(df_raw, layout=layout)
    cols = [None] + df_raw.columns.tolist()
    
    with st.expander("Configure / Confirm Column Mappings", expanded=True):
        if layout == "long":
            c1, c2, c3 = st.columns(3)
            with c1:
                date_col = st.selectbox("Date / Timestamp Column *", cols, index=cols.index(suggested["date"]) if suggested["date"] in cols else 0)
                stn_name_col = st.selectbox("Station Name Column *", cols, index=cols.index(suggested["station_name"]) if suggested["station_name"] in cols else 0)
            with c2:
                rf_col = st.selectbox("Rainfall (mm) Column *", cols, index=cols.index(suggested["rainfall"]) if suggested["rainfall"] in cols else 0)
                stn_id_col = st.selectbox("Station ID / WIMS Code (Optional)", cols, index=cols.index(suggested["station_id"]) if suggested["station_id"] in cols else 0)
            with c3:
                gauge_col = st.selectbox("Gauge Type Column (Optional)", cols, index=cols.index(suggested["gauge_type"]) if suggested["gauge_type"] in cols else 0)
                basin_col = st.selectbox("Basin / Subbasin (Optional)", cols, index=cols.index(suggested["basin"]) if suggested["basin"] in cols else 0)
                
            mapping = {
                "date": date_col,
                "station_name": stn_name_col,
                "station_id": stn_id_col,
                "rainfall": rf_col,
                "gauge_type": gauge_col,
                "basin": basin_col,
                "subbasin": None,
                "latitude": None,
                "longitude": None
            }
        else:
            c1, c2 = st.columns(2)
            with c1:
                date_col = st.selectbox("Date Column *", cols, index=cols.index(suggested["date"]) if suggested["date"] in cols else 1)
            with c2:
                st.info(f"Wide format detected. {len(df_raw.columns)-1} columns will be mapped as individual rainfall stations.")
            mapping = {"date": date_col}

    # Action button to process
    if st.button("🚀 Process & Ingest Dataset", type="primary"):
        try:
            with st.spinner("Normalizing dataset and performing initial profiling..."):
                df_norm, audit_meta = normalize_dataset(df_raw, layout=layout, mapping=mapping)
                profile = profile_raw_and_normalized_data(df_raw, df_norm, file_name, file_size, layout)
                
                # Store in session state
                st.session_state["df_raw"] = df_raw
                st.session_state["df_norm"] = df_norm
                st.session_state["df_annotated"] = df_norm.copy()
                st.session_state["profile"] = profile
                st.session_state["file_name"] = file_name
                st.session_state["min_date"] = profile.min_date
                st.session_state["max_date"] = profile.max_date
                st.session_state["flags"] = []
                st.session_state["proposals"] = []
                st.session_state["validated"] = False
                
                st.success("🎉 Dataset successfully ingested and normalized! Head to **Data Profiling** or **Primary Validation**.")
        except Exception as ex:
            st.error(f"Error processing dataset: {ex}")
            
    # Show Raw Preview
    st.markdown("#### Raw Data Preview (First 5 Rows):")
    st.dataframe(df_raw.head(5), use_container_width=True)
