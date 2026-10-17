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
    # Primary Validation Limits (NHP Manual Chapter 3)
    min_rainfall_mm: float = 0.0
    daily_ceiling_mm: float = 400.0  # Regional extreme ceiling (P3 - IMD PMP benchmark)
    hourly_ceiling_mm: float = 150.0
    daily_warning_mm: float = 200.0   # Warning level for unusual rainfall (P4)
    monthly_warning_mm: float = 1000.0 # Monthly warning level (P4/S7)
    dual_gauge_diff_limit_mm: float = 5.0 # Dual-gauge comparison threshold (P5)

    # Secondary Spatial Validation (NHP Manual Chapter 4)
    spatial_radius_km: float = 25.0       # Radius of circle of influence (S1)
    spatial_max_neighbours: int = 8      # Max reference stations (S1)
    spatial_max_per_quadrant: int = 2    # Quadrant limit to avoid spatial bias (S1)
    spatial_distance_power: float = 2.0  # Inverse distance power b (S1/S2/G4)
    spatial_xabs_mm: float = 50.0        # Admissible absolute error Xabs (S2)
    spatial_xrel_stdev: float = 2.0      # Multiplier of standard deviation Xrel (S2)
    spatial_diff_limit_mm: float = 50.0  # Legacy alias for spatial_xabs_mm
    shifted_date_window_days: int = 1    # Shifted-date lag/lead window (S3)
    accumulation_dry_days_min: int = 3   # Consecutive dry days before spike (S4)
    accumulation_spike_threshold_mm: float = 40.0 # Spike threshold for accumulation (S4)
    missed_deluge_threshold_mm: float = 50.0      # Spatial deluge threshold for missed zero (S5)
    rainy_day_threshold_mm: float = 0.1  # Hydrological rainy day definition (S6)
    rainy_day_diff_pct: float = 40.0     # Divergence in rainy days vs neighbours (S6)
    double_mass_min_years: int = 5       # Min years for double mass curve analysis (S8)

    # Missing Data Completion Hierarchy (NHP Manual Chapter 5)
    normal_ratio_threshold_pct: float = 10.0 # 10% annual normal threshold for G2 vs G3
    regression_min_r2: float = 0.70          # Minimum R^2 for linear regression (G5)
    regression_min_samples: int = 30         # Minimum paired sample size for regression (G5)
    max_interpolation_gap_days: int = 3

    # Additional Statistical & ML Safeguards
    mad_zscore_threshold: float = 3.5  # Robust median/MAD multiplier
    isolation_forest_contamination: float = 0.02
    min_historical_years: int = 3
    recommended_historical_years: int = 20
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
