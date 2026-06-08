# Formula Extraction — Backend Reference

**Date:** 2026-06-01  
**Files added/changed:**

| File | Change |
|---|---|
| `app/formula_extractor.py` | New — AST-based formula registry |
| `app/excel_generator.py` | New — openpyxl Excel workbook builder |
| `app/routes/outputs.py` | Added two endpoints; added imports |
| `requirements-backend.txt` | Added `openpyxl>=3.1.0` |

---

## Overview

The formula extraction system makes the actuarial computation logic inside the ULP model **transparent and auditable**. Given any completed model run it produces:

1. A **JSON formula registry** — one entry per CSV output column — exposable directly to the UI.
2. An **Excel workbook** where cells that are pure linear combinations of other output columns carry live Excel formulas, so Excel's native *Trace Precedents* feature draws dependency arrows on click. All other cells carry a hover comment showing the actuarial formula and the AST-extracted Python source.

---

## Module: `app/formula_extractor.py`

### Purpose

Combines two sources of truth:

- **Static registry** — hand-authored, human-readable formulas and metadata for all 33 output columns.
- **AST extraction** — Python's `ast` module walks `ulp_model/forward_projection.py`, `ulp_model/part3_cashflows.py`, and `ulp_model/outputs.py` to find the assignment statement for each variable and stores its source snippet verbatim.

### Public API

```python
from app.formula_extractor import get_formula_registry, get_formula_map, get_formula_by_name

# Full list — 33 entries
registry = get_formula_registry()   # list[dict]

# Dict keyed by variable name
fm = get_formula_map()              # dict[str, dict]

# Single entry
entry = get_formula_by_name("pv_cf_after_scr")
```

### Formula Entry Shape

```python
{
    "name":          "cf_before_zv",           # CSV column name
    "display_name":  "Cashflow Before Zeroising",
    "formula":       "unit_res_bgn[t] + prem_inc_if[t] + ...",  # actuarial formula string
    "depends_on":    ["unit_res_bgn", "prem_inc_if", ...],       # other output column names
    "part":          "Part 3 Pass 1 — Cashflows",                # model stage
    "description":   "Net shareholder cashflow before ...",
    "python_source": "# forward_projection.py\ncf_before_zv = (\n    unit_res_bgn\n    + ..."  # AST snippet
}
```

### Formula Coverage

| Model Stage | Variables |
|---|---|
| Part 2 — Decrements | `no_pols_ifsm`, `no_deaths`, `no_surrs`, `no_mats`, `no_pols_if` |
| Part 3 Pass 1 — Cashflows | `basic_prem_if`, `topup_prem_if`, `prem_inc_if`, `op_init_exp_if`, `op_ren_exp_if`, `invt_exp_if`, `comm_if`, `ovrd_if`, `death_outgo`, `surr_outgo`, `mat_outgo`, `cog_term_adj`, `unit_res_bgn`, `unit_res_end`, `unit_inc`, `non_unit_inc`, `cf_before_zv` |
| Pass 2 — Backward (Zeroising) | `zeroising_res_if` |
| Pass 3 — Forward (Tax & SCR) | `cf_after_zv`, `op_tax`, `cf_after_tax`, `tot_res_if`, `solv_cap_req`, `scr_inv_inc`, `scr_inc_tax`, `cf_after_scr` |
| Pass 4 — Backward (PV) | `pv_cf_after_scr`, `pv_prem_inc` |

### AST Extraction Detail

`_enrich_with_ast()` walks each model file with `ast.parse()`, visiting every `ast.Assign` node. The target resolution handles three assignment patterns:

```python
# Pattern 1 — local variable
cf_before_zv = unit_res_bgn + prem_inc_if + ...

# Pattern 2 — instance attribute
self.cf_before_zv = value

# Pattern 3 — tensor slice (most common in the model)
self.cf_before_zv[:, t] = value
```

All 33 variables were successfully extracted from the source as of this session.

### Caching

The registry is built once on first call and cached in `_registry_cache`. Restart the backend to pick up any changes to the model source files.

---

## Module: `app/excel_generator.py`

### Purpose

Produces a styled `.xlsx` workbook from a `summary_scen*.csv` file. Requires `openpyxl>=3.1.0`.

### Public API

```python
from app.excel_generator import build_excel

xlsx_bytes: bytes = build_excel(csv_path, formula_map, selected_fields=["no_pols_if", "cf_after_tax"])
```

| Argument | Type | Description |
|---|---|---|
| `csv_path` | `Path \| str` | Path to the summary CSV |
| `formula_map` | `dict[str, dict]` | Output of `get_formula_map()` |
| `selected_fields` | `list[str] \| None` | If provided, only these columns (plus `t`) appear in the **Summary Data** sheet. `None` (default) includes all columns. |

Returns raw `.xlsx` bytes suitable for streaming as a `FileResponse` or writing directly to disk.

The **Formula Reference** and **Python Source** sheets are unaffected by `selected_fields` and always show all variables.

### Workbook Structure

#### Sheet 1 — "Summary Data"

- Row 1: frozen header row (deep-blue fill, white bold text). Display names from the formula registry are used as column headers.
- Rows 2+: one row per projection period `t`.
- Light-blue fill marks cells that contain live Excel formulas.
- Alternating light-grey fill on value-only rows.
- Every cell (including value-only) carries an Excel comment visible on hover with:
  - Variable name and model stage
  - Actuarial formula string
  - `depends_on` list
  - Description text
- Auto-filter enabled on header row.
- `freeze_panes = "B2"` — first column and header row are always visible.

#### Variables with Live Excel Formulas

These variables are written as actual Excel formulas so that *Trace Precedents* / *Trace Dependents* work natively:

