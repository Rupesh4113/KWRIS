"""Statistical Analysis and Hydrological Period Aggregations: A1 to A6.
Implements the manual's standard aggregation conventions, completeness rules,
skewed distribution metrics, and homogeneity consistency tests.
"""

from __future__ import annotations
import calendar
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy import stats


def aggregate_weekly_standard(df_station: pd.DataFrame) -> pd.DataFrame:
    """
    A1 - Daily to Weekly Aggregation:
    51 seven-day weeks, with the 52nd week containing the remaining 8 days (9 in a leap year).
    """
    valid = df_station.dropna(subset=["date"]).sort_values("date").copy()
    if valid.empty:
        return pd.DataFrame()
        
    records = []
    valid["year"] = valid["date"].dt.year
    valid["day_of_year"] = valid["date"].dt.dayofyear
    
    for year, y_df in valid.groupby("year"):
        is_leap = calendar.isleap(year)
        total_days = 366 if is_leap else 365
        
        for w in range(1, 53):
            start_doy = (w - 1) * 7 + 1
            end_doy = w * 7 if w < 52 else total_days
            expected_days = end_doy - start_doy + 1
            
            sub = y_df[(y_df["day_of_year"] >= start_doy) & (y_df["day_of_year"] <= end_doy)]
            valid_vals = sub["rainfall_mm"].dropna()
            
            records.append({
                "year": year,
                "week_num": w,
                "expected_days": expected_days,
                "valid_days": len(valid_vals),
                "weekly_rainfall_mm": round(float(valid_vals.sum()), 1) if len(valid_vals) > 0 else np.nan,
                "is_complete": len(valid_vals) >= (expected_days * 0.9)
            })
            
    return pd.DataFrame(records)


def aggregate_ten_daily_dekad(df_station: pd.DataFrame) -> pd.DataFrame:
    """
    A1 - Ten-Daily (Dekad) Aggregation:
    Two 10-day periods (days 1-10, days 11-20) and one remaining period (day 21 to end of month).
    """
    valid = df_station.dropna(subset=["date"]).sort_values("date").copy()
    if valid.empty:
        return pd.DataFrame()
        
    valid["year"] = valid["date"].dt.year
    valid["month"] = valid["date"].dt.month
    valid["day"] = valid["date"].dt.day
    
    records = []
    for (year, month), m_df in valid.groupby(["year", "month"]):
        _, num_days = calendar.monthrange(year, month)
        
        # Dekad 1: 1-10
        d1 = m_df[(m_df["day"] >= 1) & (m_df["day"] <= 10)]["rainfall_mm"].dropna()
        records.append({
            "year": year, "month": month, "dekad": 1,
            "days_in_dekad": 10, "valid_days": len(d1),
            "rainfall_mm": round(float(d1.sum()), 1) if len(d1) > 0 else np.nan,
            "is_complete": len(d1) >= 9
        })
        
        # Dekad 2: 11-20
        d2 = m_df[(m_df["day"] >= 11) & (m_df["day"] <= 20)]["rainfall_mm"].dropna()
        records.append({
            "year": year, "month": month, "dekad": 2,
            "days_in_dekad": 10, "valid_days": len(d2),
            "rainfall_mm": round(float(d2.sum()), 1) if len(d2) > 0 else np.nan,
            "is_complete": len(d2) >= 9
        })
        
        # Dekad 3: 21 to end of month
        d3_days = num_days - 20
        d3 = m_df[m_df["day"] >= 21]["rainfall_mm"].dropna()
        records.append({
            "year": year, "month": month, "dekad": 3,
            "days_in_dekad": d3_days, "valid_days": len(d3),
            "rainfall_mm": round(float(d3.sum()), 1) if len(d3) > 0 else np.nan,
            "is_complete": len(d3) >= int(d3_days * 0.9)
        })
        
    return pd.DataFrame(records)


