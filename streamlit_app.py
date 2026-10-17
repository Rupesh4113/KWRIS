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
from app.pages.upload import render_upload_page
from app.pages.profiling import render_profiling_page
from app.pages.validation import render_validation_page
from app.pages.neighbour_validation import render_neighbour_validation_page
from app.pages.correction import render_correction_page
from app.pages.statistics import render_statistics_page
from app.pages.ranking import render_ranking_page
from app.pages.analytics import render_analytics_page
from app.pages.reports import render_reports_page
from app.pages.documentation import render_documentation_page


def main():
    # Render Sidebar and determine target page
    current_page = render_sidebar()
    
    # Route to selected page
    if current_page == "🏠 Home Dashboard":
        render_home_page()
    elif current_page == "📤 Upload Rainfall Data":
        render_upload_page()
    elif current_page == "📊 Data Profiling":
        render_profiling_page()
    elif current_page == "🔍 Primary Validation (P1–P5)":
        render_validation_page()
    elif current_page == "🌐 Neighbour Validation (S1–S8)":
        render_neighbour_validation_page()
    elif current_page == "🛠️ Missing Data & Correction (G1–G8)":
        render_correction_page()
    elif current_page == "📈 Statistical Analysis (A1–A6)":
        render_statistics_page()
    elif current_page == "🏆 Station Quality Ranking":
        render_ranking_page()
    elif current_page == "📉 Visual Analytics":
        render_analytics_page()
    elif current_page == "📑 Export Reports":
        render_reports_page()
    elif current_page == "📖 Rules & Documentation":
        render_documentation_page()
    else:
        render_home_page()


if __name__ == "__main__":
    main()
