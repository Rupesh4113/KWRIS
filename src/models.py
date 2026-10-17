"""Data models and schemas for KWRIS Rainfall Quality Platform."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import datetime
import pandas as pd


class ValidationStatus(str, Enum):
    VALID = "validated"
    DOUBTFUL = "doubtful"
    CORRECTED = "corrected"
    COMPLETED = "completed"
    MISSING = "missing"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class ValidationFlag:
    station_id: str
    station_name: str
    date: pd.Timestamp
    rule_id: str
    flag_direction: Optional[str] = None  # "+" or "-" or None
    severity: str = "warning"              # "info", "warning", "critical"
    message: str = ""
    original_value: Optional[float] = None
    expected_value: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrectionProposal:
    proposal_id: str
    station_id: str
    station_name: str
    date: pd.Timestamp
    original_value: Optional[float]
    proposed_value: Optional[float]
    rule_id: str
    method: str
    reason: str
    review_status: ReviewStatus = ReviewStatus.PENDING
    approved_value: Optional[float] = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    reviewer_comment: str = ""


@dataclass
class StationCoordinates:
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    elevation_m: Optional[float] = None
    basin: Optional[str] = None
    subbasin: Optional[str] = None
    normal_annual_rainfall_mm: Optional[float] = None


@dataclass
class DatasetProfile:
    file_name: str
    file_size_bytes: int
    row_count: int
    column_count: int
    stations_count: int
    station_ids: List[str]
    station_names: List[str]
    min_date: Optional[pd.Timestamp]
    max_date: Optional[pd.Timestamp]
    total_dates: int
    detected_format: str               # "long" or "wide"
    duplicate_rows_count: int
    duplicate_station_dates_count: int
    missing_cells_count: int
    negative_values_count: int
    placeholder_values_count: int
    completeness_pct: float
    units_detected: str = "mm"
    has_coordinates: bool = False
