"""Visual Analytics Page: Interactive charts, trends, and before-and-after comparisons."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from app.components.charts import (
    plot_rainfall_time_series,
    plot_monthly_heatmap,
    plot_double_mass_curve
)
from src.statistics import compute_station_monthly_statistics


def render_analytics_page():
    st.markdown("## 📉 Visual Analytics & Diagnostic Charts")
    st.markdown(
        "Interactive exploratory visualizations of daily rainfall profiles, spatial patterns, "
        "suspicious outliers, and before-and-after correction comparisons."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first.")
        return
        
    df_active = st.session_state.get("df_annotated", st.session_state["df_norm"])
    flags = st.session_state.get("flags", [])
    stations = sorted(df_active["station_name"].unique().tolist())
    
    col_stn, col_date = st.columns([1, 2])
    with col_stn:
        sel_station = st.selectbox("Select Station:", stations)
        
    stn_df = df_active[df_active["station_name"] == sel_station]
    valid_dates = stn_df["date"].dropna()
    min_d = valid_dates.min().to_pydatetime().date() if not valid_dates.empty else None
    max_d = valid_dates.max().to_pydatetime().date() if not valid_dates.empty else None
    
    with col_date:
        if min_d and max_d and min_d < max_d:
            date_range = st.date_input("Date Range:", value=(min_d, max_d), min_value=min_d, max_value=max_d)
        else:
            date_range = None

    # Filter by date range if specified
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
        stn_sub = stn_df[(stn_df["date"] >= pd.Timestamp(start_d)) & (stn_df["date"] <= pd.Timestamp(end_d))]
    else:
        stn_sub = stn_df
        
    tab1, tab2, tab3 = st.tabs([
        "📊 Daily Profile & Suspicious Points",
        "🌡️ Spatial Monthly Heatmap",
        "📈 Double-Mass Curve & Consistency"
    ])
    
    with tab1:
        st.markdown(f"#### Daily Observations & Flagged Anomalies: Station `{sel_station}`")
        fig_ts = plot_rainfall_time_series(stn_sub, sel_station, flags)
        st.plotly_chart(fig_ts, use_container_width=True)
        
        # Display flagged readings in range
        flags_stn = [f for f in flags if f.station_name == sel_station]
        if flags_stn:
            st.markdown(f"**Anomalies Flagged for {sel_station} ({len(flags_stn)} total):**")
            rec = [{
                "Date": f.date.strftime("%Y-%m-%d"),
                "Rule": f.rule_id,
                "Observed (mm)": f.original_value,
                "Limit / Expected": f.expected_value,
                "Reason": f.message
            } for f in flags_stn]
            st.dataframe(pd.DataFrame(rec), use_container_width=True)
        else:
            st.success(f"✓ No doubtful anomalies flagged for station {sel_station}.")
            
    with tab2:
        st.markdown("#### Regional Rainfall Monthly Heatmap across All Stations:")
        m_stats = st.session_state.get("monthly_stats")
        if m_stats is None or m_stats.empty:
            m_stats = compute_station_monthly_statistics(df_active)
            st.session_state["monthly_stats"] = m_stats
            
        avail_years = sorted(m_stats["year"].unique().tolist(), reverse=True)
        sel_year = st.selectbox("Select Year for Heatmap:", avail_years)
        fig_heat = plot_monthly_heatmap(m_stats, sel_year)
        st.plotly_chart(fig_heat, use_container_width=True)
        
    with tab3:
        st.markdown("#### Double-Mass Long-Term Homogeneity Curve (S8):")
        dm_dfs = st.session_state.get("double_mass_dfs", {})
        if sel_station in dm_dfs:
            dm_df = dm_dfs[sel_station]
            fig_dm = plot_double_mass_curve(dm_df, sel_station)
            st.plotly_chart(fig_dm, use_container_width=True)
        elif dm_dfs:
            st.info(f"Station {sel_station} has insufficient neighbouring station records for double-mass. Showing first available station:")
            alt_stn = list(dm_dfs.keys())[0]
            fig_dm = plot_double_mass_curve(dm_dfs[alt_stn], alt_stn)
            st.plotly_chart(fig_dm, use_container_width=True)
        else:
            st.info("Run **Neighbour Station Validation (S1–S8)** to calculate double-mass curves.")
