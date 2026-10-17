"""Station Quality Ranking and Triage Priority Interface."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.station_ranking import compute_station_priority_ranking


def render_ranking_page():
    st.markdown("## 🏆 Station Quality Priority Ranking")
    st.markdown(
        "A transparent operational triage scoring system to guide engineers and hydrologists "
        "to the most urgent station data problems first."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first.")
        return
        
    df_active = st.session_state.get("df_annotated", st.session_state["df_norm"])
    flags = st.session_state.get("flags", [])
    coords_map = st.session_state.get("coords_map", {})
    
    with st.spinner("Calculating multi-factor station priority scores..."):
        df_ranking = compute_station_priority_ranking(df_active, flags, coords_map)
        st.session_state["station_ranking"] = df_ranking
        
    if df_ranking.empty:
        st.info("No stations available for ranking.")
        return
        
    # Urgency metric counters
    urgency_counts = df_ranking["urgency"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Critical Urgency", f"{urgency_counts.get('CRITICAL', 0)}", delta="Requires immediate action", delta_color="inverse")
    c2.metric("High Urgency", f"{urgency_counts.get('HIGH', 0)}", delta="Review & gap-fill", delta_color="inverse")
    c3.metric("Moderate", f"{urgency_counts.get('MODERATE', 0)}")
    c4.metric("Low Urgency (Clean)", f"{urgency_counts.get('LOW', 0)}")
    
    st.divider()
    
    # Filter
    urg_filter = st.multiselect("Filter by Urgency Level:", ["CRITICAL", "HIGH", "MODERATE", "LOW"], default=["CRITICAL", "HIGH", "MODERATE", "LOW"])
    df_filtered = df_ranking[df_ranking["urgency"].isin(urg_filter)]
    
    st.markdown("### 📋 Station Priority Leaderboard")
    st.dataframe(
        df_filtered[[
            "station_id", "station_name", "priority_score", "urgency",
            "missing_pct", "doubtful_flags_count", "critical_flags_count",
            "latest_issue", "recommended_action"
        ]],
        use_container_width=True
    )
    
    # Station drill-down explanation
    st.markdown("### 🔎 Station Score Inspection & Rationale")
    selected_stn = st.selectbox("Select Station to View Scoring Breakdown:", df_ranking["station_name"].tolist())
    stn_row = df_ranking[df_ranking["station_name"] == selected_stn].iloc[0]
    
    sc1, sc2 = st.columns([1, 2])
    with sc1:
        st.metric("Priority Score", f"{stn_row['priority_score']} / 100", stn_row["urgency"])
        st.write(f"**Station ID:** `{stn_row['station_id']}`")
        st.write(f"**Missing Records:** {stn_row['missing_records']} ({stn_row['missing_pct']}%)")
        st.write(f"**Doubtful Flags:** {stn_row['doubtful_flags_count']}")
        st.write(f"**Critical Failures:** {stn_row['critical_flags_count']}")
    with sc2:
        st.markdown(f"**Why this score?**")
        st.info(stn_row["score_explanation"])
        st.markdown(f"**Recommended Next Action:**")
        st.success(f"👉 {stn_row['recommended_action']}")
