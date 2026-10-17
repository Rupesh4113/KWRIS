"""Excel Reporting and Multi-Sheet Export Engine.
Generates comprehensive 13-sheet Excel workbooks, cleaned datasets,
and executive data quality reports with openpyxl styling and frozen headers.
"""

from __future__ import annotations
import io
import datetime
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


HEADER_FILL = PatternFill(start_color="8B0000", end_color="8B0000", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
ALERT_FILL = PatternFill(start_color="FFD2D2", end_color="FFD2D2", fill_type="solid")
WARN_FILL = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
SUCCESS_FILL = PatternFill(start_color="D1E7DD", end_color="D1E7DD", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style='thin', color='DDDDDD'),
    right=Side(style='thin', color='DDDDDD'),
    top=Side(style='thin', color='DDDDDD'),
    bottom=Side(style='thin', color='DDDDDD')
)


def style_worksheet(ws: openpyxl.worksheet.worksheet.Worksheet, freeze_header: bool = True) -> None:
    """Apply standard professional styling, auto-adjusted column widths, and frozen header."""
    if freeze_header:
        ws.freeze_panes = "A2"
        
    # Style header row
    for col_idx in range(1, ws.max_column + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
    # Auto-fit column widths with sensible bounds
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = cell.value
            if val is not None:
                line_len = max(len(str(line)) for line in str(val).split("\n"))
                max_len = max(max_len, line_len)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)


