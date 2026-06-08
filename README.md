# ULP Actuarial Engine

GPU-accelerated Universal Life Policy (ULP) cashflow model with a production-grade FastAPI backend and React frontend.

For background and motivation, see [About this project](docs/about.md).

---

## Status

| Component | Status |
|-----------|--------|
| Part 1 — PAV Projection (81 steps) | ✅ Complete |
| Part 2 — Decrements (13 steps) | ✅ Complete |
| Part 3 — Shareholder Cashflows (4 passes) | ✅ Complete |
| FastAPI unified backend | ✅ Complete |
| React frontend | ✅ Complete |
| GPU / CUDA 12.1 support | ✅ Complete |
| Batch processing | ✅ Complete |
| Sensitivity / scenario analysis | ✅ Complete |
| Stochastic simulation | ⏳ Planned |

---

## Architecture

```
┌─────────────────────────────────────────┐
│           React Frontend                │
│  (client/  · Vite + TypeScript)         │
│  npm run dev  →  http://localhost:5173  │
└──────────────┬──────────────────────────┘
               │  HTTP REST  (JSON only — no SSE, no subprocess)
               ▼
┌─────────────────────────────────────────┐
│          FastAPI Backend                │
│  (app/  · Python + uvicorn)             │
│  python start_backend.py  →  :8000     │
│                                         │
│  POST /api/v1/run-model                 │
│  GET  /api/v1/job-status/{id}           │
│  GET  /api/v1/results/{id}              │
│  GET  /api/v1/results/{id}/download/…  │
│  GET  /api/v1/available-policies        │
│  GET  /api/v1/available-scenarios       │
│  GET  /api/v1/param-tables/…           │
│  GET  /api/v1/policies/…               │
│  GET  /api/v1/scenarios/…              │
│  GET  /api/v1/outputs/…                │
│  GET  /health                           │
└──────────────┬──────────────────────────┘
               │  Python imports (in-process, background thread)
               ▼
┌─────────────────────────────────────────┐
│        ULP Model Engine                 │
│  (ulp_model/  · PyTorch — UNCHANGED)    │
│                                         │
│  ForwardProjection  (Parts 1 + 2 + 3p1)│
│  CashflowProjection (Part 3 passes 2–4)│
│  Batch iterator · GPU/CPU               │
└─────────────────────────────────────────┘
```

**Key design principles:**
- Frontend communicates **only** via HTTP REST — no subprocess spawning, no SSE
- Backend runs the model in a **background thread** — FastAPI event loop stays responsive
- **Logs stay server-side** — no terminal output forwarded to the UI
- The actuarial engine (`ulp_model/`) is **completely unchanged**

---

## Quick Start

### Backend

```bash
# CPU (default)
pip install -r requirements-backend.txt
python start_backend.py

# GPU (CUDA 12.1)
pip install -r requirements-gpu.txt
pip install fastapi "uvicorn[standard]" pydantic-settings
python start_backend.py
```

Backend: **http://localhost:8000**  
Swagger UI: **http://localhost:8000/docs**

### Frontend

```bash
cd client
npm install
npm run dev
```

Frontend: **http://localhost:5173**

---

## Performance Benchmarks (GPU)

| Platform | Policies | Time |
|----------|----------|------|
| NVIDIA GTX 1060 6 GB | 1 M | ~8 s |
| NVIDIA RTX 3080 10 GB | 5 M | ~12 s |
| NVIDIA A100 80 GB | 10 M | < 2 min |

---

## Project Layout

