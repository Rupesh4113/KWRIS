"""Interactive Validation Rules and NHP Manual Documentation Page."""

from __future__ import annotations
import streamlit as st


def render_documentation_page():
    st.markdown("## 📖 Validation Rules & Hydrological Documentation")
    st.markdown(
        "Governing reference: **Manual on Rainfall Data Validation (National Hydrology Project, "
        "Ministry of Water Resources, River Development and Ganga Rejuvenation, Government of India, May 2019)**."
    )
    
    st.markdown("### 🏛️ Five Foundational Hydrological Principles")
    st.markdown(
        """
        | Principle | Operational Rule in KWRIS Platform |
        |---|---|
        | **1. Flag, do not delete** | Keep every original value intact. Mark suspects as `doubtful` and record reason. Change only when clearly wrong and traceable, marking as `corrected`. |
        | **2. A test screens; it does not decide** | No single check proves a value wrong. A flag means *'look again'*. Field metadata and neighbouring gauges confirm or clear it. |
        | **3. Extremes can be real** | Genuine extreme rainfall is the most critical information for dam safety and flood design. Do not auto-reject high values without neighbour cross-checks. |
        | **4. Zero is not missing** | 0.0 mm means no rain fell. Missing means no measurement exists. They are distinct types and must never be converted into one another. |
        | **5. Measured beats estimated** | Measured observations are always more reliable than filled estimates. Label filled gaps as `completed` with clear method attribution. |
        """
    )
    
    st.divider()
    
    tab_p, tab_s, tab_g, tab_a = st.tabs([
        "🔍 Primary Validation (P1–P5)",
        "🌐 Secondary Validation (S1–S8)",
        "🛠️ Gap Filling & Correction (G1–G8)",
        "📊 Statistical Analysis (A1–A6)"
    ])
    
    with tab_p:
        st.markdown("### Primary Validation: Single Station Screening")
        st.markdown(
            """
            - **P1 — Entry Check (Manual §3.1, §4.2):** Catches non-numeric entries, repeated dates, and missing codes such as `-99`. Distinguishes valid zero rainfall from missing data.
            - **P2 — Minimum Limit (Manual §3.4):** Flags physically impossible negative values (`< 0.0 mm`).
            - **P3 — Maximum Limit (Manual §3.4):** Flags readings exceeding station-specific daily Probable Maximum Precipitation (PMP) ceiling or 50-year maximum.
            - **P4 — Upper Warning Level (Manual §3.5):** Computes monthly warning levels: $\\text{Warning} = \\text{Mean} + 1.96 \\times \\text{Std}$ or 98th percentile. Flags unusual readings without auto-rejection.
            - **P5 — Two Gauges at One Station (Manual §3.3):** Compares manual gauge daily reading with 08:30–08:30 aggregated automatic gauge readings. Ignores differences $< 5\\%$. Diagnoses calibration drift, heavy rain double-counting, and time misalignment.
            """
        )
        
    with tab_s:
        st.markdown("### Secondary Validation: Spatial Neighbour Screening")
        st.markdown(
            """
            - **S1 — Pick Neighbours (Manual §4.6):** Selects up to 8 stations within search radius ($\le 35$ km), with at most 2 per quadrant (NE, SE, SW, NW).
            - **S2 — Neighbour Estimate Test (Manual §4.6):** Estimates station rainfall using Inverse-Distance-Squared ($1/d^2$) weighting. Flags differences $> 45$ mm or $> 2 \\times \\sigma_{\\text{neighbours}}$. Adds direction: `+` for higher, `-` for lower.
            - **S3 — Entries on Wrong Day (Manual §4.4, §4.8):** Identifies 1-day observation date shifts using opposite-direction anomaly pairs at the start and end of rainy spells. Confirms by testing shifted correlation.
            - **S4 — Accumulated Totals (Manual §4.9):** Detects consecutive zero readings with `-` flags while neighbours had rain, followed by a large `+` spike (common after weekends/holidays).
            - **S5 — Missed Entries (Manual §4.10):** Detects runs of zero readings during rain with no subsequent accumulated spike (readings were skipped, not measured as zero).
            - **S6 — Rainy Days Check (Manual §4.11):** Counts days with rainfall $\ge 0.1$ mm per month/year and flags stations with significantly fewer rainy days ($< 50\\%$ of neighbour average).
            - **S7 — Monthly & Yearly Totals (Manual §4.5):** Flags annual totals outside $\\text{Mean} - 1.645\\sigma$ or $\\text{Mean} + 1.96\\sigma$. Regional high/low clears isolated anomaly flags.
            - **S8 — Double-Mass Homogeneity (Manual §4.12):** Plots station cumulative rainfall vs mean cumulative rainfall of $\ge 3$ reliable neighbours. Bends lasting $\ge 5$ years indicate gauge relocation, tree growth, or instrument faults.
            """
        )
        
    with tab_g:
        st.markdown("### Gap Filling and Traceable Correction Rules")
        st.markdown(
            """
            - **G1 — Keep Missing as Missing (Manual §5.1):** Never fill gaps with zero. Leave values as missing (`NaN`) when no reliable neighbouring data exist.
            - **G2 — Station's Second Gauge (Manual §5.2):** Fills missing manual daily reading from automatic gauge daily total. Fills hourly automatic values by distributing manual total according to neighbour hourly pattern.
            - **G3 — Fix Wrong Day Entries (Manual §5.3):** Realigns date-shifted records by confirmed shift offset and fills the opened space.
            - **G4 — Split Accumulated Totals (Manual §5.4):** Distributes accumulated total proportionally across days based on neighbour daily estimates:
              $$\\text{Daily Share} = \\text{Total} \\times \\frac{\\text{Est}_{\\text{day}}}{\\sum \\text{Est}}$$
            - **G5 — Fill from Neighbours (Manual §5.6):** When station normals differ by $\le 10\\%$, uses Simple Average ($\ge 3$ neighbours). When normals differ by $> 10\\%$, uses Normal-Ratio method:
              $$\\text{Est} = \\frac{1}{N} \\sum_{i=1}^N \\left(P_i \\times \\frac{\\text{Normal}_{\\text{target}}}{\\text{Normal}_i}\\right)$$
            - **G6 — Account for Extra Rainy Days (Manual §5.6.4):** Distinguishes observed vs estimated rainy days to prevent artificial inflation of rainy day counts.
            - **G7 — Avoid Straight-Line Filling (Manual §2.2, §5.7.1):** Disallows linear interpolation for daily rainfall gaps.
            - **G8 — Correct Long-Term Shifts (Manual §5.5):** Adjusts inhomogeneous periods using double-mass slope ratio:
              $$\\text{Correction Factor} = \\frac{\\text{Slope}_{\\text{reference}}}{\\text{Slope}_{\\text{inconsistent}}}$$
            """
        )
        
    with tab_a:
        st.markdown("### Statistical Analysis and Hydrological Conventions")
        st.markdown(
            """
            - **A1 — Standard Periods (Manual §6.2):** 08:30 to 08:30 daily rainfall day; 51 seven-day weeks + 52nd week of 8 (or 9 leap) days; ten-daily dekads (1-10, 11-20, 21-end).
            - **A2 — Tipping Bucket Regularization (Manual §6.4):** Converts tip records to fixed intervals.
            - **A3 — Completeness Rules (Manual §4.12.3):** Requires at least $90\\%$ valid days for monthly and yearly totals. Incomplete totals are never presented as complete.
            - **A4 — Station Statistics (Manual §4.2, §7.3):** Computes mean, median, standard deviation, skewness (rainfall is positively skewed), max daily rainfall, and rainy days.
            - **A5 — Consistency Before Trends (Manual §7.2):** Validates homogeneity using double-mass curves and two-sample statistical tests (Mann-Whitney U, Student's t-test) before trend analysis.
            - **A6 — Data Quality Reporting (Manual §8.2.8):** Comprehensive reporting of valid, missing, doubtful, corrected, and completed proportions across all stations.
            """
        )
