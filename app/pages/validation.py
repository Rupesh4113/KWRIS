"""Primary Validation Interface: P1 to P5."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.primary_validation import run_all_primary_validations


def render_validation_page():
    st.markdown("## 🔍 Primary Validation (Rules P1–P5)")
    st.markdown(
        "Screens each station's record individually to detect obvious data entry typos, "
        "physically impossible negatives, excessive maximum ceilings, and dual-gauge discrepancies."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first.")
        return
        
    df_norm = st.session_state["df_norm"]
    
    # Configuration expandable panel
    with st.expander("⚙️ Configure Primary Validation Parameters", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            daily_ceiling = st.number_input("P3: Daily Ceiling Limit (mm)", min_value=100.0, max_value=800.0, value=350.0, step=10.0,
                                            help="IMD 1-day Probable Maximum Precipitation ceiling.")
        with c2:
            p4_method = st.selectbox("P4: Upper Warning Method", ["normal_multiplier", "percentile_98"],
                                     format_func=lambda x: "Mean + 1.96 × Std (Normal)" if x == "normal_multiplier" else "98th Percentile")
            p4_mult = st.slider("P4: Std Multiplier", 1.0, 3.0, 1.96, 0.05) if p4_method == "normal_multiplier" else 1.96
        with c3:
            p5_tolerance = st.slider("P5: Dual-Gauge Discrepancy Tolerance (%)", 1.0, 20.0, 5.0, 0.5)

    p_config = {
        "p1_entry_check": {"enabled": True},
        "p2_min_limit": {"enabled": True, "min_rainfall_mm": 0.0},
        "p3_max_limit": {"enabled": True, "default_daily_max_mm": daily_ceiling},
        "p4_upper_warning": {"enabled": True, "method": p4_method, "multiplier": p4_mult},
        "p5_dual_gauge": {"enabled": True, "tolerance_pct": p5_tolerance}
    }
    
    # Run validation button
    if st.button("▶️ Run Primary Validation (P1–P5)", type="primary"):
        with st.spinner("Executing rules P1 through P5..."):
            primary_flags, df_annotated = run_all_primary_validations(df_norm, p_config)
            st.session_state["primary_flags"] = primary_flags
            st.session_state["df_annotated"] = df_annotated
            st.session_state["primary_validated"] = True
            
            # Combine flags in session state
            all_flags = list(primary_flags)
            if "secondary_flags" in st.session_state:
                all_flags.extend(st.session_state["secondary_flags"])
            st.session_state["flags"] = all_flags
            
    # Display results if validated
    if st.session_state.get("primary_validated", False):
        flags = st.session_state.get("primary_flags", [])
        df_ann = st.session_state.get("df_annotated", df_norm)
        
        doubtful_count = (df_ann["validation_status"] == "doubtful").sum()
        missing_count = (df_ann["validation_status"] == "missing").sum()
        valid_count = (df_ann["validation_status"] == "validated").sum()
        
        # Summary row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Validated (Clean)", f"{valid_count:,}")
        c2.metric("Doubtful Flags Raised", f"{len(flags):,}", delta="Flag, Do Not Delete", delta_color="inverse")
        c3.metric("Missing Records", f"{missing_count:,}")
        c4.metric("Doubtful Rate", f"{(doubtful_count / max(1, len(df_ann)) * 100):.2f}%")
        
        # Breakdown by rule
        rule_counts = pd.Series([f.rule_id for f in flags]).value_counts()
        st.markdown("#### Flags by Primary Rule:")
        if not rule_counts.empty:
            st.bar_chart(rule_counts)
        else:
            st.success("✓ All records passed primary validation checks without flags.")
            
        # Table of flagged suspicious readings
        st.markdown("### 📋 Flagged Suspicious Readings Table")
        
        # Filter controls
        fc1, fc2 = st.columns(2)
        with fc1:
            stn_filter = st.selectbox("Filter by Station:", ["All Stations"] + sorted(df_ann["station_name"].unique().tolist()))
        with fc2:
            rule_filter = st.selectbox("Filter by Rule:", ["All Rules", "P1", "P2", "P3", "P4", "P5"])
            
        flag_records = []
        for f in flags:
            if stn_filter != "All Stations" and f.station_name != stn_filter:
                continue
            if rule_filter != "All Rules" and f.rule_id != rule_filter:
                continue
            flag_records.append({
                "Date": f.date.strftime("%Y-%m-%d"),
                "Station": f.station_name,
                "Rule": f.rule_id,
                "Direction": f.flag_direction if f.flag_direction else "-",
                "Severity": f.severity.upper(),
                "Observed (mm)": f.original_value,
                "Expected / Limit (mm)": f.expected_value,
                "Diagnostic Message": f.message
            })
            
        df_flags_view = pd.DataFrame(flag_records)
        if not df_flags_view.empty:
            st.dataframe(df_flags_view, use_container_width=True)
            st.caption(f"Showing {len(df_flags_view):,} flagged entries matching filter.")
        else:
            st.info("No suspicious readings matching selected filter.")
    else:
        st.info("Click **Run Primary Validation (P1–P5)** above to screen records.")
