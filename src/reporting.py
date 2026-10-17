"""Multi-Sheet Excel and CSV Production Reporting Engine for RainfallIQ."""

from __future__ import annotations
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.configuration import APP_CONFIG


def sanitize_cell_value(val: Any) -> Any:
    """
    Prevent formula injection vulnerability (CWE-1236) in exported spreadsheets.
    Prefix strings starting with =, +, -, @, \t, \r with single quote.
    """
    if isinstance(val, str) and len(val) > 0:
        if val[0] in ["=", "+", "-", "@", "\t", "\r"]:
            return f"'{val}"
    return val


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply formula injection sanitization to all string cells in DataFrame."""
    clean_df = df.copy()
    for col in clean_df.columns:
        if clean_df[col].dtype == object or pd.api.types.is_string_dtype(clean_df[col]):
            clean_df[col] = clean_df[col].apply(sanitize_cell_value)
    return clean_df


class ReportGenerator:
    """Generates styled multi-sheet Excel workbooks and CSV exports."""

    def __init__(self):
        self.primary_color = "8B0000"  # Crimson Red
        self.header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        self.header_fill = PatternFill(start_color=self.primary_color, end_color=self.primary_color, fill_type="solid")
        self.sub_header_fill = PatternFill(start_color="1A202C", end_color="1A202C", fill_type="solid")
        self.border_thin = Border(
            left=Side(style="thin", color="CCCCCC"),
            right=Side(style="thin", color="CCCCCC"),
            top=Side(style="thin", color="CCCCCC"),
            bottom=Side(style="thin", color="CCCCCC")
        )

    def _style_sheet_headers(self, ws):
        """Apply styling and auto-fit columns to a worksheet."""
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 28

        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            col_letter = get_column_letter(col_idx)
            # Determine maximum string length
            max_len = max(len(str(ws.cell(row=r, column=col_idx).value or "")) for r in range(1, min(ws.max_row + 1, 50)))
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    def generate_excel_report(
        self,
        summary_info: Dict[str, Any],
        issues_df: pd.DataFrame,
        priorities_df: pd.DataFrame,
        predictions_df: pd.DataFrame,
        audit_df: pd.DataFrame,
        dataset_df: pd.DataFrame
    ) -> io.BytesIO:
        """
        Build an enterprise 6-sheet production Excel report.
        """
        output = io.BytesIO()
        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # Remove default initial sheet

        # 1. Executive Summary Sheet
        ws_sum = wb.create_sheet(title="Executive_Summary")
        ws_sum.column_dimensions["A"].width = 30
        ws_sum.column_dimensions["B"].width = 60

        ws_sum["A1"] = "RainfallIQ Platform - Quality Validation & Correction Report"
        ws_sum["A1"].font = Font(name="Calibri", size=14, bold=True, color=self.primary_color)
        ws_sum["A2"] = f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (IST)"
        ws_sum["A2"].font = Font(name="Calibri", size=10, italic=True)

        row_idx = 4
        summary_items = [
            ("Platform Version", APP_CONFIG["version"]),
            ("Dataset Name", summary_info.get("filename", "Uploaded Dataset")),
            ("Total Records Processed", summary_info.get("total_records", 0)),
            ("Total Stations Detected", summary_info.get("total_stations", 0)),
            ("Date Range", f"{summary_info.get('start_date', 'N/A')} to {summary_info.get('end_date', 'N/A')}"),
            ("Observation Frequency", summary_info.get("frequency", "Daily")),
            ("Data Quality Score", f"{summary_info.get('quality_score', 100.0)}%"),
            ("Quality Score Explanation", summary_info.get("quality_score_explanation", "N/A")),
            ("Total Flagged Issues", len(issues_df)),
            ("Critical Priority Issues", summary_info.get("critical_count", 0)),
            ("High Priority Issues", summary_info.get("high_count", 0)),
            ("Missing Rainfall Gaps", summary_info.get("missing_count", 0)),
            ("Predicted Missing Values", len(predictions_df)),
            ("Engineering Review Actions Logged", len(audit_df)),
            ("Notice", "All generated missing rainfall values are explicitly marked ESTIMATED — NOT OBSERVED.")
        ]

        for label, val in summary_items:
            cell_lbl = ws_sum.cell(row=row_idx, column=1, value=label)
            cell_val = ws_sum.cell(row=row_idx, column=2, value=str(val))
            cell_lbl.font = Font(bold=True)
            cell_lbl.border = self.border_thin
            cell_val.border = self.border_thin
            row_idx += 1

        # 2. Issues Sheet
        if not issues_df.empty:
            ws_iss = wb.create_sheet(title="Data_Issues")
            clean_iss = sanitize_dataframe(issues_df)
            cols = list(clean_iss.columns)
            ws_iss.append(cols)
            for r in clean_iss.itertuples(index=False):
                ws_iss.append(list(r))
            self._style_sheet_headers(ws_iss)

        # 3. Station Priorities Sheet
        if not priorities_df.empty:
            ws_prio = wb.create_sheet(title="Station_Priority_Health")
            clean_prio = sanitize_dataframe(priorities_df)
            cols = list(clean_prio.columns)
            ws_prio.append(cols)
            for r in clean_prio.itertuples(index=False):
                ws_prio.append(list(r))
            self._style_sheet_headers(ws_prio)

        # 4. Predictions Sheet (ESTIMATED — NOT OBSERVED)
        if not predictions_df.empty:
            ws_pred = wb.create_sheet(title="Missing_Predictions")
            clean_pred = sanitize_dataframe(predictions_df)
            cols = list(clean_pred.columns)
            ws_pred.append(cols)
            for r in clean_pred.itertuples(index=False):
                ws_pred.append(list(r))
            self._style_sheet_headers(ws_pred)

        # 5. Audit Review Trail
        if not audit_df.empty:
            ws_aud = wb.create_sheet(title="Audit_Trail")
            clean_aud = sanitize_dataframe(audit_df)
            cols = list(clean_aud.columns)
            ws_aud.append(cols)
            for r in clean_aud.itertuples(index=False):
                ws_aud.append(list(r))
            self._style_sheet_headers(ws_aud)

        # 6. Complete Cleaned / Imputed Dataset with Provenance Flag
        if not dataset_df.empty:
            ws_data = wb.create_sheet(title="Full_Dataset_With_Estimates")
            full_export = dataset_df.copy()
            full_export["observation_type"] = "OBSERVED"
            
            # Map predictions if available
            if not predictions_df.empty and "date" in predictions_df.columns:
                pred_map = {}
                for _, pr in predictions_df.iterrows():
                    pred_map[(str(pr["station_id"]), str(pr["date"]))] = (
                        float(pr["predicted_value_mm"]),
                        f"ESTIMATED — NOT OBSERVED ({pr.get('prediction_method', 'AI')})"
                    )
                
                # Apply mapped estimates
                for idx, row in full_export.iterrows():
                    key = (str(row["station_id"]), pd.to_datetime(row["date"]).strftime("%Y-%m-%d"))
                    if key in pred_map:
                        full_export.at[idx, "imputed_rainfall_mm"] = pred_map[key][0]
                        full_export.at[idx, "observation_type"] = pred_map[key][1]

            clean_data = sanitize_dataframe(full_export)
            cols = list(clean_data.columns)
            ws_data.append(cols)
            for r in clean_data.itertuples(index=False):
                ws_data.append(list(r))
            self._style_sheet_headers(ws_data)

        wb.save(output)
        output.seek(0)
        return output
