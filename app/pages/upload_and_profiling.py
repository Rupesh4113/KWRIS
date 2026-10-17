"""Upload and Data Profiling Page.
Consolidates file ingestion, layout detection, column mapping, and data profiling into a single seamless workflow.
"""

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
from src.preprocessing import profile_raw_and_normalized_data, detect_date_gaps


def render_upload_and_profiling_page():
    st.markdown("## 📤 Dataset Ingestion & Profiling")
    st.markdown(
        "Upload raw KWRIS rainfall records in **Excel (.xlsx, .xls)** or **CSV (.csv)** format. "
        "The system automatically profiles dataset completeness, sequence gaps, and data health."
    )
    
    col_up, col_sample = st.columns([3, 2])
    with col_up:
        uploaded_file = st.file_uploader(
            "Choose a rainfall file (Excel or CSV):",
            type=["xlsx", "xls", "csv"],
            help="Original file is preserved unmodified in memory for auditing and export."
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
        if "df_norm" in st.session_state and st.session_state["df_norm"] is not None:
            st.info(f"📁 Active dataset: **{st.session_state.get('file_name', 'Loaded dataset')}**. Upload a new file above to replace.")
            _render_profiling_view(st.session_state["df_norm"], st.session_state.get("profile"))
        else:
            st.info("👆 Please upload a file or select a built-in Karnataka basin dataset above.")
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
    
    layout = st.radio(
        "Data Format Layout:",
        options=["long", "wide"],
        index=0 if detected_layout == "long" else 1,
        format_func=lambda x: "Long Format (Station, Date, Rainfall columns)" if x == "long" else "Wide Format (Date column + Station columns)",
        horizontal=True
    )
        
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
                "date": date_col, "station_name": stn_name_col, "station_id": stn_id_col,
                "rainfall": rf_col, "gauge_type": gauge_col, "basin": basin_col,
                "subbasin": None, "latitude": None, "longitude": None
            }
        else:
            c1, c2 = st.columns(2)
            with c1:
                date_col = st.selectbox("Date Column *", cols, index=cols.index(suggested["date"]) if suggested["date"] in cols else 1)
            with c2:
                st.info(f"Wide format detected: {len(df_raw.columns)-1} columns will be mapped as individual stations.")
            mapping = {"date": date_col}

    # Action button to process and profile
    if st.button("🚀 Ingest & Profile Dataset", type="primary"):
        try:
            with st.spinner("Normalizing dataset and performing profiling checks..."):
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
                st.session_state["primary_validated"] = False
                st.session_state["secondary_validated"] = False
                
                st.success("🎉 Dataset successfully ingested! Profiling diagnostics displayed below.")
        except Exception as ex:
            st.error(f"Error processing dataset: {ex}")

    # If dataset is loaded, render profiling directly
    if "df_norm" in st.session_state and st.session_state["df_norm"] is not None:
        _render_profiling_view(st.session_state["df_norm"], st.session_state.get("profile"))


def _render_profiling_view(df_norm: pd.DataFrame, profile):
    """Render comprehensive profiling cards, station coverage, and calendar sequence gaps."""
    st.divider()
    st.markdown("### 📊 Dataset Quality & Integrity Profile")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Observations", f"{len(df_norm):,}")
    with col2:
        st.metric("Unique Stations", f"{df_norm['station_name'].nunique()}")
    with col3:
        st.metric("Completeness", f"{profile.completeness_pct if profile else 0.0}%")
    with col4:
        st.metric("Missing Values", f"{df_norm['rainfall_mm'].isna().sum():,}")
        
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Negative Values (< 0 mm)", f"{(df_norm['rainfall_mm'] < 0).sum():,}")
    with col6:
        st.metric("Duplicate Station-Dates", f"{profile.duplicate_station_dates_count if profile else 0}")
    with col7:
        max_rf = df_norm['rainfall_mm'].max()
        st.metric("Max Recorded Daily Rain", f"{max_rf:.1f} mm" if pd.notna(max_rf) else "0.0 mm")
    with col8:
        st.metric("Station Coordinates", "Matched (Catalog)" if profile and profile.has_coordinates else "Ready for IDW")

    tab1, tab2 = st.tabs(["🏢 Station Coverage Breakdown", "⏱️ Calendar Sequence Gaps"])
    with tab1:
        stn_summary = []
        for stn, g in df_norm.groupby("station_name"):
            tot = len(g)
            vld = g["rainfall_mm"].notna().sum()
            miss = g["rainfall_mm"].isna().sum()
            neg = (g["rainfall_mm"] < 0).sum()
            rainy = (g["rainfall_mm"] >= 0.1).sum()
            stn_summary.append({
                "Station Name": stn,
                "Station ID": g["station_id"].iloc[0] if "station_id" in g.columns else stn,
                "Total Records": tot,
                "Valid Readings": vld,
                "Missing Records": miss,
                "Negatives": neg,
                "Rainy Days (>=0.1mm)": rainy,
                "Completeness (%)": round(vld / max(1, tot) * 100.0, 1),
                "Max Daily (mm)": round(float(g["rainfall_mm"].max()), 1) if vld > 0 else 0.0
            })
        st.dataframe(pd.DataFrame(stn_summary), use_container_width=True)

    with tab2:
        with st.spinner("Checking date sequence continuity..."):
            gaps_df = detect_date_gaps(df_norm.head(10000))
            if not gaps_df.empty:
                st.warning(f"Detected {len(gaps_df)} sequence gaps in the sample sequence.")
                st.dataframe(gaps_df.head(50), use_container_width=True)
            else:
                st.success("✓ Daily time series is continuous without missing calendar dates.")
