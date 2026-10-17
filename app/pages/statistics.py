"""Statistical Analysis and Period Aggregation Page: Rules A1 to A6."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.statistics import (
    compute_station_monthly_statistics,
    compute_station_yearly_statistics,
    aggregate_weekly_standard,
    aggregate_ten_daily_dekad,
    perform_a5_consistency_tests,
    compute_a6_quality_report
)


def render_statistics_page():
    st.markdown("## 📈 Statistical Analysis & Aggregations (Rules A1–A6)")
    st.markdown(
        "Compiles standardized hydrological periods, calculates skewed distribution statistics, "
        "enforces completeness rules, and tests records for statistical homogeneity before trend modeling."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first.")
        return
        
    df_active = st.session_state.get("df_annotated", st.session_state["df_norm"])
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 Monthly Statistics (A3, A4)",
        "📆 Yearly Statistics (A3, A4)",
        "⏳ Weekly (51+1) Aggregation (A1)",
        "⏱️ Ten-Daily (Dekad) Periods (A1)",
        "🔬 Record Consistency & Homogeneity (A5)"
    ])
    
    with tab1:
        st.markdown("#### Monthly Rainfall Totals & Skewed Distribution Measures:")
        completeness_cut = st.slider("A3: Minimum Monthly Completeness Threshold (%)", 50, 100, 90, 5)
        
        with st.spinner("Aggregating monthly statistics..."):
            m_stats = compute_station_monthly_statistics(df_active, completeness_min_pct=completeness_cut)
            st.session_state["monthly_stats"] = m_stats
            
        st.dataframe(m_stats, use_container_width=True)
        st.caption("Includes: Mean, Median, Standard Deviation, Skewness, Maximum, Rainy Days, and Completeness check.")
        
    with tab2:
        st.markdown("#### Annual Rainfall Totals & Completeness Metrics:")
        with st.spinner("Aggregating annual statistics..."):
            y_stats = compute_station_yearly_statistics(df_active, completeness_min_pct=90.0)
            st.session_state["yearly_stats"] = y_stats
            
        st.dataframe(y_stats, use_container_width=True)
        
    with tab3:
        st.markdown("#### A1 - Daily to Weekly Aggregation (51 Weeks × 7 Days + 52nd Week × 8/9 Days):")
        stn_sel = st.selectbox("Select Station for Weekly Table:", sorted(df_active["station_name"].unique()))
        stn_df = df_active[df_active["station_name"] == stn_sel]
        
        with st.spinner("Aggregating weekly standard periods..."):
            w_df = aggregate_weekly_standard(stn_df)
        st.dataframe(w_df, use_container_width=True)
        
    with tab4:
        st.markdown("#### A1 - Ten-Daily (Dekad) Aggregation (Days 1–10, 11–20, 21–End):")
        with st.spinner("Aggregating 10-daily dekads..."):
            dekad_df = aggregate_ten_daily_dekad(stn_df)
        st.dataframe(dekad_df, use_container_width=True)
        
    with tab5:
        st.markdown("#### A5 - Consistency & Homogeneity Tests (Student's t-test, Mann-Whitney U):")
        st.caption("Assesses whether historical rainfall record underwent statistically significant shifts prior to long-term trend analysis.")
        
        y_stats = st.session_state.get("yearly_stats")
        if y_stats is None or y_stats.empty:
            y_stats = compute_station_yearly_statistics(df_active)
            st.session_state["yearly_stats"] = y_stats
            
        test_stn = st.selectbox("Select Station for Homogeneity Test:", sorted(df_active["station_name"].unique()), key="sb_a5")
        stn_annual = y_stats[y_stats["station_name"] == test_stn].set_index("year")["annual_rainfall_mm"]
        
        res = perform_a5_consistency_tests(stn_annual)
        if res.get("status") == "tested":
            c1, c2, c3 = st.columns(3)
            c1.metric("Period 1 Mean (Older)", f"{res['period1_mean_mm']} mm")
            c2.metric("Period 2 Mean (Recent)", f"{res['period2_mean_mm']} mm", delta=f"{res['mean_shift_pct']}% shift")
            c3.metric("Mann-Whitney p-value", f"{res['mann_whitney_pvalue']:.4f}")
            
            if res["is_statistically_significant_shift"]:
                st.warning(f"⚠️ **Result:** {res['interpretation']} (p < 0.05). Check S8 double-mass curve for instrument relocation or fault.")
            else:
                st.success(f"✓ **Result:** {res['interpretation']} (p >= 0.05). Record is stationary.")
        else:
            st.info("Insufficient annual data for statistical tests (need at least 8 years).")
