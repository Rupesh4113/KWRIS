"""RainfallIQ Platform Configuration, Thresholds, and Constants."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any


class IssueSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ReviewStatus(str, Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    RESOLVED = "Resolved"


class PredictionQuality(str, Enum):
    HIGH = "High"
    MODERATE = "Moderate"
    LOW = "Low"
    UNAVAILABLE = "Unavailable"


@dataclass
class ValidationThresholds:
    min_rainfall_mm: float = 0.0
    daily_ceiling_mm: float = 400.0  # Regional extreme ceiling (IMD PMP benchmark)
    hourly_ceiling_mm: float = 150.0
    daily_warning_mm: float = 200.0   # Warning level for unusual rainfall
    mad_zscore_threshold: float = 3.5  # Robust median/MAD multiplier
    isolation_forest_contamination: float = 0.02
    spatial_diff_limit_mm: float = 50.0
    max_interpolation_gap_days: int = 3
    min_historical_years: int = 3
    recommended_historical_years: int = 20
    rainy_day_threshold_mm: float = 0.1
    max_dry_spell_days: int = 90
    max_wet_spell_days: int = 30


@dataclass
class PrioritizationWeights:
    missing_pct: float = 0.30
    gap_duration: float = 0.20
    anomaly_severity: float = 0.25
    historical_unreliability: float = 0.15
    network_criticality: float = 0.10


APP_CONFIG = {
    "app_name": "RainfallIQ",
    "version": "2.0.0",
    "theme_primary": "#8B0000",       # Karnataka Government Crimson Red
    "theme_secondary": "#1A202C",     # Dark Slate
    "missing_codes": [
        -99, -99.0, -999, -999.0, -9999, 9999,
        "NA", "NaN", "null", "NULL", "-", "--", "NR", "nr", "missing", "MISSING"
    ],
    "supported_units": ["mm", "cm", "inches", "in"],
    "unit_conversion_to_mm": {
        "mm": 1.0,
        "cm": 10.0,
        "inches": 25.4,
        "in": 25.4
    },
    "db_path": Path("data/rainfall_iq.db"),
    "models_dir": Path("models"),
    "sample_data_dir": Path("data/sample")
}
