# Developer Guide

## Repository Structure

```
UL/
├── app/          FastAPI backend — touch this to change API behaviour
├── client/       React frontend — touch this to change the UI
├── ulp_model/    Actuarial engine — touch this for computation changes
├── docs/         Documentation
└── api/          DEPRECATED — kept for reference only
```

## Backend: Adding a New Endpoint

1. Add a route function in the appropriate file under `app/routes/`.
2. Register the router in `app/main.py` if it is a new file.
3. Add the matching TypeScript type to `client/src/types/index.ts`.
4. Add the matching API call to `client/src/api/client.ts`.

Example — adding a new endpoint to `app/routes/model.py`:

```python
@router.get("/job-count", summary="Return total number of submitted jobs")
async def job_count() -> dict:
    return {"count": len(_store.job_store.list_ids())}
```

## Backend: Changing the Job Store

The current implementation (`app/services/job_store.py`) is a simple in-memory dict.

To replace it with Redis:

```python
import redis
r = redis.Redis()

class JobStore:
    def create(self, job_id: str) -> JobRecord: ...
    def mark_running(self, job_id: str, ...) -> None: ...
    # etc.
```

The interface (method signatures) is the contract — `model_service.py` and the routes only call the public methods.

## Backend: Changing the Model Execution

All model invocation logic is in `app/services/model_service._execute()`. This function:

1. Loads and patches `config.yaml`
2. Calls `ULPModel.run_portfolio()` (or `model.run()` for per-policy mode)
3. Writes CSVs and updates `job_store`

To add a new output type, extend `_enumerate_output_files()` and add a new `file_type` label.

## Frontend: Adding a Form Field

1. Add state in `RunForm.tsx` with `useState`.
2. Add the field to the form JSX.
3. Include the value in the `RunModelRequest` object before calling `api.runModel()`.
4. Add the field to `RunModelRequest` in `client/src/types/index.ts`.
5. Add the field to `RunModelRequest` in `app/schemas/model.py`.
6. Handle the override in `model_service._execute()`.

## Frontend: Extending the Results Panel

The `ResultsPanel` component receives a `JobResultResponse`. To show additional data:

1. Add it to `JobResultResponse` in `app/schemas/model.py`.
2. Populate it in `job_store.mark_completed()`.
3. Extend `ResultsPanel.tsx` to render the new field.

## Actuarial Engine: Making Changes

The engine lives in `ulp_model/`. It is imported directly by `model_service.py` at runtime — there is no subprocess boundary.

Changes to the engine take effect immediately on the next model run (no server restart needed if using `--reload`).

Key files for common changes:

| Change | File |
|--------|------|
| Add a new output variable | `ulp_model/outputs.py` |
| Change a formula | `ulp_model/forward_projection.py` or `part3_cashflows.py` |
| Add a new parameter table | `ulp_model/inputs.py` + `loader.py` |
| Add a new sensitivity factor | `ulp_model/sensitivity.py` |
| Change batch iteration | `ulp_model/loader.py` |

## Running Tests

```bash
# Model engine tests
pytest

# Backend smoke test (backend must be running)
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/run-model \
  -H "Content-Type: application/json" \
  -d '{"policy_file": "policy_data/test_policies_1.csv", "device": "cpu"}'
```

## Logging

Backend logs are in `logs/app.log`. To follow live:

```bash
# Linux/macOS
tail -f logs/app.log

# Windows PowerShell
Get-Content logs\app.log -Wait
```

Log level can be set in `.env`:
```
LOG_LEVEL=DEBUG
```

## Migration Notes (from api/ to app/)

The four separate FastAPI apps that previously ran on ports 8001–8004 have been consolidated into a single app on port 8000:

| Old (api/) | New (app/) | Port |
|------------|------------|------|
| `param_tables_api.py` | `app/routes/param_tables.py` | 8000 (prefix `/api/v1/param-tables`) |
| `policy_data_api.py` | `app/routes/policies.py` | 8000 (prefix `/api/v1/policies`) |
| `sen_fac_api.py` | `app/routes/sensitivity.py` | 8000 (prefix `/api/v1/scenarios`) |
| `outputs_api.py` | `app/routes/outputs.py` | 8000 (prefix `/api/v1/outputs`) |

The old files under `api/` are kept for reference but are no longer started. `api/run_all.py` is no longer used.

Model execution is now handled via `POST /api/v1/run-model` rather than spawning `run_model.py` as a subprocess.