```
UL/
├── app/                         ← FastAPI unified backend
│   ├── main.py                  ← App factory, CORS, router registration
│   ├── core/
│   │   ├── config.py            ← pydantic-settings (env vars / .env)
│   │   └── logging.py           ← Centralised logging
│   ├── schemas/
│   │   ├── model.py             ← Request/response Pydantic models
│   │   └── responses.py         ← Shared response types
│   ├── services/
│   │   ├── job_store.py         ← In-memory job status tracker
│   │   └── model_service.py     ← Background-thread model runner
│   └── routes/
│       ├── health.py            ← GET /health
│       ├── model.py             ← POST /run-model, job status, results
│       ├── param_tables.py      ← Parameter table browse
│       ├── policies.py          ← Policy dataset browse
│       ├── sensitivity.py       ← Scenario file browse
│       └── outputs.py           ← Results directory browse
│
├── client/                      ← React + Vite + TypeScript frontend
│   ├── package.json
│   ├── vite.config.ts           ← Dev proxy: /api → localhost:8000
│   └── src/
│       ├── App.tsx
│       ├── index.css
│       ├── api/client.ts        ← Axios wrapper for all API calls
│       ├── types/index.ts       ← TypeScript types
│       ├── components/
│       │   ├── RunForm.tsx      ← Configuration form
│       │   ├── JobStatus.tsx    ← Polling status panel
│       │   ├── ResultsPanel.tsx ← Metrics cards + download links
│       │   └── LoadingSpinner.tsx
│       └── pages/Dashboard.tsx  ← Main page
│
├── ulp_model/                   ← Actuarial engine (UNCHANGED)
│   ├── config.py
│   ├── inputs.py
│   ├── loader.py
│   ├── model.py
│   ├── forward_projection.py
│   ├── part3_cashflows.py
│   ├── sensitivity.py
│   ├── outputs.py
│   └── utils.py
│
├── api/                         ← DEPRECATED — superseded by app/
│   ├── param_tables_api.py      ← Was port 8001
│   ├── policy_data_api.py       ← Was port 8002
│   ├── sen_fac_api.py           ← Was port 8003
│   ├── outputs_api.py           ← Was port 8004
│   └── run_all.py               ← Was multi-process launcher
│
├── param_tables/                ← 17 CSV tables + scalar_inputs.yaml
├── policy_data/                 ← Test datasets (1 to 5 M policies)
├── sen_fac/                     ← Sensitivity scenario CSVs
├── results/                     ← Model outputs (created at runtime)
├── docs/                        ← Documentation
│
├── start_backend.py             ← Backend entry point
├── run_model.py                 ← CLI entry point (still supported)
├── config.yaml                  ← Model defaults
├── requirements.txt             ← Core model dependencies
├── requirements-backend.txt     ← Full backend (model + web)
├── requirements-gpu.txt         ← GPU variant
└── .env.example                 ← Environment variable reference
```

---

## Configuration

`config.yaml` holds model defaults. The API accepts per-request overrides.

| Key | Default | Description |
|-----|---------|-------------|
| `max_proj_years` | 90 | Projection horizon (years) |
| `float_precision` | float64 | `float64` or `float32` |
| `compute_device` | cpu | `cpu` or `cuda` |
| `batch_size` | 70000 | Policies per GPU batch |
| `output_batch_size` | 1000 | Flush size for per-policy mode |
| `policy_inputs_file` | ./policy_data/test_policies_5m.parquet | Default policy file |
| `param_tables_dir` | ./param_tables/ | Parameter table directory |
| `scenario_file` | ./sen_fac/base_scen.csv | Default scenario file |
| `output_dir` | ./results/test_1 | Base output directory |
| `output_mode` | summary | `summary`, `per_policy`, or `both` |
| `output_time_steps` | all | `all` or list of month indices |

Environment variables in `.env` override server settings — see `.env.example`.

---

## API Endpoints

Full interactive docs at **http://localhost:8000/docs**.