| Variable | Excel Formula (row `r`) |
|---|---|
| `no_pols_ifsm` | `=MAX($B{r-1}-$F{r-1},0)` |
| `no_pols_if` | `=$C{r}-$D{r}-$E{r}-$F{r}` |
| `prem_inc_if` | `=$H{r}+$I{r}` |
| `cf_before_zv` | `=$S{r}+$G{r}+$U{r}+$V{r}-$J{r}-$K{r}-...-$T{r}` |
| `cf_after_tax` | `=$Y{r}-$Z{r}` |
| `tot_res_if` | `=$T{r}+$X{r}` |
| `cf_after_scr` | `=$AA{r}+$AC{r-1}-$AC{r}+$AD{r}-$AE{r}` |

All other variables (those requiring mortality/lapse/parameter table lookups or backward-pass logic) retain their raw numeric values but still carry formula comments.

#### Sheet 2 — "Formula Reference"

Colour-coded table (one row per variable) with columns:

| Column | Content |
|---|---|
| Variable | CSV column name |
| Display Name | Human-readable label |
| Stage | Model stage (Part 2, Pass 3, etc.) |
| Formula | Actuarial formula string |
| Depends On | Comma-separated list of other output variables |
| Description | Longer explanation |

Each model stage has its own row colour for quick visual grouping.

#### Sheet 3 — "Python Source (AST)"

One row per variable. The second column contains the verbatim Python source snippet extracted by the AST parser, rendered in `Courier New` 8pt.

### Output Size

A full 361-period projection (30 years monthly) produces approximately **920 KB** per scenario.

---

## API Endpoints

### `GET /api/v1/outputs/formulas`

Returns the complete formula registry as JSON. No run or scenario is required.

**Response:**
```json
{
  "formulas": [
    {
      "name": "no_pols_if",
      "display_name": "Policies In Force (End of Month)",
      "formula": "no_pols_ifsm[t] − no_deaths[t] − no_surrs[t] − no_mats[t]",
      "depends_on": ["no_pols_ifsm", "no_deaths", "no_surrs", "no_mats"],
      "part": "Part 2 — Decrements",
      "description": "Policies in force at end of month after all decrements.",
      "python_source": "# forward_projection.py\nself.no_pols_if[:, t] = no_pols_ifsm - no_deaths - no_surrs - no_mats"
    },
    ...
  ]
}
```

**Route registration note:** `/formulas` is registered *before* `/{run}` in the router so FastAPI does not accidentally treat `"formulas"` as a run name.

---

### `GET /api/v1/outputs/{run}/excel/{scenario_id}`

Generates and streams an Excel workbook for the requested run and scenario.

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `run` | `str` | Name of a directory inside `results/` (e.g. `test_1`) |
| `scenario_id` | `int` | Scenario number matching the `scen{N}` suffix in the CSV filename |

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `fields` | `str` (optional) | Comma-separated list of output variable names to include in the **Summary Data** sheet (e.g. `no_pols_if,cf_after_tax`). The `t` column is always included. Omit to include all columns. |

**Response:**
- `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition: attachment; filename="ulp_{run}_scen{scenario_id}_formulas.xlsx"`

**Errors:**

| Status | Condition |
|---|---|
| 404 | Run directory does not exist |
| 404 | No matching summary CSV found for the scenario |
| 400 | Path traversal attempt in `run` |
| 500 | `openpyxl` not installed or other generation error |

**Example curl — all columns:**
```bash
curl -O "http://localhost:8000/api/v1/outputs/test_1/excel/1"
```

**Example curl — selected columns only:**
```bash
curl -O "http://localhost:8000/api/v1/outputs/test_1/excel/1?fields=no_pols_if,cf_after_tax,pv_cf_after_scr"
```

---

## Route Order in `outputs.py`

```
GET /api/v1/outputs                          list_runs
GET /api/v1/outputs/formulas                 formula_registry        ← must precede /{run}
GET /api/v1/outputs/{run}                    describe_run
GET /api/v1/outputs/{run}/metrics            run_metrics
GET /api/v1/outputs/{run}/summary/{id}       summary_data
GET /api/v1/outputs/{run}/summary/{id}/variable/{var}  variable_series
GET /api/v1/outputs/{run}/download/{file}    download_file
GET /api/v1/outputs/{run}/excel/{id}         download_excel
```

---

## Dependencies

| Package | Version | Usage |
|---|---|---|
| `openpyxl` | `>=3.1.0` | Excel workbook creation — styles, comments, formulas |
| `ast` (stdlib) | — | Python source parsing for formula extraction |

Install with:
```bash
pip install -r requirements-backend.txt
```

---

## Automatic Excel generation on model run

`run_model.py` calls `build_excel` automatically after writing each summary CSV. The workbook is written to the same results directory alongside the CSV:

```
results/test_1/
  summary_scen1.csv              ← projection values (always written)
  summary_scen1_formulas.xlsx    ← formula workbook (written automatically)
  scenario_metrics_summary.csv
```

If `openpyxl` is not installed the workbook step is skipped with a `[WARNING]` message and the run completes normally.

---

## How to Test

```python
# Quick smoke test from project root
import sys
sys.path.insert(0, ".")
from pathlib import Path
from app.formula_extractor import get_formula_registry, get_formula_map
from app.excel_generator import build_excel

reg = get_formula_registry()
print(f"{len(reg)} entries, {sum(1 for e in reg if e['python_source'])} with AST source")

xlsx = build_excel("results/test_1/summary_scen1.csv", get_formula_map())
Path("test_output.xlsx").write_bytes(xlsx)
print(f"Generated {len(xlsx):,} bytes")
```
