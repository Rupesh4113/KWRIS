"""Plotly Visualization Components for KWRIS Rainfall Quality Platform."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def plot_rainfall_time_series(
    df: pd.DataFrame,
    station_name: str,
    flags: Optional[List[Any]] = None
) -> go.Figure:
    """Plot interactive daily rainfall time series with flagged suspicious points."""
    stn_df = df[df["station_name"] == station_name].sort_values("date").copy()
    
    fig = go.Figure()
    
    # 1. Base measured rainfall bar / line
    fig.add_trace(go.Bar(
        x=stn_df["date"],
        y=stn_df["rainfall_mm"],
        name="Observed Rainfall (mm)",
        marker_color="#2B6CB0",
        opacity=0.75
    ))
    
    # 2. If corrected rainfall exists, overlay line
    if "validated_rainfall_mm" in stn_df.columns:
        corr_points = stn_df[stn_df.get("is_corrected", False) | stn_df.get("is_completed", False)]
        if not corr_points.empty:
            fig.add_trace(go.Scatter(
                x=corr_points["date"],
                y=corr_points["validated_rainfall_mm"],
                mode="markers",
                name="Approved Correction / Estimate",
                marker=dict(color="#38A169", size=8, symbol="diamond")
            ))
            
    # 3. Flagged doubtful points
    doubtful_points = stn_df[stn_df.get("validation_status", "") == "doubtful"]
    if not doubtful_points.empty:
        fig.add_trace(go.Scatter(
            x=doubtful_points["date"],
            y=doubtful_points["rainfall_mm"],
            mode="markers",
            name="Flagged Doubtful Reading",
            marker=dict(color="#E53E3E", size=9, symbol="x"),
            text=doubtful_points.get("issue_description", ""),
            hoverinfo="x+y+text"
        ))
        
    fig.update_layout(
        title=f"Daily Rainfall Profile: Station {station_name}",
        xaxis_title="Observation Date",
        yaxis_title="Rainfall (mm)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def plot_double_mass_curve(dm_df: pd.DataFrame, station_name: str, break_year: Optional[int] = None) -> go.Figure:
    """Plot double-mass curve comparing cumulative station rainfall against cumulative neighbour average."""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dm_df["cum_neighbours_mm"],
        y=dm_df["cum_station_mm"],
        mode="lines+markers",
        name=f"Station {station_name} Double-Mass",
        line=dict(color="#8B0000", width=2.5),
        marker=dict(size=6, color="#1A202C"),
        text=[f"Year {y}" for y in dm_df["year"]],
        hoverinfo="x+y+text"
    ))
    
    # Add reference 1:1 line or linear fit
    poly = np.polyfit(dm_df["cum_neighbours_mm"], dm_df["cum_station_mm"], 1)
    ref_y = np.polyval(poly, dm_df["cum_neighbours_mm"])
    fig.add_trace(go.Scatter(
        x=dm_df["cum_neighbours_mm"],
        y=ref_y,
        mode="lines",
        name=f"Linear Trend (Slope: {poly[0]:.3f})",
        line=dict(color="#A0AEC0", dash="dash")
    ))
    
    if break_year and break_year in dm_df["year"].values:
        row_bk = dm_df[dm_df["year"] == break_year].iloc[0]
        fig.add_annotation(
            x=row_bk["cum_neighbours_mm"],
            y=row_bk["cum_station_mm"],
            text=f"Detected Inflection Year: {break_year}",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#E53E3E",
            font=dict(color="#8B0000", size=11, family="sans-serif")
        )
        
    fig.update_layout(
        title=f"Double-Mass Consistency Curve: {station_name} vs Neighbours",
        xaxis_title="Cumulative Mean Rainfall of Neighbours (mm)",
        yaxis_title=f"Cumulative Rainfall: {station_name} (mm)",
        template="plotly_white"
    )
    return fig


def plot_monthly_heatmap(monthly_df: pd.DataFrame, year: int) -> go.Figure:
    """Plot monthly rainfall heatmap across stations for a selected year."""
    sub = monthly_df[monthly_df["year"] == year]
    if sub.empty:
        return go.Figure()
        
    piv = sub.pivot_table(index="station_name", columns="month", values="monthly_rainfall_mm", aggfunc="first")
    
    fig = px.imshow(
        piv,
        labels=dict(x="Month", y="Station", color="Rainfall (mm)"),
        x=[f"Month {m}" for m in piv.columns],
        y=piv.index,
        color_continuous_scale="Blues",
        title=f"Monthly Rainfall Spatial Distribution (Year {year})"
    )
    fig.update_layout(template="plotly_white")
    return fig


def plot_station_network_map(coords_map: Dict[str, Any], target_station: Optional[str] = None) -> go.Figure:
    """Scatter plot map of stations showing target and neighbouring quadrant stations."""
    data = []
    for stn, coords in coords_map.items():
        if coords and not np.isnan(coords[0]) and not np.isnan(coords[1]):
            is_target = (stn == target_station)
            data.append({
                "station": stn,
                "lat": coords[0],
                "lon": coords[1],
                "category": "Selected Station" if is_target else "Rainfall Station"
            })
            
    if not data:
        return go.Figure()
        
    map_df = pd.DataFrame(data)
    fig = px.scatter(
        map_df,
        x="lon",
        y="lat",
        text="station",
        color="category",
        color_discrete_map={"Selected Station": "#8B0000", "Rainfall Station": "#2B6CB0"},
        title="KWRIS Hydrological Station Network Layout",
        labels={"lon": "Longitude (°E)", "lat": "Latitude (°N)"}
    )
    fig.update_traces(textposition="top center", marker=dict(size=11))
    fig.update_layout(template="plotly_white")
    return fig
