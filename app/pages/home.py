"""Home Dashboard Overview Page for KWRIS Platform."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from app.components.dashboard import render_kpi_cards, render_health_summary_banner
from src.station_ranking import compute_station_priority_ranking


def render_home_page():
    # Header Banner
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #8B0000 0%, #B22222 100%); padding: 24px 28px; border-radius: 8px; color: white; margin-bottom: 25px;">
            <h1 style="color: white; margin: 0; font-size: 1.85rem; font-weight: 700;">
                KWRIS Rainfall Data Quality & Validation Platform
            </h1>
            <p style="margin: 6px 0 0 0; font-size: 1.05rem; opacity: 0.92;">
                Automated rainfall quality assessment, anomaly detection, gap analysis, and traceable data correction.
            </p>
            <div style="margin-top: 14px; font-size: 0.82rem; opacity: 0.85;">
                Governing standard: National Hydrology Project Manual on Rainfall Data Validation (MoWR, Govt of India)
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Active Dataset Overview
    if "df_norm" in st.session_state and st.session_state["df_norm"] is not None:
        df_active = st.session_state.get("df_annotated", st.session_state["df_norm"])
        total_rec = len(df_active)
        miss_cnt = df_active["rainfall_mm"].isna().sum()
        doubtful_cnt = (df_active.get("validation_status", "") == "doubtful").sum()
        corr_cnt = (df_active.get("is_corrected", False) == True).sum()
        comp_cnt = (df_active.get("is_completed", False) == True).sum()
        valid_cnt = (df_active.get("validation_status", "") == "validated").sum()
        if valid_cnt == 0 and doubtful_cnt == 0:
            valid_cnt = total_rec - miss_cnt
            
        completeness = round(((total_rec - miss_cnt) / max(1, total_rec) * 100.0), 1)
        
        # Render KPI Cards
        render_kpi_cards(
            total_records=total_rec,
            valid_count=valid_cnt,
            missing_count=miss_cnt,
            doubtful_count=doubtful_cnt,
            corrected_count=corr_cnt,
            completed_count=comp_cnt,
            completeness_pct=completeness
        )
        
        render_health_summary_banner(completeness, doubtful_cnt, miss_cnt)
        
        st.divider()
        
        # Priority Stations Triage
        st.markdown("### 🚨 Urgent Attention Leaderboard (Top Stations Requiring Review)")
        flags = st.session_state.get("flags", [])
        coords_map = st.session_state.get("coords_map", {})
        df_ranked = compute_station_priority_ranking(df_active, flags, coords_map)
        
        if not df_ranked.empty:
            st.dataframe(
                df_ranked.head(5)[[
                    "station_id", "station_name", "priority_score", "urgency",
                    "missing_pct", "doubtful_flags_count", "critical_flags_count",
                    "latest_issue", "recommended_action"
                ]],
                use_container_width=True
            )
        
    else:
        st.info("👋 **Welcome to KWRIS!** Get started by uploading your rainfall dataset or loading a pre-configured Karnataka basin dataset.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📂 Quick Load Sample Datasets:")
            if st.button("Load Arkavathi Basin (24 Stations, 1991–2025)"):
                st.session_state["quick_load"] = "ARKAVATHI RAINFALL.xlsx"
                st.session_state["current_page"] = "📤 Upload & Profiling"
                st.rerun()
            if st.button("Load Ghataprabha Basin (30 Stations, 1991–2025)"):
                st.session_state["quick_load"] = "GHATAPRABHA RF KWRIS 1991-2025.xlsx"
                st.session_state["current_page"] = "📤 Upload & Profiling"
                st.rerun()
        with c2:
            st.markdown("#### 🚀 Operational Capabilities:")
            st.markdown(
                """
                - **Primary Validation (P1–P5):** Automated entry screening, minimum ($<0$), daily ceiling, upper warning levels, and dual-gauge comparisons.
                - **Secondary Validation (S1–S8):** IDW spatial estimates, quadrant neighbor picker, 1-day date shift detection, accumulated total detection, and double-mass curves.
                - **Traceable Gap Filling (G1–G8):** Proportional accumulation distribution, normal-ratio neighbor filling, and double-mass slope adjustments.
                - **Hydrological Aggregation (A1–A6):** 08:30 daily cutoff, 52-week standard periods, dekads, completeness rules, and Mann-Whitney consistency tests.
                - **13-Sheet Excel Workbook:** Automated download containing all audit trails, suspicious records, and statistics.
                """
            )

    st.divider()
    
    # Validation Chain Workflow
    st.markdown("### 🔄 Hydrological Quality Validation Workflow")
    st.markdown(
        """
        ```mermaid
        flowchart LR
            A["📤 Raw Rainfall Data (Excel/CSV)"] --> B["🔍 Primary Validation (P1-P5)"]
            B --> C["🌐 Neighbour Validation (S1-S8)"]
            C --> D["🛠️ Gap-Filling & Correction (G1-G8)"]
            D --> E["📈 Statistical Compilation (A1-A6)"]
            E --> F["📑 13-Sheet Excel Export & Reports"]
        ```
        """
    )
