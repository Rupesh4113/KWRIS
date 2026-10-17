"""Data table rendering utilities and review badges for KWRIS."""

from __future__ import annotations
import streamlit as st
import pandas as pd


def render_flag_badge(rule_id: str, severity: str = "warning") -> str:
    """Return colored HTML badge for validation rule."""
    color_map = {
        "critical": "#E53E3E",
        "warning": "#DD6B20",
        "info": "#3182CE",
        "success": "#38A169"
    }
    bg = color_map.get(severity, "#718096")
    return f'<span style="background-color: {bg}; color: white; padding: 2px 7px; border-radius: 4px; font-weight: 600; font-size: 0.8rem;">{rule_id}</span>'


def render_status_pill(status: str) -> str:
    """Return status pill for validation and review states."""
    style_map = {
        "validated": ("#DEF7EC", "#03543F"),
        "doubtful": ("#FDE8E8", "#9B1C1C"),
        "corrected": ("#E1EFFE", "#1E429F"),
        "completed": ("#EDEBFE", "#5521B5"),
        "missing": ("#F3F4F6", "#374151")
    }
    bg, fg = style_map.get(str(status).lower(), ("#F3F4F6", "#374151"))
    return f'<span style="background-color: {bg}; color: {fg}; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 0.75rem;">{status.upper()}</span>'
