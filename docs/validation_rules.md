# KWRIS Rainfall Quality Rules & Hydrological Manual Specification

Reference Standard: **Manual on Rainfall Data Validation (National Hydrology Project, Ministry of Water Resources, River Development and Ganga Rejuvenation, Government of India, May 2019)**

---

## 1. Primary Validation (Single-Station Screening)

### P1 — Entry Check (Manual §3.1, §4.2)
- Catches entries that cannot be legitimate physical observations: non-numeric characters, unparseable timestamps, and duplicate station-date records.
- Detects configured placeholder missing codes (`-99`, `-999`, `-9999`, `9999`, `NA`) and normalizes them to `NaN`.
- **Hydrological Guardrail:** Preserves valid $0.0\text{ mm}$ observations as legitimate zero rainfall.

### P2 — Minimum Limit (Manual §3.4)
- Rainfall cannot physically fall below $0.0\text{ mm}$.
- Flags negative values with direction `-` and critical severity.
- **Hydrological Guardrail:** Negative values are never automatically altered to zero; they require investigation into instrument calibration or observer typos.

### P3 — Maximum Limit (Manual §3.4)
- Flags observations exceeding the daily ceiling, based on the India Meteorological Department (IMD) 1-day Probable Maximum Precipitation (PMP) or highest documented historical maximum (default: $350\text{ mm}$).
- Flagged readings are tagged as `doubtful` with direction `+`.

### P4 — Upper Warning Level (Manual §3.5)
- Catches values below the ceiling that are still unusually extreme for the specific calendar month:
  $$\text{Warning Level} = \mu_{\text{month}} + 1.96 \times \sigma_{\text{month}}$$
- Evaluated over past daily data including dry days. Supports the 98th percentile as an alternative method.

### P5 — Two Gauges at One Station (Manual §3.3)
- Where a station has both a manual standard rain gauge (SRG) and an automatic gauge (ARG/TBG), aggregates automatic hourly readings ($08:30\text{ to }08:30$) into daily totals.
- Differences below $5\%$ are ignored as instrument tolerance.
- For discrepancies $\ge 5\%$, classifies specific diagnostic patterns:
  - Automatic consistently higher/lower $\rightarrow$ Calibration drift (trust manual gauge).
  - Gap grows during heavy rainfall $\rightarrow$ Bucket double-counting or chart crowded (trust manual gauge).
  - Day-to-day lag $\rightarrow$ Manual gauge read at wrong time (trust automatic gauge).
  - Long-term identical records $\rightarrow$ Data fabrication flag (treat both as suspect).

---

## 2. Secondary Validation (Spatial Neighbour Screening)

### S1 — Pick Neighbours (Manual §4.6)
- Selects up to 8 neighbouring stations within a search radius (default: $35\text{ km}$).
- Enforces quadrant balancing: at most 2 stations per quadrant (North-East, South-East, South-West, North-West) so no single spatial direction biases estimates.

### S2 — Neighbour Estimate Test (Manual §4.6)
- Computes spatial estimate using Inverse-Distance-Squared weighting:
  $$w_i = \frac{1}{d_i^2}, \quad P_{\text{est}} = \frac{\sum w_i P_i}{\sum w_i}$$
- Flags records where $|P_{\text{obs}} - P_{\text{est}}| > 45\text{ mm}$ or $|P_{\text{obs}} - P_{\text{est}}| > 2 \times \sigma_{\text{neighbours}}$.
- Annotates direction: `+` if observed exceeds estimate, `-` if observed is lower.
- Small rain threshold ($\le 2.5\text{ mm}$) suppresses false alarms during light drizzle.

### S3 — Entries on Wrong Day (Manual §4.4, §4.8)
- Detects 1-day observation date shifts caused by observers losing track of dates during dry spells.
- Diagnoses opposite-direction anomaly pairs (`+` at wet spell onset, `-` at end, or vice versa).
- Confirms shift by testing cross-correlation with neighbours under $\pm 1$ day time shift.

### S4 — Accumulated Totals (Manual §4.9)
- Detects instances where an observer missed readings (e.g. over weekends or holidays) and entered the cumulative sum upon return.
- Signature: Run of zeros with `-` flags while neighbours had rain, followed by a large positive spike (`+`).

### S5 — Missed Entries (Manual §4.10)
- Identifies runs of zero readings during significant rain across neighbours where no subsequent accumulated spike appears. Classifies values as omitted observations, not genuine zero rainfall.

