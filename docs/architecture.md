# Architecture Guide

## Overview

The ULP Actuarial Engine is split into three independent layers:

```
React Frontend  →  FastAPI Backend  →  ULP Model Engine
(client/)           (app/)              (ulp_model/)
```

Each layer can be developed, tested, and deployed independently.

---

## Frontend (client/)

**Technology:** React 18 + Vite 5 + TypeScript

**Responsibility:** User interface only. No business logic, no model execution, no terminal output.

### Key files

| File | Purpose |
|------|---------|
| `src/api/client.ts` | Axios wrapper — all HTTP calls go through here |
| `src/types/index.ts` | TypeScript types mirroring the backend schemas |
| `src/pages/Dashboard.tsx` | Main page state machine (idle → running → done) |
| `src/components/RunForm.tsx` | Configuration form; populates dropdowns from API |
| `src/components/JobStatus.tsx` | Polls `/api/v1/job-status/{id}` every 2 s |
| `src/components/ResultsPanel.tsx` | Displays metrics cards + download links |

### Communication flow

```
User clicks "Run Model"
  → POST /api/v1/run-model  { policy_file, scenario_file, output_mode, device, ... }
  ← { job_id: "abc-123", status: "pending" }

Poll every 2 s:
  → GET /api/v1/job-status/abc-123
  ← { status: "running", progress: "Running scenario 1/3" }
  ← { status: "completed", elapsed_seconds: 14.2 }

Fetch results once complete:
  → GET /api/v1/results/abc-123
  ← { scenarios: [...metrics...], output_files: [...] }

User clicks "Download":
  → GET /api/v1/results/abc-123/download/summary_scen001.csv
  ← (file download)
```

### Development proxy

`vite.config.ts` proxies `/api` and `/health` to `http://localhost:8000` so the frontend can be developed without CORS issues.

---

## Backend (app/)

**Technology:** FastAPI + uvicorn + Python threading

**Responsibility:** REST API gateway + job management + model orchestration.

### Request lifecycle

```
HTTP POST /api/v1/run-model
  → model.py: parse RunModelRequest
  → model_service.submit_job(job_id, request)
      → job_store.create(job_id)          # record created immediately
      → threading.Thread(_execute, ...)   # background thread started
  ← 202 { job_id, status: "pending" }    # response returned immediately

Background thread (_execute):
  → load config.yaml, apply request overrides
  → load_sensitivity_scenarios()
  → for each scenario:
      → load_param_tables()
      → apply_sensitivity_factors()
      → ULPModel(config).run_portfolio()
      → compute_metrics(), write_summary_outputs()
  → job_store.mark_completed(...)
```

### Job store

`app/services/job_store.py` maintains an in-memory dict protected by `threading.Lock`.

For multi-worker deployments, replace with Redis or a database-backed store.

### Logging

`app/core/logging.py` sets up:
- `StreamHandler` → stdout at INFO level
- `FileHandler` → `logs/app.log` at DEBUG level

All actuarial logs (batch progress, throughput) go here — nothing reaches the frontend.

### Configuration

`app/core/config.py` uses `pydantic-settings`. Settings are loaded from:
1. Environment variables
2. `.env` file (if present)
3. Default values in the `Settings` class

---

## Model Engine (ulp_model/)

**Technology:** PyTorch — fully vectorized, GPU-capable

**Responsibility:** Pure computation — no HTTP, no logging to stdout (from the engine itself), no file I/O except output CSVs.

### Execution pipeline

```
ULPModel.run_portfolio(retain_full_outputs=False)
  → PolicyBatchIterator  [yields PolicyBatch of size batch_size]
  → for each batch:
      → ForwardProjection.run()       Part 1 (PAV) + Part 2 (decrements) + Part 3 Pass 1
      → CashflowProjection.run()      Part 3 Passes 2–4 (zeroising, tax, PV)
      → accumulate summary [T] tensors
  → return { summary, ape, n_policies, elapsed }
```

### Memory modes

| Mode | Storage | Use case |
|------|---------|----------|
| Summary (`retain_full_outputs=False`) | Rolling buffers + [T] accumulators | Large portfolios, memory-efficient |
| Full (`retain_full_outputs=True`) | [B, T] tensors for all variables | Per-policy output mode (≤ 1 M policies) |

### Sensitivity factors

Applied to `ParamTables` in-place **before** model execution. This keeps all calculation formulas clean — they always read from `param_tables` without needing to know about the scenario.

---

## Data Flow

```
POST /api/v1/run-model
  ↓ JSON request body
app/routes/model.py (parse + validate)
  ↓ RunModelRequest
app/services/model_service._execute()  [background thread]
  ↓ config + param_tables + policies
ulp_model/model.py (ULPModel)
  ↓ ForwardProjection + CashflowProjection
  ↓ summary tensors [T]
ulp_model/outputs.py (write CSVs)
  ↓ results/{job_id}/summary_scen001.csv
app/services/job_store.mark_completed()
  ↓ job record updated
GET /api/v1/results/{job_id}
  ↓ JSON: metrics + file list + download URLs
GET /api/v1/results/{job_id}/download/summary_scen001.csv
  ↓ FileResponse (CSV download)
```

---

## API-First Design Principles

1. **No subprocess spawning from the API** — the model runs as a Python import
2. **No SSE / streaming** — all responses are complete JSON documents
3. **No logs forwarded to the client** — frontend never sees Python stdout/stderr
4. **Async-compatible** — long-running model jobs run in a `threading.Thread` so uvicorn's event loop handles other requests concurrently
5. **Idempotent result retrieval** — `GET /results/{id}` can be called any number of times

---

## Deployment

See [deployment.md](deployment.md) for production setup instructions.
