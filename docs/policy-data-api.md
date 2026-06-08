# Policy Data API

**Date:** 2026-06-01  
**File changed:** `server/routes.ts` (in `Updated-FIA-Validation-Tool-UI`)  
**Base path:** `/api/policy-data`

---

## Overview

Four REST endpoints were added to the FIA Validation Tool's Express server to manage the UL model's `policy_data` directory. They allow the frontend Data View page to list, download, upload, replace, and delete policy data files without touching the file system directly.

---

## Directory Configuration

```ts
const POLICY_DATA_DIR =
  process.env.POLICY_DATA_DIR ?? path.join(PRODUCTS_DIR, "UL", "policy_data");
```

- **Default:** `C:\projects\UL\policy_data`  
- **Override:** Set the `POLICY_DATA_DIR` environment variable to point elsewhere.  
- `PRODUCTS_DIR` itself defaults to the parent of the app's working directory (`C:\projects`), overridable via `PRODUCTS_DIR`.

---

## Security

All endpoints run the requested filename through the shared `isSafeFilename()` helper before constructing a file path:

```ts
function isSafeFilename(name: string): boolean {
  return !(/[/\\]/.test(name)) && !/\.\./.test(name) && name.length > 0;
}
```

This rejects path traversal patterns (`../`, `..\`, absolute paths containing slashes or backslashes).

---

## Endpoints

### `GET /api/policy-data`

Returns a sorted list of all files in `POLICY_DATA_DIR`.

**Response**
```json
{
  "files": [
    { "name": "test_policies_1.csv",      "size": 2148,   "modified": "2026-05-30T14:00:00.000Z" },
    { "name": "test_policies_20.csv",     "size": 4512,   "modified": "2026-05-30T14:00:00.000Z" },
    { "name": "test_policies_10000.csv",  "size": 1048576,"modified": "2026-05-30T14:00:00.000Z" },
    { "name": "test_policies_50000.csv",  "size": 5242880,"modified": "2026-05-30T14:00:00.000Z" },
    { "name": "test_policies_200000.csv", "size": 20971520,"modified": "2026-05-30T14:00:00.000Z" },
    { "name": "5m.parquet",              "size": 52428800,"modified": "2026-05-30T14:00:00.000Z" }
  ]
}
```

- Files are alphabetically sorted by name.
- Returns `{ "files": [] }` if the directory does not exist (no 500 error).

---

### `GET /api/policy-data/:filename`

Streams a file from `POLICY_DATA_DIR` as a download attachment.

**URL parameter:** `filename` — must pass `isSafeFilename` validation.

**Response:** Binary file stream with `Content-Disposition: attachment` header.

**Error responses**

| Status | Condition |
|---|---|
| 400 | Filename fails safety check |
| 404 | File does not exist in `POLICY_DATA_DIR` |

---

### `POST /api/policy-data/upload/:filename`

Uploads a new file or replaces an existing one. The body is the raw file bytes — no JSON envelope, no base64 encoding.

**URL parameter:** `filename` — the name under which the file will be stored in `POLICY_DATA_DIR`.

**Request**
```
Content-Type: application/octet-stream
Body: <raw file bytes>
```

The route applies `express.raw({ type: "*/*", limit: "500mb" })` as inline middleware so it does not interfere with the global `express.json()` parser applied to other routes.

**Response**
```json
{ "success": true, "filename": "test_policies_20.csv", "size": 4512 }
```

**Notes**
- If `POLICY_DATA_DIR` does not exist it is created recursively before writing.
- Existing files are silently overwritten — used by the UI's "Replace" action.
- The 500 MB limit covers even the largest expected policy datasets.

**Error responses**

| Status | Condition |
|---|---|
| 400 | Filename fails safety check |
| 500 | Filesystem write error |

---

### `DELETE /api/policy-data/:filename`

Permanently removes a file from `POLICY_DATA_DIR`.

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

## Upload Transport — Why Raw Bytes

The assumptions API (`POST /api/assumptions/files`) sends file content as a UTF-8 JSON string, which works for small text files. Policy data files can reach several hundred MB (e.g., `5m.parquet` is a binary format). Sending those as JSON strings would:

- Require base64 encoding, inflating size by ~33 %.
- Force the entire file into memory before transmission.

The raw-bytes approach streams directly from the browser `File` object to disk and requires no extra dependencies beyond what Express already provides (`express.raw`).

---

## policy_data File Inventory (as of 2026-06-01)

| File | Format | Approx. rows | Notes |
|---|---|---|---|
| `test_policies_1.csv` | CSV | 1 | Minimal smoke-test dataset |
| `test_policies_20.csv` | CSV | 20 | Small functional test |
| `test_policies_10000.csv` | CSV | 10 000 | Mid-size regression dataset |
| `test_policies_50000.csv` | CSV | 50 000 | Performance baseline |
| `test_policies_200000.csv` | CSV | 200 000 | Large-scale test |
| `5m.parquet` | Parquet | ~5 000 000 | Full portfolio; binary format |

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `POLICY_DATA_DIR` | `<PRODUCTS_DIR>/UL/policy_data` | Override the policy data location |
| `PRODUCTS_DIR` | Parent of app working directory | Root of all product folders |

---

## Relationship to Other APIs

| API | Base path | Directory |
|---|---|---|
| Policy Data *(this doc)* | `/api/policy-data` | `C:\projects\UL\policy_data` |
| Assumption Tables | `/api/assumptions/files` | `C:\projects\UL\param_tables` |
| Model Outputs | `/api/outputs` | `C:\projects\UL\results` |

---

## Adding a New Endpoint

To add further file operations (e.g., rename, validate schema):

1. Add the route handler inside `registerRoutes` in `server/routes.ts`, after the existing policy-data routes.
2. Always validate the filename with `isSafeFilename()` before constructing a path with `path.join(POLICY_DATA_DIR, filename)`.
3. Document the new endpoint in this file.
