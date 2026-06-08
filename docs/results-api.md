# Results API & Output File Reference

**Date:** 2026-06-01  
**File changed:** `server/routes.ts` (in `Updated-FIA-Validation-Tool-UI`)  
**Endpoint:** `GET /api/results/financial-summary`  
**Results directory:** `C:\projects\UL\results\test_1`

---

## Overview

The FIA Validation Tool's Express server exposes a read-only endpoint that parses and serves the UL model's projection output files. This allows the **Financial Summary** page in the UI to display scenario KPIs and per-period cashflow data without any direct filesystem access from the browser.

---

## Results Directory Structure

```
C:\projects\UL\results\
└── test_1\
    ├── scenario_metrics_summary.csv   # High-level KPIs (one row per scenario)
    └── summary_scen1.csv              # Full per-period projection output (Scenario 1)
```

The directory is fixed at `test_1` for the current integration. See [Environment Variables](#environment-variables) to override.

---

## Directory Configuration

```ts
// server/routes.ts
const RESULTS_DIR =
  process.env.RESULTS_DIR ?? path.join(PRODUCTS_DIR, "UL", "results", "test_1");
```

- **Default:** `C:\projects\UL\results\test_1`
- **Override:** Set `RESULTS_DIR` to point to a different run's output folder.
- `PRODUCTS_DIR` itself defaults to the parent of the app's working directory (`C:\projects`), overridable via `PRODUCTS_DIR`.

---

## Endpoint

### `GET /api/results/financial-summary`

Returns parsed CSV data from both output files in a single JSON response.

**Response** `200 OK`:

```json
{
  "metrics": {
    "headers": ["Scenario ID", "Elapsed (s)", "Output File", "APE (in mil)", "PV CF (in mil)", "PV CF / APE", "PV CF / PV Prem"],
    "rows": [
      ["1", "1089.63", "summary_scen1.csv", "26996165.50", "-17772084.69", "-0.6583", "-0.1522"]
    ]
  },
  "summary": {
    "headers": ["t", "no_pols_if", "no_pols_ifsm", "no_deaths", "no_surrs", ...],
    "rows": [
      ["0", "500000.000000", "0.000000", ...],
      ["1", "490787.886786", "500000.000000", ...],
      ...
    ]
  }
}
```

- If a file does not exist, its key is omitted from the response (no error).
- Both files are parsed with the shared `parseCSV()` helper (handles CRLF/LF, quoted fields, leading/trailing whitespace).

**Error response:**

| Status | Condition |
|---|---|
| 500 | Filesystem read error (permissions, corrupt file, etc.) |

---

## Output File Reference

### `scenario_metrics_summary.csv`

One header row + one data row per scenario run.

| Column | Unit | Description |
|---|---|---|
| `Scenario ID` | integer | Scenario number (matches `--scenario-id` CLI argument) |
| `Elapsed (s)` | seconds | Wall-clock time for the scenario run |
| `Output File` | filename | Name of the detailed output CSV for this scenario |
| `APE (in mil)` | millions | Annual Premium Equivalent — total annualised new business premium |
| `PV CF (in mil)` | millions | Present Value of cashflows after SCR |
| `PV CF / APE` | ratio | PV CF divided by APE |
| `PV CF / PV Prem` | ratio | PV CF divided by PV of premium income |

**Sample row:**

```
1, 1089.63, summary_scen1.csv, 26996165.50, -17772084.69, -0.6583, -0.1522
```

---

### `summary_scen1.csv`

Per-period cashflow output for Scenario 1. Each row is one projection period (`t`).  
All monetary values are in **raw model units** (divide by 1,000,000 to convert to millions).

#### Policyholder Counts

| Column | Description |
|---|---|
| `t` | Projection period index (0 = start of projection) |
| `no_pols_if` | Number of policies in force (end of period) |
| `no_pols_ifsm` | Number of policies in force (start of period, smoothed) |
| `no_deaths` | Deaths during the period |
| `no_surrs` | Surrenders during the period |
| `no_mats` | Maturities during the period |

#### Premium Income

| Column | Description |
|---|---|
| `prem_inc_if` | Total premium income from in-force policies |
| `basic_prem_if` | Basic (regular) premium component |
| `topup_prem_if` | Top-up (single / additional) premium component |

#### Expenses & Commissions

| Column | Description |
|---|---|
| `op_init_exp_if` | Initial (acquisition) expenses |
| `op_ren_exp_if` | Renewal (maintenance) expenses |
| `invt_exp_if` | Investment management expenses |
| `comm_if` | Commission payable |
| `ovrd_if` | Override commission |

#### Benefit Outgos

| Column | Description |
|---|---|
| `death_outgo` | Death benefit payments |
| `surr_outgo` | Surrender benefit payments |
| `mat_outgo` | Maturity benefit payments |
| `cog_term_adj` | Cost of guarantee termination adjustment |

#### Unit Reserve

| Column | Description |
|---|---|
| `unit_res_bgn` | Unit reserve at beginning of period |
| `unit_res_end` | Unit reserve at end of period |
| `unit_inc` | Change in unit reserve (income to non-unit fund) |

#### Non-Unit Cashflows

| Column | Description |
|---|---|
| `non_unit_inc` | Non-unit fund income |
| `cf_before_zv` | Cashflow before zeroising valuation |
| `zeroising_res_if` | Zeroising reserve (floor adjustment) |
| `cf_after_zv` | Cashflow after zeroising valuation |
| `op_tax` | Operating tax |
| `cf_after_tax` | Post-tax cashflow |

#### Reserves & Solvency

| Column | Description |
|---|---|
| `tot_res_if` | Total reserve (unit + non-unit) |
| `solv_cap_req` | Solvency Capital Requirement (SCR) |
| `scr_inv_inc` | Investment income on SCR |
| `scr_inc_tax` | Income tax on SCR investment income |
| `cf_after_scr` | Cashflow after SCR |

#### Present Values (computed at t=0)

| Column | Description |
|---|---|
| `pv_cf_after_scr` | Present value of cashflow after SCR |
| `pv_prem_inc` | Present value of premium income |

---

## `parseCSV()` Helper

Both files are parsed by the shared helper already present in `server/routes.ts`:

```ts
function parseCSV(content: string): { headers: string[]; rows: string[][] } {
  const lines = content.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim().split("\n");
  if (lines.length === 0) return { headers: [], rows: [] };
  const splitLine = (line: string) =>
    line.split(",").map((cell) => cell.trim().replace(/^"(.*)"$/, "$1"));
  return {
    headers: splitLine(lines[0]),
    rows: lines.slice(1).filter(Boolean).map(splitLine),
  };
}
```

- Normalises Windows (`\r\n`) and Unix (`\n`) line endings.
- Strips surrounding double-quotes from quoted fields.
- Trims leading/trailing whitespace from each cell.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RESULTS_DIR` | `<PRODUCTS_DIR>/UL/results/test_1` | Path to the results folder to serve |
| `PRODUCTS_DIR` | Parent of app working directory | Root of all product folders |

---

## Relationship to Other APIs

| API | Base path | Directory |
|---|---|---|
| Results *(this doc)* | `/api/results/financial-summary` | `C:\projects\UL\results\test_1` |
| Policy Data | `/api/policy-data` | `C:\projects\UL\policy_data` |
| Assumption Tables | `/api/assumptions/files` | `C:\projects\UL\param_tables` |

---

## UI Consumer

The endpoint is consumed exclusively by the Financial Summary view in the FIA Validation Tool UI.  
Full frontend documentation: `C:\projects\Updated-FIA-Validation-Tool-UI\docs\financial-summary-view.md`

---

## Adding Results for a New Run

When the UL model produces a new run (e.g., `test_2`):

1. Create the output folder and copy or symlink the CSV files:
   ```
   C:\projects\UL\results\test_2\scenario_metrics_summary.csv
   C:\projects\UL\results\test_2\summary_scen2.csv
   ```
2. Set `RESULTS_DIR=C:\projects\UL\results\test_2` in the FIA Validation Tool's environment before starting the server, or restart with the updated `.env`.
3. No code changes are required — the endpoint reads whatever files are present in `RESULTS_DIR`.
