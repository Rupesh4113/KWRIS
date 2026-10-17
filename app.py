"""RainfallIQ - Automated Rainfall Data Quality, Anomaly Detection & Prediction Platform.

Main Streamlit Application Entrypoint.
"""

from __future__ import annotations
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np

from src.configuration import APP_CONFIG, ValidationThresholds, PrioritizationWeights
from src.historical_data import HistoricalDataManager
from src.storage import StorageManager
from src.ingestion import read_raw_data, normalize_rainfall_dataset
from src.schema_detection import detect_columns, detect_dataset_format
from src.data_validation import DataQualityValidator
from src.anomaly_detection import AnomalyDetector
from src.secondary_validation import SecondaryQualityValidator
from src.prioritization import StationPrioritizer
from src.station_timeline_validation import (
    generate_checkpoint1_report,
    Checkpoint1Thresholds
)


def init_session_state():
    """Initialize persistent session variables for multi-page workflow."""
    if "hist_mgr" not in st.session_state:
        st.session_state.hist_mgr = HistoricalDataManager()

    if "storage_mgr" not in st.session_state:
        st.session_state.storage_mgr = StorageManager()

    if "norm_df" not in st.session_state:
        st.session_state.norm_df = pd.DataFrame()

    if "raw_df" not in st.session_state:
        st.session_state.raw_df = pd.DataFrame()

    if "dataset_name" not in st.session_state:
        st.session_state.dataset_name = "No dataset loaded"

    if "summary_info" not in st.session_state:
        st.session_state.summary_info = {}

    if "issues_df" not in st.session_state:
        st.session_state.issues_df = pd.DataFrame()

    if "priorities_df" not in st.session_state:
        st.session_state.priorities_df = pd.DataFrame()

    if "predictions_df" not in st.session_state:
        st.session_state.predictions_df = pd.DataFrame()

    if "checkpoint1_report" not in st.session_state:
        st.session_state.checkpoint1_report = {}

    if "cp1_thresholds" not in st.session_state:
        st.session_state.cp1_thresholds = Checkpoint1Thresholds()


def load_arkavathi_dataset():
    """Load Arkavathi Basin dataset (275k records) and run Checkpoint 1."""
    sample_dir = Path("data/sample")
    ark_file = sample_dir / "ARKAVATHI_RAINFALL.xlsx"
    if not ark_file.exists():
        ark_file = sample_dir / "ARKAVATHI RAINFALL.xlsx"

    if not ark_file.exists():
        st.error("Arkavathi dataset file not found in data/sample.")
        return

    raw_df = pd.read_excel(ark_file)
    mapping = {
        "date": "Day",
        "station_code": "WIMS Code",
        "station_name": "LocationName",
        "rainfall": "RF(mm)"
    }

    # Execute Checkpoint 1 First
    thresh = st.session_state.get("cp1_thresholds", Checkpoint1Thresholds())
    cp1_rep = generate_checkpoint1_report(raw_df, mapping, thresholds=thresh)

    # Ingestion & Normalization
    norm_mapping = {
        "date": "Day",
        "station_id": "WIMS Code",
        "station_name": "LocationName",
        "rainfall": "RF(mm)"
    }
    norm_df, summary = normalize_rainfall_dataset(raw_df, norm_mapping, unit="mm")

    # Run Checkpoints 2, 3 & 4
    val = DataQualityValidator()
    issues_df, val_summary = val.validate(norm_df, dataset_name="ARKAVATHI_RAINFALL.xlsx")

    detector = AnomalyDetector()
    anom_df, anom_summary = detector.detect_anomalies(norm_df, dataset_name="ARKAVATHI_RAINFALL.xlsx")

    sec_val = SecondaryQualityValidator()
    sec_issues, sec_summary = sec_val.validate_dataset(norm_df, dataset_name="ARKAVATHI_RAINFALL.xlsx")

    all_issues = pd.concat([issues_df, anom_df, sec_issues], ignore_index=True)
    all_issues.drop_duplicates(subset=["station_id", "observation_date", "validation_rule"], inplace=True)

    # Prioritization
    prioritizer = StationPrioritizer()
    priorities_df = prioritizer.prioritize_stations(norm_df, all_issues)
    score, formula = prioritizer.calculate_overall_quality_score(len(norm_df), all_issues)

    summary["quality_score"] = score
    summary["quality_score_explanation"] = formula
    summary["critical_count"] = val_summary.get("critical_count", 0) + anom_summary.get("extreme_ceilings", 0)
    summary["high_count"] = val_summary.get("high_count", 0) + anom_summary.get("statistical_spikes", 0)

    st.session_state.raw_df = raw_df
    st.session_state.norm_df = norm_df
    st.session_state.dataset_name = "Arkavathi Basin Rainfall (2001-2025)"
    st.session_state.summary_info = summary
    st.session_state.issues_df = all_issues
    st.session_state.priorities_df = priorities_df
    st.session_state.checkpoint1_report = cp1_rep


