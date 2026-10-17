# KWRIS Platform Deployment Guide

## 1. Local Setup and Execution

### Prerequisites
- Python 3.10 or 3.11 installed.
- (Recommended) `uv` package manager, or standard `pip` / `venv`.

### Step 1: Clone Repository
```bash
git clone https://github.com/Rupesh4113/KWRIS.git
cd KWRIS
```

### Step 2: Create Virtual Environment & Install Dependencies
Using standard `pip`:
```bash
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Or using `uv` (faster):
```bash
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

### Step 3: Run Automated Tests
```bash
pytest -v
```
All 23 automated unit and integration tests must pass.

### Step 4: Launch the Streamlit Application
```bash
streamlit run streamlit_app.py
```
Open your browser at `http://localhost:8501`.

---

## 2. Streamlit Community Cloud Deployment

Follow these steps to deploy directly from GitHub:

1. **Push Changes to GitHub:**
   Ensure all files are committed and pushed to your GitHub repository:
   ```bash
   git add .
   git commit -m "feat: complete KWRIS rainfall quality validation platform"
   git push origin main
   ```

2. **Connect to Streamlit Cloud:**
   - Navigate to [share.streamlit.io](https://share.streamlit.io).
   - Sign in with your GitHub account.
   - Click **"New app"**.

3. **Configure Repository Settings:**
   - **Repository:** `Rupesh4113/KWRIS`
   - **Branch:** `main` (or `master`)
   - **Main file path:** `streamlit_app.py`
   - **App URL:** (Optional custom subdomain, e.g., `kwris-rainfall-quality.streamlit.app`)

4. **Advanced Settings (Optional):**
   - Python Version: Select **3.11**.
   - Secrets: Not required for standard operation. If needed, refer to `.streamlit/secrets.toml.example`.

5. **Deploy:**
   - Click **"Deploy!"**.
   - Streamlit Cloud will automatically install dependencies from `requirements.txt` and launch the application.

---

## 3. Configuration & Tuning

Configuration settings are located in `config/validation_rules.yaml`:
- **P3 Daily Ceiling:** Default $350.0\text{ mm}$ (tunable via UI or YAML).
- **P4 Warning Multiplier:** Default $1.96$ ($95\%$ / $98\%$ confidence limit).
- **S1 Search Radius:** Default $35.0\text{ km}$, max 2 stations per quadrant.
- **S2 Discrepancy Threshold:** Default $45.0\text{ mm}$ or $2\times\sigma_{\text{neighbours}}$.
- **Theme Settings:** `.streamlit/config.toml` sets the Karnataka Government deep red (`#8B0000`) branding and responsive layout.

---

## 4. Troubleshooting

| Issue | Root Cause | Solution |
|---|---|---|
| Large file upload error ($>200\text{ MB}$) | Streamlit max upload limit exceeded. | Increased to $200\text{ MB}$ in `.streamlit/config.toml`. For larger archives, split by basin or year. |
| Incomplete spatial tests | Coordinates missing for uploaded custom stations. | Ensure latitude and longitude columns are provided or station names match Karnataka catalog in `src/reference_data.py`. |
| Memory usage on 30-year dataset | High memory footprint when plotting entire multi-station time series. | Use the Station and Date filters in the **Visual Analytics** page to focus on specific periods. |
