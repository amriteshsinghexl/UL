"""
Parameter tables routes — migrated from api/param_tables_api.py.
Mounted at /api/v1/param-tables.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings

router = APIRouter(prefix="/api/v1/param-tables", tags=["Parameter Tables"])

_BASE = Path(settings.base_dir)
_PARAM_DIR = _BASE / "param_tables"

TABLES: Dict[str, str] = {
    "admin_chg": "admin_chg_tbl.csv",
    "alloc_chg": "alloc_chg_tbl.csv",
    "surr_chg": "surr_chg_tbl.csv",
    "coi": "coi_tbl.csv",
    "hard_g_inv": "hard_g_inv_tbl.csv",
    "lien": "lien_tbl.csv",
    "op_exp": "op_exp_tbl.csv",
    "comm": "comm_tbl.csv",
    "ovrd": "ovrd_tbl.csv",
    "lapse": "lapse_tbl.csv",
    "mortality_select_male": "mortality_select_male.csv",
    "mortality_select_female": "mortality_select_female.csv",
    "basic_lb_rate": "basic_lb_rate_tbl.csv",
    "topup_lb_rate": "topup_lb_rate_tbl.csv",
    "sb_coi_rate": "sb_coi_rate_tbl.csv",
    "sb_acp_rate": "sb_acp_rate_tbl.csv",
    "reg_param": "reg_param_tbl.csv",
}


def _load_csv(name: str) -> List[Dict[str, Any]]:
    if name not in TABLES:
        raise HTTPException(status_code=404, detail=f"Table '{name}' not found")
    path = _PARAM_DIR / TABLES[name]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {TABLES[name]}")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _paginate(data: list, skip: int, limit: int) -> dict:
    return {
        "total": len(data),
        "skip": skip,
        "limit": limit,
        "data": data[skip : skip + limit],
    }


@router.get("", summary="List all available parameter table names")
async def list_tables() -> dict:
    return {"tables": list(TABLES.keys())}


@router.get("/scalar-inputs", summary="Get scalar model assumptions (scalar_inputs.yaml)")
async def scalar_inputs() -> dict:
    path = _PARAM_DIR / "scalar_inputs.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="scalar_inputs.yaml not found")
    with open(path) as f:
        return yaml.safe_load(f)


@router.get("/{table_name}", summary="Get rows from a parameter table")
async def get_table(
    table_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
) -> dict:
    rows = _load_csv(table_name)
    return _paginate(rows, skip, limit)


@router.get("/{table_name}/columns", summary="Get column names and row count")
async def table_columns(table_name: str) -> dict:
    rows = _load_csv(table_name)
    cols = list(rows[0].keys()) if rows else []
    return {"table": table_name, "columns": cols, "row_count": len(rows)}


@router.get("/coi/lookup", summary="Look up COI rate by age and sex")
async def coi_lookup(
    age: int = Query(..., ge=0, le=120),
    sex: str = Query(..., pattern="^(male|female)$"),
) -> dict:
    rows = _load_csv("coi")
    match = [r for r in rows if int(r.get("age", -1)) == age and r.get("sex", "").lower() == sex]
    return {"age": age, "sex": sex, "data": match}


@router.get("/lapse/lookup", summary="Look up lapse rates by policy year")
async def lapse_lookup(pol_year: int = Query(..., ge=1)) -> dict:
    rows = _load_csv("lapse")
    match = [r for r in rows if int(r.get("pol_year", -1)) == pol_year]
    return {"pol_year": pol_year, "data": match}


@router.get("/mortality/lookup", summary="Look up mortality rates by sex and entry age")
async def mortality_lookup(
    sex: str = Query(..., pattern="^(male|female)$"),
    age: Optional[int] = Query(None, ge=0, le=120),
) -> dict:
    key = f"mortality_select_{sex}"
    rows = _load_csv(key)
    if age is not None:
        rows = [r for r in rows if int(r.get("age", -1)) == age]
    return {"sex": sex, "age": age, "data": rows}