def load_demo_datasets():
    """Load pre-generated realistic sample datasets for instant demonstration."""
    sample_dir = Path("data/sample")
    curr_file = sample_dir / "sample_current_rainfall.csv"
    hist_file = sample_dir / "sample_20yr_historical_rainfall.csv"

    if not curr_file.exists() or not hist_file.exists():
        st.error("Sample datasets not found in data/sample. Please generate them first.")
        return

    # Ingest historical
    hist_df = pd.read_csv(hist_file)
    st.session_state.hist_mgr.ingest_records(hist_df, dataset_source="Karnataka 20-Year Baseline (2004-2023)")

    # Ingest current operational
    raw_df, meta = read_raw_data(curr_file, "sample_current_rainfall.csv")
    cols = list(raw_df.columns)
    mapping = detect_columns(cols)
    norm_df, summary = normalize_rainfall_dataset(raw_df, mapping, unit="mm")

    # Checkpoint 1
    thresh = st.session_state.get("cp1_thresholds", Checkpoint1Thresholds())
    cp1_mapping = {
        "date": mapping.get("date"),
        "station_code": mapping.get("station_id"),
        "station_name": mapping.get("station_name"),
        "rainfall": mapping.get("rainfall")
    }
    cp1_rep = generate_checkpoint1_report(raw_df, cp1_mapping, thresholds=thresh)

    # Initial validation & anomaly detection
    val = DataQualityValidator()
    issues_df, val_summary = val.validate(norm_df, dataset_name="sample_current_rainfall.csv")

    detector = AnomalyDetector()
    anom_df, anom_summary = detector.detect_anomalies(norm_df, dataset_name="sample_current_rainfall.csv")

    sec_val = SecondaryQualityValidator()
    sec_issues, sec_summary = sec_val.validate_dataset(norm_df, dataset_name="sample_current_rainfall.csv")

    all_issues = pd.concat([issues_df, anom_df, sec_issues], ignore_index=True)
    all_issues.drop_duplicates(subset=["station_id", "observation_date", "validation_rule"], inplace=True)

    # Station Prioritization & Quality Score
    prioritizer = StationPrioritizer()
    coverage_df = st.session_state.hist_mgr.get_station_coverage(list(norm_df["station_id"].unique()))
    priorities_df = prioritizer.prioritize_stations(norm_df, all_issues, coverage_df=coverage_df)
    score, formula = prioritizer.calculate_overall_quality_score(len(norm_df), all_issues)

    summary["quality_score"] = score
    summary["quality_score_explanation"] = formula
    summary["critical_count"] = val_summary.get("critical_count", 0) + anom_summary.get("extreme_ceilings", 0)
    summary["high_count"] = val_summary.get("high_count", 0) + anom_summary.get("statistical_spikes", 0)

    st.session_state.raw_df = raw_df
    st.session_state.norm_df = norm_df
    st.session_state.dataset_name = "Monsoon 2024 Operational (Demo)"
    st.session_state.summary_info = summary
    st.session_state.issues_df = all_issues
    st.session_state.priorities_df = priorities_df
    st.session_state.checkpoint1_report = cp1_rep


