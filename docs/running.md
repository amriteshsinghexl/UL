# Running the Project

Two processes run independently — start both to use the full application.

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- (Optional) NVIDIA GPU with CUDA 12.1 for GPU acceleration

---

## Step 1 — Install Backend Dependencies

Open a terminal in the project root (`C:\projects\UL\`):

```powershell
pip install -r requirements-backend.txt
```

For GPU support instead:

```powershell
pip install -r requirements-gpu.txt
pip install fastapi "uvicorn[standard]" pydantic-settings
```

---

## Step 2 — Start the Backend

From the project root (`C:\projects\UL\`):

```powershell
python start_backend.py
```

The backend starts at **http://localhost:8000**

| URL | Description |
|-----|-------------|
| http://localhost:8000/health | Health check |
| http://localhost:8000/docs | Swagger UI (interactive API docs) |
| http://localhost:8000/redoc | ReDoc API reference |

> Keep this terminal open.

---

## Step 3 — Install Frontend Dependencies

Open a **second** terminal in `C:\projects\UL\client\`:

```powershell
npm install
```

---

## Step 4 — Start the Frontend

```powershell
npm run dev
```

The frontend starts at **http://localhost:5173**

> Keep this terminal open.

---

## Step 5 — Open the App

Navigate to **http://localhost:5173** in your browser.

You will see the ULP dashboard with:
- **Configure Run** form — select policy file, scenario, output mode, device
- **Job Status** panel — appears when a job is submitted (polls every 2 seconds)
- **Results** panel — appears when the job completes, with metrics cards and download buttons

---

## Verify Both Services Are Running

```powershell
# Backend health check
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"2.0.0","base_dir":"C:\\projects\\UL"}
```

Frontend proxy routes all `/api` requests to the backend automatically — no extra configuration needed.

---

## Quick Smoke Test (Command Line)

```powershell
# 1. Submit a fast job (1-policy dataset, CPU)
curl -X POST http://localhost:8000/api/v1/run-model `
  -H "Content-Type: application/json" `
  -d '{"policy_file": "policy_data/test_policies_1.csv", "device": "cpu"}'

# Returns: {"job_id": "<uuid>", "status": "pending"}

# 2. Poll status (replace <job_id> with the returned value)
curl http://localhost:8000/api/v1/job-status/<job_id>

# 3. Fetch results once status is "completed"
curl http://localhost:8000/api/v1/results/<job_id>

# 4. Download output CSV
curl -O http://localhost:8000/api/v1/results/<job_id>/download/summary_scen001.csv
```

---

## Optional — Backend Flags

```powershell
# Custom port
python start_backend.py --port 9000

# Auto-reload on code changes (development)
python start_backend.py --reload

# Multiple workers (production — use only without background GPU jobs)
python start_backend.py --workers 4
```

---

## Optional — CLI (no frontend required)

The original command-line interface still works independently:

```powershell
python run_model.py --config config.yaml --device cpu --mode summary
python run_model.py --device cuda --batch-size 100000 --scenario-id 1
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: pydantic_settings` | `pip install pydantic-settings` |
| `ModuleNotFoundError: fastapi` | `pip install -r requirements-backend.txt` |
| `npm: command not found` | Install Node.js from https://nodejs.org |
| Frontend shows "Failed to submit job" | Confirm the backend is running on port 8000 |
| `CUDA not available` | Use `"device": "cpu"` or install CUDA 12.1 PyTorch |
| Port 8000 already in use | `python start_backend.py --port 9000` then update `client/vite.config.ts` target |