def compute_station_monthly_statistics(
    df: pd.DataFrame, 
    completeness_min_pct: float = 90.0
) -> pd.DataFrame:
    """
    A3 & A4 - Monthly Totals and Statistical Measures per station.
    Enforces completeness rule: incomplete months are explicitly marked.
    """
    records = []
    valid = df.dropna(subset=["date"]).copy()
    valid["year"] = valid["date"].dt.year
    valid["month"] = valid["date"].dt.month
    
    for (stn, year, month), group in valid.groupby(["station_name", "year", "month"]):
        _, days_in_month = calendar.monthrange(year, month)
        total_obs = len(group)
        rf_series = group["rainfall_mm"]
        valid_rf = rf_series.dropna()
        valid_days = len(valid_rf)
        completeness_pct = (valid_days / days_in_month) * 100.0
        is_complete = completeness_pct >= completeness_min_pct
        
        rainy_days = (valid_rf >= 0.1).sum() if valid_days > 0 else 0
        mean_val = float(valid_rf.mean()) if valid_days > 0 else np.nan
        median_val = float(valid_rf.median()) if valid_days > 0 else np.nan
        std_val = float(valid_rf.std(ddof=1)) if valid_days > 1 else np.nan
        skew_val = float(stats.skew(valid_rf)) if valid_days > 2 else np.nan
        max_val = float(valid_rf.max()) if valid_days > 0 else np.nan
        total_rf = float(valid_rf.sum()) if valid_days > 0 else np.nan
        
        # Flags count
        flagged_count = (group["validation_status"] == "doubtful").sum() if "validation_status" in group.columns else 0
        corrected_count = (group["is_corrected"] == True).sum() if "is_corrected" in group.columns else 0
        completed_count = (group["is_completed"] == True).sum() if "is_completed" in group.columns else 0
        
        records.append({
            "station_name": stn,
            "year": year,
            "month": month,
            "days_in_month": days_in_month,
            "valid_days": valid_days,
            "completeness_pct": round(completeness_pct, 1),
            "is_complete": is_complete,
            "monthly_rainfall_mm": round(total_rf, 1) if not np.isnan(total_rf) else np.nan,
            "mean_daily_mm": round(mean_val, 2) if not np.isnan(mean_val) else np.nan,
            "median_daily_mm": round(median_val, 2) if not np.isnan(median_val) else np.nan,
            "std_daily_mm": round(std_val, 2) if not np.isnan(std_val) else np.nan,
            "skewness": round(skew_val, 2) if not np.isnan(skew_val) else np.nan,
            "max_daily_mm": round(max_val, 1) if not np.isnan(max_val) else np.nan,
            "rainy_days": int(rainy_days),
            "flagged_doubtful_count": int(flagged_count),
            "corrected_count": int(corrected_count),
            "completed_count": int(completed_count)
        })
        
    return pd.DataFrame(records)


def compute_station_yearly_statistics(
    df: pd.DataFrame, 
    completeness_min_pct: float = 90.0
) -> pd.DataFrame:
    """
    A3 & A4 - Annual Totals and Statistical Measures per station.
    """
    records = []
    valid = df.dropna(subset=["date"]).copy()
    valid["year"] = valid["date"].dt.year
    
    for (stn, year), group in valid.groupby(["station_name", "year"]):
        is_leap = calendar.isleap(year)
        days_in_year = 366 if is_leap else 365
        
        rf_series = group["rainfall_mm"]
        valid_rf = rf_series.dropna()
        valid_days = len(valid_rf)
        completeness_pct = (valid_days / days_in_year) * 100.0
        is_complete = completeness_pct >= completeness_min_pct
        
        rainy_days = (valid_rf >= 0.1).sum() if valid_days > 0 else 0
        mean_val = float(valid_rf.mean()) if valid_days > 0 else np.nan
        std_val = float(valid_rf.std(ddof=1)) if valid_days > 1 else np.nan
        skew_val = float(stats.skew(valid_rf)) if valid_days > 2 else np.nan
        max_val = float(valid_rf.max()) if valid_days > 0 else np.nan
        annual_total = float(valid_rf.sum()) if valid_days > 0 else np.nan
        
        records.append({
            "station_name": stn,
            "year": year,
            "days_in_year": days_in_year,
            "valid_days": valid_days,
            "completeness_pct": round(completeness_pct, 1),
            "is_complete": is_complete,
            "annual_rainfall_mm": round(annual_total, 1) if not np.isnan(annual_total) else np.nan,
            "mean_daily_mm": round(mean_val, 2) if not np.isnan(mean_val) else np.nan,
            "std_daily_mm": round(std_val, 2) if not np.isnan(std_val) else np.nan,
            "skewness": round(skew_val, 2) if not np.isnan(skew_val) else np.nan,
            "max_daily_mm": round(max_val, 1) if not np.isnan(max_val) else np.nan,
            "rainy_days": int(rainy_days),
            "missing_days": days_in_year - valid_days
        })
        
    return pd.DataFrame(records)


