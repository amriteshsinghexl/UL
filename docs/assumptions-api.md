# Assumption Parameter Tables API

**Date:** 2026-06-01  
**File changed:** `server/routes.ts` (in `Updated-FIA-Validation-Tool-UI`)  
**Base path:** `/api/assumptions/files`

---

## Overview

Four REST endpoints were added to the FIA Validation Tool's Express server to manage the UL model's `param_tables` directory. They allow the frontend to list, read, upload, and delete actuarial parameter table files without touching the file system directly.

---

## Directory Configuration

```ts
const PARAM_TABLES_DIR =
  process.env.PARAM_TABLES_DIR ?? path.join(PRODUCTS_DIR, "UL", "param_tables");
```

- **Default:** `C:\projects\UL\param_tables`  
- **Override:** Set the `PARAM_TABLES_DIR` environment variable to point elsewhere.  
- `PRODUCTS_DIR` itself defaults to the parent of the app's working directory (`C:\projects`), overridable via `PRODUCTS_DIR`.

---

## Security

All endpoints run the requested filename through `isSafeFilename()` before constructing a file path:

```ts
function isSafeFilename(name: string): boolean {
  return !(/[/\\]/.test(name)) && !/\.\./.test(name) && name.length > 0;
}
```

This rejects path traversal patterns (`../`, `..\`, absolute paths containing slashes).

---

## Endpoints

### `GET /api/assumptions/files`

Returns a sorted list of all files in `PARAM_TABLES_DIR`.

**Response**
```json
{
  "files": [
    { "name": "admin_chg_tbl.csv",  "size": 1024, "modified": "2025-01-15T10:30:00.000Z" },
    { "name": "coi_tbl.csv",        "size": 4096, "modified": "2025-03-20T08:00:00.000Z" },
    { "name": "scalar_inputs.yaml", "size": 512,  "modified": "2025-02-01T12:00:00.000Z" }
  ]
}
```

- Files are alphabetically sorted by name.
- Returns `{ "files": [] }` if the directory does not exist (no 500 error).

---

### `GET /api/assumptions/files/:filename`

Reads and returns the content of a single file.

**URL parameter:** `filename` — must pass `isSafeFilename` validation.

**Response — CSV files (`.csv`)**
```json
{
  "filename": "coi_tbl.csv",
  "type": "csv",
  "headers": ["age", "rate_male", "rate_female"],
  "rows": [
    ["25", "0.00120", "0.00085"],
    ["26", "0.00130", "0.00090"]
  ]
}
```

**Response — all other files (`.yaml`, `.yml`, `.txt`, etc.)**
```json
{
  "filename": "scalar_inputs.yaml",
  "type": "text",
  "content": "discount_rate: 0.045\nexpense_ratio: 0.012\n..."
}
```

**Error responses**

| Status | Condition |
|---|---|
| 400 | Filename fails safety check |
| 404 | File does not exist in `PARAM_TABLES_DIR` |
| 500 | Filesystem read error |

---

### `POST /api/assumptions/files`

Creates a new file or overwrites an existing one.

**Request body** (`Content-Type: application/json`)
```json
{
  "filename": "lapse_tbl.csv",
  "content": "age,base_lapse,dynamic_lapse\n25,0.05,0.03\n26,0.04,0.03\n"
}
```

- `filename`: target filename inside `PARAM_TABLES_DIR`.
- `content`: full file content as a UTF-8 string.

**Response**
```json
{ "success": true, "filename": "lapse_tbl.csv" }
```

**Notes**
- If `PARAM_TABLES_DIR` does not exist it is created recursively before writing.
- Existing files are silently overwritten (used by the UI's "Replace" action).

**Error responses**

| Status | Condition |
|---|---|
| 400 | Missing `filename` or `content`; or filename fails safety check |
| 500 | Filesystem write error |

---

### `DELETE /api/assumptions/files/:filename`

Permanently deletes a file from `PARAM_TABLES_DIR`.

**URL parameter:** `filename` — must pass `isSafeFilename` validation.

**Response**
```json
{ "success": true }
```

**Error responses**

| Status | Condition |
|---|---|
| 400 | Filename fails safety check |
| 404 | File does not exist |
| 500 | Filesystem delete error |

---

## CSV Parser

A lightweight inline parser is used (no external dependency):

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

**Limitations**
- Does not handle multi-line quoted fields.
- Does not handle commas inside quoted values.
- Suitable for the flat numeric tables in `param_tables`; if a file uses complex quoting, consider switching to a library such as `csv-parse`.

---

## param_tables File Inventory (as of 2026-06-01)

| File | Type | Description |
|---|---|---|
| `admin_chg_tbl.csv` | CSV | Administrative charge rates |
| `alloc_chg_tbl.csv` | CSV | Allocation charge rates |
| `basic_lb_rate_tbl.csv` | CSV | Basic living benefit rates |
| `coi_tbl.csv` | CSV | Cost of insurance rates |
| `comm_tbl.csv` | CSV | Commission table |
| `hard_g_inv_tbl.csv` | CSV | Guaranteed investment rates |
| `lapse_tbl.csv` | CSV | Base lapse rates |
| `lien_tbl.csv` | CSV | Lien rates |
| `mortality_select_female.csv` | CSV | Select mortality — female |
| `mortality_select_male.csv` | CSV | Select mortality — male |
| `op_exp_tbl.csv` | CSV | Operating expense table |
| `ovrd_tbl.csv` | CSV | Override table |
| `reg_param_tbl.csv` | CSV | Regulatory parameters |
| `sb_acp_rate_tbl.csv` | CSV | Surrender benefit ACP rates |
| `sb_coi_rate_tbl.csv` | CSV | Surrender benefit COI rates |
| `scalar_inputs.yaml` | YAML | Scalar model inputs (non-tabular) |
| `surr_chg_tbl.csv` | CSV | Surrender charge table |
| `topup_lb_rate_tbl.csv` | CSV | Top-up living benefit rates |

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `PARAM_TABLES_DIR` | `<PRODUCTS_DIR>/UL/param_tables` | Override the param tables location |
| `PRODUCTS_DIR` | Parent of app working directory | Root of all product folders |

---

## Adding a New Endpoint

To add further file operations (e.g., rename, diff):

1. Add the route handler inside the `registerRoutes` function in `server/routes.ts`, after the existing assumption routes.
2. Always validate the filename with `isSafeFilename()` before constructing a path with `path.join(PARAM_TABLES_DIR, filename)`.
3. Document the new endpoint in this file.
