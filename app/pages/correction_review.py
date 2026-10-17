"""Correction Review & Approval Workflow (Rules G1–G8).
Interactive decision interface for reviewing traceable gap-filling estimates and corrections.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from src.gap_filling import generate_all_correction_proposals, apply_approved_corrections
from src.audit import AuditTrailManager
from src.models import ReviewStatus


def render_correction_review_page():
    st.markdown("## 🛠️ Correction Review & Gap-Filling (G1–G8)")
    st.markdown(
        "Review and approve traceable corrections generated under the National Hydrology Project manual. "
        "Every change is tracked in an immutable audit trail and requires reviewer approval before adoption."
    )
    
    if "df_norm" not in st.session_state or st.session_state["df_norm"] is None:
        st.warning("⚠️ No active dataset found. Please upload or load a dataset first in **Upload & Profiling**.")
        return
        
    df_norm = st.session_state["df_norm"]
    mode = st.session_state.get("processing_mode", "Suggest Corrections")
    coords_map = st.session_state.get("coords_map", {})
    primary_flags = st.session_state.get("primary_flags", [])
    secondary_flags = st.session_state.get("secondary_flags", [])
    
    st.info(f"**Current Operational Mode:** `{mode}`")
    
    if mode == "Validation Only":
        st.warning(
            "🔒 **Mode Lock:** Platform is currently in **Validation Only** mode. "
            "To generate or approve corrections, switch mode in the sidebar to 'Suggest Corrections' or 'Apply Approved Corrections'."
        )
        return

    # Generation button & bulk action
    c_gen, c_bulk = st.columns([2, 3])
    with c_gen:
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
                st.success(f"✓ Generated {len(proposals):,} traceable correction proposals.")

    audit_mgr = st.session_state.get("audit_mgr")
    if not audit_mgr or len(audit_mgr.get_proposals_list()) == 0:
        st.info("Click **Generate Correction Proposals (G1–G8)** above to calculate gap estimates.")
        return

    proposals_list = audit_mgr.get_proposals_list()
    by_status = pd.Series([p.review_status.value for p in proposals_list]).value_counts()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Proposals", f"{len(proposals_list):,}")
    c2.metric("Pending Review", f"{by_status.get('pending', 0):,}")
    c3.metric("Approved", f"{by_status.get('approved', 0):,}")
    c4.metric("Rejected / Deferred", f"{by_status.get('rejected', 0) + by_status.get('deferred', 0):,}")
    
    # Bulk actions
    with c_bulk:
        st.markdown("**Bulk Review Actions:**")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✅ Approve All Pending"):
                cnt = audit_mgr.approve_all()
                st.success(f"Approved {cnt} proposals.")
                st.rerun()
        with b2:
            r_sel = st.selectbox("Approve by Rule:", ["Select Rule...", "G2", "G3", "G4", "G5", "G8"])
            if r_sel != "Select Rule..." and st.button(f"Approve All {r_sel}"):
                cnt = audit_mgr.approve_all(rule_filter=r_sel)
                st.success(f"Approved {cnt} proposals for rule {r_sel}.")
                st.rerun()

    st.markdown("### 📋 Interactive Proposal Review & Decision Table")
    stn_filter = st.selectbox("Filter proposals by station:", ["All Stations"] + sorted(list({p.station_name for p in proposals_list})))
    
    records = []
    for p in proposals_list:
        if stn_filter != "All Stations" and p.station_name != stn_filter:
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
        
    df_view = pd.DataFrame(records)
    if not df_view.empty:
        st.dataframe(df_view.head(200), use_container_width=True)
        st.caption(f"Displaying up to 200 of {len(df_view):,} proposals matching filter.")
    else:
        st.info("No proposals matching filter.")

    with st.expander("📝 Review / Modify Individual Proposal"):
        prop_id_input = st.selectbox("Select Proposal ID:", [p.proposal_id for p in proposals_list[:100]])
        if prop_id_input:
            p_sel = audit_mgr.proposals[prop_id_input]
            st.write(f"**Station:** {p_sel.station_name} | **Date:** {p_sel.date.strftime('%Y-%m-%d')} | **Rule:** {p_sel.rule_id}")
            st.write(f"**Original:** {p_sel.original_value} mm  ➡️  **Proposed:** {p_sel.proposed_value} mm")
            st.write(f"**Method:** {p_sel.method} | **Reason:** {p_sel.reason}")
            
            val_input = st.number_input("Approved Rainfall (mm):", value=float(p_sel.proposed_value) if p_sel.proposed_value is not None else 0.0)
            cmt = st.text_input("Reviewer Comment / Justification:", value=p_sel.reviewer_comment)
            
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("✅ Approve", key="prop_appr"):
                    audit_mgr.approve_proposal(prop_id_input, approved_val=val_input, comment=cmt)
                    st.success(f"Proposal {prop_id_input} approved.")
                    st.rerun()
            with a2:
                if st.button("❌ Reject", key="prop_rej"):
                    audit_mgr.reject_proposal(prop_id_input, comment=cmt)
                    st.warning(f"Proposal {prop_id_input} rejected.")
                    st.rerun()
            with a3:
                if st.button("⏸️ Defer", key="prop_def"):
                    audit_mgr.defer_proposal(prop_id_input, comment=cmt)
                    st.info(f"Proposal {prop_id_input} deferred.")
                    st.rerun()

    st.divider()
    st.markdown("### 💾 Commit Approved Corrections to Working Dataset")
    if st.button("⚡ Apply Approved Corrections", type="primary"):
        with st.spinner("Updating working dataset with approved corrections..."):
            df_corrected = apply_approved_corrections(
                df=st.session_state.get("df_annotated", df_norm),
                proposals=proposals_list
            )
            st.session_state["df_annotated"] = df_corrected
            corr_cnt = (df_corrected.get("is_corrected", False) == True).sum()
            comp_cnt = (df_corrected.get("is_completed", False) == True).sum()
            st.success(f"🎉 Applied {corr_cnt} corrections and {comp_cnt} completed estimates! View changes in **Station Priority & Analytics** or **Export Reports**.")
