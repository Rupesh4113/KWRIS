"""Secondary Validation Interface: S1 to S8 (Neighbour Station Comparison)."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.secondary_validation import run_all_secondary_validations
from src.reference_data import lookup_station_coordinates, select_neighbours
from app.components.charts import plot_double_mass_curve, plot_station_network_map


def render_neighbour_validation_page():
    st.markdown("## 🌐 Neighbour Station Validation (Rules S1–S8)")
    st.markdown(
        "Tests spatial consistency across neighbouring stations within hydrological quadrants. "
        "Catches spatial outliers, date shifts, accumulated totals, and long-term instrument changes."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first.")
        return
        
    df_norm = st.session_state["df_norm"]
    
    # Build coordinates map from data or built-in catalog
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
    
    # Secondary validation parameters
    with st.expander("⚙️ Configure Spatial Validation Parameters", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            search_radius = st.number_input("S1: Search Radius (km)", min_value=10.0, max_value=100.0, value=35.0, step=5.0)
            max_quad = st.slider("S1: Max Stations per Quadrant", 1, 4, 2)
        with c2:
            s2_diff_limit = st.number_input("S2: Absolute Discrepancy Limit (mm)", min_value=20.0, max_value=100.0, value=45.0, step=5.0)
            s2_std_mult = st.slider("S2: Neighbour Std Multiplier", 1.0, 3.5, 2.0, 0.25)
        with c3:
            s6_ratio = st.slider("S6: Rainy Days Tolerance Ratio", 0.2, 0.8, 0.5, 0.05,
                                 help="Flag if station rainy days < this fraction of neighbour average.")
            s8_slope_thresh = st.slider("S8: Double-Mass Slope Change Threshold", 0.05, 0.35, 0.15, 0.05)

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
    
    # Run Secondary Validation Button
    if st.button("▶️ Run Neighbour Validation (S1–S8)", type="primary"):
        with st.spinner("Analyzing spatial neighbours, IDW estimates, date shifts, and double-mass curves..."):
            sec_flags, est_df, dm_dfs = run_all_secondary_validations(df_norm, coords_map, s_config)
            st.session_state["secondary_flags"] = sec_flags
            st.session_state["neighbour_estimates_df"] = est_df
            st.session_state["double_mass_dfs"] = dm_dfs
            st.session_state["secondary_validated"] = True
            
            # Combine all flags
            all_flags = []
            if "primary_flags" in st.session_state:
                all_flags.extend(st.session_state["primary_flags"])
            all_flags.extend(sec_flags)
            st.session_state["flags"] = all_flags

    # Display results
    if st.session_state.get("secondary_validated", False):
        sec_flags = st.session_state.get("secondary_flags", [])
        est_df = st.session_state.get("neighbour_estimates_df", pd.DataFrame())
        dm_dfs = st.session_state.get("double_mass_dfs", {})
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Secondary Flags Raised", f"{len(sec_flags):,}")
        c2.metric("Neighbour Estimates Computed", f"{len(est_df):,}")
        c3.metric("Double-Mass Stations Analyzed", f"{len(dm_dfs)}")
        
        # Rule breakdown
        rule_counts = pd.Series([f.rule_id for f in sec_flags]).value_counts()
        if not rule_counts.empty:
            st.markdown("#### Flags by Secondary Rule:")
            st.bar_chart(rule_counts)
            
        # Tabs for detailed inspection
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Flagged Spatial Anomalies",
            "📊 IDW Estimates Table",
            "📈 Double-Mass Curves (S8)",
            "🗺️ Station Network & Quadrants (S1)"
        ])
        
        with tab1:
            st.markdown("#### Spatial & Sequence Anomalies Detected:")
            records = []
            for f in sec_flags:
                records.append({
                    "Date": f.date.strftime("%Y-%m-%d"),
                    "Station": f.station_name,
                    "Rule": f.rule_id,
                    "Direction": f.flag_direction if f.flag_direction else "-",
                    "Severity": f.severity.upper(),
                    "Observed (mm)": f.original_value,
                    "Expected (mm)": f.expected_value,
                    "Explanation": f.message
                })
            df_sec_view = pd.DataFrame(records)
            if not df_sec_view.empty:
                st.dataframe(df_sec_view, use_container_width=True)
            else:
                st.success("✓ No spatial discrepancies exceeding configured thresholds.")
                
        with tab2:
            st.markdown("#### Daily Neighbour Estimates & Discrepancies (S2):")
            if not est_df.empty:
                st.dataframe(est_df.head(500), use_container_width=True)
            else:
                st.info("No neighbour estimates available (insufficient stations or coordinates).")
                
        with tab3:
            st.markdown("#### Long-Term Double-Mass Homogeneity Analysis (S8):")
            if dm_dfs:
                selected_dm_stn = st.selectbox("Select Station for Double-Mass Curve:", options=list(dm_dfs.keys()))
                dm_df = dm_dfs[selected_dm_stn]
                
                # Check if this station had an S8 flag
                stn_s8_flags = [f for f in sec_flags if f.rule_id == "S8" and f.station_name == selected_dm_stn]
                break_year = stn_s8_flags[0].details.get("break_year") if stn_s8_flags else None
                
                fig_dm = plot_double_mass_curve(dm_df, selected_dm_stn, break_year)
                st.plotly_chart(fig_dm, use_container_width=True)
                
                if stn_s8_flags:
                    st.warning(f"⚠️ {stn_s8_flags[0].message}")
                else:
                    st.success("✓ Station shows consistent double-mass alignment with neighbouring stations.")
            else:
                st.info("Requires at least 8 common observation years across >= 3 neighbouring stations.")
                
        with tab4:
            st.markdown("#### Hydrological Station Network Map:")
            sel_stn = st.selectbox("Highlight Target Station:", ["-- None --"] + sorted(list(coords_map.keys())))
            fig_map = plot_station_network_map(coords_map, target_station=sel_stn if sel_stn != "-- None --" else None)
            st.plotly_chart(fig_map, use_container_width=True)
            
            if sel_stn != "-- None --":
                neighbours = select_neighbours(sel_stn, list(coords_map.keys()), coords_map)
                st.markdown(f"**Selected Neighbours for {sel_stn} (at most 2 per quadrant, <= 35 km):**")
                st.table(pd.DataFrame(neighbours))
    else:
        st.info("Click **Run Neighbour Validation (S1–S8)** above to perform spatial validation.")
