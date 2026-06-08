"""
Model output browse routes — migrated from api/outputs_api.py.
Mounted at /api/v1/outputs.

These endpoints allow browsing pre-existing results directories, independent
of the job system (useful for results generated via the CLI run_model.py).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from app.core.config import settings
from app.formula_extractor import get_formula_map, get_formula_registry

router = APIRouter(prefix="/api/v1/outputs", tags=["Model Outputs"])

_BASE = Path(settings.base_dir)
_RESULTS_DIR = _BASE / "results"

_SCEN_RE = re.compile(r"scen(\d+)", re.IGNORECASE)


def _resolve_run(run: str) -> Path:
    path = (_RESULTS_DIR / run).resolve()
    if not str(path).startswith(str(_RESULTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid run name")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Run '{run}' not found")
    return path


def _scen_id(filename: str) -> Optional[int]:
    m = _SCEN_RE.search(filename)
    return int(m.group(1)) if m else None


def _load_csv(path: Path) -> List[Dict[str, Any]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _paginate(data: list, skip: int, limit: int) -> dict:
    return {"total": len(data), "skip": skip, "limit": limit, "data": data[skip : skip + limit]}


@router.get("", summary="List all result run directories")
async def list_runs() -> dict:
    if not _RESULTS_DIR.exists():
        return {"runs": []}
    runs = []
    for d in sorted(_RESULTS_DIR.iterdir()):
        if d.is_dir():
            files = [f.name for f in d.iterdir() if f.is_file()]
            runs.append({"run": d.name, "files": files})
    return {"runs": runs}


@router.get("/formulas", summary="Return the ULP formula registry as JSON")
async def formula_registry() -> dict:
    """
    Return the full formula registry — one entry per output column — including
    the human-readable formula string, dependencies, model stage, description,
    and the AST-extracted Python source snippet.
    """
    return {"formulas": get_formula_registry()}


@router.get("/{run}", summary="Describe a result run")
async def describe_run(run: str) -> dict:
    path = _resolve_run(run)
    files: List[dict] = []
    for f in sorted(path.iterdir()):
        if not f.is_file():
            continue
        ftype = "per_policy" if "per_policy" in f.stem else (
            "metrics" if "metrics_summary" in f.stem else "summary"
        )
        files.append({
            "filename": f.name,
            "type": ftype,
            "scenario_id": _scen_id(f.stem),
            "size_bytes": f.stat().st_size,
        })
    return {"run": run, "files": files}


@router.get("/{run}/metrics", summary="Get scenario metrics summary for a run")
async def run_metrics(run: str) -> dict:
    path = _resolve_run(run) / "scenario_metrics_summary.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="scenario_metrics_summary.csv not found")
    return {"run": run, "data": _load_csv(path)}


@router.get("/{run}/summary/{scenario_id}", summary="Get summary data for a scenario")
async def summary_data(
    run: str,
    scenario_id: int,
    t_min: Optional[int] = Query(None, ge=0),
    t_max: Optional[int] = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=50000),
) -> dict:
    run_path = _resolve_run(run)
    candidates = [
        f for f in run_path.iterdir()
        if f.is_file() and "summary" in f.stem and _scen_id(f.stem) == scenario_id
        and "per_policy" not in f.stem
    ]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"No summary file for scenario {scenario_id}")
    rows = _load_csv(candidates[0])
    if t_min is not None:
        rows = [r for r in rows if int(r.get("t", -1)) >= t_min]
    if t_max is not None:
        rows = [r for r in rows if int(r.get("t", -1)) <= t_max]
    return _paginate(rows, skip, limit)


@router.get("/{run}/summary/{scenario_id}/variable/{variable}", summary="Single variable time-series")
async def variable_series(run: str, scenario_id: int, variable: str) -> dict:
    run_path = _resolve_run(run)
    candidates = [
        f for f in run_path.iterdir()
        if f.is_file() and "summary" in f.stem and _scen_id(f.stem) == scenario_id
        and "per_policy" not in f.stem
    ]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"No summary file for scenario {scenario_id}")
    rows = _load_csv(candidates[0])
    if rows and variable not in rows[0]:
        raise HTTPException(status_code=404, detail=f"Variable '{variable}' not found")
    return {
        "variable": variable,
        "scenario_id": scenario_id,
        "data": [{"t": r.get("t"), "value": r.get(variable)} for r in rows],
    }


@router.get("/{run}/download/{filename}", summary="Download an output file from a run")
async def download_file(run: str, filename: str) -> FileResponse:
    run_path = _resolve_run(run)
    target = (run_path / filename).resolve()
    if not str(target).startswith(str(run_path.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    return FileResponse(path=str(target), filename=filename, media_type="text/csv")


@router.get(
    "/{run}/excel/{scenario_id}",
    summary="Download summary output as Excel (.xlsx) with embedded formulas",
)
async def download_excel(
    run: str,
    scenario_id: int,
    fields: Optional[str] = Query(None, description="Comma-separated list of output variable names to include"),
) -> Response:
    """
    Generate and stream an Excel workbook for the requested run / scenario.

    The workbook contains three sheets:
      • Summary Data     — projection values; cells with simple linear
                           dependencies carry live Excel formulas so that
                           Excel's "Trace Precedents" arrows work natively;
                           every cell has a hover comment with the actuarial
                           formula.
      • Formula Reference — human-readable formula dictionary.
      • Python Source (AST) — actual Python code extracted from the model.
    """
    try:
        from app.excel_generator import build_excel
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    run_path = _resolve_run(run)
    candidates = [
        f for f in run_path.iterdir()
        if f.is_file() and "summary" in f.stem and _scen_id(f.stem) == scenario_id
        and "per_policy" not in f.stem
    ]
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"No summary file for scenario {scenario_id} in run '{run}'",
        )

    csv_path = candidates[0]
    formula_map = get_formula_map()
    selected_fields = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

    try:
        xlsx_bytes = build_excel(csv_path, formula_map, selected_fields)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    filename = f"ulp_{run}_scen{scenario_id}_formulas.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
