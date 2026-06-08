"""
Sensitivity factor routes — migrated from api/sen_fac_api.py.
Mounted at /api/v1/scenarios.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings

router = APIRouter(prefix="/api/v1/scenarios", tags=["Sensitivity Scenarios"])

_BASE = Path(settings.base_dir)
_SEN_DIR = _BASE / "sen_fac"

SCENARIO_FILES: Dict[str, str] = {
    "base": "base_scen.csv",
    "scenarios": "scenarios.csv",
    "scenarios_2": "scenarios_2.csv",
    "scenarios_3": "scenarios_3.csv",
}


def _load_scenario_file(key: str) -> List[Dict[str, Any]]:
    if key not in SCENARIO_FILES:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario file '{key}' not found. Available: {list(SCENARIO_FILES)}",
        )
    path = _SEN_DIR / SCENARIO_FILES[key]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {SCENARIO_FILES[key]}")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _scen_id_col(row: dict) -> Optional[int]:
    for col in ("Scen ID", "Scenario ID", "scen_id", "scenario_id"):
        if col in row:
            try:
                return int(row[col])
            except (ValueError, TypeError):
                pass
    return None


@router.get("", summary="List available scenario files")
async def list_scenario_files() -> dict:
    available = []
    for key, filename in SCENARIO_FILES.items():
        path = _SEN_DIR / filename
        available.append({"key": key, "filename": filename, "exists": path.exists()})
    return {"scenario_files": available}


@router.get("/{file_key}", summary="Get all rows from a scenario file")
async def get_scenarios(
    file_key: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    rows = _load_scenario_file(file_key)
    total = len(rows)
    return {"total": total, "skip": skip, "limit": limit, "data": rows[skip : skip + limit]}


@router.get("/{file_key}/scenario/{scen_id}", summary="Get a single scenario by ID")
async def get_scenario(file_key: str, scen_id: int) -> dict:
    rows = _load_scenario_file(file_key)
    match = [r for r in rows if _scen_id_col(r) == scen_id]
    if not match:
        raise HTTPException(status_code=404, detail=f"Scenario {scen_id} not found")
    return match[0]


@router.get("/{file_key}/factor/{factor_name}", summary="Get a factor across all scenarios")
async def factor_time_series(file_key: str, factor_name: str) -> dict:
    rows = _load_scenario_file(file_key)
    if rows and factor_name not in rows[0]:
        raise HTTPException(status_code=404, detail=f"Factor '{factor_name}' not in this file")
    series = [
        {"scenario_id": _scen_id_col(r), "value": r.get(factor_name)}
        for r in rows
    ]
    return {"factor": factor_name, "file": file_key, "data": series}
