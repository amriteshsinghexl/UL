# API Reference

All endpoints are served by a single FastAPI application on **port 8000**.

Interactive Swagger UI: **http://localhost:8000/docs**  
ReDoc: **http://localhost:8000/redoc**

---

## Authentication

No authentication is required for local development. Add an API key middleware or OAuth2 for production deployments.

---

## Model Execution

### POST `/api/v1/run-model`

Submit an actuarial model run. Returns a job ID immediately; the model runs in the background.

**Request body** (`application/json`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `policy_file` | string | config.yaml value | Path to policy CSV or Parquet (relative to project root) |
| `scenario_file` | string | config.yaml value | Path to scenario CSV |
| `output_dir` | string | config.yaml value | Base directory for output files |
| `output_mode` | `"summary"` \| `"per_policy"` \| `"both"` | `"summary"` | Output file type |
| `device` | `"cpu"` \| `"cuda"` | `"cpu"` | Compute device |
| `batch_size` | integer | config.yaml value | Policies per batch |
| `scenario_id` | integer | _(all)_ | Run a single scenario only |

**Response** `202 Accepted`:
```json
{ "job_id": "3fa85f64-...", "status": "pending" }
```

---

### GET `/api/v1/job-status/{job_id}`

Poll the status of a submitted job.

**Response** `200`:
```json
{
  "job_id": "3fa85f64-...",
  "status": "running",
  "created_at": "2025-05-26T10:00:00Z",
  "started_at": "2025-05-26T10:00:01Z",
  "completed_at": null,
  "elapsed_seconds": null,
  "progress": "Running scenario 1/3",
  "error": null
}
```

`status` values: `pending` → `running` → `completed` | `failed`

---

### GET `/api/v1/results/{job_id}`

Retrieve result metadata for a completed job. Returns 409 if the job has not finished.

**Response** `200`:
```json
{
  "job_id": "3fa85f64-...",
  "status": "completed",
  "output_dir": "/projects/UL/results/3fa85f64-...",
  "total_elapsed_seconds": 14.2,
  "n_policies": 200,
  "scenarios": [
    {
      "scenario_id": 1,
      "ape": 1234567.89,
      "pv_cf": 987654.32,
      "pv_prem": 2345678.0,
      "pvcf_over_ape": 0.7998,
      "pvcf_over_pv_prem": 0.4211,
      "elapsed_seconds": 13.9
    }
  ],
  "output_files": [
    {
      "filename": "summary_scen001.csv",
      "file_type": "summary",
      "scenario_id": 1,
      "size_bytes": 45678,
      "download_url": "/api/v1/results/3fa85f64-.../download/summary_scen001.csv"
    },
    {
      "filename": "scenario_metrics_summary.csv",
      "file_type": "metrics",
      "scenario_id": null,
      "size_bytes": 234,
      "download_url": "/api/v1/results/3fa85f64-.../download/scenario_metrics_summary.csv"
    }
  ]
}
```

---

### GET `/api/v1/results/{job_id}/download/{filename}`

Download an output file. Returns the CSV as a file attachment.

---

### GET `/api/v1/jobs`

List all known job IDs.

```json
{ "job_ids": ["3fa85f64-...", "7b8c9d0e-..."] }
```

---

## Discovery

### GET `/api/v1/available-policies`

List policy dataset files in `policy_data/`.

```json
{
  "files": [
    { "key": "test_policies_1.csv", "path": "policy_data/test_policies_1.csv", "size_bytes": 512 },
    { "key": "test_policies_5m.parquet", "path": "policy_data/test_policies_5m.parquet", "size_bytes": 52428800 }
  ]
}
```

### GET `/api/v1/available-scenarios`

List scenario files in `sen_fac/`.

---

## Parameter Tables (`/api/v1/param-tables`)

### GET `/api/v1/param-tables`
List all 17 table names.

### GET `/api/v1/param-tables/{table_name}`
Get rows from a table. Query params: `skip`, `limit` (max 10,000).

### GET `/api/v1/param-tables/{table_name}/columns`
Get column names and row count without loading data.

### GET `/api/v1/param-tables/scalar-inputs`
Return `scalar_inputs.yaml` as JSON.

### GET `/api/v1/param-tables/coi/lookup?age=45&sex=male`
Look up COI rate by age and sex.

### GET `/api/v1/param-tables/lapse/lookup?pol_year=5`
Look up lapse rates by policy year.

### GET `/api/v1/param-tables/mortality/lookup?sex=male&age=30`
Look up mortality rates.

---

## Policy Data (`/api/v1/policies`)

### GET `/api/v1/policies`
List available datasets (keys: `1`, `20`, `200`, `1000`, `10000`, `50000`, `200000`, `5m`).

### GET `/api/v1/policies/{size}`
Get policy rows with optional filters:

| Query param | Description |
|-------------|-------------|
| `sex` | Filter by `male` / `female` |
| `age_min`, `age_max` | Filter by entry age |
| `db_opt` | Filter by death benefit option (1 or 2) |
| `prem_freq` | Filter by premium frequency |
| `sum_assd_min`, `sum_assd_max` | Filter by sum assured |
| `skip`, `limit` | Pagination (max 10,000) |

### GET `/api/v1/policies/{size}/summary`
Descriptive statistics for a dataset.

### GET `/api/v1/policies/{size}/policy/{policy_id}`
Single policy record by ID.

### GET `/api/v1/policies/{size}/sex-distribution`
Count policies by sex.

### GET `/api/v1/policies/{size}/age-distribution?band=5`
Count policies by age band.

---

## Scenarios (`/api/v1/scenarios`)

### GET `/api/v1/scenarios`
List scenario files (keys: `base`, `scenarios`, `scenarios_2`, `scenarios_3`).

### GET `/api/v1/scenarios/{file_key}`
All rows from a scenario file. Query: `skip`, `limit`.

### GET `/api/v1/scenarios/{file_key}/scenario/{scen_id}`
Single scenario by ID.

### GET `/api/v1/scenarios/{file_key}/factor/{factor_name}`
Time-series of a single factor across all scenarios.

---

## Outputs Browse (`/api/v1/outputs`)

These endpoints browse pre-existing `results/` directories (useful for CLI-generated outputs).

### GET `/api/v1/outputs`
List all result run directories.

### GET `/api/v1/outputs/{run}`
Describe a run directory (file list with types and sizes).

### GET `/api/v1/outputs/{run}/metrics`
`scenario_metrics_summary.csv` as JSON.

### GET `/api/v1/outputs/{run}/summary/{scenario_id}`
Summary time-series for a scenario. Query: `t_min`, `t_max`, `skip`, `limit`.

### GET `/api/v1/outputs/{run}/summary/{scenario_id}/variable/{variable}`
Single variable time-series.

### GET `/api/v1/outputs/{run}/download/{filename}`
Download a file from a run directory.

---

## Health

### GET `/health`

```json
{ "status": "ok", "version": "2.0.0", "base_dir": "C:\\projects\\UL" }
```

---

## Common Response Shapes

### Paginated list
```json
{ "total": 1000, "skip": 0, "limit": 100, "data": [...] }
```

### Error
```json
{ "detail": "Job '3fa85f64-...' not found" }
```
