"""
FastAPI service for UL model outputs.

Reads files written by run_model.py under the configured output directory.
Supports multiple result runs (e.g. results/test_1, results/test_2).

Output file types:
  summary_scen{id}.csv          – portfolio-level time-series per scenario
  per_policy_scen{id}.csv       – per-policy per-timestep data per scenario
  scenario_metrics_summary.csv  – one-row-per-scenario metrics table
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"

app = FastAPI(
    title="UL Model Outputs API",
    description="REST API for Universal Life actuarial model output files",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_run(run: str) -> Path:
    """Return the path for a named run directory, raising 404 if missing."""
    path = RESULTS_ROOT / run
    if not path.exists() or not path.is_dir():
        available = [d.name for d in RESULTS_ROOT.iterdir() if d.is_dir()] if RESULTS_ROOT.exists() else []
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run}' not found under {RESULTS_ROOT}. Available: {available}",
        )
    return path


def _scenario_id_from_filename(fname: str) -> int:
    """Extract integer scenario ID from filenames like summary_scen001.csv."""
    m = re.search(r"scen(\d+)", fname)
    return int(m.group(1)) if m else -1


def _list_scenario_files(run_dir: Path, prefix: str) -> list[Path]:
    """Return sorted list of files matching prefix in a run directory."""
    return sorted(run_dir.glob(f"{prefix}_scen*.csv"))


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path.name}")
    return pd.read_csv(path)


def _paginate(df: pd.DataFrame, skip: int, limit: int) -> dict:
    total = len(df)
    rows = df.iloc[skip : skip + limit].to_dict(orient="records")
    return {"total": total, "skip": skip, "limit": limit, "data": rows}


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


@app.get("/", summary="API root")
def root():
    runs = [d.name for d in RESULTS_ROOT.iterdir() if d.is_dir()] if RESULTS_ROOT.exists() else []
    return {
        "message": "UL Model Outputs API",
        "results_root": str(RESULTS_ROOT),
        "available_runs": runs,
    }


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------


@app.get("/runs", summary="List all available result run directories")
def list_runs():
    if not RESULTS_ROOT.exists():
        return {"results_root": str(RESULTS_ROOT), "runs": [], "message": "Results directory does not exist yet."}
    runs = []
    for d in sorted(RESULTS_ROOT.iterdir()):
        if not d.is_dir():
            continue
        summary_files = list(_list_scenario_files(d, "summary"))
        per_policy_files = list(_list_scenario_files(d, "per_policy"))
        metrics_file = d / "scenario_metrics_summary.csv"
        runs.append({
            "run": d.name,
            "path": str(d),
            "summary_scenarios": [_scenario_id_from_filename(f.name) for f in summary_files],
            "per_policy_scenarios": [_scenario_id_from_filename(f.name) for f in per_policy_files],
            "has_metrics_summary": metrics_file.exists(),
        })
    return {"results_root": str(RESULTS_ROOT), "runs": runs}


@app.get("/runs/{run}", summary="Describe a specific run directory")
def describe_run(run: str):
    run_dir = _resolve_run(run)
    summary_files = _list_scenario_files(run_dir, "summary")
    per_policy_files = _list_scenario_files(run_dir, "per_policy")
    metrics_file = run_dir / "scenario_metrics_summary.csv"

    info: dict = {
        "run": run,
        "path": str(run_dir),
        "summary_files": [f.name for f in summary_files],
        "per_policy_files": [f.name for f in per_policy_files],
        "has_metrics_summary": metrics_file.exists(),
    }

    # Column preview from first summary file
    if summary_files:
        df = pd.read_csv(summary_files[0], nrows=0)
        info["summary_columns"] = list(df.columns)

    if per_policy_files:
        df = pd.read_csv(per_policy_files[0], nrows=0)
        info["per_policy_columns"] = list(df.columns)

    return info


# ---------------------------------------------------------------------------
# Scenario metrics summary
# ---------------------------------------------------------------------------


@app.get("/runs/{run}/metrics", summary="Get scenario_metrics_summary.csv for a run")
def get_metrics_summary(run: str):
    run_dir = _resolve_run(run)
    path = run_dir / "scenario_metrics_summary.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="scenario_metrics_summary.csv not found in this run.")
    df = _load_csv(path)
    return {"run": run, "scenario_count": len(df), "data": df.to_dict(orient="records")}


# ---------------------------------------------------------------------------
# Summary outputs  (portfolio-level time-series)
# ---------------------------------------------------------------------------


@app.get("/runs/{run}/summary", summary="List available summary scenario files")
def list_summary_scenarios(run: str):
    run_dir = _resolve_run(run)
    files = _list_scenario_files(run_dir, "summary")
    return {
        "run": run,
        "scenarios": [{"scenario_id": _scenario_id_from_filename(f.name), "file": f.name} for f in files],
    }


@app.get("/runs/{run}/summary/{scenario_id}", summary="Get summary output for a specific scenario")
def get_summary(
    run: str,
    scenario_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=50000),
    t_min: Optional[int] = Query(None, description="Minimum time step (month) to include"),
    t_max: Optional[int] = Query(None, description="Maximum time step (month) to include"),
    columns: Optional[str] = Query(None, description="Comma-separated column names to return (default: all)"),
):
    run_dir = _resolve_run(run)
    # Find matching file (pad scenario_id to any digit width)
    candidates = list(run_dir.glob(f"summary_scen*.csv"))
    match = next((f for f in candidates if _scenario_id_from_filename(f.name) == scenario_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Summary file for scenario {scenario_id} not found in run '{run}'.")

    df = _load_csv(match)

    if t_min is not None:
        df = df[df["t"] >= t_min]
    if t_max is not None:
        df = df[df["t"] <= t_max]
    if columns:
        cols = [c.strip() for c in columns.split(",") if c.strip() in df.columns]
        if not cols:
            raise HTTPException(status_code=400, detail="None of the requested columns exist.")
        if "t" not in cols:
            cols = ["t"] + cols
        df = df[cols]

    return _paginate(df, skip, limit)


@app.get("/runs/{run}/summary/{scenario_id}/columns", summary="Get column names of a summary file")
def get_summary_columns(run: str, scenario_id: int):
    run_dir = _resolve_run(run)
    candidates = list(run_dir.glob("summary_scen*.csv"))
    match = next((f for f in candidates if _scenario_id_from_filename(f.name) == scenario_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Summary file for scenario {scenario_id} not found.")
    df = pd.read_csv(match, nrows=0)
    return {"run": run, "scenario_id": scenario_id, "columns": list(df.columns)}


@app.get("/runs/{run}/summary/{scenario_id}/at/{t}", summary="Get summary output at a single time step t")
def get_summary_at_t(run: str, scenario_id: int, t: int):
    run_dir = _resolve_run(run)
    candidates = list(run_dir.glob("summary_scen*.csv"))
    match = next((f for f in candidates if _scenario_id_from_filename(f.name) == scenario_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Summary file for scenario {scenario_id} not found.")
    df = _load_csv(match)
    row = df[df["t"] == t]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Time step t={t} not found.")
    return {"run": run, "scenario_id": scenario_id, "t": t, "data": row.to_dict(orient="records")}


@app.get("/runs/{run}/summary/{scenario_id}/variable/{variable}", summary="Get a single variable time-series across all t")
def get_summary_variable(run: str, scenario_id: int, variable: str):
    run_dir = _resolve_run(run)
    candidates = list(run_dir.glob("summary_scen*.csv"))
    match = next((f for f in candidates if _scenario_id_from_filename(f.name) == scenario_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Summary file for scenario {scenario_id} not found.")
    df = _load_csv(match)
    if variable not in df.columns:
        raise HTTPException(status_code=404, detail=f"Variable '{variable}' not in file. Available: {list(df.columns)}")
    series = df[["t", variable]].to_dict(orient="records")
    return {"run": run, "scenario_id": scenario_id, "variable": variable, "data": series}


# ---------------------------------------------------------------------------
# Per-policy outputs
# ---------------------------------------------------------------------------


@app.get("/runs/{run}/per_policy", summary="List available per-policy scenario files")
def list_per_policy_scenarios(run: str):
    run_dir = _resolve_run(run)
    files = _list_scenario_files(run_dir, "per_policy")
    return {
        "run": run,
        "scenarios": [{"scenario_id": _scenario_id_from_filename(f.name), "file": f.name} for f in files],
    }


@app.get("/runs/{run}/per_policy/{scenario_id}", summary="Get per-policy output for a specific scenario")
def get_per_policy(
    run: str,
    scenario_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
    policy_id: Optional[int] = Query(None, description="Filter by a single policy ID"),
    t_min: Optional[int] = Query(None, description="Minimum time step"),
    t_max: Optional[int] = Query(None, description="Maximum time step"),
    columns: Optional[str] = Query(None, description="Comma-separated columns to return"),
):
    run_dir = _resolve_run(run)
    candidates = list(run_dir.glob("per_policy_scen*.csv"))
    match = next((f for f in candidates if _scenario_id_from_filename(f.name) == scenario_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Per-policy file for scenario {scenario_id} not found in run '{run}'.")

    df = _load_csv(match)

    if policy_id is not None:
        df = df[df["policy_id"] == policy_id]
    if t_min is not None:
        df = df[df["t"] >= t_min]
    if t_max is not None:
        df = df[df["t"] <= t_max]
    if columns:
        cols = [c.strip() for c in columns.split(",") if c.strip() in df.columns]
        if not cols:
            raise HTTPException(status_code=400, detail="None of the requested columns exist.")
        base = [c for c in ("policy_id", "t") if c not in cols]
        df = df[base + cols]

    return _paginate(df, skip, limit)


@app.get("/runs/{run}/per_policy/{scenario_id}/policy/{policy_id}", summary="Get all time steps for a single policy")
def get_policy_timeseries(run: str, scenario_id: int, policy_id: int):
    run_dir = _resolve_run(run)
    candidates = list(run_dir.glob("per_policy_scen*.csv"))
    match = next((f for f in candidates if _scenario_id_from_filename(f.name) == scenario_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Per-policy file for scenario {scenario_id} not found.")
    df = _load_csv(match)
    rows = df[df["policy_id"] == policy_id]
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found in scenario {scenario_id}.")
    return {"run": run, "scenario_id": scenario_id, "policy_id": policy_id, "data": rows.to_dict(orient="records")}


# ---------------------------------------------------------------------------
# Cross-scenario comparison
# ---------------------------------------------------------------------------


@app.get("/runs/{run}/compare/variable/{variable}", summary="Compare a summary variable across all scenarios")
def compare_variable_across_scenarios(run: str, variable: str):
    run_dir = _resolve_run(run)
    files = _list_scenario_files(run_dir, "summary")
    if not files:
        raise HTTPException(status_code=404, detail="No summary files found in this run.")

    result = {}
    for f in files:
        scen_id = _scenario_id_from_filename(f.name)
        df = pd.read_csv(f)
        if variable not in df.columns:
            continue
        result[scen_id] = df[["t", variable]].to_dict(orient="records")

    if not result:
        raise HTTPException(status_code=404, detail=f"Variable '{variable}' not found in any scenario file.")
    return {"run": run, "variable": variable, "scenarios": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("outputs_api:app", host="0.0.0.0", port=8004, reload=True)
