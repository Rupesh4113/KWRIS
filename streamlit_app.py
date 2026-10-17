"""KWRIS Rainfall Data Quality & Validation Platform - Main Streamlit Entry Point."""

from __future__ import annotations
import streamlit as st

# Configure page settings
st.set_page_config(
    page_title="KWRIS - Rainfall Quality Platform",
    page_icon="🌧️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Karnataka government inspired theme
st.markdown(
    """
    <style>
    /* Karnataka theme accents */
    .main-header {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.7rem;
        font-weight: 700;
        color: #1A202C;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem;
        font-weight: 600;
        color: #4A5568;
    }
    /* Buttons */
    button[kind="primary"] {
        background-color: #8B0000 !important;
        border-color: #8B0000 !important;
    }
    button[kind="primary"]:hover {
        background-color: #A30000 !important;
        border-color: #A30000 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Import components and page renderers
from app.components.sidebar import render_sidebar
from app.pages.home import render_home_page
from app.pages.upload_and_profiling import render_upload_and_profiling_page
from app.pages.validation_results import render_validation_results_page
from app.pages.station_priority_analytics import render_station_priority_analytics_page
from app.pages.correction_review import render_correction_review_page
from app.pages.export_reports import render_export_reports_page


def main():
    # Render Sidebar and determine target page
    current_page = render_sidebar()
    
    # Route to selected page
    if current_page == "🏠 Executive Dashboard":
        render_home_page()
    elif current_page == "📤 Upload & Profiling":
        render_upload_and_profiling_page()
    elif current_page == "🔍 Validation Results":
        render_validation_results_page()
    elif current_page == "🏆 Station Priority & Analytics":
        render_station_priority_analytics_page()
    elif current_page == "🛠️ Correction & Audit":
        render_correction_review_page()
    elif current_page == "📑 Export Reports & Rules":
        render_export_reports_page()
    else:
        render_home_page()


if __name__ == "__main__":
    main()