### Model Execution

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/run-model` | Submit a model job |
| `GET` | `/api/v1/job-status/{id}` | Poll job status |
| `GET` | `/api/v1/results/{id}` | Result metadata + file list |
| `GET` | `/api/v1/results/{id}/download/{file}` | Download output CSV |
| `GET` | `/api/v1/jobs` | List all job IDs |
| `GET` | `/api/v1/available-policies` | List policy dataset files |
| `GET` | `/api/v1/available-scenarios` | List scenario files |

### Data Browsing

| Prefix | Description |
|--------|-------------|
| `/api/v1/param-tables/` | 17 parameter tables + scalar inputs |
| `/api/v1/policies/` | Policy dataset browse |
| `/api/v1/scenarios/` | Scenario file browse |
| `/api/v1/outputs/` | Results directory browse |

---

## Example: Run a model via curl

```bash
# 1. Submit job
curl -X POST http://localhost:8000/api/v1/run-model \
  -H "Content-Type: application/json" \
  -d '{
    "policy_file": "policy_data/test_policies_20.csv",
    "output_mode": "summary",
    "device": "cpu"
  }'
# → {"job_id": "abc-123-...", "status": "pending"}

# 2. Poll until complete
curl http://localhost:8000/api/v1/job-status/abc-123-...

# 3. Fetch result metadata
curl http://localhost:8000/api/v1/results/abc-123-...

# 4. Download output CSV
curl -O http://localhost:8000/api/v1/results/abc-123-.../download/summary_scen001.csv
```

---

## CLI (still supported)

```bash
python run_model.py --config config.yaml --device cpu --mode summary
python run_model.py --device cuda --batch-size 100000 --scenario-id 1
```

---

## Input Specification

### Policy columns

| Column | Type | Description |
|--------|------|-------------|
| `policy_id` | int | Unique identifier |
| `age_at_entry` | int | Issue age |
| `sex` | str | `male` / `female` |
| `pol_term` | int | Policy term (years) |
| `prem_term` | int | Premium paying term |
| `prem_freq` | int | 1/3/6/12 |
| `sum_assd` | float | Sum assured |
| `db_opt` | int | 1=basic, 2=escalating |
| `acp` | float | Annual contractual premium |
| `atp` | float | Annual top-up premium |
| `topup_term` | int | Top-up term |
| `topup_freq` | int | Top-up frequency |
| `mort_loading` | float | Mortality loading (%) |
| `init_pols_if` | float | Initial in-force count |

### Sensitivity factors (16 total)

Multiplicative (base = 100): `op_exp_sen`, `ie_pp_sen`, `re_pp_sen`, `comm_sen`, `ovrd_sen`, `mort_sen`, `lapse_sen`

Additive (base = 0): `ie_pc_sen`, `re_pc_sen`, `inf_sen`, `fme_sen`, `fmc_sen`, `ulp_fer_sen`, `sh_fer_sen`, `rdr_sen`, `vir_sen`

---

## Output Modes

| Mode | Files produced |
|------|---------------|
| `summary` | `summary_scen{N}.csv` — portfolio-level time series |
| `per_policy` | `per_policy_scen{N}.csv` — per-policy time series (≤ 1 M policies) |
| `both` | Both of the above |

All runs also produce `scenario_metrics_summary.csv`.

---

## Logging

All logs stay in the backend (`logs/app.log` and stdout). Nothing is forwarded to the frontend.

Set `LOG_LEVEL=DEBUG` in `.env` to increase verbosity.

---

## Module Reference

| Module | Purpose |
|--------|---------|
| `ulp_model/config.py` | YAML config loader |
| `ulp_model/inputs.py` | `PolicyBatch` + `ParamTables` dataclasses |
| `ulp_model/loader.py` | CSV/Parquet I/O + `PolicyBatchIterator` |
| `ulp_model/model.py` | `ULPModel` orchestrator |
| `ulp_model/forward_projection.py` | Parts 1, 2, 3-Pass-1 forward loop |
| `ulp_model/part3_cashflows.py` | Part 3 Passes 2–4 |
| `ulp_model/sensitivity.py` | Factor loading + application |
| `ulp_model/outputs.py` | APE, metrics, CSV writers |
| `ulp_model/utils.py` | Age/year helpers, rate lookups |
