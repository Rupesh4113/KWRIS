"""Page 3: Validation Results & Detected Issues for RainfallIQ."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np


def render_validation_results_page():
    st.title("🔍 Validation Results & Issue Inspection")
    st.markdown("Detailed breakdown of all detected missing observations, invalid readings, and suspected anomalies.")

    if "issues_df" not in st.session_state or st.session_state.issues_df.empty:
        st.info("No flagged issues detected. Please upload and validate a dataset in **Page 2: Upload Data** or click **⚡ Load Demo Dataset**.")
        return

    issues_df = st.session_state.issues_df.copy()

    # Issue Summary Metric Cards
    crit_count = int((issues_df["severity"] == "Critical").sum())
    high_count = int((issues_df["severity"] == "High").sum())
    med_count = int((issues_df["severity"] == "Medium").sum())
    low_count = int((issues_df["severity"] == "Low").sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Issues", f"{len(issues_df)}")
    c2.metric("Critical", f"{crit_count}")
    c3.metric("High", f"{high_count}")
    c4.metric("Medium", f"{med_count}")
    c5.metric("Low", f"{low_count}")

    st.markdown("---")

    # Multi-factor Filters
    st.subheader("Filter Issues")
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)

    with f_col1:
        stn_options = ["All Stations"] + sorted(list(issues_df["station_id"].astype(str).unique()))
        selected_stn = st.selectbox("Station ID:", stn_options)

    with f_col2:
        sev_options = ["All Severities"] + sorted(list(issues_df["severity"].unique()))
        selected_sev = st.selectbox("Severity:", sev_options)

    with f_col3:
        type_options = ["All Issue Types"] + sorted(list(issues_df["issue_type"].unique()))
        selected_type = st.selectbox("Issue Type:", type_options)

    with f_col4:
        rule_options = ["All Rules"] + sorted(list(issues_df["validation_rule"].unique()))
        selected_rule = st.selectbox("Validation Rule:", rule_options)

    # Apply Filters
    filtered_df = issues_df.copy()
    if selected_stn != "All Stations":
        filtered_df = filtered_df[filtered_df["station_id"] == selected_stn]
    if selected_sev != "All Severities":
        filtered_df = filtered_df[filtered_df["severity"] == selected_sev]
    if selected_type != "All Issue Types":
        filtered_df = filtered_df[filtered_df["issue_type"] == selected_type]
    if selected_rule != "All Rules":
        filtered_df = filtered_df[filtered_df["validation_rule"] == selected_rule]

    st.markdown(f"**Showing {len(filtered_df)} of {len(issues_df)} records:**")

    # Styled DataFrame Display
    display_cols = [
        "station_id", "observation_date", "original_value", "issue_type",
        "severity", "validation_rule", "explanation", "recommended_action", "review_status"
    ]
    st.dataframe(
        filtered_df[display_cols],
        use_container_width=True,
        column_config={
            "severity": st.column_config.TextColumn(
                "Severity",
                help="Critical: Immediate action required; High: Suspicious reading; Medium: Moderate anomaly."
            ),
            "original_value": st.column_config.TextColumn("Original Reading"),
            "recommended_action": st.column_config.TextColumn("Action Required", width="large"),
            "explanation": st.column_config.TextColumn("Hydrological Explanation", width="large")
        }
    )

    st.markdown("---")
    st.caption("Tip: Head to **Page 6: Engineer Action Center** to accept estimates or resolve flagged issues.")


render_validation_results_page()
