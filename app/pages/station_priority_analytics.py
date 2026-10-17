"""Station Priority Ranking & Engineering Decision Analytics.
Consolidates operational station triage, visual decision charts, and hydrological statistics (A1–A6).
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.station_ranking import compute_station_priority_ranking
from src.statistics import (
    compute_station_monthly_statistics,
    compute_station_yearly_statistics,
    aggregate_weekly_standard,
    aggregate_ten_daily_dekad,
    perform_a5_consistency_tests
)
from app.components.charts import (
    plot_rainfall_time_series,
    plot_double_mass_curve,
    plot_monthly_heatmap
)


def render_station_priority_analytics_page():
    st.markdown("## 🏆 Station Priority & Engineering Analytics")
    st.markdown(
        "Combines operational triage priority scoring with interactive decision charts "
        "and standard hydrological statistics (Rules A1–A6)."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first in **Upload & Profiling**.")
        return
        
    df_active = st.session_state.get("df_annotated", st.session_state["df_norm"])
    flags = st.session_state.get("flags", [])
    coords_map = st.session_state.get("coords_map", {})
    
    # Calculate priority rankings
    with st.spinner("Updating station priority triage rankings..."):
        df_ranking = compute_station_priority_ranking(df_active, flags, coords_map)
        st.session_state["station_ranking"] = df_ranking

    if df_ranking.empty:
        st.info("No station records available for ranking.")
        return
        
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚨 Station Priority Leaderboard",
        "📊 Time Series & Flagged Points",
        "📈 Double-Mass & Spatial Heatmap (S8)",
        "🔬 Hydrological Period Statistics (A1–A6)"
    ])
    
    # Tab 1: Station Priority Leaderboard
    with tab1:
        urgency_counts = df_ranking["urgency"].value_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Critical Urgency", f"{urgency_counts.get('CRITICAL', 0)}", delta="Needs immediate review", delta_color="inverse")
        c2.metric("High Urgency", f"{urgency_counts.get('HIGH', 0)}", delta="Review & gap-fill", delta_color="inverse")
        c3.metric("Moderate", f"{urgency_counts.get('MODERATE', 0)}")
        c4.metric("Low Urgency (Clean)", f"{urgency_counts.get('LOW', 0)}")
        
        urg_filter = st.multiselect("Filter Urgency:", ["CRITICAL", "HIGH", "MODERATE", "LOW"], default=["CRITICAL", "HIGH", "MODERATE", "LOW"])
        df_filtered = df_ranking[df_ranking["urgency"].isin(urg_filter)]
        
        st.dataframe(
            df_filtered[[
                "station_id", "station_name", "priority_score", "urgency",
                "missing_pct", "doubtful_flags_count", "critical_flags_count",
                "latest_issue", "recommended_action"
            ]],
            use_container_width=True
        )
        
        with st.expander("🔎 Station Score Breakdown & Rationale"):
            selected_stn = st.selectbox("Inspect Station Rationale:", df_ranking["station_name"].tolist())
            stn_row = df_ranking[df_ranking["station_name"] == selected_stn].iloc[0]
            
            sc1, sc2 = st.columns([1, 2])
            with sc1:
                st.metric("Priority Score", f"{stn_row['priority_score']} / 100", stn_row["urgency"])
                st.write(f"**Missing:** {stn_row['missing_records']} ({stn_row['missing_pct']}%)")
                st.write(f"**Flags:** {stn_row['doubtful_flags_count']} (Critical: {stn_row['critical_flags_count']})")
            with sc2:
                st.info(f"**Scoring Rationale:** {stn_row['score_explanation']}")
                st.success(f"👉 **Next Step:** {stn_row['recommended_action']}")

    # Tab 2: Time Series & Flagged Points
    with tab2:
        stn_list = sorted(df_active["station_name"].unique().tolist())
        c_stn, c_dt = st.columns([1, 2])
        with c_stn:
            sel_stn_ts = st.selectbox("Select Station for Time Series:", stn_list, key="ts_stn")
            
        stn_df = df_active[df_active["station_name"] == sel_stn_ts]
        valid_dates = stn_df["date"].dropna()
        min_d = valid_dates.min().to_pydatetime().date() if not valid_dates.empty else None
        max_d = valid_dates.max().to_pydatetime().date() if not valid_dates.empty else None
        
        with c_dt:
            if min_d and max_d and min_d < max_d:
                dt_range = st.date_input("Date Range:", value=(min_d, max_d), min_value=min_d, max_value=max_d, key="ts_dt")
            else:
                dt_range = None
                
        if dt_range and isinstance(dt_range, tuple) and len(dt_range) == 2:
            s_d, e_d = dt_range
            stn_sub = stn_df[(stn_df["date"] >= pd.Timestamp(s_d)) & (stn_df["date"] <= pd.Timestamp(e_d))]
        else:
            stn_sub = stn_df
            
        fig_ts = plot_rainfall_time_series(stn_sub, sel_stn_ts, flags)
        st.plotly_chart(fig_ts, use_container_width=True)

    # Tab 3: Double-Mass Curves & Spatial Heatmap
    with tab3:
        dm_dfs = st.session_state.get("double_mass_dfs", {})
        if dm_dfs:
            st.markdown("#### Long-Term Homogeneity Curve (S8):")
            sel_dm_stn = st.selectbox("Select Station for Double-Mass:", options=list(dm_dfs.keys()), key="dm_stn")
            dm_df = dm_dfs[sel_dm_stn]
            
            s8_flags = [f for f in flags if f.rule_id == "S8" and f.station_name == sel_dm_stn]
            break_yr = s8_flags[0].details.get("break_year") if s8_flags else None
            
            fig_dm = plot_double_mass_curve(dm_df, sel_dm_stn, break_yr)
            st.plotly_chart(fig_dm, use_container_width=True)
            if s8_flags:
                st.warning(f"⚠️ {s8_flags[0].message}")
        else:
            st.info("Run validation on multiple stations to calculate double-mass curves.")
            
        st.divider()
        st.markdown("#### Spatial Monthly Heatmap:")
        m_stats = st.session_state.get("monthly_stats")
        if m_stats is None or m_stats.empty:
            m_stats = compute_station_monthly_statistics(df_active)
            st.session_state["monthly_stats"] = m_stats
            
        avail_years = sorted(m_stats["year"].unique().tolist(), reverse=True)
        sel_yr = st.selectbox("Select Year for Heatmap:", avail_years, key="hm_yr")
        fig_heat = plot_monthly_heatmap(m_stats, sel_yr)
        st.plotly_chart(fig_heat, use_container_width=True)

    # Tab 4: Hydrological Period Statistics (A1–A6)
    with tab4:
        sub1, sub2, sub3, sub4 = st.tabs([
            "Monthly (A3, A4)", "Yearly (A3, A4)", "Weekly 51+1 (A1)", "Homogeneity Tests (A5)"
        ])
        with sub1:
            st.markdown("##### Monthly Rainfall Sums & Distribution Metrics:")
            st.dataframe(m_stats, use_container_width=True)
        with sub2:
            st.markdown("##### Annual Rainfall Sums & Completeness:")
            y_stats = st.session_state.get("yearly_stats")
            if y_stats is None or y_stats.empty:
                y_stats = compute_station_yearly_statistics(df_active)
                st.session_state["yearly_stats"] = y_stats
            st.dataframe(y_stats, use_container_width=True)
        with sub3:
            st.markdown("##### Standard Weekly Aggregation (51 Weeks × 7 Days + 52nd Week × 8/9 Days):")
            sel_stn_w = st.selectbox("Station for Weekly Table:", stn_list, key="w_stn")
            w_df = aggregate_weekly_standard(df_active[df_active["station_name"] == sel_stn_w])
            st.dataframe(w_df, use_container_width=True)
        with sub4:
            st.markdown("##### Mann-Whitney U & Student's t-test Homogeneity Tests (A5):")
            sel_stn_test = st.selectbox("Station for Statistical Test:", stn_list, key="test_stn")
            if y_stats is not None and not y_stats.empty:
                stn_annual = y_stats[y_stats["station_name"] == sel_stn_test].set_index("year")["annual_rainfall_mm"]
                res = perform_a5_consistency_tests(stn_annual)
                if res.get("status") == "tested":
                    c_t1, c_t2, c_t3 = st.columns(3)
                    c_t1.metric("Period 1 Mean", f"{res['period1_mean_mm']} mm")
                    c_t2.metric("Period 2 Mean", f"{res['period2_mean_mm']} mm", delta=f"{res['mean_shift_pct']}% shift")
                    c_t3.metric("Mann-Whitney p-value", f"{res['mann_whitney_pvalue']:.4f}")
                    if res["is_statistically_significant_shift"]:
                        st.warning(f"⚠️ {res['interpretation']} (p < 0.05). Check S8 double-mass curve.")
                    else:
                        st.success(f"✓ {res['interpretation']} (p >= 0.05). Record is stationary.")
                else:
                    st.info("Insufficient annual data for statistical tests (need at least 8 years).")