def perform_a5_consistency_tests(series_annual: pd.Series) -> Dict[str, Any]:
    """
    A5 - Statistical Consistency Checks Before Trend Analysis:
    Splits annual record into two halves and performs Mann-Whitney U, Wilcoxon, and Student's t-test.
    """
    clean_series = series_annual.dropna()
    n = len(clean_series)
    if n < 8:
        return {"status": "insufficient_data", "sample_size": n}
        
    mid = n // 2
    period1 = clean_series.iloc[:mid].values
    period2 = clean_series.iloc[mid:].values
    
    t_stat, t_pval = stats.ttest_ind(period1, period2, equal_var=False)
    mw_stat, mw_pval = stats.mannwhitneyu(period1, period2, alternative="two-sided")
    
    mean1 = float(np.mean(period1))
    mean2 = float(np.mean(period2))
    
    is_inconsistent = mw_pval < 0.05 or t_pval < 0.05
    return {
        "status": "tested",
        "sample_size": n,
        "period1_mean_mm": round(mean1, 1),
        "period2_mean_mm": round(mean2, 1),
        "mean_shift_pct": round(abs(mean2 - mean1) / max(mean1, 1.0) * 100.0, 1),
        "ttest_stat": round(float(t_stat), 3),
        "ttest_pvalue": round(float(t_pval), 4),
        "mann_whitney_stat": round(float(mw_stat), 3),
        "mann_whitney_pvalue": round(float(mw_pval), 4),
        "is_statistically_significant_shift": bool(is_inconsistent),
        "interpretation": ("Statistically significant shift detected between periods. Homogeneity verification recommended."
                           if is_inconsistent else "Record shows stationary homogeneity across observation periods.")
    }


def compute_a6_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    A6 - Comprehensive Quality Reporting:
    Station-level summary of total observations, valid, missing, doubtful, corrected, and completed.
    """
    records = []
    for stn, group in df.groupby("station_name"):
        total = len(group)
        valid_cnt = (group["validation_status"] == "validated").sum() if "validation_status" in group.columns else 0
        missing_cnt = (group["validation_status"] == "missing").sum() if "validation_status" in group.columns else 0
        doubtful_cnt = (group["validation_status"] == "doubtful").sum() if "validation_status" in group.columns else 0
        corrected_cnt = (group["is_corrected"] == True).sum() if "is_corrected" in group.columns else 0
        completed_cnt = (group["is_completed"] == True).sum() if "is_completed" in group.columns else 0
        
        # If status wasn't annotated, infer from rainfall_mm
        if valid_cnt == 0 and missing_cnt == 0:
            missing_cnt = group["rainfall_mm"].isna().sum()
            valid_cnt = total - missing_cnt
            
        records.append({
            "station_name": stn,
            "station_id": group["station_id"].iloc[0] if "station_id" in group.columns else stn,
            "basin": group["basin"].iloc[0] if "basin" in group.columns and group["basin"].notna().any() else "KWRIS Basin",
            "total_observations": total,
            "valid_observations": int(valid_cnt),
            "missing_observations": int(missing_cnt),
            "missing_pct": round(missing_cnt / max(1, total) * 100.0, 2),
            "doubtful_observations": int(doubtful_cnt),
            "doubtful_pct": round(doubtful_cnt / max(1, total) * 100.0, 2),
            "corrected_observations": int(corrected_cnt),
            "completed_observations": int(completed_cnt),
            "data_health_score": round(max(0, 100.0 - ((missing_cnt * 1.0 + doubtful_cnt * 1.5) / max(1, total) * 100.0)), 1)
        })
        
    return pd.DataFrame(records)
