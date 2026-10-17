"""Dashboard overview and KPI metrics cards component."""

from __future__ import annotations
import streamlit as st
import pandas as pd


def render_kpi_cards(
    total_records: int,
    valid_count: int,
    missing_count: int,
    doubtful_count: int,
    corrected_count: int,
    completed_count: int,
    completeness_pct: float
):
    """Render professional KPI metric cards."""
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Total Observations",
            value=f"{total_records:,}"
        )
    with col2:
        st.metric(
            label="Valid Records",
            value=f"{valid_count:,}",
            delta=f"{(valid_count/max(1, total_records)*100):.1f}%"
        )
    with col3:
        st.metric(
            label="Missing Values",
            value=f"{missing_count:,}",
            delta=f"-{(missing_count/max(1, total_records)*100):.1f}%",
            delta_color="inverse"
        )
    with col4:
        st.metric(
            label="Doubtful Flags",
            value=f"{doubtful_count:,}",
            delta=f"{(doubtful_count/max(1, total_records)*100):.1f}%",
            delta_color="inverse"
        )
    with col5:
        st.metric(
            label="Dataset Completeness",
            value=f"{completeness_pct:.1f}%",
            delta="Normal" if completeness_pct >= 90 else "Action Required"
        )


def render_health_summary_banner(completeness_pct: float, doubtful_count: int, missing_count: int):
    """Render operational status alert banner."""
    if completeness_pct >= 95.0 and doubtful_count == 0 and missing_count == 0:
        st.success("🟢 **Dataset Health: Excellent.** All observations validated without doubtful flags or missing records.")
    elif completeness_pct >= 85.0 and doubtful_count < 50:
        st.warning("🟡 **Dataset Health: Moderate Attention Required.** Gaps or doubtful anomalies detected. Propose neighbour corrections or review flags.")
    else:
        st.error("🔴 **Dataset Health: Critical Action Needed.** Substantial data gaps, negative entries, or significant spatial discrepancies detected.")
