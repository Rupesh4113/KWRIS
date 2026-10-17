"""Page 5: AI-Based Missing Rainfall Prediction Hierarchy for RainfallIQ."""

from __future__ import annotations
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from src.missing_value_prediction import MissingRainfallPredictor


def render_prediction_page():
    st.title("🤖 AI-Based Missing Rainfall Prediction")
    st.markdown("""
    Estimate missing rainfall observations using the hydrological prediction hierarchy:
    **Method 1 (Historical Baseline)** ➔ **Method 2 (Time-Series Interpolation $\\le 3$ Days)** ➔
    **Method 3 (Machine Learning)** ➔ **Method 4 (Spatial IDW)**.
    """)

    if "norm_df" not in st.session_state or st.session_state.norm_df.empty:
        st.info("No active dataset loaded. Please upload data or load the demo dataset.")
        return

    norm_df = st.session_state.norm_df
    predictor = MissingRainfallPredictor(historical_manager=st.session_state.hist_mgr)

    # Station Selection & Configuration
    st.subheader("Prediction Configuration")
    c1, c2, c3 = st.columns(3)

    with c1:
        stn_options = sorted(list(norm_df["station_id"].unique()))
        selected_stn = st.selectbox("Select Station for Imputation:", stn_options)

    with c2:
        method_choice = st.selectbox(
            "Prediction Hierarchy Mode:",
            [
                "Auto Hierarchy (Recommended)",
                "Method 1: Historical Seasonal Baseline",
                "Method 2: Time-Series Interpolation",
                "Method 3: Machine Learning (Random Forest)",
                "Method 4: Spatial IDW"
            ],
            help="Auto Hierarchy selects the most scientifically justified method based on gap length, historical baseline, and spatial neighbors."
        )

    with c3:
        st.write("")
        st.write("")
        run_btn = st.button("🔮 Run Missing Value Prediction", type="primary", use_container_width=True)

    # Run Prediction Engine
    if run_btn:
        with st.spinner(f"Predicting missing observations for {selected_stn}..."):
            pref_method = None if method_choice.startswith("Auto") else method_choice
            preds_df = predictor.predict_gap_series(norm_df, selected_stn, preferred_method=pref_method)
            
            if preds_df.empty:
                st.success(f"No missing observations detected for station {selected_stn}!")
            else:
                # Merge into session state predictions
                if "predictions_df" not in st.session_state or st.session_state.predictions_df.empty:
                    st.session_state.predictions_df = preds_df
                else:
                    # Update existing or append
                    existing = st.session_state.predictions_df[st.session_state.predictions_df["station_id"] != selected_stn]
                    st.session_state.predictions_df = pd.concat([existing, preds_df], ignore_index=True)

                st.success(f"Generated {len(preds_df)} predicted estimates for station {selected_stn}!")

    # Display Current Predictions
    if "predictions_df" in st.session_state and not st.session_state.predictions_df.empty:
        all_preds = st.session_state.predictions_df
        stn_preds = all_preds[all_preds["station_id"] == selected_stn] if selected_stn in all_preds["station_id"].values else all_preds

        st.markdown("---")
        st.subheader("Predicted Estimates Table")
        st.caption("All estimated values are explicitly tagged **`ESTIMATED — NOT OBSERVED`** with confidence bounds:")

        st.dataframe(
            stn_preds[[
                "station_id", "date", "predicted_value_mm", "confidence_lower_mm",
                "confidence_upper_mm", "prediction_method", "prediction_quality",
                "mae", "rmse", "observations_used", "manual_review_required", "explanation"
            ]],
            use_container_width=True,
            column_config={
                "predicted_value_mm": st.column_config.NumberColumn("Estimated (mm)", format="%.2f mm"),
                "confidence_lower_mm": st.column_config.NumberColumn("Lower Bound (mm)", format="%.2f mm"),
                "confidence_upper_mm": st.column_config.NumberColumn("Upper Bound (mm)", format="%.2f mm"),
                "mae": st.column_config.NumberColumn("MAE", format="%.2f mm"),
                "rmse": st.column_config.NumberColumn("RMSE", format="%.2f mm"),
                "manual_review_required": st.column_config.CheckboxColumn("Review Req.?"),
                "explanation": st.column_config.TextColumn("Model Explanation", width="large")
            }
        )

        # Comparison Plot: Observed vs Estimated
        st.markdown("#### **Hydrograph Profile with Imputed Estimates**")
        stn_records = norm_df[norm_df["station_id"] == selected_stn].sort_values("date")
        
        fig_comp = go.Figure()

        # Observed Readings
        fig_comp.add_trace(go.Bar(
            x=stn_records["date"], y=stn_records["rainfall"],
            name="Observed Readings (mm)",
            marker_color="#2B6CB0",
            opacity=0.85
        ))

        # Imputed Missing Values
        if not stn_preds.empty:
            pred_dates = pd.to_datetime(stn_preds["date"])
            fig_comp.add_trace(go.Scatter(
                x=pred_dates, y=stn_preds["predicted_value_mm"],
                mode="markers+lines",
                name="ESTIMATED — NOT OBSERVED",
                line=dict(color="#DD6B20", width=2, dash="dot"),
                marker=dict(color="#DD6B20", size=8, symbol="diamond")
            ))

        fig_comp.update_layout(
            title=f"Observed vs Imputed Missing Rainfall — {selected_stn}",
            xaxis_title="Date", yaxis_title="Rainfall (mm)",
            hovermode="x unified", height=400,
            margin=dict(t=35, b=20, l=20, r=20)
        )
        st.plotly_chart(fig_comp, use_container_width=True)


render_prediction_page()
