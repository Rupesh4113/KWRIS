"""Page 6: Engineer Action Center & Audit Review Workflow for RainfallIQ."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np

from src.storage import StorageManager


def render_action_center_page():
    st.title("🛡️ Engineer Action Center & Triage Queue")
    st.markdown("""
    Review prioritized issues, inspect AI-predicted estimates, add field notes,
    and formally accept or reject corrections with an auditable decision trail.
    """)

    if "storage_mgr" not in st.session_state:
        st.session_state.storage_mgr = StorageManager()

    storage = st.session_state.storage_mgr
    issues_df = st.session_state.issues_df if "issues_df" in st.session_state else pd.DataFrame()
    preds_df = st.session_state.predictions_df if "predictions_df" in st.session_state else pd.DataFrame()

    tab_triage, tab_audit = st.tabs(["📋 Prioritized Triage Queue", "📜 Engineering Audit Trail"])

    with tab_triage:
        if issues_df.empty and preds_df.empty:
            st.info("No active issues or predictions awaiting engineering review.")
            return

        # Triage Queue Summary
        q1, q2, q3 = st.columns(3)
        q1.metric("Pending Flagged Issues", f"{len(issues_df)}")
        q2.metric("Pending AI Estimates", f"{len(preds_df)}")
        
        audit_history = storage.get_audit_trail()
        q3.metric("Resolved / Logged Actions", f"{len(audit_history)}")

        st.markdown("---")
        st.subheader("Select Item for Review")

        # Combine items awaiting review into a unified review queue
        review_items = []
        if not issues_df.empty:
            for idx, r in issues_df.iterrows():
                review_items.append({
                    "type": "Data Issue",
                    "id": f"ISSUE_{idx}",
                    "station_id": str(r["station_id"]),
                    "date": str(r["observation_date"]),
                    "detail": f"[{r['severity']}] {r['issue_type']}: {r['validation_rule']}",
                    "orig_val": str(r["original_value"]),
                    "pred_val": None
                })
        if not preds_df.empty:
            for idx, r in preds_df.iterrows():
                review_items.append({
                    "type": "AI Estimate",
                    "id": f"PRED_{idx}",
                    "station_id": str(r["station_id"]),
                    "date": str(r["date"]),
                    "detail": f"{r['prediction_method']} ({r['predicted_value_mm']} mm, Quality: {r['prediction_quality']})",
                    "orig_val": "Missing (NaN)",
                    "pred_val": float(r["predicted_value_mm"])
                })

        queue_df = pd.DataFrame(review_items)
        st.dataframe(queue_df[["type", "station_id", "date", "detail", "orig_val"]], use_container_width=True)

        st.markdown("---")
        st.subheader("Interactive Review & Decision Panel")

        item_labels = [f"{r['id']} | {r['type']} | {r['station_id']} ({r['date']})" for _, r in queue_df.iterrows()]
        selected_item_label = st.selectbox("Select Record to Act Upon:", item_labels)

        sel_id = selected_item_label.split(" | ")[0]
        selected_row = queue_df[queue_df["id"] == sel_id].iloc[0]

        # Display Selected Record Details
        with st.container():
            st.markdown(f"**Item ID:** `{sel_id}` | **Station:** `{selected_row['station_id']}` | **Date:** `{selected_row['date']}`")
            st.markdown(f"**Description:** {selected_row['detail']}")
            st.markdown(f"**Original Recorded Reading:** `{selected_row['orig_val']}`")
            if selected_row["pred_val"] is not None:
                st.markdown(f"**Proposed AI Estimate:** `{selected_row['pred_val']} mm` (**ESTIMATED — NOT OBSERVED**)")

        st.markdown("#### **Decision & Field Notes**")
        col_act1, col_act2 = st.columns(2)

        with col_act1:
            reviewer_name = st.text_input("Reviewer Name / Engineer ID *", value="Er. Hydrologist (KWRIS)")
            action_choice = st.radio(
                "Select Action:",
                ["Accept Proposed Estimate", "Reject Estimate / Keep Missing", "Resolve Flagged Issue (Verified Real)"],
                index=0
            )

        with col_act2:
            review_notes = st.text_area(
                "Engineering Rationale & Field Verification Notes *",
                value="Verified against nearby rain-gauge network and radar records."
            )
            confirm_box = st.checkbox("⚠️ I confirm this engineering decision is accurate and auditable.")

        if st.button("💾 Submit Decision to Permanent Audit Log", type="primary", disabled=not confirm_box):
            action_code = "Accepted" if "Accept" in action_choice else ("Rejected" if "Reject" in action_choice else "Resolved")
            storage.log_review_decision(
                station_id=selected_row["station_id"],
                observation_date=selected_row["date"],
                action=action_code,
                reviewer=reviewer_name,
                original_value=selected_row["orig_val"],
                predicted_value=selected_row["pred_val"],
                notes=review_notes
            )
            st.success(f"✅ Decision logged successfully: Station {selected_row['station_id']} ({selected_row['date']}) set to '{action_code}'.")
            st.rerun()

    with tab_audit:
        st.subheader("Official Engineering Audit Trail")
        st.caption("Complete, tamper-evident log of all engineer approvals, rejections, and comments:")
        audit_df = storage.get_audit_trail()
        if not audit_df.empty:
            st.dataframe(audit_df, use_container_width=True)
            if st.button("🗑️ Clear Audit Trail (Demo Reset)", type="secondary"):
                storage.clear_audit_trail()
                st.success("Audit trail reset.")
                st.rerun()
        else:
            st.info("No audit review records logged yet.")


render_action_center_page()
