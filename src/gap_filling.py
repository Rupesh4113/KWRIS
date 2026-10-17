"""Gap-Filling and Traceable Correction Engine: G1 to G8.
Generates defensible, reproducible gap estimates and corrections according to
the Manual on Rainfall Data Validation (National Hydrology Project, May 2019).
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from src.models import CorrectionProposal, ReviewStatus, ValidationFlag
from src.reference_data import haversine_distance_km, select_neighbours


def calculate_normal_annual_rainfall(df_station: pd.DataFrame, exclude_years: Optional[List[int]] = None) -> Optional[float]:
    """Calculate long-term average annual rainfall (normal) for a station over complete baseline years."""
    valid_data = df_station[df_station["rainfall_mm"].notna() & df_station["date"].notna()].copy()
    if valid_data.empty:
        return None
    valid_data["year"] = valid_data["date"].dt.year
    if exclude_years:
        valid_data = valid_data[~valid_data["year"].isin(exclude_years)]
        if valid_data.empty:
            # Fallback to all valid data if no other years exist
            valid_data = df_station[df_station["rainfall_mm"].notna() & df_station["date"].notna()].copy()
            valid_data["year"] = valid_data["date"].dt.year
            
    annual_sums = valid_data.groupby("year")["rainfall_mm"].sum()
    if len(annual_sums) < 1:
        return None
    return float(annual_sums.mean())


def propose_g2_second_gauge_corrections(
    df: pd.DataFrame,
    config: Dict[str, Any]
) -> List[CorrectionProposal]:
    """
    G2 - Use Station's Second Gauge:
    Fill missing manual-gauge daily values from automatic gauge daily total.
    """
    proposals: List[CorrectionProposal] = []
    if "gauge_type" not in df.columns or df["gauge_type"].nunique() < 2:
        return proposals
        
    for stn, stn_df in df.groupby("station_name"):
        piv = stn_df.pivot_table(index="date", columns="gauge_type", values="rainfall_mm", aggfunc="first")
        if "manual" not in piv.columns or "automatic" not in piv.columns:
            continue
            
        missing_manual = piv[piv["manual"].isna() & piv["automatic"].notna()]
        for date, row in missing_manual.iterrows():
            auto_val = float(row["automatic"])
            proposals.append(CorrectionProposal(
                proposal_id=f"G2_{uuid.uuid4().hex[:8]}",
                station_id=stn,
                station_name=stn,
                date=date,
                original_value=np.nan,
                proposed_value=auto_val,
                rule_id="G2",
                method="Second Gauge (Automatic Daily Total)",
                reason=f"Filled missing manual daily record from automatic gauge daily reading ({auto_val:.1f} mm).",
                review_status=ReviewStatus.PENDING
            ))
            
    return proposals


def propose_g3_wrong_day_corrections(
    df: pd.DataFrame,
    s3_flags: List[ValidationFlag],
    config: Dict[str, Any]
) -> List[CorrectionProposal]:
    """
    G3 - Fix Entries on the Wrong Day:
    Propose shifting affected records by +1 or -1 day as identified by S3.
    """
    proposals: List[CorrectionProposal] = []
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    
    for flag in s3_flags:
        if flag.rule_id != "S3":
            continue
            
        shift_days = flag.details.get("suggested_shift_days", 0)
        start_date = flag.details.get("start_date")
        end_date = flag.details.get("end_date")
        stn = flag.station_name
        
        if shift_days == 0 or not start_date or not end_date or stn not in piv.columns:
            continue
            
        date_range = pd.date_range(start_date, end_date, freq="D")
        for d in date_range:
            if d in piv.index:
                orig_val = piv.loc[d, stn]
                target_d = d + pd.Timedelta(days=shift_days)
                
                proposals.append(CorrectionProposal(
                    proposal_id=f"G3_{uuid.uuid4().hex[:8]}",
                    station_id=stn,
                    station_name=stn,
                    date=d,
                    original_value=orig_val if not pd.isna(orig_val) else np.nan,
                    proposed_value=piv.loc[target_d, stn] if target_d in piv.index and not pd.isna(piv.loc[target_d, stn]) else 0.0,
                    rule_id="G3",
                    method=f"Date Realignment ({'+1' if shift_days > 0 else '-1'} day shift)",
                    reason=f"Corrected 1-day observation date lag confirmed by spatial correlation with neighbours.",
                    review_status=ReviewStatus.PENDING
                ))
                
    return proposals


def propose_g4_split_accumulated_corrections(
    df: pd.DataFrame,
    s4_flags: List[ValidationFlag],
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[CorrectionProposal]:
    """
    G4 - Split Accumulated Totals:
    Distribute accumulated rainfall total across affected days in proportion
    to neighbour daily estimates:
    share_day = accumulated_total * (neighbour_est_day / sum(neighbour_est_period))
    """
    proposals: List[CorrectionProposal] = []
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    all_stations = piv.columns.tolist()
    
    for flag in s4_flags:
        if flag.rule_id != "S4":
            continue
            
        stn = flag.station_name
        acc_date = flag.date
        acc_total = flag.original_value
        zero_dates = flag.details.get("zero_period_dates", [])
        
        if acc_total is None or not zero_dates:
            continue
            
        neighbours = select_neighbours(stn, all_stations, coords_map)
        if not neighbours:
            continue
        neigh_names = [n["station"] for n in neighbours]
        
        # Period covers zero_dates + accumulated_date
        all_period_dates = list(zero_dates) + [acc_date]
        neigh_daily_means = piv.loc[all_period_dates, neigh_names].mean(axis=1)
        total_neigh_est = neigh_daily_means.sum()
        
        if total_neigh_est <= 0:
            # Cannot fabricate proportion without rainfall in neighbours
            continue
            
        # Allocate shares proportionally
        allocated_sum = 0.0
        shares = {}
        for d in all_period_dates:
            share = acc_total * (neigh_daily_means.loc[d] / total_neigh_est)
            shares[d] = round(float(share), 2)
            allocated_sum += shares[d]
            
        # Adjust small rounding difference to match original accumulated total exactly
        diff = round(acc_total - allocated_sum, 2)
        if abs(diff) > 0 and len(all_period_dates) > 0:
            shares[all_period_dates[-1]] = round(shares[all_period_dates[-1]] + diff, 2)
            
        # Create proposals for each affected day
        for d in all_period_dates:
            orig_val = float(piv.loc[d, stn]) if d in piv.index and not pd.isna(piv.loc[d, stn]) else 0.0
            proposals.append(CorrectionProposal(
                proposal_id=f"G4_{uuid.uuid4().hex[:8]}",
                station_id=stn,
                station_name=stn,
                date=d,
                original_value=orig_val,
                proposed_value=shares[d],
                rule_id="G4",
                method="Proportional Neighbor Distribution",
                reason=(f"Split accumulated total of {acc_total:.1f} mm across {len(all_period_dates)} days "
                        f"proportional to neighbour rainfall patterns."),
                review_status=ReviewStatus.PENDING
            ))
            
    return proposals


def propose_g5_fill_from_neighbours(
    df: pd.DataFrame,
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[CorrectionProposal]:
    """
    G5 - Fill from Neighbours:
    When long-term normal annual rainfall differs by <= 10%, use simple average (>= 3 neighbours).
    When normals differ by > 10%, use normal-ratio method:
      P_est = (1/N) * sum(P_i * Normal_target / Normal_i).
    Also supports inverse distance weighting with normal ratio adjustment.
    """
    proposals: List[CorrectionProposal] = []
    normal_diff_thresh = float(config.get("normal_diff_threshold_pct", 10.0))
    min_neighbours = int(config.get("min_neighbours_for_avg", 3))
    
    piv = df.pivot_table(index="date", columns="station_name", values="rainfall_mm", aggfunc="first")
    all_stations = piv.columns.tolist()
    
    # Pre-calculate normals for all stations using complete baseline years
    gap_years = df[df["rainfall_mm"].isna()]["date"].dt.year.dropna().unique().tolist()
    station_normals: Dict[str, Optional[float]] = {}
    for stn in all_stations:
        stn_sub = df[df["station_name"] == stn]
        station_normals[stn] = calculate_normal_annual_rainfall(stn_sub, exclude_years=gap_years)
        
    for stn in all_stations:
        missing_dates = piv[piv[stn].isna()].index
        if len(missing_dates) == 0:
            continue
            
        neighbours = select_neighbours(stn, all_stations, coords_map)
        if len(neighbours) < 1:
            continue
            
        target_normal = station_normals.get(stn)
        
        for date in missing_dates:
            available_neighs = []
            for n in neighbours:
                n_name = n["station"]
                n_val = piv.loc[date, n_name] if date in piv.index and n_name in piv.columns else np.nan
                if not pd.isna(n_val):
                    available_neighs.append({
                        "station": n_name,
                        "value": float(n_val),
                        "distance_km": n["distance_km"],
                        "normal": station_normals.get(n_name)
                    })
                    
            if len(available_neighs) == 0:
                continue
                
            # Determine method based on normal comparison
            has_valid_normals = (target_normal is not None and target_normal > 0 and
                                 all(an["normal"] is not None and an["normal"] > 0 for an in available_neighs))
            
            use_simple_avg = False
            if has_valid_normals:
                max_diff_pct = max(abs(an["normal"] - target_normal) / target_normal * 100.0 for an in available_neighs)
                if max_diff_pct <= normal_diff_thresh and len(available_neighs) >= min_neighbours:
                    use_simple_avg = True
                    
            if use_simple_avg:
                # Simple average of neighbours
                est_val = sum(an["value"] for an in available_neighs) / len(available_neighs)
                method_name = f"Simple Average ({len(available_neighs)} neighbours within 10% normal)"
            elif has_valid_normals:
                # Normal-ratio method
                adjusted_vals = [an["value"] * (target_normal / an["normal"]) for an in available_neighs]
                est_val = sum(adjusted_vals) / len(adjusted_vals)
                method_name = f"Normal-Ratio Method ({len(available_neighs)} neighbours)"
            else:
                # Fallback to IDW
                weights = [1.0 / (max(an["distance_km"], 0.1) ** 2) for an in available_neighs]
                est_val = sum(w * an["value"] for w, an in zip(weights, available_neighs)) / sum(weights)
                method_name = f"Inverse Distance Weighting ({len(available_neighs)} neighbours)"
                
            proposals.append(CorrectionProposal(
                proposal_id=f"G5_{uuid.uuid4().hex[:8]}",
                station_id=stn,
                station_name=stn,
                date=date,
                original_value=np.nan,
                proposed_value=round(float(est_val), 2),
                rule_id="G5",
                method=method_name,
                reason=f"Gap completed from {len(available_neighs)} surrounding station records on {date.strftime('%Y-%m-%d')}.",
                review_status=ReviewStatus.PENDING
            ))
            
    return proposals


def propose_g8_long_term_shift_corrections(
    df: pd.DataFrame,
    s8_flags: List[ValidationFlag],
    config: Dict[str, Any]
) -> List[CorrectionProposal]:
    """
    G8 - Correct Long-Term Shifts:
    Multiply inconsistent period record by correction factor:
    factor = slope_reference / slope_inconsistent
    """
    proposals: List[CorrectionProposal] = []
    
    for flag in s8_flags:
        if flag.rule_id != "S8":
            continue
            
        stn = flag.station_name
        factor = flag.details.get("suggested_correction_factor")
        break_year = flag.details.get("break_year")
        
        if factor is None or factor <= 0 or break_year is None:
            continue
            
        # Target records from break_year onwards
        stn_mask = (df["station_name"] == stn) & (df["date"].dt.year >= break_year) & df["rainfall_mm"].notna()
        shift_df = df[stn_mask]
        
        for idx, row in shift_df.iterrows():
            orig_val = float(row["rainfall_mm"])
            corr_val = round(orig_val * factor, 2)
            proposals.append(CorrectionProposal(
                proposal_id=f"G8_{uuid.uuid4().hex[:8]}",
                station_id=stn,
                station_name=stn,
                date=row["date"],
                original_value=orig_val,
                proposed_value=corr_val,
                rule_id="G8",
                method=f"Double-Mass Slope Correction (factor={factor:.4f})",
                reason=(f"Long-term slope correction for data post-{break_year} "
                        f"to restore homogeneity with reference network."),
                review_status=ReviewStatus.PENDING
            ))
            
    return proposals


def generate_all_correction_proposals(
    df: pd.DataFrame,
    primary_flags: List[ValidationFlag],
    secondary_flags: List[ValidationFlag],
    coords_map: Dict[str, Tuple[float, float]],
    config: Dict[str, Any]
) -> List[CorrectionProposal]:
    """
    Generate all traceable correction and gap-filling proposals for reviewer inspection.
    """
    proposals: List[CorrectionProposal] = []
    
    # G2 proposals
    g2_cfg = config.get("g2_second_gauge", {})
    if g2_cfg.get("enabled", True):
        proposals.extend(propose_g2_second_gauge_corrections(df, g2_cfg))
        
    # G3 proposals (from S3 flags)
    g3_cfg = config.get("g3_wrong_day_shift", {})
    if g3_cfg.get("enabled", True):
        proposals.extend(propose_g3_wrong_day_corrections(df, secondary_flags, g3_cfg))
        
    # G4 proposals (from S4 flags)
    g4_cfg = config.get("g4_split_accumulated", {})
    if g4_cfg.get("enabled", True):
        proposals.extend(propose_g4_split_accumulated_corrections(df, secondary_flags, coords_map, g4_cfg))
        
    # G5 proposals
    g5_cfg = config.get("g5_neighbour_filling", {})
    if g5_cfg.get("enabled", True):
        proposals.extend(propose_g5_fill_from_neighbours(df, coords_map, g5_cfg))
        
    # G8 proposals (from S8 flags)
    g8_cfg = config.get("g8_long_term_shift_correction", {})
    if g8_cfg.get("enabled", True):
        proposals.extend(propose_g8_long_term_shift_corrections(df, secondary_flags, g8_cfg))
        
    return proposals


def apply_approved_corrections(
    df: pd.DataFrame,
    proposals: List[CorrectionProposal]
) -> pd.DataFrame:
    """
    Apply ONLY explicitly approved corrections to the working DataFrame.
    Original measurements are strictly preserved; corrected values are populated in
    'validated_rainfall_mm' and annotated with 'validation_status'.
    """
    df_out = df.copy()
    
    if "validated_rainfall_mm" not in df_out.columns:
        df_out["validated_rainfall_mm"] = df_out["rainfall_mm"].copy()
    if "is_corrected" not in df_out.columns:
        df_out["is_corrected"] = False
    if "is_completed" not in df_out.columns:
        df_out["is_completed"] = False
    if "correction_method" not in df_out.columns:
        df_out["correction_method"] = ""
    if "correction_reason" not in df_out.columns:
        df_out["correction_reason"] = ""
        
    approved_count = 0
    for p in proposals:
        if p.review_status == ReviewStatus.APPROVED and p.proposed_value is not None:
            mask = (df_out["station_name"] == p.station_name) & (df_out["date"] == p.date)
            if mask.any():
                df_out.loc[mask, "validated_rainfall_mm"] = p.proposed_value
                if pd.isna(p.original_value):
                    df_out.loc[mask, "is_completed"] = True
                    df_out.loc[mask, "validation_status"] = "completed"
                else:
                    df_out.loc[mask, "is_corrected"] = True
                    df_out.loc[mask, "validation_status"] = "corrected"
                df_out.loc[mask, "correction_method"] = p.method
                df_out.loc[mask, "correction_reason"] = p.reason
                approved_count += 1
                
    return df_out
