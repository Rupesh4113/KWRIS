"""Secondary Validation Module: S1 to S8.
Compares records against neighbouring stations to detect spatial anomalies,
wrong-day shifts, accumulated totals, missed entries, and long-term instrument drifts.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from src.models import ValidationFlag, ValidationStatus
from src.reference_data import haversine_distance_km, select_neighbours


def calculate_idw_estimate(
    observed_vals: List[float], 
    distances: List[float], 
    power: float = 2.0
) -> Tuple[float, float]:
    """
    Calculate inverse distance weighted estimate and standard deviation.
    Weight = 1 / (distance ** power).
    Returns (idw_estimate, neighbour_std).
    """
    if not observed_vals or not distances or len(observed_vals) != len(distances):
        return np.nan, np.nan
        
    weights = [1.0 / (max(d, 0.1) ** power) for d in distances]
    total_weight = sum(weights)
    if total_weight <= 0:
        return np.nan, np.nan
        
    est = sum(w * v for w, v in zip(weights, observed_vals)) / total_weight
    std = float(np.std(observed_vals, ddof=1)) if len(observed_vals) > 1 else 0.0
    return float(est), std


def run_s1_neighbour_selection(
    station_name: str,
    all_stations: List[str],
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    S1 - Neighbour Selection:
    Select up to 8 neighbours within search radius, at most 2 per quadrant.
    """
    max_neighbours = int(config.get("max_neighbours", 8))
    max_per_quadrant = int(config.get("max_per_quadrant", 2))
    search_radius = float(config.get("search_radius_km", 35.0))
    
    return select_neighbours(
        target_station=station_name,
        all_stations=all_stations,
        coords_map=coords_map,
        max_neighbours=max_neighbours,
        max_per_quadrant=max_per_quadrant,
        search_radius_km=search_radius
    )


