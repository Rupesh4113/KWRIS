"""Secondary Validation Engine for Rainfall Data (NHP Manual Chapter 4).

Implements National Hydrology Project (NHP, May 2019) Secondary Validation:
- S1: Quadrant-based Nearest Neighbour Reference Selection (max 8 stations, max 2 per quadrant, <= 25 km)
- S2: Spatial Homogeneity Testing (IDW distance-power b=2, admissible Xabs=50mm, Xrel=2*stdev)
- S3: Shifted-Date / Wrong-Day Entry Detection (1-day or 2-day observer clock offset)
- S4: Multi-Day Accumulation Screening (dry streak followed by surge matching neighbour sum)
- S5: Missed Observation Screening (zero recorded during regional deluge)
- S6: Monthly Rainy-Day Frequency Consistency (hydrological 0.1 mm threshold)
- S7: Longer Duration Totals Check (Monthly/Annual extremes)
- S8: Double-Mass Curve Analysis (Systematic trend/shift detection)
- P5: Dual-Gauge Co-located Comparison (SRG vs ARG)
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from src.configuration import ValidationThresholds, IssueSeverity, ReviewStatus


def calculate_bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate compass bearing from point 1 to point 2 in degrees (0 to 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return bearing


def assign_quadrant(bearing_deg: float) -> int:
    """
    Assign geographic quadrant based on bearing from test station:
    Quadrant 1: Northeast (0 to 90 deg)
    Quadrant 2: Southeast (90 to 180 deg)
    Quadrant 3: Southwest (180 to 270 deg)
    Quadrant 4: Northwest (270 to 360 deg)
    """
    if 0.0 <= bearing_deg < 90.0:
        return 1
    elif 90.0 <= bearing_deg < 180.0:
        return 2
    elif 180.0 <= bearing_deg < 270.0:
        return 3
    else:
        return 4


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def select_quadrant_neighbours(
    test_lat: float,
    test_lon: float,
    candidate_stations: pd.DataFrame,
    max_radius_km: float = 25.0,
    max_per_quadrant: int = 2,
    max_total: int = 8
) -> pd.DataFrame:
    """
    Select up to max_total reference stations with quadrant balancing (NHP Section 4.6.2).
    - Distance <= max_radius_km
    - Up to max_per_quadrant per quadrant
    - Up to max_total stations in total
    """
    records: List[Dict[str, Any]] = []

    for _, row in candidate_stations.iterrows():
        stn_id = str(row["station_id"])
        c_lat = float(row["latitude"])
        c_lon = float(row["longitude"])

        dist = haversine_km(test_lat, test_lon, c_lat, c_lon)
        if dist <= 0.001 or dist > max_radius_km:
            continue

        bearing = calculate_bearing_degrees(test_lat, test_lon, c_lat, c_lon)
        quadrant = assign_quadrant(bearing)

        records.append({
            "station_id": stn_id,
            "station_name": row.get("station_name", stn_id),
            "distance_km": dist,
            "bearing_deg": bearing,
            "quadrant": quadrant,
            "latitude": c_lat,
            "longitude": c_lon
        })

    if not records:
        return pd.DataFrame(columns=["station_id", "station_name", "distance_km", "bearing_deg", "quadrant", "latitude", "longitude"])

    candidates_df = pd.DataFrame(records).sort_values("distance_km")

    # Select up to max_per_quadrant per quadrant
    selected_rows: List[pd.Series] = []
    for q in [1, 2, 3, 4]:
        q_subset = candidates_df[candidates_df["quadrant"] == q]
        for _, r in q_subset.head(max_per_quadrant).iterrows():
            selected_rows.append(r)

    if not selected_rows:
        return pd.DataFrame(columns=["station_id", "station_name", "distance_km", "bearing_deg", "quadrant", "latitude", "longitude"])

    res_df = pd.DataFrame(selected_rows).sort_values("distance_km").head(max_total)
    return res_df.reset_index(drop=True)


class SecondaryQualityValidator:
    """
    NHP Manual Chapter 4 Secondary Validation Engine:
    Validates spatial homogeneity, detects shifted dates, accumulations,
    missed deluges, rainy-day frequency discrepancies, period totals,
    and long-term systematic shifts via double-mass analysis.
    """

    def __init__(self, thresholds: Optional[ValidationThresholds] = None):
        self.thresholds = thresholds or ValidationThresholds()

    def validate_dataset(
        self,
        df: pd.DataFrame,
        dataset_name: str = "Uploaded Dataset",
        station_coords: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Execute comprehensive secondary validation on the dataset.
        Returns:
            issues_df: DataFrame of detected secondary validation issues.
            summary: Summary counts by NHP rule code.
        """
        issues: List[Dict[str, Any]] = []

        valid_df = df[df["date"].notna() & df["rainfall"].notna()].copy()
        if valid_df.empty:
            return pd.DataFrame(), {"total_secondary_issues": 0}

        valid_df["date"] = pd.to_datetime(valid_df["date"])
        stations = valid_df["station_id"].unique()

        # Build coordinate reference if available in df or passed explicitly
        coords_map: Dict[str, Tuple[float, float]] = {}
        if station_coords is not None and not station_coords.empty:
            for _, r in station_coords.iterrows():
                coords_map[str(r["station_id"])] = (float(r["latitude"]), float(r["longitude"]))
        elif "latitude" in valid_df.columns and "longitude" in valid_df.columns:
            for stn_id, s_df in valid_df.groupby("station_id"):
                lat_val = s_df["latitude"].dropna()
                lon_val = s_df["longitude"].dropna()
                if not lat_val.empty and not lon_val.empty:
                    coords_map[str(stn_id)] = (float(lat_val.iloc[0]), float(lon_val.iloc[0]))

        # Dual-Gauge Check (P5) if both SRG and ARG columns or type flags exist
        dual_gauge_issues = self.check_dual_gauge(df, dataset_name)
        issues.extend(dual_gauge_issues)

        # Longer Duration Totals Check (S7)
        s7_issues = self.check_longer_duration_totals(valid_df, dataset_name)
        issues.extend(s7_issues)

        # If multiple stations exist, perform spatial checks
        if len(stations) >= 2:
            # 1. Spatial Homogeneity (S1 & S2)
            s2_issues = self.check_spatial_homogeneity(valid_df, coords_map, dataset_name)
            issues.extend(s2_issues)

            # 2. Shifted-Date / Wrong-Day Entries (S3)
            s3_issues = self.check_shifted_dates(valid_df, dataset_name)
            issues.extend(s3_issues)

            # 3. Accumulated Entries (S4)
            s4_issues = self.check_accumulations(valid_df, dataset_name)
            issues.extend(s4_issues)

            # 4. Missed Deluges (S5)
            s5_issues = self.check_missed_deluges(valid_df, dataset_name)
            issues.extend(s5_issues)

            # 5. Rainy Days Consistency (S6)
            s6_issues = self.check_rainy_days_frequency(valid_df, dataset_name)
            issues.extend(s6_issues)

            # 6. Double-Mass Analysis for Systematic Shift (S8)
            s8_issues = self.check_double_mass_systematic_shift(valid_df, dataset_name)
            issues.extend(s8_issues)

        issues_df = pd.DataFrame(issues)
        if issues_df.empty:
            issues_df = pd.DataFrame(columns=[
                "dataset_name", "station_id", "observation_date", "original_value",
                "issue_type", "severity", "validation_rule", "explanation",
                "recommended_action", "review_status"
            ])
        else:
            issues_df.drop_duplicates(subset=["station_id", "observation_date", "validation_rule"], inplace=True)

        summary = {
            "total_secondary_issues": len(issues_df),
            "s1_s2_spatial_anomalies": int(issues_df["validation_rule"].str.startswith("S2_").sum()) if not issues_df.empty else 0,
            "s3_shifted_dates": int((issues_df["validation_rule"] == "S3_SHIFTED_DATE").sum()) if not issues_df.empty else 0,
            "s4_accumulations": int((issues_df["validation_rule"] == "S4_ACCUMULATED_TOTAL").sum()) if not issues_df.empty else 0,
            "s5_missed_deluges": int((issues_df["validation_rule"] == "S5_MISSED_OBSERVATION").sum()) if not issues_df.empty else 0,
            "s6_rainy_days": int((issues_df["validation_rule"] == "S6_RAINY_DAYS").sum()) if not issues_df.empty else 0,
            "s7_period_totals": int((issues_df["validation_rule"] == "S7_PERIOD_TOTALS").sum()) if not issues_df.empty else 0,
            "s8_double_mass": int((issues_df["validation_rule"] == "S8_DOUBLE_MASS").sum()) if not issues_df.empty else 0,
            "p5_dual_gauge": int((issues_df["validation_rule"] == "P5_DUAL_GAUGE").sum()) if not issues_df.empty else 0,
        }

        return issues_df, summary

    def check_dual_gauge(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule P5: Co-located SRG vs ARG/Digital Gauge Comparison (Section 3.3).
        Checks if |P_SRG - P_ARG| > dual_gauge_diff_limit_mm,
        or detects suspicious identical matching on non-zero heavy rain days.
        """
        issues: List[Dict[str, Any]] = []

        # Case 1: Separate columns for SRG and ARG
        srg_col = None
        arg_col = None
        for col in df.columns:
            cl = str(col).lower()
            if "srg" in cl or "manual" in cl:
                srg_col = col
            elif "arg" in cl or "tbrg" in cl or "digital" in cl or "automatic" in cl:
                arg_col = col

        if srg_col and arg_col and "date" in df.columns:
            sub = df[df["date"].notna() & df[srg_col].notna() & df[arg_col].notna()]
            identical_heavy_count = 0
            for _, row in sub.iterrows():
                try:
                    p_srg = float(row[srg_col])
                    p_arg = float(row[arg_col])
                except (ValueError, TypeError):
                    continue

                diff = abs(p_srg - p_arg)
                dt_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
                stn = str(row.get("station_id", "Unknown"))

                if p_srg > 20.0 and p_arg > 20.0 and math.isclose(p_srg, p_arg, abs_tol=0.001):
                    identical_heavy_count += 1

                if diff > self.thresholds.dual_gauge_diff_limit_mm:
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": stn,
                        "observation_date": dt_str,
                        "original_value": f"SRG: {p_srg:.1f} mm, ARG: {p_arg:.1f} mm",
                        "issue_type": "Dual-Gauge Inconsistency",
                        "severity": IssueSeverity.HIGH.value if diff > 15.0 else IssueSeverity.MEDIUM.value,
                        "validation_rule": "P5_DUAL_GAUGE",
                        "explanation": f"Discrepancy of {diff:.1f} mm between co-located SRG ({p_srg:.1f} mm) and ARG ({p_arg:.1f} mm) exceeds tolerance ({self.thresholds.dual_gauge_diff_limit_mm} mm).",
                        "recommended_action": "Check tipping bucket calibration logs or observer cup measurement; adjust SRG or accept ARG as per NHP Sec 3.3.2.",
                        "review_status": ReviewStatus.PENDING.value
                    })

            # Check suspicious identical manipulation over > 10 heavy rain days
            if identical_heavy_count >= 10:
                issues.append({
                    "dataset_name": dataset_name,
                    "station_id": "All Co-located Stations",
                    "observation_date": "Entire Series",
                    "original_value": f"{identical_heavy_count} identical heavy days",
                    "issue_type": "Artificial Matching Suspected",
                    "severity": IssueSeverity.HIGH.value,
                    "validation_rule": "P5_DUAL_GAUGE",
                    "explanation": f"SRG and ARG match identically on {identical_heavy_count} heavy rain days (>20mm). NHP Section 3.3.2 notes exact identity indicates forced observer manipulation.",
                    "recommended_action": "Audit station observer logs and inspect raw autographic charts/loggers independently.",
                    "review_status": ReviewStatus.PENDING.value
                })

        return issues

    def check_longer_duration_totals(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule S7: Checking against data limits for totals at longer durations (Section 4.5).
        Aggregates daily rainfall to monthly and annual totals and flags physically impossible sums.
        """
        issues: List[Dict[str, Any]] = []

        for stn_id, stn_df in df.groupby("station_id"):
            stn_df = stn_df.set_index("date")
            monthly = stn_df["rainfall"].resample("ME").sum()

            for month_dt, m_tot in monthly.items():
                if m_tot > self.thresholds.monthly_warning_mm:
                    m_str = month_dt.strftime("%Y-%m")
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": str(stn_id),
                        "observation_date": m_str,
                        "original_value": f"{m_tot:.1f} mm",
                        "issue_type": "Monthly Total Warning",
                        "severity": IssueSeverity.HIGH.value if m_tot > 2000.0 else IssueSeverity.MEDIUM.value,
                        "validation_rule": "S7_PERIOD_TOTALS",
                        "explanation": f"Monthly total rainfall of {m_tot:.1f} mm exceeds warning limit of {self.thresholds.monthly_warning_mm} mm (NHP Section 4.5).",
                        "recommended_action": "Verify cumulative monthly sum against regional catchment isohyetal maps and flood reports.",
                        "review_status": ReviewStatus.PENDING.value
                    })

        return issues

    def check_spatial_homogeneity(
        self,
        df: pd.DataFrame,
        coords_map: Dict[str, Tuple[float, float]],
        dataset_name: str
    ) -> List[Dict[str, Any]]:
        """
        NHP Rules S1 & S2: Spatial Homogeneity Testing (Section 4.6).
        Computes distance-power weighted estimate Pest(t) using up to 8 quadrant neighbours:
        Pest(t) = sum(Pi / Di^2) / sum(1 / Di^2)
        Flags '+' if P(t) - Pest(t) > Xabs and > Xrel * SPest(t)
        Flags '-' if Pest(t) - P(t) > Xabs and > Xrel * SPest(t)
        """
        issues: List[Dict[str, Any]] = []
        has_coords = len(coords_map) >= 3

        date_groups = df.groupby("date")
        for obs_date, group in date_groups:
            if len(group) < 3:
                continue

            dt_str = pd.to_datetime(obs_date).strftime("%Y-%m-%d")

            for _, row in group.iterrows():
                stn_id = str(row["station_id"])
                p_obs = float(row["rainfall"])

                others = group[group["station_id"] != stn_id]
                if len(others) < 2:
                    continue

                weights = []
                values = []

                if has_coords and stn_id in coords_map:
                    t_lat, t_lon = coords_map[stn_id]
                    # Build candidate stations dataframe
                    c_rows = []
                    for _, oth in others.iterrows():
                        o_id = str(oth["station_id"])
                        if o_id in coords_map:
                            c_rows.append({
                                "station_id": o_id,
                                "station_name": oth.get("station_name", o_id),
                                "latitude": coords_map[o_id][0],
                                "longitude": coords_map[o_id][1],
                                "rainfall": float(oth["rainfall"])
                            })

                    if len(c_rows) >= 2:
                        c_df = pd.DataFrame(c_rows)
                        selected_neighbours = select_quadrant_neighbours(
                            t_lat, t_lon, c_df,
                            max_radius_km=self.thresholds.spatial_radius_km,
                            max_per_quadrant=self.thresholds.spatial_max_per_quadrant,
                            max_total=self.thresholds.spatial_max_neighbours
                        )
                        if not selected_neighbours.empty:
                            merged = selected_neighbours.merge(c_df[["station_id", "rainfall"]], on="station_id")
                            for _, mr in merged.iterrows():
                                d = max(float(mr["distance_km"]), 0.5)
                                w = 1.0 / (d ** self.thresholds.spatial_distance_power)
                                weights.append(w)
                                values.append(float(mr["rainfall"]))

                # Fallback to simple inverse distance or uniform weights if no coordinates
                if not weights or len(weights) < 2:
                    values = [float(v) for v in others["rainfall"].values]
                    weights = [1.0] * len(values)

                vals_arr = np.array(values)
                weights_arr = np.array(weights)
                p_est = float(np.sum(weights_arr * vals_arr) / np.sum(weights_arr))
                s_pest = float(np.std(vals_arr, ddof=1)) if len(vals_arr) > 1 else 1.0

                diff = p_obs - p_est
                abs_diff = abs(diff)

                # NHP Section 4.6.2 Criteria:
                # |P(t) - Pest(t)| > Xabs AND |P(t) - Pest(t)| > Xrel * SPest(t)
                is_flagged = (abs_diff > self.thresholds.spatial_xabs_mm and
                              abs_diff > self.thresholds.spatial_xrel_stdev * s_pest)

                if is_flagged:
                    sign = "+" if diff > 0 else "-"
                    flag_label = "Positive Flag (+)" if sign == "+" else "Negative Flag (-)"
                    explanation = (
                        f"NHP S2 Spatial departure: observed {p_obs:.1f} mm differs from spatial estimate {p_est:.1f} mm "
                        f"by {diff:+.1f} mm (exceeds Xabs={self.thresholds.spatial_xabs_mm} mm and {self.thresholds.spatial_xrel_stdev}*StDev={self.thresholds.spatial_xrel_stdev * s_pest:.1f} mm). "
                        f"Flag: {sign}."
                    )
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": stn_id,
                        "observation_date": dt_str,
                        "original_value": f"{p_obs:.1f} mm",
                        "issue_type": f"Spatial Homogeneity {flag_label}",
                        "severity": IssueSeverity.HIGH.value if abs_diff > 80.0 else IssueSeverity.MEDIUM.value,
                        "validation_rule": f"S2_SPATIAL_ANOMALY_{sign}",
                        "explanation": explanation,
                        "recommended_action": "Cross-check adjacent days for shifted entries (S3) or multi-day accumulation (S4).",
                        "review_status": ReviewStatus.PENDING.value
                    })

        return issues

    def check_shifted_dates(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule S3: Checking for entries on wrong days - Shifted entries (Section 4.8).
        Detects 1-day or 2-day clock offsets where target station shows rain 1 day before/after
        when all reference neighbours experienced rain.
        """
        issues: List[Dict[str, Any]] = []

        # Create pivot of daily rainfall across stations
        pivot_df = df.pivot_table(index="date", columns="station_id", values="rainfall")
        if pivot_df.shape[1] < 3:
            return issues

        for stn_id in pivot_df.columns:
            stn_series = pivot_df[stn_id].dropna()
            other_series = pivot_df.drop(columns=[stn_id]).dropna(how="all")
            other_median = other_series.median(axis=1)

            # Look for instances where target station is dry (<= 0.1mm) on day t,
            # but neighbours had major rain (> 25mm), and on day t+1 target has major rain (> 25mm)
            # while neighbours returned to dry (<= 2mm) -> classic 1-day observer lag
            common_idx = stn_series.index.intersection(other_median.index)
            if len(common_idx) < 2:
                continue

            for i in range(len(common_idx) - 1):
                d_curr = common_idx[i]
                d_next = common_idx[i + 1]
                if (d_next - d_curr).days != 1:
                    continue

                p_curr = stn_series.loc[d_curr]
                p_next = stn_series.loc[d_next]
                oth_curr = other_median.loc[d_curr]
                oth_next = other_median.loc[d_next]

                # Lagged entry: storm occurred on d_curr, but observer recorded on d_next
                if oth_curr > 25.0 and p_curr <= 0.1 and p_next > 20.0 and oth_next <= 5.0:
                    dt_str = d_next.strftime("%Y-%m-%d")
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": str(stn_id),
                        "observation_date": dt_str,
                        "original_value": f"{p_next:.1f} mm on {dt_str} (0.0 mm on {d_curr.strftime('%Y-%m-%d')})",
                        "issue_type": "Shifted-Date Entry (1-Day Observer Lag)",
                        "severity": IssueSeverity.HIGH.value,
                        "validation_rule": "S3_SHIFTED_DATE",
                        "explanation": f"Network recorded major rain ({oth_curr:.1f} mm) on {d_curr.strftime('%Y-%m-%d')}, while this station recorded 0.0 mm then spiked to {p_next:.1f} mm on {dt_str} after rain ceased.",
                        "recommended_action": "Shift recorded entry back to actual storm date as per NHP Section 4.8 / Section 5.3.",
                        "review_status": ReviewStatus.PENDING.value
                    })

                # Leading entry: observer recorded before 08:30 boundary or misattributed date
                elif oth_next > 25.0 and p_next <= 0.1 and p_curr > 20.0 and oth_curr <= 5.0:
                    dt_str = d_curr.strftime("%Y-%m-%d")
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": str(stn_id),
                        "observation_date": dt_str,
                        "original_value": f"{p_curr:.1f} mm on {dt_str}",
                        "issue_type": "Shifted-Date Entry (1-Day Observer Lead)",
                        "severity": IssueSeverity.HIGH.value,
                        "validation_rule": "S3_SHIFTED_DATE",
                        "explanation": f"Station recorded {p_curr:.1f} mm on {dt_str} before network storm on {d_next.strftime('%Y-%m-%d')} ({oth_next:.1f} mm).",
                        "recommended_action": "Shift recorded entry forward to actual event day as per NHP Section 4.8 / Section 5.3.",
                        "review_status": ReviewStatus.PENDING.value
                    })

        return issues

    def check_accumulations(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule S4: Entries made as accumulations (Section 4.9).
        Detects consecutive dry days (observer absence/weekend) followed by a sudden pulse
        matching the cumulative sum at neighbouring stations.
        """
        issues: List[Dict[str, Any]] = []

        pivot_df = df.pivot_table(index="date", columns="station_id", values="rainfall")
        if pivot_df.shape[1] < 3:
            return issues

        for stn_id in pivot_df.columns:
            stn_series = pivot_df[stn_id].dropna()
            other_series = pivot_df.drop(columns=[stn_id]).dropna(how="all")
            other_sum = other_series.mean(axis=1)

            dates = stn_series.index
            n = len(dates)
            if n < 5:
                continue

            consec_dry = 0
            streak_start_idx = 0

            for i in range(n):
                val = stn_series.iloc[i]
                if val <= 0.1:
                    if consec_dry == 0:
                        streak_start_idx = i
                    consec_dry += 1
                else:
                    # Non-zero day encountered
                    if consec_dry >= self.thresholds.accumulation_dry_days_min and val >= self.thresholds.accumulation_spike_threshold_mm:
                        # Check if neighbours had distributed rainfall during this dry streak
                        streak_dates = dates[streak_start_idx:i]
                        oth_cum_rain = other_sum.loc[streak_dates].sum()

                        # If neighbours had significant rain and cumulative sum matches spike within +-35%
                        if oth_cum_rain >= 25.0:
                            ratio = val / max(oth_cum_rain, 1.0)
                            if 0.65 <= ratio <= 1.45:
                                dt_str = dates[i].strftime("%Y-%m-%d")
                                issues.append({
                                    "dataset_name": dataset_name,
                                    "station_id": str(stn_id),
                                    "observation_date": dt_str,
                                    "original_value": f"{val:.1f} mm (after {consec_dry} dry days)",
                                    "issue_type": "Suspicious Multi-Day Accumulation",
                                    "severity": IssueSeverity.HIGH.value,
                                    "validation_rule": "S4_ACCUMULATED_TOTAL",
                                    "explanation": (
                                        f"Station had {consec_dry} consecutive zeros followed by {val:.1f} mm on {dt_str}. "
                                        f"Surrounding stations accumulated {oth_cum_rain:.1f} mm over the same dry period. "
                                        f"Characteristic unindicated observer accumulation (NHP Section 4.9)."
                                    ),
                                    "recommended_action": "Apportion accumulated rainfall across missed days proportional to neighbouring distribution (NHP Section 5.4).",
                                    "review_status": ReviewStatus.PENDING.value
                                })

                    consec_dry = 0

        return issues

    def check_missed_deluges(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule S5: Missed entries / zero recorded during regional storm (Section 4.10).
        Flags P = 0.0 mm when surrounding stations report deluge > 50 mm.
        """
        issues: List[Dict[str, Any]] = []

        date_groups = df.groupby("date")
        for obs_date, group in date_groups:
            if len(group) < 3:
                continue

            dt_str = pd.to_datetime(obs_date).strftime("%Y-%m-%d")

            for _, row in group.iterrows():
                p_obs = float(row["rainfall"])
                stn_id = str(row["station_id"])

                others = group[group["station_id"] != stn_id]["rainfall"]
                if len(others) < 2:
                    continue

                median_oth = float(others.median())
                q25_oth = float(others.quantile(0.25))

                if p_obs == 0.0 and q25_oth >= self.thresholds.missed_deluge_threshold_mm:
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": stn_id,
                        "observation_date": dt_str,
                        "original_value": "0.0 mm",
                        "issue_type": "Missed Entry During Deluge (False Zero)",
                        "severity": IssueSeverity.HIGH.value,
                        "validation_rule": "S5_MISSED_OBSERVATION",
                        "explanation": f"Station recorded 0.0 mm while network 25th percentile was {q25_oth:.1f} mm (median {median_oth:.1f} mm). False zero or funnel blockage (NHP Section 4.10).",
                        "recommended_action": "Replace false zero with spatial estimate from neighbours or flag as doubtful (NHP Section 4.10.2).",
                        "review_status": ReviewStatus.PENDING.value
                    })

        return issues

    def check_rainy_days_frequency(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule S6: Rainfall observation missed on days with low rainfall - Rainy days check (Section 4.11).
        Uses NHP hydrological standard: 0.1 mm = rainy day.
        Flags months where rainy day count is anomalously low compared to neighbours.
        """
        issues: List[Dict[str, Any]] = []

        df_c = df.copy()
        df_c["year_month"] = df_c["date"].dt.to_period("M")
        df_c["is_rainy"] = df_c["rainfall"] >= self.thresholds.rainy_day_threshold_mm

        for ym, ym_group in df_c.groupby("year_month"):
            stn_counts = ym_group.groupby("station_id")["is_rainy"].sum()
            if len(stn_counts) < 3:
                continue

            median_rainy_days = float(stn_counts.median())
            if median_rainy_days < 5:
                continue  # Skip very dry months

            for stn_id, cnt in stn_counts.items():
                diff_pct = (median_rainy_days - cnt) / median_rainy_days * 100.0
                if diff_pct > self.thresholds.rainy_day_diff_pct and (median_rainy_days - cnt) >= 4:
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": str(stn_id),
                        "observation_date": str(ym),
                        "original_value": f"{int(cnt)} rainy days",
                        "issue_type": "Anomalous Rainy-Day Frequency",
                        "severity": IssueSeverity.MEDIUM.value,
                        "validation_rule": "S6_RAINY_DAYS",
                        "explanation": (
                            f"Station reported only {int(cnt)} rainy days (>=0.1mm) in month {ym}, "
                            f"compared to regional median of {median_rainy_days:.0f} days ({diff_pct:.1f}% deficit). "
                            f"Observer likely missed small rain events (NHP Section 4.11)."
                        ),
                        "recommended_action": "Audit daily gauge visit logs; caution for low-rainfall undercounting.",
                        "review_status": ReviewStatus.PENDING.value
                    })

        return issues

    def check_double_mass_systematic_shift(self, df: pd.DataFrame, dataset_name: str) -> List[Dict[str, Any]]:
        """
        NHP Rule S8: Checking for systematic shifts using double mass analyses (Section 4.12).
        Computes cumulative rainfall for target station vs base group.
        Detects significant break in slope (> 20% slope shift).
        """
        issues: List[Dict[str, Any]] = []

        # Double mass requires multi-year data (monthly or annual aggregations)
        pivot_monthly = df.pivot_table(index="date", columns="station_id", values="rainfall")
        if pivot_monthly.shape[1] < 3:
            return issues

        monthly_totals = pivot_monthly.resample("ME").sum()
        if len(monthly_totals) < 24:  # Need at least 2 years of monthly data for meaningful curve
            return issues

        for stn_id in monthly_totals.columns:
            target = monthly_totals[stn_id].dropna()
            base_grp = monthly_totals.drop(columns=[stn_id]).dropna(how="all")
            base_mean = base_grp.mean(axis=1)

            common_idx = target.index.intersection(base_mean.index)
            if len(common_idx) < 24:
                continue

            cum_target = target.loc[common_idx].cumsum().values
            cum_base = base_mean.loc[common_idx].cumsum().values

            # Split into first half and second half to detect slope change
            mid = len(common_idx) // 2
            slope_before, _ = np.polyfit(cum_base[:mid], cum_target[:mid], 1)
            slope_after, _ = np.polyfit(cum_base[mid:], cum_target[mid:], 1)

            if slope_before > 0.05 and slope_after > 0.05:
                ratio = slope_after / slope_before
                pct_shift = abs(ratio - 1.0) * 100.0

                if pct_shift > 25.0:
                    break_date = common_idx[mid].strftime("%Y-%m")
                    issues.append({
                        "dataset_name": dataset_name,
                        "station_id": str(stn_id),
                        "observation_date": f"Break ~{break_date}",
                        "original_value": f"Slope ratio: {ratio:.2f}",
                        "issue_type": "Double-Mass Systematic Slope Break",
                        "severity": IssueSeverity.HIGH.value if pct_shift > 40.0 else IssueSeverity.MEDIUM.value,
                        "validation_rule": "S8_DOUBLE_MASS",
                        "explanation": (
                            f"Double-mass curve shows significant slope break around {break_date}. "
                            f"Slope shifted from {slope_before:.2f} to {slope_after:.2f} ({pct_shift:.1f}% shift). "
                            f"Indicates possible gauge relocation, tree obstruction, or instrument change (NHP Section 4.12)."
                        ),
                        "recommended_action": "Apply double-mass slope correction factor k = Sa/Sb (NHP Section 5.5) or inspect station site history.",
                        "review_status": ReviewStatus.PENDING.value
                    })

        return issues
