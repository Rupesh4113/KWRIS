# KWRIS: AI-Powered Rainfall Data Quality Validation & Correction Platform

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/)
[![Validation Manual](https://img.shields.io/badge/NHP%20Manual-May%202019-darkred.svg)](Manual_Rainfall_Data_Validation.pdf)
[![Tests Passing](https://img.shields.io/badge/tests-23%20passed-success.svg)](tests/)

An enterprise-grade hydrological validation, anomaly detection, gap-filling, and traceable data correction platform built for the **Karnataka Water Resources Information System (KWRIS)**.

Governed strictly by the **Manual on Rainfall Data Validation (National Hydrology Project, Ministry of Water Resources, River Development and Ganga Rejuvenation, Government of India, May 2019)**.

---

## 🏛️ Foundational Hydrological Principles

1. **Flag, do not delete:** Every original observation is permanently preserved. Suspicious readings are flagged as `doubtful`. Changes require stated reasons and are labeled `corrected` (Manual §2.1.1).
2. **A test screens; it does not decide:** No single automated check proves a value wrong. A flag means *"look again"*; spatial context and field data confirm or clear it (Manual §2.1.1.2).
3. **Extremes can be real:** Genuine extreme rainfall is vital for dam safety and flood design. High values are never discarded without neighbouring cross-checks (Manual §4.1).
4. **Zero is not missing:** $0.0\text{ mm}$ means no rain fell; missing means no measurement exists. They are distinct types and never interchanged (Manual §4.10.1).
5. **Measured beats estimated:** Field measurements always supersede filled values. Filled gaps are explicitly tagged as `completed` (Manual §5.1).

---

## 📋 Comprehensive Requirements Mapping Table

| Requirement | Existing Implementation in Repo | Gap Identified | Proposed & Implemented Action |
|---|---|---|---|
| **Excel/CSV Upload** | Raw sample datasets present (`ARKAVATHI RAINFALL.xlsx`, `GHATAPRABHA`, `K3`, `K4`). | No upload UI, sheet selector, or schema mapper existed. | Built `src/ingestion.py` supporting `.xlsx`, `.xls`, `.csv`, multi-sheet selection, and automatic long/wide format detection. |
| **Data Profiling** | None in repository. | No data health diagnostics or sequence gap detection. | Built `src/preprocessing.py` and profiling UI for completeness %, missingness, negatives, duplicates, and date gaps. |
| **Primary Validation** | None in repository. | Rules P1–P5 completely missing. | Built `src/primary_validation.py`: P1 (entry check), P2 (min limit $<0$), P3 (daily ceiling), P4 (monthly upper warning), P5 (dual-gauge comparison). |
| **Neighbour Validation** | Static IDW summary sheet in K3/K4. | No dynamic neighbour selection or automated spatial screening. | Built `src/secondary_validation.py`: S1 (quadrant neighbours), S2 (IDW estimate test), S3 (1-day date shifts), S4 (accumulated totals), S5 (missed entries), S6 (rainy days), S7 (annual totals), S8 (double-mass curve). |
| **Missing Data & Correction** | Static pre-filled sheets in K3/K4. | No interactive review workflow, audit trail, or traceable proposals. | Built `src/gap_filling.py` and `src/audit.py`: G1 (keep missing), G2 (second gauge), G3 (wrong-day shift), G4 (split accumulated totals), G5 (normal-ratio filling), G6 (rainy day accounting), G7 (no straight-line daily filling), G8 (double-mass shift correction). |
| **Statistical Analysis** | None in repository. | Hydrological period aggregations missing. | Built `src/statistics.py`: A1 (08:30 daily, 52-week standard, dekads), A2 (tipping-bucket regularization), A3 (completeness $\ge 90\%$), A4 (skewness, median, std), A5 (Mann-Whitney / t-test consistency), A6 (quality reporting). |
| **Streamlit Dashboard** | None in repository. | No web interface. | Built 11-page responsive Streamlit application with Karnataka Government theme (`#8B0000`). |
| **Station Quality Ranking** | None in repository. | No triage priority scoring. | Built `src/station_ranking.py` with multi-factor scoring (0–100 scale), urgency badges, and actionable guidance. |
| **Excel Export** | None in repository. | No standardized reporting. | Built `src/reporting.py` generating full 13-sheet production workbook with openpyxl styling and frozen headers. |
| **Automated Testing** | None in repository. | No automated test suite. | Implemented 23 comprehensive Pytest tests in `tests/` covering all rules with synthetic datasets. |
| **Cloud Deployment** | None in repository. | No deployment configuration. | Created `streamlit_app.py`, `requirements.txt`, `.streamlit/config.toml`, and deployment guide. |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10 or 3.11 installed.

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Rupesh4113/KWRIS.git
cd KWRIS

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
# or: source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Run Automated Tests
```bash
pytest -v
```
*Result: 23 passing tests verifying P1–P5, S1–S8, G1–G8, A1–A6, ingestion, and Excel generation.*

### 4. Launch Application
```bash
streamlit run streamlit_app.py
```
Open your browser at `http://localhost:8501`.

---

## 🗂️ Project Directory Structure

```text
KWRIS/
├── streamlit_app.py              # Main Streamlit application entry point
├── requirements.txt              # Production Python dependencies
├── pytest.ini                    # Pytest configuration
├── README.md                     # Platform documentation & mapping table
├── .gitignore                    # Git exclusions
├── .streamlit/
│   ├── config.toml               # Karnataka deep red UI theme configuration
│   └── secrets.toml.example      # Secrets template
├── app/
│   ├── components/
│   │   ├── sidebar.py            # Navigation & mode selector (Validation / Suggest / Apply)
│   │   ├── dashboard.py          # Metric KPI cards & health banner
│   │   ├── charts.py             # Plotly charts (time series, double-mass, heatmap)
│   │   └── data_tables.py        # Table formatting & rule badges
│   └── pages/
│       ├── home.py                        # 1. Executive dashboard & urgent leaderboard
│       ├── upload_and_profiling.py        # 2. Unified upload, column mapping & profiling
│       ├── validation_results.py          # 3. Unified primary & secondary validation (P1–P5, S1–S8)
│       ├── station_priority_analytics.py  # 4. Station priority ranking & decision analytics (A1–A6)
│       ├── correction_review.py           # 5. Missing data review & approval workflow (G1–G8)
│       └── export_reports.py              # 6. 13-sheet Excel report export & rules guide
├── src/
│   ├── ingestion.py              # Ingestion, format detection, normalization
│   ├── preprocessing.py          # Dataset profiling & date gap detection
│   ├── reference_data.py         # Haversine distance & Karnataka station catalog
│   ├── primary_validation.py     # Rules P1–P5 implementation
│   ├── secondary_validation.py   # Rules S1–S8 implementation
│   ├── gap_filling.py            # Rules G1–G8 implementation
│   ├── audit.py                  # AuditTrailManager for traceable decisions
│   ├── statistics.py             # Rules A1–A6 aggregations & consistency
│   ├── station_ranking.py        # Transparent 0–100 priority ranking
│   ├── reporting.py              # 13-sheet openpyxl Excel generator
│   └── models.py                 # Pydantic schemas & dataclasses
├── config/
│   └── validation_rules.yaml     # Tunable rule thresholds & parameters
├── tests/
│   ├── test_ingestion.py         # Tests for file reading & normalization
│   ├── test_primary_validation.py# Tests for rules P1–P5
│   ├── test_secondary_validation.py # Tests for rules S1–S8
│   ├── test_gap_filling.py       # Tests for rules G1–G8
│   ├── test_statistics.py        # Tests for rules A1–A6
│   └── test_reporting.py         # Tests for 13-sheet export & audit
└── docs/
    ├── architecture.md           # System architecture & data flow
    ├── validation_rules.md       # Full rules manual specification
    └── deployment.md             # Streamlit Cloud & local deployment guide
```

---

## 📑 13-Worksheet Production Excel Export

The platform automatically generates a comprehensive 13-sheet Excel report:
1. `Read_Me`: Processing summary, hydrological conventions, limitations, and user guide.
2. `Original_Data`: Unmodified raw uploaded rainfall observations.
3. `Validated_Data`: Complete dataset annotated with validation statuses and rule flags.
4. `Corrected_Data`: Approved traceable corrections and completed gap estimates.
5. `Missing_Data`: Records with missing measurements or placeholder codes.
6. `Suspicious_Readings`: Detailed flags raised by primary and secondary validation checks.
7. `Station_Summary`: Station-level quality metrics, data health scores, and priority ranks.
8. `Monthly_Statistics`: Monthly sums, skewness, median, and completeness validation.
9. `Yearly_Statistics`: Annual sums, rainy days ($\ge 0.1\text{ mm}$), and completeness.
10. `Neighbour_Analysis`: Spatial IDW estimates, contributing stations, and distances.
11. `Correction_Audit`: Immutable audit trail (original, proposed, method, reason, reviewer).
12. `Validation_Rules`: Complete catalog of 27 rules, formulas, and active thresholds.
13. `Processing_Log`: Execution steps, warnings, and system log messages.

---

## ☁️ Streamlit Community Cloud Deployment

1. Commit and push repository to GitHub (`Rupesh4113/KWRIS`).
2. Log in to [share.streamlit.io](https://share.streamlit.io).
3. Connect repository `Rupesh4113/KWRIS`, branch `main`, and main file `streamlit_app.py`.
4. Deploy! Streamlit will automatically resolve `requirements.txt` and launch the app.

---

## 📜 Governing Reference
Ministry of Water Resources, River Development and Ganga Rejuvenation (May 2019). **Manual on Rainfall Data Validation**. National Hydrology Project, Government of India, New Delhi.
