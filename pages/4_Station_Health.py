"""Page 4: Station Health & Hydrological Diagnostic Profiling for RainfallIQ."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


def render_station_health_page():
    st.title("🏥 Station Health & Telemetry Diagnostics")
    st.markdown("Detailed health diagnostics, historical coverage, and rainfall timelines for individual monitoring stations.")

    if "norm_df" not in st.session_state or st.session_state.norm_df.empty:
        st.info("No active dataset loaded. Please upload data or load the demo dataset.")
        return

    norm_df = st.session_state.norm_df
    priorities_df = st.session_state.priorities_df
    issues_df = st.session_state.issues_df

    st.subheader("Station Quality Leaderboard")
    if not priorities_df.empty:
        st.dataframe(
            priorities_df[[
                "station_id", "station_name", "priority_category", "priority_score",
                "completeness_pct", "missing_records", "max_gap_days", "critical_issues",
                "high_issues", "historical_years", "primary_reason"
            ]],
            use_container_width=True,
            column_config={
                "priority_category": st.column_config.TextColumn("Priority Tier"),
                "priority_score": st.column_config.ProgressColumn(
                    "Priority Score (0-100)", min_value=0, max_value=100, format="%.1f"
                ),
                "completeness_pct": st.column_config.NumberColumn("Completeness %", format="%.1f%%"),
                "primary_reason": st.column_config.TextColumn("Diagnostic Rationale", width="large")
            }
        )

    st.markdown("---")

    # Station Deep Dive Selector
    st.subheader("Station Time-Series Deep Dive")
    station_list = sorted(list(norm_df["station_id"].unique()))
    selected_stn = st.selectbox("Select Station for Deep-Dive Analysis:", station_list)

    stn_df = norm_df[norm_df["station_id"] == selected_stn].sort_values("date").copy()
    stn_issues = issues_df[issues_df["station_id"] == selected_stn] if not issues_df.empty else pd.DataFrame()
    stn_prio = priorities_df[priorities_df["station_id"] == selected_stn].iloc[0] if not priorities_df.empty else None

    # Station KPI Card Row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Station Name", stn_df["station_name"].iloc[0] if "station_name" in stn_df.columns else selected_stn)
    k2.metric("Completeness", f"{stn_prio['completeness_pct']}%" if stn_prio is not None else "N/A")
    k3.metric("Missing Days", f"{stn_prio['missing_records']}" if stn_prio is not None else "0")
    k4.metric("Max Gap", f"{stn_prio['max_gap_days']} days" if stn_prio is not None else "0")
    k5.metric("Historical Baseline", f"{stn_prio['historical_years']} Years" if stn_prio is not None else "0")

    # Interactive Plotly Time Series Plot
    fig = go.Figure()

    # Valid observed readings
    valid_obs = stn_df.dropna(subset=["rainfall"])
    fig.add_trace(go.Bar(
        x=valid_obs["date"], y=valid_obs["rainfall"],
        name="Observed Rainfall (mm)",
        marker_color="#2B6CB0",
        opacity=0.8
    ))

    # Flagged Anomaly Points (Overlay in red)
    if not stn_issues.empty:
        anom_dates = stn_issues[stn_issues["severity"].isin(["Critical", "High"])]["observation_date"]
        anom_rows = valid_obs[valid_obs["date"].dt.strftime("%Y-%m-%d").isin(anom_dates)]
        if not anom_rows.empty:
            fig.add_trace(go.Scatter(
                x=anom_rows["date"], y=anom_rows["rainfall"],
                mode="markers",
                name="Flagged Critical/High Anomaly",
                marker=dict(color="#8B0000", size=10, symbol="triangle-up")
            ))

    fig.update_layout(
        title=f"Daily Rainfall Observation Profile — {selected_stn}",
        xaxis_title="Date", yaxis_title="Daily Rainfall (mm)",
        hovermode="x unified", height=380,
        margin=dict(t=35, b=20, l=20, r=20)
    )
    st.plotly_chart(fig, use_container_width=True)

    # Missing Dates Timeline
    missing_dates = stn_df[stn_df["rainfall"].isna()]["date"]
    if not missing_dates.empty:
        st.markdown(f"#### **Missing Dates Timeline ({len(missing_dates)} Days)**")
        missing_str = ", ".join(missing_dates.dt.strftime("%Y-%m-%d").tolist()[:30])
        if len(missing_dates) > 30:
            missing_str += f" ... (+{len(missing_dates) - 30} more)"
        st.caption(f"Dates with missing observations: {missing_str}")
    else:
        st.success("No missing observation dates detected for this station!")


render_station_health_page()
