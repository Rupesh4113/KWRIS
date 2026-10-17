"""Historical Data Integration and Climatological Analysis (Up to 20 Years)."""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np

from src.configuration import APP_CONFIG


class HistoricalDataManager:
    """
    Manages historical rainfall baselines (up to 20 years).
    Calculates station coverage, historical climatology, and matches current stations.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(APP_CONFIG["db_path"])
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite tables for historical data persistence."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_records (
                    station_id TEXT,
                    station_name TEXT,
                    date TEXT,
                    rainfall REAL,
                    unit TEXT,
                    latitude REAL,
                    longitude REAL,
                    dataset_source TEXT,
                    PRIMARY KEY (station_id, date)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_metadata (
                    source_id TEXT PRIMARY KEY,
                    filename TEXT,
                    import_timestamp TEXT,
                    record_count INTEGER,
                    station_count INTEGER,
                    year_min INTEGER,
                    year_max INTEGER
                )
            """)
            conn.commit()

    def ingest_records(
        self,
        df: pd.DataFrame,
        dataset_source: str = "Historical Upload"
    ) -> Dict[str, Any]:
        """
        Validate and store historical records into persistent database.
        df must contain [station_id, date, rainfall].
        """
        required = ["station_id", "date", "rainfall"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Historical dataset missing required column: '{col}'")

        work_df = df.copy()
        work_df["date"] = pd.to_datetime(work_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        work_df = work_df[work_df["date"].notna()]
        work_df["station_id"] = work_df["station_id"].astype(str).str.strip()
        work_df["station_name"] = work_df.get("station_name", work_df["station_id"]).astype(str).str.strip()
        work_df["rainfall"] = pd.to_numeric(work_df["rainfall"], errors="coerce")
        work_df["unit"] = work_df.get("unit", "mm")
        work_df["latitude"] = pd.to_numeric(work_df.get("latitude"), errors="coerce")
        work_df["longitude"] = pd.to_numeric(work_df.get("longitude"), errors="coerce")
        work_df["dataset_source"] = dataset_source

        # Remove negative rainfall
        work_df = work_df[work_df["rainfall"].isna() | (work_df["rainfall"] >= 0.0)]
        work_df.drop_duplicates(subset=["station_id", "date"], keep="last", inplace=True)

        # Batch insert with UPSERT
        records_to_insert = work_df[[
            "station_id", "station_name", "date", "rainfall", "unit",
            "latitude", "longitude", "dataset_source"
        ]].values.tolist()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO historical_records 
                (station_id, station_name, date, rainfall, unit, latitude, longitude, dataset_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(station_id, date) DO UPDATE SET
                    rainfall=excluded.rainfall,
                    station_name=excluded.station_name,
                    dataset_source=excluded.dataset_source
            """, records_to_insert)
            conn.commit()

        dates = pd.to_datetime(work_df["date"])
        year_min = int(dates.dt.year.min()) if not dates.empty else 0
        year_max = int(dates.dt.year.max()) if not dates.empty else 0

        summary = {
            "records_imported": len(work_df),
            "stations_imported": work_df["station_id"].nunique(),
            "year_range": f"{year_min} - {year_max}",
            "source": dataset_source
        }
        return summary

    def get_station_coverage(self, station_ids: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Calculate historical coverage metrics for stations:
        - coverage_years: count of distinct years with data
        - completeness_pct: percentage of expected days available
        - start_year, end_year
        - total_observations
        """
        query = "SELECT station_id, station_name, date, rainfall FROM historical_records"
        params = []
        if station_ids:
            placeholders = ",".join("?" for _ in station_ids)
            query += f" WHERE station_id IN ({placeholders})"
            params = station_ids

        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            return pd.DataFrame(columns=[
                "station_id", "station_name", "coverage_years", "completeness_pct",
                "start_year", "end_year", "total_records", "has_adequate_history"
            ])

        df["date"] = pd.to_datetime(df["date"])
        df["year"] = df["date"].dt.year

        coverage_list = []
        for stn_id, group in df.groupby("station_id"):
            stn_name = group["station_name"].iloc[0]
            start_year = int(group["year"].min())
            end_year = int(group["year"].max())
            year_span = max(1, end_year - start_year + 1)
            
            # Count years having at least 100 observations
            yearly_counts = group.groupby("year")["rainfall"].count()
            active_years = int((yearly_counts >= 100).sum())
            total_records = len(group)
            
            expected_days = year_span * 365.25
            completeness = min(100.0, (total_records / expected_days) * 100.0)

            coverage_list.append({
                "station_id": str(stn_id),
                "station_name": str(stn_name),
                "coverage_years": active_years,
                "completeness_pct": round(completeness, 1),
                "start_year": start_year,
                "end_year": end_year,
                "total_records": total_records,
                "has_adequate_history": active_years >= 3
            })

        return pd.DataFrame(coverage_list)

    def get_station_history(self, station_id: str) -> pd.DataFrame:
        """Fetch all historical records for a specific station."""
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                "SELECT station_id, station_name, date, rainfall, unit, latitude, longitude "
                "FROM historical_records WHERE station_id = ? ORDER BY date ASC",
                conn,
                params=[station_id]
            )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def compute_daily_climatology(self, station_id: str) -> pd.DataFrame:
        """
        Compute daily historical climatology for day-of-year (1 to 366):
        - mean, median, p10, p90, probability of rain (pr_rain)
        """
        hist_df = self.get_station_history(station_id)
        if hist_df.empty:
            return pd.DataFrame()

        hist_df["doy"] = hist_df["date"].dt.dayofyear
        
        clima = []
        for doy, group in hist_df.groupby("doy"):
            clean_rf = group["rainfall"].dropna()
            if clean_rf.empty:
                continue
            pr_rain = (clean_rf > 0.1).mean()
            clima.append({
                "doy": doy,
                "mean_mm": float(clean_rf.mean()),
                "median_mm": float(clean_rf.median()),
                "p10_mm": float(clean_rf.quantile(0.10)),
                "p90_mm": float(clean_rf.quantile(0.90)),
                "pr_rain": float(pr_rain),
                "sample_size": len(clean_rf)
            })

        return pd.DataFrame(clima)
