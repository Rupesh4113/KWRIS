"""Page 1: Overview Dashboard for RainfallIQ."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from src.configuration import APP_CONFIG


def render_overview_page():
    st.title("📊 Executive Overview & Quality Scorecard")
    st.markdown("Real-time hydrological health metrics, issue severity distribution, and station quality breakdown.")

    if "norm_df" not in st.session_state or st.session_state.norm_df.empty:
        st.warning("⚠️ No dataset currently loaded. Please upload a dataset in **Page 2: Upload Data** or click **⚡ Load Demo Dataset** on the Home page.")
        return

    norm_df = st.session_state.norm_df
    summary = st.session_state.summary_info
    issues_df = st.session_state.issues_df
    priorities_df = st.session_state.priorities_df
    predictions_df = st.session_state.predictions_df

    # Top KPI Metrics Row
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Records", f"{len(norm_df):,}")
    m2.metric("Total Stations", f"{summary.get('total_stations', 0)}")
    m3.metric("Missing Readings", f"{summary.get('missing_rainfall_count', 0)}")
    m4.metric("Flagged Issues", f"{len(issues_df)}")
    m5.metric("Predicted Estimates", f"{len(predictions_df)}")
    
    score = summary.get("quality_score", 100.0)
    score_delta = "Healthy" if score >= 85 else ("Attention Req." if score >= 60 else "Critical")
    m6.metric("Data Quality Score", f"{score}%", delta=score_delta)

    st.markdown("---")

    # Quality Score Transparency Box
    with st.expander("ℹ️ How the Data Quality Score is Calculated", expanded=True):
        st.markdown(f"**Explanation:** {summary.get('quality_score_explanation', 'N/A')}")
        st.caption("Penalties: Critical errors (-6.0 per record%), High severity (-2.5%), Medium issues (-0.8%), Low (-0.2%). Clamped between 0% and 100%.")

    # Visualizations Row 1: Severity Breakdown & Station Quality Ranking
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Issue Severity Breakdown")
        if not issues_df.empty:
            sev_counts = issues_df["severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]
            color_map = {"Critical": "#8B0000", "High": "#DD6B20", "Medium": "#D69E2E", "Low": "#3182CE"}
            fig_sev = px.pie(
                sev_counts, values="Count", names="Severity",
                color="Severity", color_discrete_map=color_map,
                hole=0.45
            )
            fig_sev.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            st.info("No issues detected in current dataset.")

    with col_chart2:
        st.subheader("Station Priority Tiers")
        if not priorities_df.empty:
            cat_counts = priorities_df["priority_category"].value_counts().reset_index()
            cat_counts.columns = ["Priority Tier", "Stations"]
            color_map = {"Critical": "#8B0000", "High": "#DD6B20", "Medium": "#D69E2E", "Low": "#38A169"}
            fig_prio = px.bar(
                cat_counts, x="Priority Tier", y="Stations",
                color="Priority Tier", color_discrete_map=color_map
            )
            fig_prio.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_prio, use_container_width=True)
        else:
            st.info("Station priority data not available.")

    # Visualizations Row 2: Rainfall Time Series & Historical Coverage
    col_ts, col_cov = st.columns([3, 2])

    with col_ts:
        st.subheader("Network Rainfall Observations Timeline")
        # Sample or aggregate to daily network average for performance
        ts_agg = norm_df.groupby("date")["rainfall"].agg(["mean", "max", "min"]).reset_index()
        fig_ts = go.Figure()
        fig_ts.add_trace(go.Scatter(
            x=ts_agg["date"], y=ts_agg["max"],
            mode="lines", name="Daily Network Max (mm)",
            line=dict(color="#8B0000", width=1.5)
        ))
        fig_ts.add_trace(go.Scatter(
            x=ts_agg["date"], y=ts_agg["mean"],
            mode="lines", name="Daily Network Mean (mm)",
            line=dict(color="#3182CE", width=2)
        ))
        fig_ts.update_layout(
            xaxis_title="Date", yaxis_title="Rainfall (mm)",
            hovermode="x unified", height=320,
            margin=dict(t=20, b=20, l=20, r=20)
        )
        st.plotly_chart(fig_ts, use_container_width=True)

    with col_cov:
        st.subheader("Available Historical Baseline Coverage")
        if "hist_mgr" in st.session_state:
            stn_ids = list(norm_df["station_id"].unique())
            cov_df = st.session_state.hist_mgr.get_station_coverage(stn_ids)
            if not cov_df.empty:
                fig_cov = px.bar(
                    cov_df, x="station_id", y="coverage_years",
                    color="coverage_years", color_continuous_scale="Reds",
                    labels={"coverage_years": "Years Available", "station_id": "Station ID"}
                )
                fig_cov.add_hline(y=20, line_dash="dash", line_color="green", annotation_text="Target (20 Yrs)")
                fig_cov.update_layout(height=320, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_cov, use_container_width=True)
            else:
                st.warning("No historical records currently loaded for these stations.")


render_overview_page()
