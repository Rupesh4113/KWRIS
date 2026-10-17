"""Persistent Storage and Audit Review Logging for RainfallIQ."""

from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd

from src.configuration import APP_CONFIG


class StorageManager:
    """Manages audit trails, user reviews, and state persistence via SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(APP_CONFIG["db_path"])
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _init_tables(self):
        """Create audit log tables if not present."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT,
                    observation_date TEXT,
                    action TEXT,
                    reviewer TEXT,
                    timestamp TEXT,
                    original_value TEXT,
                    predicted_value REAL,
                    notes TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_state (
                    session_key TEXT PRIMARY KEY,
                    data_json TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def log_review_decision(
        self,
        station_id: str,
        observation_date: str,
        action: str,  # 'Accepted', 'Rejected', 'Resolved'
        reviewer: str = "Hydrology Engineer",
        original_value: Optional[str] = None,
        predicted_value: Optional[float] = None,
        notes: str = ""
    ) -> int:
        """Record an explicit engineering review action in the audit log."""
        timestamp = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_reviews 
                (station_id, observation_date, action, reviewer, timestamp, original_value, predicted_value, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(station_id),
                str(observation_date),
                action,
                reviewer,
                timestamp,
                str(original_value),
                predicted_value,
                notes
            ))
            conn.commit()
            return cursor.lastrowid

    def get_audit_trail(self, station_id: Optional[str] = None) -> pd.DataFrame:
        """Retrieve complete historical audit trail of engineer reviews."""
        query = "SELECT id, station_id, observation_date, action, reviewer, timestamp, original_value, predicted_value, notes FROM audit_reviews"
        params = []
        if station_id:
            query += " WHERE station_id = ? ORDER BY timestamp DESC"
            params.append(str(station_id))
        else:
            query += " ORDER BY timestamp DESC"

        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)
        return df

    def clear_audit_trail(self):
        """Reset audit trail (primarily for testing/demo resets)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM audit_reviews")
            conn.commit()
