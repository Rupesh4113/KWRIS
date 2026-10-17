"""Page 3: Validation Results & Checkpoint 1 Station Timeline Validation."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from src.station_timeline_validation import generate_checkpoint1_report, Checkpoint1Thresholds


def render_validation_results_page():
    st.title("🔍 Data Validation & Diagnostic Checkpoints")
    st.markdown("Automated multi-checkpoint validation pipeline governed by the National Hydrology Project (NHP) standards.")

    if "raw_df" not in st.session_state or st.session_state.raw_df.empty:
        st.info("⚠️ No dataset currently active. Please upload a dataset in **Page 2: Upload Data** or click **⚡ Load Demo Dataset**.")
        return

    raw_df = st.session_state.raw_df
    norm_df = st.session_state.norm_df
    issues_df = st.session_state.get("issues_df", pd.DataFrame())

    # Ensure Checkpoint 1 report exists
    if "checkpoint1_report" not in st.session_state or not st.session_state.checkpoint1_report:
        with st.spinner("Generating Checkpoint 1: Station Timeline Validation Report..."):
            col_map = {
                "date": "Day" if "Day" in raw_df.columns else norm_df.columns[0],
                "station_code": "WIMS Code" if "WIMS Code" in raw_df.columns else "station_id",
                "station_name": "LocationName" if "LocationName" in raw_df.columns else "station_name",
                "rainfall": "RF(mm)" if "RF(mm)" in raw_df.columns else "rainfall"
            }
            thresh = st.session_state.get("cp1_thresholds", Checkpoint1Thresholds())
            st.session_state.checkpoint1_report = generate_checkpoint1_report(raw_df, col_map, thresholds=thresh)

    cp1_rep = st.session_state.checkpoint1_report

    # Main Tabs for the Validation Checkpoints
    tab_cp1, tab_cp2, tab_cp3, tab_cp4 = st.tabs([
        "🕒 Checkpoint 1 — Station Timeline Validation",
        "⚠️ Checkpoint 2 — Limits & Record Integrity (P1, P2)",
        "🌪️ Checkpoint 3 — Ceilings & Statistical Anomalies (P3, P4)",
        "🌐 Checkpoint 4 — Spatial Homogeneity & NHP Rules (S1–S8, P5)"
    ])

    # =========================================================================
    # TAB 1: CHECKPOINT 1 — STATION TIMELINE VALIDATION
    # =========================================================================
    with tab_cp1:
        st.subheader("Checkpoint 1 — Station Timeline Validation")
        st.caption("Continuity analysis: Expected calendar days vs unique valid recorded dates, blackout gaps, and duplicates.")

        metrics = cp1_rep.get("metrics", {})
        summary_df = cp1_rep.get("station_summary", pd.DataFrame())
        missing_dates_df = cp1_rep.get("missing_dates_detail", pd.DataFrame())
        invalid_df = cp1_rep.get("invalid_records", pd.DataFrame())
        dup_df = cp1_rep.get("duplicate_records", pd.DataFrame())

        # 8 KPI Metric Cards
        kpi_row1 = st.columns(4)
        kpi_row1[0].metric("Total Stations Identified", f"{metrics.get('total_stations', 0)}")
        kpi_row1[1].metric("Valid Recorded Obs", f"{metrics.get('total_valid_obs', 0):,}")
        kpi_row1[2].metric("Expected Observation Days", f"{metrics.get('total_expected_days', 0):,}")
        kpi_row1[3].metric("Missing Calendar Days", f"{metrics.get('total_missing_days', 0):,}")

        kpi_row2 = st.columns(4)
        kpi_row2[0].metric("Duplicate Station-Dates", f"{metrics.get('duplicate_records_count', 0):,}")
        kpi_row2[1].metric("Invalid Essential Records", f"{metrics.get('invalid_records_count', 0):,}")
        kpi_row2[2].metric("Stations Requiring Attention", f"{metrics.get('stations_requiring_attention', 0)}")
        completeness = metrics.get('overall_completeness_pct', 0.0)
        kpi_row2[3].metric(
            "Overall Date Completeness",
            f"{completeness:.1f}%",
            delta="Healthy" if completeness >= 95 else ("Attention" if completeness >= 85 else "Severe Gap")
        )

        st.markdown("---")

        # Station Summary Table & Filters
        st.markdown("### **Station Timeline Summary Table**")
        st.caption("Default sorted by highest missing calendar days. Use filters below to refine stations:")

        if not summary_df.empty:
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                stn_code_filter = st.multiselect("Station Code:", sorted(summary_df["station_code"].unique()))
            with f2:
                priority_filter = st.multiselect("Priority Tier:", ["Critical", "High", "Medium", "Low"])
            with f3:
                min_completeness = st.slider("Min Completeness %:", 0.0, 100.0, 0.0, step=5.0)
            with f4:
                min_missing_days = st.number_input("Min Missing Days:", min_value=0, value=0, step=10)

            filtered_summary = summary_df.copy()
            if stn_code_filter:
                filtered_summary = filtered_summary[filtered_summary["station_code"].isin(stn_code_filter)]
            if priority_filter:
                filtered_summary = filtered_summary[filtered_summary["priority_level"].isin(priority_filter)]
            if min_completeness > 0.0:
                filtered_summary = filtered_summary[filtered_summary["data_completeness_pct"] >= min_completeness]
            if min_missing_days > 0:
                filtered_summary = filtered_summary[filtered_summary["missing_calendar_days"] >= min_missing_days]

            st.dataframe(
                filtered_summary[[
                    "station_code", "station_name", "first_recorded_date", "last_recorded_date",
                    "expected_calendar_days", "unique_recorded_dates", "missing_calendar_days",
                    "data_completeness_pct", "max_consecutive_gap_days", "duplicate_records",
                    "invalid_date_records", "missing_rainfall_values", "priority_level",
                    "issue_description", "recommended_action"
                ]],
                use_container_width=True,
                column_config={
                    "priority_level": st.column_config.TextColumn(
                        "Priority Level",
                        help="Critical: Severe missing volume or >30d blackout; High: >14d gap; Medium: >3d gap; Low: Complete/minor"
                    ),
                    "data_completeness_pct": st.column_config.ProgressColumn(
                        "Completeness %", min_value=0, max_value=100, format="%.1f%%"
                    ),
                    "expected_calendar_days": st.column_config.NumberColumn("Expected Days", format="%d"),
                    "unique_recorded_dates": st.column_config.NumberColumn("Recorded Days", format="%d"),
                    "missing_calendar_days": st.column_config.NumberColumn("Missing Days", format="%d"),
                    "max_consecutive_gap_days": st.column_config.NumberColumn("Max Gap (Days)", format="%d d"),
                    "issue_description": st.column_config.TextColumn("Diagnostic Rationale", width="large"),
                    "recommended_action": st.column_config.TextColumn("Recommended Action", width="large")
                }
            )

            st.markdown("---")

            # Station Deep Dive Panel
            st.markdown("### **Station Timeline Diagnostic Deep-Dive**")
            station_choices = summary_df["station_code"].tolist()
            selected_stn_code = st.selectbox("Select Station Code for Deep-Dive Timeline:", station_choices)

            stn_row = summary_df[summary_df["station_code"] == selected_stn_code].iloc[0]

            sd1, sd2, sd3, sd4 = st.columns(4)
            sd1.metric("Station Name", stn_row["station_name"])
            sd1.caption(f"Code: `{stn_row['station_code']}`")
            sd2.metric("Recording Window", f"{stn_row['first_recorded_date']} to {stn_row['last_recorded_date']}")
            sd2.caption(f"{stn_row['expected_calendar_days']:,} expected calendar days")
            sd3.metric("Max Consecutive Gap", f"{stn_row['max_consecutive_gap_days']} days", delta=f"{stn_row['priority_level']} Priority", delta_color="inverse")
            sd4.metric("Duplicates / Invalids", f"{stn_row['duplicate_records']} / {stn_row['invalid_date_records']}")

            # Timeline Plot of Valid vs Missing Days
            st.markdown("#### **Timeline of Available Observations & Transmission Blackouts**")
            stn_missing = missing_dates_df[missing_dates_df["station_code"] == selected_stn_code] if not missing_dates_df.empty else pd.DataFrame()

            fig_timeline = go.Figure()
            # Show missing date points or gap intervals
            if not stn_missing.empty:
                miss_dts = pd.to_datetime(stn_missing["missing_date"])
                fig_timeline.add_trace(go.Scatter(
                    x=miss_dts, y=[1] * len(miss_dts),
                    mode="markers",
                    name="Missing Calendar Day",
                    marker=dict(color="#8B0000", size=7, symbol="x")
                ))
                fig_timeline.update_layout(
                    title=f"Missing Observation Calendar Days — {stn_row['station_name']} ({len(stn_missing):,} Days)",
                    xaxis_title="Date", yaxis_visible=False,
                    height=240, margin=dict(t=35, b=20, l=20, r=20)
                )
                st.plotly_chart(fig_timeline, use_container_width=True)
            else:
                st.success("No missing observation dates detected for this station!")

            # Granular Problematic Dates Table
            st.markdown("#### **Granular Problematic Dates Registry**")
            sub_tab_miss, sub_tab_dup, sub_tab_inv = st.tabs([
                f"Missing Observation Dates ({len(stn_missing):,})",
                f"Duplicate Records ({stn_row['duplicate_records']})",
                f"Invalid Date Rows ({stn_row['invalid_date_records']})"
            ])

            with sub_tab_miss:
                if not stn_missing.empty:
                    st.dataframe(
                        stn_missing[["missing_date", "year", "month", "gap_id", "consecutive_gap_length", "status"]],
                        use_container_width=True,
                        column_config={
                            "missing_date": st.column_config.TextColumn("Missing Calendar Date"),
                            "consecutive_gap_length": st.column_config.NumberColumn("Continuous Gap Length (Days)")
                        }
                    )
                else:
                    st.info("No missing calendar dates.")

            with sub_tab_dup:
                stn_dups = dup_df[dup_df["station_code"] == selected_stn_code] if not dup_df.empty else pd.DataFrame()
                if not stn_dups.empty:
                    st.dataframe(stn_dups, use_container_width=True)
                else:
                    st.info("No duplicate records for this station.")

            with sub_tab_inv:
                stn_invalids = invalid_df[invalid_df["station_code"] == selected_stn_code] if not invalid_df.empty else pd.DataFrame()
                if not stn_invalids.empty:
                    st.dataframe(stn_invalids, use_container_width=True)
                else:
                    st.info("No invalid date rows for this station.")

            st.markdown(f"**Recommended Action:** {stn_row['recommended_action']}")

    # =========================================================================
    # TAB 2: CHECKPOINT 2 — MISSING VALUES & INVALID READINGS
    # =========================================================================
    with tab_cp2:
        st.subheader("Checkpoint 2 — Missing Values & Invalid Readings")
        st.caption("Verification of negative values (< 0 mm), null entries, and conflicting duplicate records.")

        if not issues_df.empty:
            cp2_issues = issues_df[issues_df["validation_rule"].str.startswith("V_")]
            if not cp2_issues.empty:
                st.dataframe(
                    cp2_issues[[
                        "station_id", "observation_date", "original_value", "issue_type",
                        "severity", "validation_rule", "explanation", "recommended_action"
                    ]],
                    use_container_width=True
                )
            else:
                st.success("No Checkpoint 2 value-level defects detected!")
        else:
            st.info("No issues detected.")

    # =========================================================================
    # TAB 3: CHECKPOINT 3 — SUSPICIOUS OBSERVATIONS & ANOMALIES
    # =========================================================================
    with tab_cp3:
        st.subheader("Checkpoint 3 — Suspicious Observations & Anomaly Detection")
        st.caption("Physical domain ceilings (IMD 400 mm benchmark), robust MAD Z-scores, Isolation Forest ML, and spatial discordance.")

        if not issues_df.empty:
            cp3_issues = issues_df[issues_df["validation_rule"].str.startswith("A_")]
            if not cp3_issues.empty:
                st.dataframe(
                    cp3_issues[[
                        "station_id", "observation_date", "original_value", "issue_type",
                        "severity", "validation_rule", "explanation", "recommended_action"
                    ]],
                    use_container_width=True
                )
            else:
                st.success("No Checkpoint 3 anomalies detected!")
        else:
            st.info("No anomalies detected.")

    # =========================================================================
    # TAB 4: CHECKPOINT 4 — SPATIAL HOMOGENEITY & NHP RULES (S1–S8, P5)
    # =========================================================================
    with tab_cp4:
        st.subheader("Checkpoint 4 — Spatial Homogeneity & NHP Rules (S1–S8, P5)")
        st.caption("Governed by NHP Manual Chapter 4: Quadrant reference selection, shifted-date checks, multi-day accumulations, false zeroes, rainy-day frequency, and double-mass trend analysis.")

        if not issues_df.empty:
            cp4_issues = issues_df[
                issues_df["validation_rule"].str.startswith("S") |
                issues_df["validation_rule"].str.startswith("P5")
            ]
            if not cp4_issues.empty:
                # Summary metrics
                c_s1, c_s2, c_s3, c_s4 = st.columns(4)
                s2_count = int(cp4_issues["validation_rule"].str.startswith("S2").sum())
                s3_count = int((cp4_issues["validation_rule"] == "S3_SHIFTED_DATE").sum())
                s4_count = int((cp4_issues["validation_rule"] == "S4_ACCUMULATED_TOTAL").sum())
                s8_count = int((cp4_issues["validation_rule"] == "S8_DOUBLE_MASS").sum())

                c_s1.metric("Spatial Homogeneity Departures (S2)", f"{s2_count}")
                c_s2.metric("Shifted Dates / Observer Lags (S3)", f"{s3_count}")
                c_s3.metric("Multi-Day Accumulations (S4)", f"{s4_count}")
                c_s4.metric("Double-Mass Systematic Breaks (S8)", f"{s8_count}")

                st.markdown("---")
                st.dataframe(
                    cp4_issues[[
                        "station_id", "observation_date", "original_value", "issue_type",
                        "severity", "validation_rule", "explanation", "recommended_action"
                    ]],
                    use_container_width=True
                )
            else:
                st.success("No Checkpoint 4 spatial inconsistencies or systematic shifts detected!")
        else:
            st.info("No spatial validation issues recorded.")


render_validation_results_page()
