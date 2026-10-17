"""Unified Validation Results Page (Primary P1–P5 & Secondary S1–S8).
Consolidates single-station entry screening and spatial neighbour tests into one comprehensive screen.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.primary_validation import run_all_primary_validations
from src.secondary_validation import run_all_secondary_validations
from src.reference_data import lookup_station_coordinates, select_neighbours
from app.components.charts import plot_station_network_map


def render_validation_results_page():
    st.markdown("## 🔍 Validation Results (Rules P1–P5 & S1–S8)")
    st.markdown(
        "Screens uploaded rainfall observations against the National Hydrology Project manual rules. "
        "Flags physical violations, statistical outliers, 1-day date shifts, accumulated totals, and spatial discrepancies."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first in **Upload & Profiling**.")
        return
        
    df_norm = st.session_state["df_norm"]
    
    # Coordinates mapping from data or Karnataka catalog
    coords_map = {}
    for stn in df_norm["station_name"].unique():
        stn_sub = df_norm[df_norm["station_name"] == stn]
        lat = stn_sub["latitude"].dropna().iloc[0] if stn_sub["latitude"].notna().any() else None
        lon = stn_sub["longitude"].dropna().iloc[0] if stn_sub["longitude"].notna().any() else None
        if lat is not None and lon is not None:
            coords_map[stn] = (float(lat), float(lon))
        else:
            cat_coords = lookup_station_coordinates(stn)
            if cat_coords:
                coords_map[stn] = cat_coords
    st.session_state["coords_map"] = coords_map

    # Parameter tuning configuration panel
    with st.expander("⚙️ Validation Rule Parameters & Ceilings", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Primary Validation (P1–P5):**")
            daily_ceiling = st.number_input("P3: Daily Ceiling (mm)", 100.0, 800.0, 350.0, step=10.0,
                                            help="IMD 1-day Probable Maximum Precipitation ceiling.")
            p4_mult = st.slider("P4: Monthly Warning Std Multiplier", 1.0, 3.0, 1.96, 0.05)
            p5_tolerance = st.slider("P5: Dual-Gauge Discrepancy Tolerance (%)", 1.0, 20.0, 5.0, 0.5)
        with c2:
            st.markdown("**Spatial Neighbours (S1–S2):**")
            search_radius = st.number_input("S1: Search Radius (km)", 10.0, 100.0, 35.0, step=5.0)
            max_quad = st.slider("S1: Max per Quadrant", 1, 4, 2)
            s2_diff_limit = st.number_input("S2: Absolute Discrepancy Limit (mm)", 20.0, 100.0, 45.0, step=5.0)
        with c3:
            st.markdown("**Regional & Long-Term (S6–S8):**")
            s2_std_mult = st.slider("S2: Neighbour Std Multiplier", 1.0, 3.5, 2.0, 0.25)
            s6_ratio = st.slider("S6: Rainy Days Tolerance Ratio", 0.2, 0.8, 0.5, 0.05)
            s8_slope_thresh = st.slider("S8: Double-Mass Slope Shift Threshold", 0.05, 0.35, 0.15, 0.05)

    p_config = {
        "p1_entry_check": {"enabled": True},
        "p2_min_limit": {"enabled": True, "min_rainfall_mm": 0.0},
        "p3_max_limit": {"enabled": True, "default_daily_max_mm": daily_ceiling},
        "p4_upper_warning": {"enabled": True, "method": "normal_multiplier", "multiplier": p4_mult},
        "p5_dual_gauge": {"enabled": True, "tolerance_pct": p5_tolerance}
    }
    
    s_config = {
        "s1_pick_neighbours": {"enabled": True, "search_radius_km": search_radius, "max_per_quadrant": max_quad},
        "s2_neighbour_estimate": {"enabled": True, "absolute_diff_limit_mm": s2_diff_limit, "std_multiplier": s2_std_mult},
        "s3_wrong_day": {"enabled": True},
        "s4_accumulated_totals": {"enabled": True},
        "s5_missed_entries": {"enabled": True},
        "s6_rainy_days": {"enabled": True, "tolerance_ratio": s6_ratio},
        "s7_monthly_yearly_totals": {"enabled": True},
        "s8_double_mass": {"enabled": True, "slope_change_threshold": s8_slope_thresh, "min_shift_years": 5.0}
    }

    # Unified Run Validation Button
    if st.button("▶️ Run Full Validation Pipeline (P1–P5 & S1–S8)", type="primary"):
        with st.spinner("Executing primary checks and spatial neighbour calculations..."):
            primary_flags, df_annotated = run_all_primary_validations(df_norm, p_config)
            sec_flags, est_df, dm_dfs = run_all_secondary_validations(df_norm, coords_map, s_config)
            
            all_flags = list(primary_flags) + list(sec_flags)
            st.session_state["primary_flags"] = primary_flags
            st.session_state["secondary_flags"] = sec_flags
            st.session_state["flags"] = all_flags
            st.session_state["df_annotated"] = df_annotated
            st.session_state["neighbour_estimates_df"] = est_df
            st.session_state["double_mass_dfs"] = dm_dfs
            st.session_state["validated"] = True
            st.success(f"✓ Validation complete: {len(primary_flags)} primary flags and {len(sec_flags)} spatial flags raised.")

    if not st.session_state.get("validated", False):
        st.info("Click **Run Full Validation Pipeline (P1–P5 & S1–S8)** to execute all rules.")
        return

    all_flags = st.session_state.get("flags", [])
    df_ann = st.session_state.get("df_annotated", df_norm)
    est_df = st.session_state.get("neighbour_estimates_df", pd.DataFrame())
    
    # Metric KPI Row
    valid_count = (df_ann["validation_status"] == "validated").sum()
    doubtful_count = (df_ann["validation_status"] == "doubtful").sum()
    missing_count = (df_ann["validation_status"] == "missing").sum()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Validated (Clean)", f"{valid_count:,}")
    c2.metric("Doubtful Flags", f"{len(all_flags):,}", delta="Screen, do not delete", delta_color="inverse")
    c3.metric("Missing Records", f"{missing_count:,}")
    c4.metric("Doubtful Rate", f"{(doubtful_count / max(1, len(df_ann)) * 100):.2f}%")

    # Tabs for clean structured inspection
    tab1, tab2, tab3 = st.tabs([
        "📋 Flagged Suspicious Readings Table",
        "📊 Spatial Neighbour Estimates (S2)",
        "🗺️ Station Quadrant Network Map (S1)"
    ])
    
    with tab1:
        st.markdown("#### Filter Suspicious Observations:")
        f1, f2, f3 = st.columns(3)
        with f1:
            stn_filter = st.selectbox("Filter Station:", ["All Stations"] + sorted(df_ann["station_name"].unique().tolist()))
        with f2:
            avail_rules = ["All Rules"] + sorted(list({f.rule_id for f in all_flags}))
            rule_filter = st.selectbox("Filter Rule:", avail_rules)
        with f3:
            sev_filter = st.selectbox("Filter Severity:", ["All Severities", "CRITICAL", "WARNING", "INFO"])
            
        filtered_records = []
        for f in all_flags:
            if stn_filter != "All Stations" and f.station_name != stn_filter:
                continue
            if rule_filter != "All Rules" and f.rule_id != rule_filter:
                continue
            if sev_filter != "All Severities" and f.severity.upper() != sev_filter:
                continue
            filtered_records.append({
                "Date": f.date.strftime("%Y-%m-%d"),
                "Station": f.station_name,
                "Rule": f.rule_id,
                "Direction": f.flag_direction if f.flag_direction else "-",
                "Severity": f.severity.upper(),
                "Observed (mm)": f.original_value,
                "Expected / Limit (mm)": f.expected_value,
                "Diagnostic Message": f.message
            })
            
        df_view = pd.DataFrame(filtered_records)
        if not df_view.empty:
            st.dataframe(df_view, use_container_width=True)
            st.caption(f"Showing {len(df_view):,} flagged entries matching filter criteria.")
        else:
            st.success("✓ No suspicious readings matching the selected filters.")

    with tab2:
        st.markdown("#### Inverse-Distance-Squared Neighbour Estimates (Rule S2):")
        if not est_df.empty:
            st.dataframe(est_df.head(500), use_container_width=True)
        else:
            st.info("No spatial estimates computed (need at least 2 stations with valid coordinates).")

    with tab3:
        st.markdown("#### Hydrological Station Spatial Layout & Quadrants:")
        sel_map_stn = st.selectbox("Inspect Neighbours for Station:", ["-- None --"] + sorted(list(coords_map.keys())))
        fig_map = plot_station_network_map(coords_map, target_station=sel_map_stn if sel_map_stn != "-- None --" else None)
        st.plotly_chart(fig_map, use_container_width=True)
        
        if sel_map_stn != "-- None --":
            neighbours = select_neighbours(sel_map_stn, list(coords_map.keys()), coords_map)
            st.markdown(f"**Selected Neighbours for {sel_map_stn} (at most 2 per quadrant, $\le 35$ km):**")
            st.table(pd.DataFrame(neighbours))
