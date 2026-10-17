"""Sidebar navigation and session configuration component."""

from __future__ import annotations
import streamlit as st


def render_sidebar():
    """Render the Karnataka-styled compact navigation sidebar with mode selector and session stats."""
    with st.sidebar:
        # Karnataka Government / KWRIS branding
        st.markdown(
            """
            <div style="background-color: #8B0000; padding: 12px; border-radius: 6px; color: white; text-align: center; margin-bottom: 15px;">
                <h3 style="margin: 0; color: white; font-size: 1.15rem; font-weight: 700;">KWRIS</h3>
                <div style="font-size: 0.82rem; opacity: 0.95;">Rainfall Quality & Validation</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Operational Processing Mode
        st.markdown("### ⚙️ Operational Mode")
        mode = st.radio(
            "Select mode:",
            options=["Validation Only", "Suggest Corrections", "Apply Approved Corrections"],
            index=["Validation Only", "Suggest Corrections", "Apply Approved Corrections"].index(
                st.session_state.get("processing_mode", "Suggest Corrections")
            ),
            help=(
                "• Validation Only: Screens and flags suspicious readings without proposing changes.\n"
                "• Suggest Corrections: Generates traceable gap estimates and fixes for reviewer approval.\n"
                "• Apply Approved Corrections: Updates working dataset with explicitly approved changes."
            )
        )
        st.session_state["processing_mode"] = mode
        
        st.divider()
        
        # Compact 6-Stage Primary Navigation
        st.markdown("### 📌 Navigation")
        pages = [
            "🏠 Executive Dashboard",
            "📤 Upload & Profiling",
            "🔍 Validation Results",
            "🏆 Station Priority & Analytics",
            "🛠️ Correction & Audit",
            "📑 Export Reports & Rules"
        ]
        
        # Set default page if previous page was from old schema
        saved_page = st.session_state.get("current_page", "🏠 Executive Dashboard")
        if saved_page not in pages:
            saved_page = "🏠 Executive Dashboard"
            
        current_page = st.radio(
            "Go to stage:",
            pages,
            index=pages.index(saved_page),
            label_visibility="collapsed"
        )
        st.session_state["current_page"] = current_page
        
        st.divider()
        
        # Dataset status chip
        st.markdown("### 📁 Active Dataset")
        if "df_norm" in st.session_state and st.session_state["df_norm"] is not None:
            df = st.session_state["df_norm"]
            st.success(f"✓ {st.session_state.get('file_name', 'Dataset')}")
            st.caption(f"**Records:** {len(df):,} | **Stations:** {df['station_name'].nunique()}")
            if "min_date" in st.session_state and st.session_state["min_date"] is not None:
                st.caption(f"**Span:** {st.session_state['min_date'].strftime('%Y-%m-%d')} to {st.session_state['max_date'].strftime('%Y-%m-%d')}")
        else:
            st.info("No dataset uploaded yet. Use sample or upload your file.")
            
        st.markdown(
            """
            <div style="font-size: 0.72rem; color: #666; margin-top: 20px; text-align: center;">
                Karnataka Water Resources Information System<br>
                Based on NHP Validation Manual (2019)
            </div>
            """,
            unsafe_allow_html=True
        )
        
    return current_page
