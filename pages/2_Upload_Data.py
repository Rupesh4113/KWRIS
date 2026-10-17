"""Page 2: Upload Data & Column Mapping for RainfallIQ."""

from __future__ import annotations
import io
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np

from src.configuration import APP_CONFIG
from src.ingestion import read_raw_data, normalize_rainfall_dataset, get_excel_sheet_names
from src.schema_detection import detect_columns, detect_dataset_format, convert_wide_to_long
from src.data_validation import DataQualityValidator
from src.anomaly_detection import AnomalyDetector
from src.prioritization import StationPrioritizer


def render_upload_page():
    st.title("📂 Data Ingestion & Schema Profiling")
    st.markdown("Upload operational rainfall datasets or multi-year historical archives in CSV or Excel formats.")

    tab_operational, tab_historical, tab_sample = st.tabs([
        "🌧️ Upload Operational Rainfall Data",
        "🏛️ Ingest Historical Archives (Up to 20 Yrs)",
        "⚡ Sample Dataset Loader"
    ])

    with tab_operational:
        st.subheader("Operational Dataset Upload")
        uploaded_file = st.file_uploader(
            "Choose a CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            help="Supports standard station-date rows or wide matrix spreadsheets."
        )

        if uploaded_file is not None:
            filename = uploaded_file.name
            ext = Path(filename).suffix.lower()
            
            # Worksheet selector for Excel
            sheet_name = None
            if ext in [".xlsx", ".xls"]:
                available_sheets = get_excel_sheet_names(uploaded_file)
                sheet_name = st.selectbox("Select Worksheet:", available_sheets)

            try:
                raw_df, meta = read_raw_data(uploaded_file, filename, sheet_name=sheet_name)
                
                # File Metadata Banner
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("File Name", filename[:20])
                c2.metric("Raw Rows", f"{len(raw_df):,}")
                c3.metric("Columns", f"{len(raw_df.columns)}")
                c4.metric("Encoding", meta.get("encoding", "utf-8"))

                st.markdown("#### **Raw Data Preview (Top 5 Rows)**")
                st.dataframe(raw_df.head(5), use_container_width=True)

                # Automatic Schema Detection
                cols = list(raw_df.columns)
                auto_mapping = detect_columns(cols)
                date_candidate = auto_mapping.get("date")
                detected_fmt = detect_dataset_format(raw_df, date_candidate)

                st.markdown("---")
                st.subheader("Column Schema Mapping")
                st.caption("Verify or adjust automatically detected column associations:")

                col_map1, col_map2, col_map3 = st.columns(3)
                
                with col_map1:
                    date_col = st.selectbox(
                        "Date Column *",
                        options=cols,
                        index=cols.index(date_candidate) if date_candidate in cols else 0
                    )
                    format_type = st.selectbox(
                        "Data Layout Format",
                        options=["long", "wide"],
                        index=0 if detected_fmt == "long" else 1,
                        help="'long': records with station ID column; 'wide': dates as rows, stations as columns."
                    )
                    unit = st.selectbox("Measurement Unit", options=["mm", "cm", "inches"], index=0)

                with col_map2:
                    if format_type == "long":
                        stn_id_cand = auto_mapping.get("station_id")
                        stn_name_cand = auto_mapping.get("station_name")
                        stn_id_col = st.selectbox(
                            "Station ID Column *",
                            options=cols,
                            index=cols.index(stn_id_cand) if stn_id_cand in cols else 0
                        )
                        stn_name_col = st.selectbox(
                            "Station Name Column",
                            options=["[Use Station ID]"] + cols,
                            index=cols.index(stn_name_cand) + 1 if stn_name_cand in cols else 0
                        )
                    else:
                        stn_id_col = None
                        stn_name_col = None
                        st.info("In 'wide' format, column headers will automatically represent Station IDs.")

                with col_map3:
                    if format_type == "long":
                        rf_cand = auto_mapping.get("rainfall")
                        rf_col = st.selectbox(
                            "Rainfall Value Column *",
                            options=cols,
                            index=cols.index(rf_cand) if rf_cand in cols else 0
                        )
                    else:
                        rf_col = None

                    lat_cand = auto_mapping.get("latitude")
                    lon_cand = auto_mapping.get("longitude")
                    lat_col = st.selectbox(
                        "Latitude (Optional)",
                        options=["[None]"] + cols,
                        index=cols.index(lat_cand) + 1 if lat_cand in cols else 0
                    )
                    lon_col = st.selectbox(
                        "Longitude (Optional)",
                        options=["[None]"] + cols,
                        index=cols.index(lon_cand) + 1 if lon_cand in cols else 0
                    )

                active_mapping = {
                    "date": date_col,
                    "station_id": stn_id_col,
                    "station_name": None if stn_name_col == "[Use Station ID]" else stn_name_col,
                    "rainfall": rf_col,
                    "latitude": None if lat_col == "[None]" else lat_col,
                    "longitude": None if lon_col == "[None]" else lon_col
                }

                if st.button("🚀 Process, Validate & Profile Dataset", type="primary", use_container_width=True):
                    with st.spinner("Normalizing dataset and executing validation engine..."):
                        norm_df, summary = normalize_rainfall_dataset(
                            raw_df, active_mapping, unit=unit, format_type=format_type
                        )

                        # Run Validation Rules
                        val = DataQualityValidator()
                        issues_df, val_summary = val.validate(norm_df, dataset_name=filename)

                        # Run Anomaly Detection
                        detector = AnomalyDetector()
                        anom_df, anom_summary = detector.detect_anomalies(norm_df, dataset_name=filename)

                        all_issues = pd.concat([issues_df, anom_df], ignore_index=True)
                        all_issues.drop_duplicates(subset=["station_id", "observation_date", "validation_rule"], inplace=True)

                        # Run Prioritization
                        prioritizer = StationPrioritizer()
                        cov_df = st.session_state.hist_mgr.get_station_coverage(list(norm_df["station_id"].unique()))
                        priorities_df = prioritizer.prioritize_stations(norm_df, all_issues, coverage_df=cov_df)
                        score, formula = prioritizer.calculate_overall_quality_score(len(norm_df), all_issues)

                        summary["quality_score"] = score
                        summary["quality_score_explanation"] = formula
                        summary["critical_count"] = val_summary.get("critical_count", 0) + anom_summary.get("extreme_ceilings", 0)
                        summary["high_count"] = val_summary.get("high_count", 0) + anom_summary.get("statistical_spikes", 0)

                        st.session_state.raw_df = raw_df
                        st.session_state.norm_df = norm_df
                        st.session_state.dataset_name = filename
                        st.session_state.summary_info = summary
                        st.session_state.issues_df = all_issues
                        st.session_state.priorities_df = priorities_df

                        st.success(f"✅ Processed {len(norm_df):,} records across {summary['total_stations']} stations! Data Quality Score: {score}%.")
                        st.info("Navigate to **Page 3: Validation Results** or **Page 4: Station Health** to review issues.")

            except Exception as e:
                st.error(f"Error reading file: {str(e)}")

    with tab_historical:
        st.subheader("Historical Rainfall Baseline Archive (Up to 20 Years)")
        st.markdown("""
        Ingest historical daily rainfall records to train Machine Learning models, compute station climatological
        medians, and track station network coverage over time.
        """)
        hist_file = st.file_uploader("Upload Historical Dataset (CSV or Excel):", type=["csv", "xlsx"], key="hist_upload")
        hist_source = st.text_input("Dataset Source / Archive Name:", value="IMD/KWRIS Historical Archive")

        if hist_file is not None:
            if st.button("📥 Import Historical Records into Database", use_container_width=True):
                with st.spinner("Importing and calculating climatological baselines..."):
                    try:
                        raw_hist, _ = read_raw_data(hist_file, hist_file.name)
                        h_cols = list(raw_hist.columns)
                        h_map = detect_columns(h_cols)
                        
                        # Re-map standard column names
                        import_df = pd.DataFrame()
                        import_df["station_id"] = raw_hist[h_map["station_id"]] if h_map["station_id"] else raw_hist.iloc[:, 0]
                        import_df["date"] = raw_hist[h_map["date"]] if h_map["date"] else raw_hist.iloc[:, 1]
                        import_df["rainfall"] = raw_hist[h_map["rainfall"]] if h_map["rainfall"] else raw_hist.iloc[:, 2]
                        if h_map.get("station_name"):
                            import_df["station_name"] = raw_hist[h_map["station_name"]]
                        if h_map.get("latitude"):
                            import_df["latitude"] = raw_hist[h_map["latitude"]]
                        if h_map.get("longitude"):
                            import_df["longitude"] = raw_hist[h_map["longitude"]]

                        res = st.session_state.hist_mgr.ingest_records(import_df, dataset_source=hist_source)
                        st.success(f"✅ Successfully imported {res['records_imported']:,} historical records across {res['stations_imported']} stations (Year range: {res['year_range']})!")
                    except Exception as err:
                        st.error(f"Historical import error: {str(err)}")

        # Display current stored historical coverage
        st.markdown("#### **Stored Historical Station Coverage**")
        cov_all = st.session_state.hist_mgr.get_station_coverage()
        if not cov_all.empty:
            st.dataframe(cov_all, use_container_width=True)
        else:
            st.info("No historical archives currently stored in local database.")

    with tab_sample:
        st.subheader("Instant Sample Demonstrations")
        st.markdown("""
        Load realistic synthetic monsoon datasets for Karnataka to test the entire validation, anomaly detection,
        prediction, and reporting pipeline immediately:
        """)
        c_dem1, c_dem2 = st.columns(2)
        with c_dem1:
            st.markdown("""
            **Dataset 1: Operational Monsoon 2024**
            - 5 Stations: Bangalore Urban, Mysuru, Shivamogga, Belagavi, KRS Dam
            - 4 Months: June - September 2024 (611 records)
            - Includes: Missing values (-99), negative reading (-14.5 mm), domain ceiling spike (485 mm), statistical outlier, duplicate record.
            """)
        with c_dem2:
            st.markdown("""
            **Dataset 2: 20-Year Historical Baseline (2004–2023)**
            - 36,525 daily observations
            - Full seasonal monsoon cycle calibrated for Karnataka hydrology
            - Enables multi-year climatological comparisons and Random Forest ML prediction.
            """)

        if st.button("⚡ Click to Load Both Sample Datasets", type="primary", use_container_width=True):
            from app import load_demo_datasets
            with st.spinner("Loading demo datasets..."):
                load_demo_datasets()
                st.success("✅ Operational & 20-year baseline datasets successfully loaded into session!")
                st.rerun()


render_upload_page()