def generate_kwris_excel_report(
    df_raw: pd.DataFrame,
    df_annotated: pd.DataFrame,
    flags: List[Any],
    audit_df: pd.DataFrame,
    estimates_df: pd.DataFrame,
    monthly_stats: pd.DataFrame,
    yearly_stats: pd.DataFrame,
    station_ranking: pd.DataFrame,
    processing_log: List[str],
    rules_config: Dict[str, Any]
) -> io.BytesIO:
    """
    Generate the complete 13-worksheet KWRIS Rainfall Quality Excel workbook.
    """
    output = io.BytesIO()
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)
    
    # 1. Read_Me Sheet
    ws_readme = wb.create_sheet(title="Read_Me")
    readme_content = [
        ["KWRIS Rainfall Data Quality Validation & Correction Report"],
        ["Generated on:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["Governing Specification:", "Manual on Rainfall Data Validation (National Hydrology Project, MoWR/RD/GR, May 2019)"],
        [""],
        ["Workbook Structure (13 Worksheets):"],
        ["1. Read_Me", "Processing summary, conventions, limitations, and user instructions."],
        ["2. Original_Data", "Unmodified uploaded rainfall data preserved for auditing integrity."],
        ["3. Validated_Data", "Complete dataset with validation statuses and flagged rule codes."],
        ["4. Corrected_Data", "Data with approved traceable corrections and filled gaps."],
        ["5. Missing_Data", "Records with missing rainfall values or placeholder codes requiring review."],
        ["6. Suspicious_Readings", "Records flagged by primary or secondary validation rules."],
        ["7. Station_Summary", "Station-level quality summary, completeness, and priority rankings."],
        ["8. Monthly_Statistics", "Monthly aggregated rainfall sums and statistical distribution metrics."],
        ["9. Yearly_Statistics", "Annual rainfall totals, rainy day counts, and completeness metrics."],
        ["10. Neighbour_Analysis", "Spatial neighbour estimates, distances, and spatial discrepancy tests."],
        ["11. Correction_Audit", "Traceable history of all proposed and approved modifications."],
        ["12. Validation_Rules", "Inventory of rules P1-P5, S1-S8, G1-G8, A1-A6 and thresholds."],
        ["13. Processing_Log", "Execution log, warnings, and processing messages."],
        [""],
        ["Scientific & Hydrological Conventions:"],
        ["- Observation Day:", "Standard Indian Meteorological rainfall day runs from 08:30 to 08:30."],
        ["- Rainy Day Definition:", "Daily rainfall >= 0.1 mm."],
        ["- Zero vs Missing:", "0.0 mm represents observed dry weather; missing indicates lack of measurement."],
        ["- Status Labels:", "validated (passed), doubtful (flagged for review), corrected (modified), completed (gap-filled)."]
    ]
    for row in readme_content:
        ws_readme.append(row)
    ws_readme.column_dimensions["A"].width = 25
    ws_readme.column_dimensions["B"].width = 80
    ws_readme.cell(row=1, column=1).font = Font(name="Calibri", size=14, bold=True, color="8B0000")
    
    # Helper to append DataFrame cleanly
    def append_df_to_sheet(sheet_title: str, df_data: pd.DataFrame, max_rows: int = 50000) -> None:
        ws = wb.create_sheet(title=sheet_title)
        if df_data.empty:
            ws.append(["No records available."])
            return
            
        # Format dates as strings
        df_clean = df_data.head(max_rows).copy()
        for col in df_clean.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
            df_clean[col] = df_clean[col].dt.strftime("%Y-%m-%d")
            
        # Append header
        ws.append(list(df_clean.columns))
        # Append rows
        for row in df_clean.itertuples(index=False):
            ws.append(list(row))
        style_worksheet(ws)

    # 2. Original_Data
    append_df_to_sheet("Original_Data", df_raw)
    
    # 3. Validated_Data
    append_df_to_sheet("Validated_Data", df_annotated)
    
    # 4. Corrected_Data
    corr_cols = [c for c in df_annotated.columns if c in [
        "station_id", "station_name", "date", "rainfall_mm", "validated_rainfall_mm",
        "validation_status", "is_corrected", "is_completed", "correction_method", "correction_reason"
    ]]
    df_corr = df_annotated[corr_cols] if corr_cols else df_annotated
    append_df_to_sheet("Corrected_Data", df_corr)
    
    # 5. Missing_Data
    missing_mask = df_annotated["rainfall_mm"].isna() | (df_annotated.get("validation_status", "") == "missing")
    df_missing = df_annotated[missing_mask]
    append_df_to_sheet("Missing_Data", df_missing)
    
    # 6. Suspicious_Readings
    susp_mask = df_annotated.get("validation_status", "") == "doubtful"
    df_susp = df_annotated[susp_mask]
    append_df_to_sheet("Suspicious_Readings", df_susp)
    
    # 7. Station_Summary
    append_df_to_sheet("Station_Summary", station_ranking)
    
    # 8. Monthly_Statistics
    append_df_to_sheet("Monthly_Statistics", monthly_stats)
    
    # 9. Yearly_Statistics
    append_df_to_sheet("Yearly_Statistics", yearly_stats)
    
    # 10. Neighbour_Analysis
    append_df_to_sheet("Neighbour_Analysis", estimates_df)
    
    # 11. Correction_Audit
    append_df_to_sheet("Correction_Audit", audit_df)
    
    # 12. Validation_Rules
    rules_inventory = [
        {"Rule_ID": "P1", "Name": "Entry Check", "Category": "Primary", "Description": "Catches non-numeric, repeated dates, and missing codes like -99."},
        {"Rule_ID": "P2", "Name": "Minimum Limit", "Category": "Primary", "Description": "Flags negative rainfall below 0 mm."},
        {"Rule_ID": "P3", "Name": "Maximum Limit", "Category": "Primary", "Description": "Flags rainfall exceeding daily Probable Maximum Precipitation (PMP)."},
        {"Rule_ID": "P4", "Name": "Upper Warning Level", "Category": "Primary", "Description": "Flags readings exceeding monthly mean + 1.96*std or 98th percentile."},
        {"Rule_ID": "P5", "Name": "Two Gauges at One Station", "Category": "Primary", "Description": "Compares manual and automatic gauges, diagnoses >5% discrepancy."},
        {"Rule_ID": "S1", "Name": "Pick Neighbours", "Category": "Secondary", "Description": "Selects up to 8 stations within search radius, <= 2 per quadrant."},
        {"Rule_ID": "S2", "Name": "Neighbour Estimate Test", "Category": "Secondary", "Description": "Flags discrepancies against 1/d^2 IDW neighbour estimate."},
        {"Rule_ID": "S3", "Name": "Entries on Wrong Day", "Category": "Secondary", "Description": "Detects 1-day observation date shifts using spatial correlation."},
        {"Rule_ID": "S4", "Name": "Accumulated Totals", "Category": "Secondary", "Description": "Detects zeros during rain followed by a single accumulated spike."},
        {"Rule_ID": "S5", "Name": "Missed Entries", "Category": "Secondary", "Description": "Detects zero runs during neighbour rain with no subsequent spike."},
        {"Rule_ID": "S6", "Name": "Rainy Days Check", "Category": "Secondary", "Description": "Flags stations with suspiciously low counts of days >= 0.1 mm."},
        {"Rule_ID": "S7", "Name": "Monthly and Yearly Totals", "Category": "Secondary", "Description": "Flags annual totals outside mean +/- std bounds, cross-checked regionally."},
        {"Rule_ID": "S8", "Name": "Double Mass Analysis", "Category": "Secondary", "Description": "Identifies long-term slope shifts (>5 years) against neighbour average."},
        {"Rule_ID": "G1", "Name": "Keep Missing as Missing", "Category": "Correction", "Description": "Never fills gaps with zero; keeps missing distinct."},
        {"Rule_ID": "G2", "Name": "Use Station Second Gauge", "Category": "Correction", "Description": "Fills manual daily from automatic gauge and vice versa."},
        {"Rule_ID": "G3", "Name": "Fix Wrong Day Entries", "Category": "Correction", "Description": "Realigns date shifted records based on neighbour timing."},
        {"Rule_ID": "G4", "Name": "Split Accumulated Totals", "Category": "Correction", "Description": "Proportionally distributes accumulated total based on neighbour daily shares."},
        {"Rule_ID": "G5", "Name": "Fill from Neighbours", "Category": "Correction", "Description": "Fills gaps using Normal-Ratio or Simple Average based on normal diff."},
        {"Rule_ID": "G6", "Name": "Account Extra Rainy Days", "Category": "Correction", "Description": "Labels filled rain as completed; distinguishes measured rainy days."},
        {"Rule_ID": "G7", "Name": "Avoid Straight-Line Filling", "Category": "Correction", "Description": "Rejects linear interpolation for daily rainfall."},
        {"Rule_ID": "G8", "Name": "Correct Long-Term Shifts", "Category": "Correction", "Description": "Applies double-mass slope adjustment factor to inconsistent period."},
        {"Rule_ID": "A1", "Name": "Standard Periods", "Category": "Analysis", "Description": "08:30 daily cutoff, 52-week annual aggregation, 10-daily dekads."},
        {"Rule_ID": "A2", "Name": "Tipping Bucket Regularization", "Category": "Analysis", "Description": "Aggregates tip timestamps to regular hourly intervals."},
        {"Rule_ID": "A3", "Name": "Completeness Rules", "Category": "Analysis", "Description": "Requires minimum 90% valid days for monthly/yearly statistics."},
        {"Rule_ID": "A4", "Name": "Station Statistics", "Category": "Analysis", "Description": "Computes mean, median, std, skewness, max, and rainy days."},
        {"Rule_ID": "A5", "Name": "Consistency Before Trends", "Category": "Analysis", "Description": "Performs Mann-Whitney and t-tests for homogeneity."},
        {"Rule_ID": "A6", "Name": "Data Quality Reporting", "Category": "Analysis", "Description": "Generates data health scores and problem counts across network."}
    ]
    append_df_to_sheet("Validation_Rules", pd.DataFrame(rules_inventory))
    
    # 13. Processing_Log
    ws_log = wb.create_sheet(title="Processing_Log")
    ws_log.append(["Timestamp", "Log_Level", "Message"])
    for msg in processing_log:
        ws_log.append([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "INFO", msg])
    style_worksheet(ws_log)
    
    wb.save(output)
    output.seek(0)
    return output


def generate_cleaned_dataset_excel(df_annotated: pd.DataFrame) -> io.BytesIO:
    """Export clean/corrected dataset only."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_annotated.to_excel(writer, sheet_name="Cleaned_Rainfall_Data", index=False)
    output.seek(0)
    return output