def run_s2_neighbour_estimate_test(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> Tuple[List[ValidationFlag], pd.DataFrame]:
    """
    S2 - Neighbour Estimate Test:
    Compare observed rainfall against IDW estimate from selected neighbours.
    Flag when |obs - est| > limit (e.g. 45 mm) or > 2 * std(neighbours).
    Mark '+' when observed > estimate, '-' when lower.
    """
    flags: List[ValidationFlag] = []
    diff_limit = float(config.get("absolute_diff_limit_mm", 45.0))
    std_mult = float(config.get("std_multiplier", 2.0))
    low_rain_thresh = float(config.get("low_rain_threshold_mm", 2.5))
    
    # Pivot date x station_name
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    all_stations = piv.columns.tolist()
    
    estimate_records = []
    
    for stn in all_stations:
        neighbours = run_s1_neighbour_selection(stn, all_stations, coords_map, config)
        if not neighbours:
            continue
            
        neigh_names = [n["station"] for n in neighbours]
        neigh_dists = [n["distance_km"] for n in neighbours]
        
        stn_series = piv[stn]
        neigh_df = piv[neigh_names]
        
        for date, obs_val in stn_series.items():
            if pd.isna(obs_val):
                continue
                
            row_neigh = neigh_df.loc[date]
            valid_mask = row_neigh.notna()
            if valid_mask.sum() == 0:
                continue
                
            valid_vals = row_neigh[valid_mask].values.tolist()
            valid_dists = [d for d, m in zip(neigh_dists, valid_mask) if m]
            
            est_val, neigh_std = calculate_idw_estimate(valid_vals, valid_dists)
            if np.isnan(est_val):
                continue
                
            abs_diff = abs(obs_val - est_val)
            
            # Store estimate record for reporting
            estimate_records.append({
                "date": date,
                "station_name": stn,
                "observed_mm": obs_val,
                "estimated_mm": round(est_val, 2),
                "abs_diff_mm": round(abs_diff, 2),
                "neighbour_count": len(valid_vals),
                "contributing_stations": ", ".join([f"{n}({d:.1f}km)" for n, d in zip(row_neigh[valid_mask].index, valid_dists)])
            })
            
            # Low rain check: ignore small discrepancies
            if obs_val < low_rain_thresh and est_val < low_rain_thresh:
                continue
                
            # Discrepancy test
            is_discrepant = (abs_diff > diff_limit) or (neigh_std > 0 and abs_diff > (std_mult * neigh_std))
            if is_discrepant:
                direction = "+" if obs_val > est_val else "-"
                msg = (f"Neighbour estimate discrepancy: Observed={obs_val:.1f} mm, "
                       f"Neighbour Est={est_val:.1f} mm (diff: {direction}{abs_diff:.1f} mm).")
                flags.append(ValidationFlag(
                    station_id=stn,
                    station_name=stn,
                    date=date,
                    rule_id="S2",
                    flag_direction=direction,
                    severity="warning" if abs_diff < 70 else "critical",
                    message=msg,
                    original_value=obs_val,
                    expected_value=round(est_val, 1),
                    details={
                        "observed_mm": obs_val,
                        "estimated_mm": round(est_val, 2),
                        "abs_diff_mm": round(abs_diff, 2),
                        "direction": direction,
                        "contributing_stations": [n["station"] for n in neighbours],
                        "distances_km": neigh_dists
                    }
                ))
                
    return flags, pd.DataFrame(estimate_records)


def run_s3_wrong_day_check(
    df: pd.DataFrame,
    s2_flags: List[ValidationFlag],
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[ValidationFlag]:
    """
    S3 - Entries on the Wrong Day:
    Detect 1-day shifts when observers lose track of dates.
    Signs: '+' flag at start of wet spell and '-' at end (or reverse).
    Confirms by testing whether 1-day shift reduces discrepancy with neighbours.
    """
    flags: List[ValidationFlag] = []
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    
    # Group S2 flags by station
    flags_by_stn: Dict[str, List[ValidationFlag]] = {}
    for f in s2_flags:
        if f.rule_id == "S2":
            flags_by_stn.setdefault(f.station_name, []).append(f)
            
    for stn, stn_flags in flags_by_stn.items():
        if len(stn_flags) < 2 or stn not in piv.columns:
            continue
            
        stn_flags.sort(key=lambda x: x.date)
        neighbours = run_s1_neighbour_selection(stn, piv.columns.tolist(), coords_map, config)
        if not neighbours:
            continue
        neigh_names = [n["station"] for n in neighbours]
        neigh_mean = piv[neigh_names].mean(axis=1)
        stn_series = piv[stn]
        
        # Scan for clusters of opposing flags within 3-7 days
        for i in range(len(stn_flags) - 1):
            f1 = stn_flags[i]
            f2 = stn_flags[i + 1]
            day_gap = (f2.date - f1.date).days
            
            if 1 <= day_gap <= 5 and f1.flag_direction and f2.flag_direction:
                if f1.flag_direction != f2.flag_direction:
                    # Test shifts: forward (+1 day) and backward (-1 day)
                    window_start = f1.date - pd.Timedelta(days=2)
                    window_end = f2.date + pd.Timedelta(days=2)
                    
                    orig_win = stn_series.loc[window_start:window_end]
                    neigh_win = neigh_mean.loc[window_start:window_end]
                    
                    if len(orig_win) > 3 and orig_win.sum() > 5.0:
                        corr_orig = orig_win.corr(neigh_win)
                        corr_shift_fwd = orig_win.shift(1).corr(neigh_win)
                        corr_shift_bwd = orig_win.shift(-1).corr(neigh_win)
                        
                        best_shift = 0
                        best_corr = corr_orig if not np.isnan(corr_orig) else -1
                        if not np.isnan(corr_shift_fwd) and corr_shift_fwd > best_corr + 0.35:
                            best_shift = 1
                            best_corr = corr_shift_fwd
                        if not np.isnan(corr_shift_bwd) and corr_shift_bwd > best_corr + 0.35:
                            best_shift = -1
                            
                        if best_shift != 0:
                            direction_str = "forward (+1 day)" if best_shift == 1 else "backward (-1 day)"
                            flags.append(ValidationFlag(
                                station_id=stn,
                                station_name=stn,
                                date=f1.date,
                                rule_id="S3",
                                severity="warning",
                                message=(f"Suspected entry on wrong day between {f1.date.strftime('%Y-%m-%d')} "
                                         f"and {f2.date.strftime('%Y-%m-%d')}. Discrepancy resolves if shifted {direction_str}."),
                                details={
                                    "start_date": f1.date,
                                    "end_date": f2.date,
                                    "suggested_shift_days": best_shift,
                                    "original_correlation": round(float(corr_orig), 3) if not np.isnan(corr_orig) else None,
                                    "shifted_correlation": round(float(best_corr), 3)
                                }
                            ))
                            
    return flags


def run_s4_accumulated_totals_check(
    df: pd.DataFrame,
    s2_flags: List[ValidationFlag],
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[ValidationFlag]:
    """
    S4 - Accumulated Totals:
    Observer missed some days and entered the total upon return.
    Signs: sequence of zeros with '-' flags while neighbours had rain,
    followed by one large '+' spike.
    """
    flags: List[ValidationFlag] = []
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    
    for stn in piv.columns:
        stn_series = piv[stn].dropna()
        if len(stn_series) < 10:
            continue
            
        neighbours = run_s1_neighbour_selection(stn, piv.columns.tolist(), coords_map, config)
        if not neighbours:
            continue
        neigh_names = [n["station"] for n in neighbours]
        neigh_rain = piv[neigh_names].mean(axis=1)
        
        # Find spikes in station rainfall
        dates = stn_series.index
        for idx in range(3, len(dates)):
            curr_date = dates[idx]
            curr_val = stn_series.loc[curr_date]
            
            if curr_val >= 35.0:  # Potential accumulated spike
                # Look at previous 2-5 days
                prev_dates = dates[max(0, idx-4):idx]
                prev_vals = stn_series.loc[prev_dates]
                prev_neigh = neigh_rain.loc[prev_dates]
                
                # Condition: target was zero/dry while neighbours had significant rain
                if (prev_vals == 0.0).sum() >= 2 and prev_neigh.sum() >= 15.0:
                    zero_dates = prev_dates[prev_vals == 0.0].tolist()
                    flags.append(ValidationFlag(
                        station_id=stn,
                        station_name=stn,
                        date=curr_date,
                        rule_id="S4",
                        flag_direction="+",
                        severity="warning",
                        message=(f"Suspected accumulated reading on {curr_date.strftime('%Y-%m-%d')} ({curr_val:.1f} mm) "
                                 f"following {len(zero_dates)} zero-reading days when neighbours had rain ({prev_neigh.sum():.1f} mm)."),
                        original_value=curr_val,
                        expected_value=round(float(prev_neigh.mean()), 1),
                        details={
                            "accumulated_date": curr_date,
                            "accumulated_value_mm": curr_val,
                            "zero_period_dates": zero_dates,
                            "neighbour_accumulated_sum_mm": round(float(prev_neigh.sum()), 1)
                        }
                    ))
                    
    return flags


def run_s5_missed_entries_check(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[ValidationFlag]:
    """
    S5 - Missed Entries:
    Signs: Run of zero readings with '-' flags during rainy spell at neighbouring stations,
    with NO subsequent large spike. The zeros probably represent readings never taken.
    """
    flags: List[ValidationFlag] = []
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    
    for stn in piv.columns:
        stn_series = piv[stn].dropna()
        if len(stn_series) < 10:
            continue
            
        neighbours = run_s1_neighbour_selection(stn, piv.columns.tolist(), coords_map, config)
        if not neighbours:
            continue
        neigh_names = [n["station"] for n in neighbours]
        neigh_rain = piv[neigh_names].mean(axis=1)
        
        dates = stn_series.index
        consecutive_missed = 0
        missed_dates = []
        
        for idx in range(len(dates) - 1):
            d = dates[idx]
            val = stn_series.loc[d]
            n_val = neigh_rain.loc[d]
            
            if val == 0.0 and n_val >= 8.0:
                consecutive_missed += 1
                missed_dates.append(d)
            else:
                if consecutive_missed >= 3:
                    # Verify no large spike followed on the next day
                    next_val = stn_series.loc[dates[idx]]
                    if next_val < 25.0:
                        flags.append(ValidationFlag(
                            station_id=stn,
                            station_name=stn,
                            date=missed_dates[0],
                            rule_id="S5",
                            flag_direction="-",
                            severity="warning",
                            message=(f"Suspected missed entries over {consecutive_missed} days "
                                     f"({missed_dates[0].strftime('%Y-%m-%d')} to {missed_dates[-1].strftime('%Y-%m-%d')}). "
                                     f"Zeros recorded while neighbours averaged {round(float(neigh_rain.loc[missed_dates].mean()), 1)} mm."),
                            original_value=0.0,
                            expected_value=round(float(neigh_rain.loc[missed_dates].mean()), 1),
                            details={
                                "missed_dates": missed_dates,
                                "consecutive_count": consecutive_missed,
                                "neighbour_mean_rain_mm": round(float(neigh_rain.loc[missed_dates].mean()), 1)
                            }
                        ))
                consecutive_missed = 0
                missed_dates = []
                
    return flags


def run_s6_rainy_days_check(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[ValidationFlag]:
    """
    S6 - Rainy Days Check:
    Count days with rainfall >= 0.1 mm per month and per year, and compare with neighbours.
    A station with far fewer rainy days may be skipping light-rain days.
    """
    flags: List[ValidationFlag] = []
    min_rain = float(config.get("min_rain_threshold_mm", 0.1))
    tolerance_ratio = float(config.get("tolerance_ratio", 0.5))
    
    valid_data = df[df["rainfall_mm"].notna() & df["date"].notna()].copy()
    if valid_data.empty:
        return flags
        
    valid_data["year_month"] = valid_data["date"].dt.to_period("M")
    valid_data["is_rainy"] = valid_data["rainfall_mm"] >= min_rain
    
    # Monthly rainy day counts: index=(year_month, station_name)
    monthly_counts = valid_data.groupby(["year_month", "station_name"])["is_rainy"].sum().unstack(level="station_name")
    all_stations = monthly_counts.columns.tolist()
    
    for stn in all_stations:
        neighbours = run_s1_neighbour_selection(stn, all_stations, coords_map, config)
        if not neighbours:
            continue
        neigh_names = [n["station"] for n in neighbours if n["station"] in monthly_counts.columns]
        if not neigh_names:
            continue
            
        for ym, stn_count in monthly_counts[stn].items():
            if pd.isna(stn_count):
                continue
            neigh_counts = monthly_counts.loc[ym, neigh_names].dropna()
            if len(neigh_counts) < 2:
                continue
            neigh_avg = neigh_counts.mean()
            
            # If neighbours averaged >= 6 rainy days and station has < 50% of neighbour count
            if neigh_avg >= 6.0 and stn_count < (neigh_avg * tolerance_ratio):
                flags.append(ValidationFlag(
                    station_id=stn,
                    station_name=stn,
                    date=ym.to_timestamp(),
                    rule_id="S6",
                    flag_direction="-",
                    severity="warning",
                    message=(f"Unusually low rainy days in {ym}: Station had {int(stn_count)} rainy days "
                             f"vs neighbour average of {neigh_avg:.1f} days. Possible skipping of light-rain observations."),
                    original_value=float(stn_count),
                    expected_value=round(float(neigh_avg), 1),
                    details={
                        "month": str(ym),
                        "station_rainy_days": int(stn_count),
                        "neighbour_avg_rainy_days": round(float(neigh_avg), 1),
                        "neighbours_compared": len(neigh_counts)
                    }
                ))
                
    return flags


def run_s7_monthly_yearly_totals(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[ValidationFlag]:
    """
    S7 - Monthly and Yearly Totals:
    Sum daily data to monthly and yearly totals.
    Flag years below mean - 1.645*std or above mean + 1.96*std (or outside 5th/95th percentiles).
    Cross-check with neighbours: regional wet/dry year clears the anomaly.
    """
    flags: List[ValidationFlag] = []
    lower_mult = float(config.get("lower_std_multiplier", 1.645))
    upper_mult = float(config.get("upper_std_multiplier", 1.96))
    
    valid_data = df[df["rainfall_mm"].notna() & df["date"].notna()].copy()
    if valid_data.empty:
        return flags
        
    valid_data["year"] = valid_data["date"].dt.year
    annual_sums = valid_data.groupby(["year", "station_name"])["rainfall_mm"].sum().unstack(level="station_name")
    all_stations = annual_sums.columns.tolist()
    
    for stn in all_stations:
        stn_annual = annual_sums[stn].dropna()
        if len(stn_annual) < 5:  # Need minimum historical years for statistics
            continue
            
        mean_ann = stn_annual.mean()
        std_ann = stn_annual.std(ddof=1)
        lower_limit = mean_ann - (lower_mult * std_ann)
        upper_limit = mean_ann + (upper_mult * std_ann)
        
        neighbours = run_s1_neighbour_selection(stn, all_stations, coords_map, config)
        neigh_names = [n["station"] for n in neighbours if n["station"] in annual_sums.columns]
        
        for year, val in stn_annual.items():
            if val < lower_limit or val > upper_limit:
                direction = "+" if val > upper_limit else "-"
                
                # Check neighbours for regional coherence
                is_regional = False
                neigh_vals = annual_sums.loc[year, neigh_names].dropna() if neigh_names else pd.Series(dtype=float)
                if len(neigh_vals) >= 2:
                    neigh_mean_yr = neigh_vals.mean()
                    # If target is high and neighbours are also high, it's a regional wet year
                    if direction == "+" and neigh_mean_yr > mean_ann:
                        is_regional = True
                    elif direction == "-" and neigh_mean_yr < mean_ann:
                        is_regional = True
                        
                msg = (f"Year {year} total ({val:.1f} mm) is outside warning range "
                       f"[{lower_limit:.1f} - {upper_limit:.1f} mm]. "
                       f"{'Regional weather pattern confirms event.' if is_regional else 'Isolated station anomaly.'}")
                
                flags.append(ValidationFlag(
                    station_id=stn,
                    station_name=stn,
                    date=pd.Timestamp(f"{year}-01-01"),
                    rule_id="S7",
                    flag_direction=direction,
                    severity="info" if is_regional else "warning",
                    message=msg,
                    original_value=round(val, 1),
                    expected_value=round(mean_ann, 1),
                    details={
                        "year": year,
                        "annual_total_mm": round(val, 1),
                        "historical_mean_mm": round(mean_ann, 1),
                        "is_regional_event": is_regional,
                        "neighbours_compared": len(neigh_vals)
                    }
                ))
                
    return flags


def run_s8_double_mass_check(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> Tuple[List[ValidationFlag], Dict[str, pd.DataFrame]]:
    """
    S8 - Long-Term Shift / Double-Mass Analysis:
    Running total of station rainfall vs running total of average of >=3 neighbours.
    Bend lasting >= 5 years indicates gauge relocation, tree growth, or instrument fault.
    Returns (flags, double_mass_dfs).
    """
    flags: List[ValidationFlag] = []
    dm_dfs: Dict[str, pd.DataFrame] = {}
    slope_threshold = float(config.get("slope_change_threshold", 0.15))
    min_years = float(config.get("min_shift_years", 5.0))
    
    valid_data = df[df["rainfall_mm"].notna() & df["date"].notna()].copy()
    if valid_data.empty:
        return flags, dm_dfs
        
    valid_data["year"] = valid_data["date"].dt.year
    annual_piv = valid_data.groupby(["year", "station_name"])["rainfall_mm"].sum().unstack(level="station_name")
    all_stations = annual_piv.columns.tolist()
    
    for stn in all_stations:
        stn_series = annual_piv[stn].dropna()
        if len(stn_series) < 8:  # Minimum 8 years required for double-mass trend
            continue
            
        neighbours = run_s1_neighbour_selection(stn, all_stations, coords_map, config)
        neigh_names = [n["station"] for n in neighbours if n["station"] in annual_piv.columns]
        if len(neigh_names) < 3:
            continue
            
        common_years = annual_piv[[stn] + neigh_names].dropna().index
        if len(common_years) < 8:
            continue
            
        y_station = annual_piv.loc[common_years, stn].cumsum()
        x_neighbours = annual_piv.loc[common_years, neigh_names].mean(axis=1).cumsum()
        
        dm_df = pd.DataFrame({
            "year": common_years,
            "station_annual_mm": annual_piv.loc[common_years, stn],
            "neighbour_annual_mm": annual_piv.loc[common_years, neigh_names].mean(axis=1),
            "cum_station_mm": y_station,
            "cum_neighbours_mm": x_neighbours
        })
        dm_dfs[stn] = dm_df
        
        # Test for slope break around midpoint
        mid = len(common_years) // 2
        p1_x = x_neighbours.iloc[:mid].values
        p1_y = y_station.iloc[:mid].values
        p2_x = x_neighbours.iloc[mid:].values
        p2_y = y_station.iloc[mid:].values
        
        if (p1_x[-1] - p1_x[0]) > 0 and (p2_x[-1] - p2_x[0]) > 0:
            slope1, _ = np.polyfit(p1_x, p1_y, 1)
            slope2, _ = np.polyfit(p2_x, p2_y, 1)
            
            slope_diff = abs(slope2 - slope1) / max(slope1, 0.01)
            if slope_diff > slope_threshold and len(common_years) >= (min_years * 2):
                break_year = int(common_years[mid])
                correction_factor = slope1 / slope2 if slope2 > 0 else 1.0
                flags.append(ValidationFlag(
                    station_id=stn,
                    station_name=stn,
                    date=pd.Timestamp(f"{break_year}-01-01"),
                    rule_id="S8",
                    severity="warning",
                    message=(f"Long-term slope shift detected around year {break_year} (slope shifted from {slope1:.3f} to {slope2:.3f}, {slope_diff*100:.1f}% change). "
                             f"Suspected gauge relocation, environmental exposure change, or instrument fault. Suggested G8 correction factor = {correction_factor:.4f}."),
                    details={
                        "break_year": break_year,
                        "initial_slope": round(float(slope1), 4),
                        "shifted_slope": round(float(slope2), 4),
                        "slope_change_pct": round(float(slope_diff * 100.0), 1),
                        "suggested_correction_factor": round(float(correction_factor), 4)
                    }
                ))
                
    return flags, dm_dfs


def run_all_secondary_validations(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> Tuple[List[ValidationFlag], pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Execute all Secondary Validation rules S1 to S8.
    Returns (flags_list, neighbour_estimates_df, double_mass_dict).
    """
    flags: List[ValidationFlag] = []
    dm_dfs: Dict[str, pd.DataFrame] = {}
    
    # Check if coordinates are available for at least 2 stations
    valid_coords = {k: v for k, v in coords_map.items() if not np.isnan(v[0]) and not np.isnan(v[1])}
    if len(valid_coords) < 2:
        # Cannot run spatial validations reliably
        return flags, pd.DataFrame(), dm_dfs

    # S2: Neighbour Estimate Test
    s2_cfg = config.get("s2_neighbour_estimate", {})
    s2_flags, est_df = run_s2_neighbour_estimate_test(df, coords_map, s2_cfg)
    flags.extend(s2_flags)
    
    # S3: Wrong Day Check
    s3_cfg = config.get("s3_wrong_day", {})
    if s3_cfg.get("enabled", True):
        flags.extend(run_s3_wrong_day_check(df, s2_flags, coords_map, s3_cfg))
        
    # S4: Accumulated Totals
    s4_cfg = config.get("s4_accumulated_totals", {})
    if s4_cfg.get("enabled", True):
        flags.extend(run_s4_accumulated_totals_check(df, s2_flags, coords_map, s4_cfg))
        
    # S5: Missed Entries
    s5_cfg = config.get("s5_missed_entries", {})
    if s5_cfg.get("enabled", True):
        flags.extend(run_s5_missed_entries_check(df, coords_map, s5_cfg))
        
    # S6: Rainy Days Check
    s6_cfg = config.get("s6_rainy_days", {})
    if s6_cfg.get("enabled", True):
        flags.extend(run_s6_rainy_days_check(df, coords_map, s6_cfg))
        
    # S7: Monthly and Yearly Totals
    s7_cfg = config.get("s7_monthly_yearly_totals", {})
    if s7_cfg.get("enabled", True):
        flags.extend(run_s7_monthly_yearly_totals(df, coords_map, s7_cfg))
        
    # S8: Double Mass Analysis
    s8_cfg = config.get("s8_double_mass", {})
    if s8_cfg.get("enabled", True):
        s8_flags, dm_dfs = run_s8_double_mass_check(df, coords_map, s8_cfg)
        flags.extend(s8_flags)
        
    return flags, est_df, dm_dfs