### S6 — Rainy Days Check (Manual §4.11)
- Counts days with rainfall $\ge 0.1\text{ mm}$ per month and year.
- Flags stations recording significantly fewer rainy days ($< 50\%$ of neighbour average), indicative of observers skipping light-rain events.

### S7 — Monthly and Yearly Totals (Manual §4.5)
- Sums daily records to monthly and annual totals.
- Flags values outside $\mu \pm 1.96\sigma$. Cross-checks against neighbouring stations: if high or low rainfall is regionally coherent, the isolated flag is cleared or annotated.

### S8 — Double-Mass Homogeneity Analysis (Manual §4.12)
- Plots station cumulative rainfall vs. cumulative mean of $\ge 3$ reliable neighbours using annual totals.
- Identifies slope breaks persisting for $\ge 5$ years, diagnosing gauge relocation, new tree/building obstacles, or instrument changes.

---

## 3. Missing Data & Correction Engine (G1–G8)

### G1 — Keep Missing as Missing (Manual §5.1)
- Never fills a gap with zero. Gaps without sufficient neighbouring evidence remain missing (`NaN`).

### G2 — Use Station's Second Gauge (Manual §5.2)
- Fills missing manual daily values from automatic daily totals, and distributes manual totals into hourly estimates using neighbour hourly fractions.

### G3 — Fix Wrong Day Entries (Manual §5.3)
- Realigns confirmed date-shifted sequences by the verified offset ($\pm 1$ day) and records original timestamps in the audit trail.

### G4 — Split Accumulated Totals (Manual §5.4)
- Proportionally distributes accumulated totals across affected days:
  $$\text{Daily Share} = P_{\text{accumulated}} \times \frac{P_{\text{neighbour, day}}}{\sum P_{\text{neighbour, period}}}$$
- Numerical reconciliation guarantees the sum of distributed shares matches the original total within $0.05\text{ mm}$.

### G5 — Fill from Neighbours (Manual §5.6)
- Evaluates long-term normal annual rainfall difference:
  - If normals differ by $\le 10\%$: Simple Average of $\ge 3$ neighbours.
  - If normals differ by $> 10\%$: Normal-Ratio Method:
    $$P_{\text{est}} = \frac{1}{N} \sum_{i=1}^N \left( P_i \times \frac{N_{\text{target}}}{N_i} \right)$$
  - Fallback: Inverse-Distance Weighting ($1/d^2$).

### G6 — Account for Extra Rainy Days (Manual §5.6.4)
- Marks filled estimates as `completed` and distinguishes observed vs. completed rainy days.

### G7 — Avoid Straight-Line Filling (Manual §2.2, §5.7.1)
- Rejects linear interpolation for daily rainfall gaps; enforces neighbour-based estimation.

### G8 — Correct Long-Term Shifts (Manual §5.5)
- Computes double-mass correction factor:
  $$\text{Correction Factor} = \frac{\text{Slope}_{\text{reference}}}{\text{Slope}_{\text{inconsistent}}}$$
- Scales the inhomogeneous portion of the record upon reviewer approval.

---

## 4. Statistical Analysis & Compilations (A1–A6)

### A1 — Standard Periods (Manual §6.2)
- **Daily:** $08:30\text{ to }08:30$ standard Indian Meteorological rainfall day.
- **Weekly:** 51 seven-day weeks, with Week 52 comprising 8 days (9 in leap years).
- **Dekad (Ten-Daily):** Days 1–10, 11–20, and 21 to end of month.
- **Monthly/Yearly:** Sums of daily observations subject to completeness rules.

### A2 — Tipping-Bucket Regularization (Manual §6.4)
- Regularizes timestamped bucket tips into fixed 60-minute intervals. Missing telemetry remains `NaN`.

### A3 — Completeness Rules (Manual §4.12.3)
- Enforces minimum $90\%$ valid days for monthly and yearly totals. Incomplete periods are explicitly flagged and never disguised as complete sums.

### A4 — Station Statistics (Manual §4.2, §7.3)
- Computes mean, median, standard deviation, skewness (accounting for positive rainfall skew), maximum daily rain, and rainy-day counts.

### A5 — Homogeneity & Consistency Tests (Manual §7.2)
- Conducts two-sample Student's t-test and Mann-Whitney U rank-sum test between historical periods to confirm stationarity prior to trend analysis.

### A6 — Data Quality Reporting (Manual §8.2.8)
- Generates data health summaries across stations and basins, tracking valid, doubtful, missing, corrected, and completed proportions.
