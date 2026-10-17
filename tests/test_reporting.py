"""Tests for Excel Reporting and Audit Trail Export."""

import io
import pandas as pd
import numpy as np
import openpyxl
import pytest
from src.reporting import generate_kwris_excel_report, generate_cleaned_dataset_excel
from src.audit import AuditTrailManager
from src.models import CorrectionProposal, ReviewStatus


def test_13_sheet_excel_report_generation():
    df_raw = pd.DataFrame({
        "LocationName": ["Adankuppe", "Adankuppe"],
        "Day": ["2024-01-01", "2024-01-02"],
        "RF(mm)": [0.0, 15.5]
    })
    df_annotated = pd.DataFrame({
        "station_id": ["STN1", "STN1"],
        "station_name": ["Adankuppe", "Adankuppe"],
        "date": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        "rainfall_mm": [0.0, 15.5],
        "validated_rainfall_mm": [0.0, 15.5],
        "validation_status": ["validated", "validated"],
        "is_corrected": [False, False],
        "is_completed": [False, False],
        "correction_method": ["", ""],
        "correction_reason": ["", ""]
    })
    
    excel_io = generate_kwris_excel_report(
        df_raw=df_raw,
        df_annotated=df_annotated,
        flags=[],
        audit_df=pd.DataFrame(),
        estimates_df=pd.DataFrame(),
        monthly_stats=pd.DataFrame(),
        yearly_stats=pd.DataFrame(),
        station_ranking=pd.DataFrame(),
        processing_log=["Test execution started."],
        rules_config={}
    )
    
    wb = openpyxl.load_workbook(excel_io, read_only=True)
    expected_sheets = [
        "Read_Me", "Original_Data", "Validated_Data", "Corrected_Data",
        "Missing_Data", "Suspicious_Readings", "Station_Summary",
        "Monthly_Statistics", "Yearly_Statistics", "Neighbour_Analysis",
        "Correction_Audit", "Validation_Rules", "Processing_Log"
    ]
    assert len(wb.sheetnames) == 13
    for s in expected_sheets:
        assert s in wb.sheetnames


def test_audit_trail_lifecycle():
    mgr = AuditTrailManager()
    p1 = CorrectionProposal(
        proposal_id="PROP_001",
        station_id="STN_1",
        station_name="Station 1",
        date=pd.Timestamp("2024-01-01"),
        original_value=np.nan,
        proposed_value=22.4,
        rule_id="G5",
        method="Normal Ratio",
        reason="Gap filled from 3 neighbours",
        review_status=ReviewStatus.PENDING
    )
    mgr.add_proposal(p1)
    
    # Approve
    mgr.approve_proposal("PROP_001", approved_val=22.4, comment="Approved by Hydrologist")
    audit_df = mgr.to_dataframe()
    
    assert len(audit_df) == 1
    assert audit_df.iloc[0]["proposal_id"] == "PROP_001"
    assert audit_df.iloc[0]["review_status"] == "approved"
    assert audit_df.iloc[0]["approved_rainfall_mm"] == 22.4
    assert audit_df.iloc[0]["reviewer_comment"] == "Approved by Hydrologist"
