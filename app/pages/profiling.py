"""Data Profiling Page for inspecting dataset health and integrity."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.preprocessing import detect_date_gaps


def render_profiling_page():
    st.markdown("## 📊 Rainfall Data Profiling")
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first in **Upload Rainfall Data**.")
        return
        
    df_norm = st.session_state["df_norm"]
    profile = st.session_state.get("profile")
    
    # Summary cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Records", f"{len(df_norm):,}")
    with col2:
        st.metric("Unique Stations", f"{df_norm['station_name'].nunique()}")
    with col3:
        st.metric("Completeness", f"{profile.completeness_pct if profile else 0.0}%")
    with col4:
        st.metric("Missing Values", f"{df_norm['rainfall_mm'].isna().sum():,}")
        
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Negative Values (<0 mm)", f"{(df_norm['rainfall_mm'] < 0).sum():,}")
    with col6:
        st.metric("Duplicate Station-Dates", f"{profile.duplicate_station_dates_count if profile else 0}")
    with col7:
        st.metric("Max Recorded Daily Rain", f"{df_norm['rainfall_mm'].max():.1f} mm" if not df_norm['rainfall_mm'].dropna().empty else "0 mm")
    with col8:
        st.metric("Coordinates Matched", "Yes (Catalog/File)" if profile and profile.has_coordinates else "No (Fallback IDW)")

    st.divider()
    
    # Station-wise profile breakdown
    st.markdown("### 🏢 Station Breakdown & Coverage")
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
    df_stn_summary = pd.DataFrame(stn_summary)
    st.dataframe(df_stn_summary, use_container_width=True)

    # Date gaps check
    st.markdown("### ⏱️ Missing Date Gaps in Sequence")
    with st.spinner("Checking for sequence gaps..."):
        gaps_df = detect_date_gaps(df_norm.head(10000))  # limit to sample for instant responsiveness
        if not gaps_df.empty:
            st.warning(f"Found {len(gaps_df)} date gaps in the first 10,000 sequence rows.")
            st.dataframe(gaps_df.head(50), use_container_width=True)
        else:
            st.success("✓ No calendar date gaps found in time sequence.")