def main():
    st.set_page_config(
        page_title="RainfallIQ — Rainfall Data Quality & Prediction",
        page_icon="🌧️",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    init_session_state()

    # Custom Header Styling
    st.markdown("""
        <style>
        .kwris-header {
            background: linear-gradient(90deg, #8B0000 0%, #4A0000 100%);
            color: white;
            padding: 24px;
            border-radius: 8px;
            margin-bottom: 24px;
        }
        .kwris-title {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .kwris-subtitle {
            font-size: 1.05rem;
            opacity: 0.9;
        }
        </style>
        <div class="kwris-header">
            <div class="kwris-title">🌧️ RainfallIQ</div>
            <div class="kwris-subtitle">
                Automated Rainfall Data Quality Validation, Anomaly Detection & AI Missing-Value Prediction Platform
                <br><b>Karnataka Water Resources Information System (KWRIS)</b>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Sidebar Navigation & Platform Status
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Seal_of_Karnataka.svg/200px-Seal_of_Karnataka.svg.png", width=70)
        st.markdown("### **Platform Navigation**")
        st.info("Use the pages menu above to navigate through the 7 platform stages.")

        st.markdown("---")
        st.markdown("### **Quick Action**")
        if st.button("🌊 Load Arkavathi Dataset (275k Rows)", use_container_width=True, type="primary"):
            with st.spinner("Loading Arkavathi dataset & computing Checkpoint 1 timelines..."):
                load_arkavathi_dataset()
                st.success("Arkavathi dataset loaded! Proceed to Checkpoint 1 on Page 3.")

        if st.button("⚡ Load Monsoon 2024 Demo", use_container_width=True):
            with st.spinner("Ingesting 20-year baseline & running validation engine..."):
                load_demo_datasets()
                st.success("Demo dataset loaded successfully! Head to Page 1: Overview.")

        st.markdown("---")
        st.caption(f"**RainfallIQ v{APP_CONFIG['version']}** | NHP Guidelines (GoI)")

    # Main Page Content
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("""
        ### **Welcome to RainfallIQ**
        **RainfallIQ** is a mission-critical hydrological engineering platform designed for water-resource engineers,
        hydrologists, and quality-assurance teams. It enforces the **National Hydrology Project (NHP)** validation standards
        with a strict multi-checkpoint processing pipeline:

        1. **Checkpoint 1: Station Timeline & Missing-Day Validation**
           - Full observation window tracking (`min_date` to `max_date`)
           - Expected calendar days vs unique valid recorded dates
           - Precise missing day and consecutive blackout gap analysis
           - Duplicate station-date detection without inflating completeness
           - Non-destructive triage preserving all invalid records in an audit log
        2. **Checkpoint 2: Missing Values & Invalid Readings Validation**
           - Identification of negative values ($< 0.0\text{ mm}$), nulls, and missing codes (`-99`, `-999`, `NA`, `NR`).
        3. **Checkpoint 3: Suspicious Observations & Anomaly Detection**
           - IMD PMP physical ceilings (400 mm), MAD Z-scores, Isolation Forest ML, and spatial discordance.
        4. **Checkpoint 4: 20-Year Historical Climatology & AI Prediction**
           - 4-tier prediction hierarchy (Climatology, Short Interpolation, Random Forest ML, Spatial IDW).
        5. **Checkpoint 5: Station Prioritization & Engineer Triage**
           - Transparent 0–100 priority scoring and auditable review decision log.
        6. **Reporting & Provenance Export**
           - Multi-sheet Excel workbook and sanitized CSV exports with `ESTIMATED — NOT OBSERVED` tags.
        """)

        st.markdown("---")
        st.markdown("#### **Current Session Status**")
        if not st.session_state.norm_df.empty:
            st.success(f"Active Dataset: **{st.session_state.dataset_name}** ({len(st.session_state.norm_df):,} records, {st.session_state.summary_info.get('total_stations', 0)} stations)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Quality Score", f"{st.session_state.summary_info.get('quality_score', 100.0)}%")
            c2.metric("Total Flagged Issues", len(st.session_state.issues_df))
            c3.metric("Critical / High", f"{st.session_state.summary_info.get('critical_count', 0)} / {st.session_state.summary_info.get('high_count', 0)}")
            c4.metric("Predicted Estimates", len(st.session_state.predictions_df))
            
            if "checkpoint1_report" in st.session_state and st.session_state.checkpoint1_report:
                cp1_m = st.session_state.checkpoint1_report.get("metrics", {})
                st.info(f"**Checkpoint 1 Summary:** {cp1_m.get('total_stations', 0)} stations analyzed | {cp1_m.get('overall_completeness_pct', 0)}% date completeness | {cp1_m.get('total_missing_days', 0):,} missing observation days.")
        else:
            st.warning("No dataset currently active in session. Click the buttons in the sidebar or navigate to **Page 2: Upload Data** to get started.")

    with col_right:
        st.markdown("### **Hydrological Principles**")
        st.markdown("""
        > **1. Flag, Do Not Delete**  
        > Original field data is permanently preserved. Suspicious readings are flagged for review.

        > **2. Zero is NOT Missing**  
        > $0.0\\text{ mm}$ means no rain fell; missing means no measurement exists. They are distinct types.

        > **3. Extremes Can Be Real**  
        > Genuine extreme weather is critical for reservoir management. High readings are never discarded without neighbouring checks.

        > **4. All Estimates Traceable**  
        > Predicted missing values are stamped **`ESTIMATED — NOT OBSERVED`** with confidence intervals.
        """)


if __name__ == "__main__":
    main()
