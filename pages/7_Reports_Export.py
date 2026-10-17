"""Page 7: Reports and Data Export Center for RainfallIQ."""

from __future__ import annotations
from datetime import datetime
import streamlit as st
import pandas as pd

from src.reporting import ReportGenerator, sanitize_dataframe


def render_reports_page():
    st.title("📑 Reports & Data Export Center")
    st.markdown("Download full multi-sheet production Excel workbooks and CSV files with complete provenance and audit trails.")

    if "norm_df" not in st.session_state or st.session_state.norm_df.empty:
        st.info("No active dataset loaded. Please upload data or load the demo dataset.")
        return

    norm_df = st.session_state.norm_df
    summary = st.session_state.summary_info
    issues_df = st.session_state.issues_df
    priorities_df = st.session_state.priorities_df
    predictions_df = st.session_state.predictions_df
    audit_df = st.session_state.storage_mgr.get_audit_trail() if "storage_mgr" in st.session_state else pd.DataFrame()

    cp1_rep = st.session_state.get("checkpoint1_report", {})
    cp1_summary = cp1_rep.get("station_summary", pd.DataFrame())
    cp1_missing = cp1_rep.get("missing_dates_detail", pd.DataFrame())

    generator = ReportGenerator()

    # Pre-generate Excel Workbook in-memory
    with st.spinner("Generating styled multi-sheet production Excel workbook..."):
        excel_buffer = generator.generate_excel_report(
            summary_info=summary,
            issues_df=issues_df,
            priorities_df=priorities_df,
            predictions_df=predictions_df,
            audit_df=audit_df,
            dataset_df=norm_df,
            checkpoint1_summary=cp1_summary,
            missing_dates_df=cp1_missing
        )

    st.subheader("Production Excel Workbook (Up to 8 Sheets)")
    st.markdown("""
    Includes:
    1. **Executive_Summary**: KPIs, Quality Score calculation formula, and provenance metadata.
    2. **Station_Timeline_CP1**: Checkpoint 1 Station-wise expected vs recorded days, missing days, and blackout gaps.
    3. **Missing_Dates_Detail**: Granular calendar dates missing from each station's continuous observation window.
    4. **Data_Issues**: Full catalog of flagged errors, severities, rules, and recommended actions.
    5. **Station_Priority_Health**: Ranked station health scores (0-100) and urgency triage tiers.
    6. **Missing_Predictions**: All AI-imputed values tagged **`ESTIMATED — NOT OBSERVED`** with confidence intervals.
    7. **Audit_Trail**: Immutable engineering review decisions, notes, and timestamps.
    8. **Full_Dataset_With_Estimates**: Original field measurements preserved with separate estimated fields.
    """)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"RainfallIQ_Validation_Report_{timestamp_str}.xlsx"

    st.download_button(
        label="📥 Download Complete Production Excel Workbook (.xlsx)",
        data=excel_buffer,
        file_name=excel_filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )

    st.markdown("---")
    st.subheader("Granular CSV Exports")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown("#### **Checkpoint 1 Timeline Summary CSV**")
        st.caption(f"{len(cp1_summary)} stations analyzed for timeline continuity.")
        if not cp1_summary.empty:
            clean_cp1_csv = sanitize_dataframe(cp1_summary).to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download CP1 Summary CSV",
                data=clean_cp1_csv,
                file_name=f"RainfallIQ_CP1_Timeline_Summary_{timestamp_str}.csv",
                mime="text/csv",
                use_container_width=True
            )

    with c2:
        st.markdown("#### **Missing Dates Detail CSV**")
        st.caption(f"{len(cp1_missing):,} exact missing calendar dates.")
        if not cp1_missing.empty:
            clean_miss_csv = sanitize_dataframe(cp1_missing).to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Missing Dates CSV",
                data=clean_miss_csv,
                file_name=f"RainfallIQ_Missing_Dates_{timestamp_str}.csv",
                mime="text/csv",
                use_container_width=True
            )

    with c3:
        st.markdown("#### **Flagged Issues CSV**")
        st.caption(f"{len(issues_df)} flagged validation issues and anomalies.")
        if not issues_df.empty:
            clean_issues = sanitize_dataframe(issues_df)
            csv_issues = clean_issues.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Issues CSV",
                data=csv_issues,
                file_name=f"RainfallIQ_Issues_{timestamp_str}.csv",
                mime="text/csv",
                use_container_width=True
            )

    with c4:
        st.markdown("#### **Missing Predictions CSV**")
        st.caption(f"{len(predictions_df)} AI estimates (ESTIMATED — NOT OBSERVED).")
        if not predictions_df.empty:
            clean_preds = sanitize_dataframe(predictions_df)
            csv_preds = clean_preds.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Estimates CSV",
                data=csv_preds,
                file_name=f"RainfallIQ_Estimates_{timestamp_str}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("No predictions yet.")

    st.markdown("---")
    st.info("🔒 **Data Governance & Security Note:** All exports are automatically sanitized against spreadsheet formula injection (CWE-1236) and preserve original measured observations without in-place mutation.")


render_reports_page()
