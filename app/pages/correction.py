"""Missing Data & Traceable Correction Review Workflow (G1–G8)."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.gap_filling import generate_all_correction_proposals, apply_approved_corrections
from src.audit import AuditTrailManager
from src.models import ReviewStatus


def render_correction_page():
    st.markdown("## 🛠️ Missing Data & Traceable Correction Engine (G1–G8)")
    st.markdown(
        "Generates defensible, reproducible gap estimates and corrections according to the NHP Validation Manual. "
        "Every change is tracked in an immutable audit trail and requires reviewer approval before adoption."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first.")
        return
        
    df_norm = st.session_state["df_norm"]
    mode = st.session_state.get("processing_mode", "Suggest Corrections")
    coords_map = st.session_state.get("coords_map", {})
    primary_flags = st.session_state.get("primary_flags", [])
    secondary_flags = st.session_state.get("secondary_flags", [])
    
    st.info(f"**Current Operational Mode:** `{mode}`")
    
    if mode == "Validation Only":
        st.warning(
            "🔒 **Mode Lock:** The platform is running in **Validation Only** mode. "
            "Proposed corrections cannot be generated or applied. Switch mode in the sidebar to 'Suggest Corrections' to enable."
        )
        return

    # Button to generate proposals
    col_gen, col_bulk = st.columns([2, 3])
    with col_gen:
        if st.button("💡 Generate Correction Proposals (G1–G8)", type="primary"):
            with st.spinner("Calculating neighbour-ratio gap estimates, date shifts, and accumulated distributions..."):
                proposals = generate_all_correction_proposals(
                    df=df_norm,
                    primary_flags=primary_flags,
                    secondary_flags=secondary_flags,
                    coords_map=coords_map,
                    config={
                        "g2_second_gauge": {"enabled": True},
                        "g3_wrong_day_shift": {"enabled": True},
                        "g4_split_accumulated": {"enabled": True},
                        "g5_neighbour_filling": {"enabled": True, "normal_diff_threshold_pct": 10.0},
                        "g8_long_term_shift_correction": {"enabled": True}
                    }
                )
                audit_mgr = AuditTrailManager(proposals)
                st.session_state["audit_mgr"] = audit_mgr
                st.session_state["proposals_generated"] = True
                st.success(f"✓ Generated {len(proposals):,} traceable correction proposals.")

    audit_mgr = st.session_state.get("audit_mgr")
    if not audit_mgr or len(audit_mgr.get_proposals_list()) == 0:
        st.info("Click **Generate Correction Proposals (G1–G8)** above to calculate estimates.")
        return

    proposals_list = audit_mgr.get_proposals_list()
    
    # Proposal summary metrics
    by_rule = pd.Series([p.rule_id for p in proposals_list]).value_counts()
    by_status = pd.Series([p.review_status.value for p in proposals_list]).value_counts()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Proposals", f"{len(proposals_list):,}")
    c2.metric("Pending Review", f"{by_status.get('pending', 0):,}")
    c3.metric("Approved", f"{by_status.get('approved', 0):,}")
    c4.metric("Rejected / Deferred", f"{by_status.get('rejected', 0) + by_status.get('deferred', 0):,}")
    
    st.markdown("#### Proposals Breakdown by Method (Rules G2–G8):")
    st.bar_chart(by_rule)
    
    # Bulk actions bar
    with col_bulk:
        st.markdown("**Bulk Approval Actions:**")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ Approve All Proposals"):
                approved_cnt = audit_mgr.approve_all()
                st.success(f"Approved {approved_cnt} proposals.")
                st.rerun()
        with b2:
            rule_sel = st.selectbox("Approve by Rule:", ["Select Rule...", "G2", "G3", "G4", "G5", "G8"])
            if rule_sel != "Select Rule...":
                if st.button(f"Approve All {rule_sel}"):
                    approved_cnt = audit_mgr.approve_all(rule_filter=rule_sel)
                    st.success(f"Approved {approved_cnt} proposals for rule {rule_sel}.")
                    st.rerun()

    # Interactive Review Table
    st.markdown("### 📋 Interactive Proposal Review & Decision Table")
    
    # Filter
    stn_opts = ["All Stations"] + sorted(list({p.station_name for p in proposals_list}))
    stn_sel = st.selectbox("Filter proposals by station:", stn_opts)
    
    # Render table of proposals
    records = []
    for p in proposals_list:
        if stn_sel != "All Stations" and p.station_name != stn_sel:
            continue
        records.append({
            "Proposal ID": p.proposal_id,
            "Station": p.station_name,
            "Date": p.date.strftime("%Y-%m-%d"),
            "Rule": p.rule_id,
            "Original (mm)": f"{p.original_value:.1f}" if p.original_value is not None and not pd.isna(p.original_value) else "Missing (NaN)",
            "Proposed (mm)": f"{p.proposed_value:.1f}" if p.proposed_value is not None else "-",
            "Method": p.method,
            "Reason": p.reason,
            "Status": p.review_status.value.upper()
        })
        
    df_prop_view = pd.DataFrame(records)
    if not df_prop_view.empty:
        st.dataframe(df_prop_view.head(200), use_container_width=True)
        st.caption(f"Showing up to 200 of {len(df_prop_view)} proposals matching filter.")
    else:
        st.info("No proposals matching filter.")

    # Single Proposal Decision Form
    with st.expander("📝 Review / Modify Individual Proposal"):
        prop_id_input = st.selectbox("Select Proposal ID to act upon:", [p.proposal_id for p in proposals_list[:100]])
        if prop_id_input:
            selected_p = audit_mgr.proposals[prop_id_input]
            st.write(f"**Station:** {selected_p.station_name} | **Date:** {selected_p.date.strftime('%Y-%m-%d')} | **Rule:** {selected_p.rule_id}")
            st.write(f"**Original Value:** {selected_p.original_value} mm  ➡️  **Proposed Value:** {selected_p.proposed_value} mm")
            st.write(f"**Method:** {selected_p.method}")
            st.write(f"**Reason:** {selected_p.reason}")
            
            custom_val = st.number_input("Approved Value (mm):", value=float(selected_p.proposed_value) if selected_p.proposed_value is not None else 0.0)
            comment = st.text_input("Reviewer Comment / Justification:", value=selected_p.reviewer_comment)
            
            act1, act2, act3 = st.columns(3)
            with act1:
                if st.button("✅ Approve", key="btn_appr"):
                    audit_mgr.approve_proposal(prop_id_input, approved_val=custom_val, comment=comment)
                    st.success(f"Proposal {prop_id_input} approved.")
                    st.rerun()
            with act2:
                if st.button("❌ Reject", key="btn_rej"):
                    audit_mgr.reject_proposal(prop_id_input, comment=comment)
                    st.warning(f"Proposal {prop_id_input} rejected.")
                    st.rerun()
            with act3:
                if st.button("⏸️ Defer", key="btn_def"):
                    audit_mgr.defer_proposal(prop_id_input, comment=comment)
                    st.info(f"Proposal {prop_id_input} deferred.")
                    st.rerun()

    st.divider()
    
    # Apply Corrections Button
    st.markdown("### 💾 Commit Approved Corrections to Working Dataset")
    if st.button("⚡ Apply Approved Corrections", type="primary"):
        with st.spinner("Updating working dataset with approved corrections..."):
            df_corrected = apply_approved_corrections(
                df=st.session_state.get("df_annotated", df_norm),
                proposals=proposals_list
            )
            st.session_state["df_annotated"] = df_corrected
            st.session_state["corrections_applied"] = True
            
            corr_cnt = (df_corrected.get("is_corrected", False) == True).sum()
            comp_cnt = (df_corrected.get("is_completed", False) == True).sum()
            st.success(f"🎉 Successfully applied {corr_cnt} corrections and {comp_cnt} completed gap estimates! View changes in **Visual Analytics** or **Export Reports**.")
