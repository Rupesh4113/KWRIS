"""Export Reports & Validation Documentation Page.
Provides single-click downloads for the production 13-sheet Excel report, cleaned data, and rules reference.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.reporting import generate_kwris_excel_report, generate_cleaned_dataset_excel
from src.statistics import compute_station_monthly_statistics, compute_station_yearly_statistics
from src.station_ranking import compute_station_priority_ranking


def render_export_reports_page():
    st.markdown("## 📑 Export Reports & Validation Standards")
    st.markdown(
        "Generate audit-ready Excel reports, export cleaned hydrological records, "
        "and review the National Hydrology Project manual validation principles."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first in **Upload & Profiling**.")
        return
        
    df_raw = st.session_state.get("df_raw", pd.DataFrame())
    df_annotated = st.session_state.get("df_annotated", st.session_state["df_norm"])
    flags = st.session_state.get("flags", [])
    audit_mgr = st.session_state.get("audit_mgr")
    audit_df = audit_mgr.to_dataframe() if audit_mgr else pd.DataFrame()
    est_df = st.session_state.get("neighbour_estimates_df", pd.DataFrame())
    
    monthly_stats = st.session_state.get("monthly_stats")
    if monthly_stats is None or monthly_stats.empty:
        monthly_stats = compute_station_monthly_statistics(df_annotated)
        st.session_state["monthly_stats"] = monthly_stats
        
    yearly_stats = st.session_state.get("yearly_stats")
    if yearly_stats is None or yearly_stats.empty:
        yearly_stats = compute_station_yearly_statistics(df_annotated)
        st.session_state["yearly_stats"] = yearly_stats
        
    station_ranking = st.session_state.get("station_ranking")
    if station_ranking is None or station_ranking.empty:
        station_ranking = compute_station_priority_ranking(df_annotated, flags, st.session_state.get("coords_map", {}))
        st.session_state["station_ranking"] = station_ranking

    processing_log = [
        f"Ingested {st.session_state.get('file_name', 'Dataset')} ({len(df_annotated):,} records).",
        f"Primary Validation Flags: {len(st.session_state.get('primary_flags', []))}.",
        f"Secondary Validation Flags: {len(st.session_state.get('secondary_flags', []))}.",
        f"Correction Proposals: {len(audit_df)} (Approved: {(audit_df.get('review_status', '') == 'approved').sum() if not audit_df.empty else 0})."
    ]
    
    tab1, tab2, tab3 = st.tabs([
        "📥 Download Production Workbooks",
        "📋 13-Sheet Workbook Structure",
        "📖 NHP Validation Standards & Principles"
    ])
    
    # Tab 1: Downloads
    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### 1. Complete 13-Sheet Excel")
            st.caption("Full audit-ready workbook with Read_Me, Original_Data, Validated_Data, Corrected_Data, Suspicious_Readings, Station_Summary, Monthly/Yearly Stats, and Audit Trail.")
            with st.spinner("Compiling 13-sheet report..."):
                excel_bytes = generate_kwris_excel_report(
                    df_raw=df_raw,
                    df_annotated=df_annotated,
                    flags=flags,
                    audit_df=audit_df,
                    estimates_df=est_df,
                    monthly_stats=monthly_stats,
                    yearly_stats=yearly_stats,
                    station_ranking=station_ranking,
                    processing_log=processing_log,
                    rules_config={}
                )
            st.download_button(
                label="⬇️ Download Full 13-Sheet Report",
                data=excel_bytes.getvalue(),
                file_name=f"KWRIS_Rainfall_Quality_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
        with c2:
            st.markdown("#### 2. Cleaned Data (Excel)")
            st.caption("Validated dataset with approved corrections and filled gaps for hydrological modeling.")
            cleaned_bytes = generate_cleaned_dataset_excel(df_annotated)
            st.download_button(
                label="⬇️ Download Cleaned Data (XLSX)",
                data=cleaned_bytes.getvalue(),
                file_name=f"KWRIS_Cleaned_Rainfall_Data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        with c3:
            st.markdown("#### 3. Cleaned Data (CSV)")
            st.caption("Lightweight CSV format of validated observations and flags.")
            csv_data = df_annotated.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download Cleaned Data (CSV)",
                data=csv_data,
                file_name=f"KWRIS_Cleaned_Rainfall_Data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

    # Tab 2: Workbook Overview
    with tab2:
        sheets_info = [
            ("Read_Me", "Processing summary, conventions, limitations, and user instructions."),
            ("Original_Data", f"Unchanged original uploaded data ({len(df_raw):,} rows)."),
            ("Validated_Data", f"Observations with validation statuses and rule tags ({len(df_annotated):,} rows)."),
            ("Corrected_Data", "Proposed and approved traceable corrections."),
            ("Missing_Data", f"Records with missing rainfall ({(df_annotated['rainfall_mm'].isna()).sum():,} records)."),
            ("Suspicious_Readings", f"Flagged doubtful anomalies ({len(flags):,} flags)."),
            ("Station_Summary", f"Station quality health metrics and priority scores ({len(station_ranking)} stations)."),
            ("Monthly_Statistics", f"Standard monthly aggregations and skewness ({len(monthly_stats):,} records)."),
            ("Yearly_Statistics", f"Annual totals and completeness checks ({len(yearly_stats):,} records)."),
            ("Neighbour_Analysis", f"Spatial IDW estimates and discrepancies ({len(est_df):,} records)."),
            ("Correction_Audit", f"Complete audit trail of all proposals and decisions ({len(audit_df):,} records)."),
            ("Validation_Rules", "Inventory of all 27 validation and correction rules."),
            ("Processing_Log", "Execution log and system messages.")
        ]
        st.table(pd.DataFrame(sheets_info, columns=["Worksheet", "Contents & Purpose"]))

    # Tab 3: Standards & Principles
    with tab3:
        st.markdown("### 🏛️ Foundational Hydrological Principles (NHP Manual, May 2019)")
        st.markdown(
            """
            | Principle | Operational Rule in KWRIS Platform |
            |---|---|
            | **1. Flag, do not delete** | Keep every original value intact. Mark suspects as `doubtful` and record reason. Change only when clearly wrong and traceable, marking as `corrected`. |
            | **2. A test screens; it does not decide** | No single check proves a value wrong. A flag means *'look again'*. Field metadata and neighbouring gauges confirm or clear it. |
            | **3. Extremes can be real** | Genuine extreme rainfall is vital for dam safety and flood design. Do not auto-reject high values without neighbour cross-checks. |
            | **4. Zero is not missing** | $0.0\text{ mm}$ means no rain fell. Missing means no measurement exists. They are distinct types and must never be converted into one another. |
            | **5. Measured beats estimated** | Measured observations are always more reliable than filled estimates. Label filled gaps as `completed` with clear method attribution. |
            """
        )
