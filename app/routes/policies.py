"""
Policy data routes — migrated from api/policy_data_api.py.
Mounted at /api/v1/policies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings

router = APIRouter(prefix="/api/v1/policies", tags=["Policy Data"])

_BASE = Path(settings.base_dir)
_POLICY_DIR = _BASE / "policy_data"

DATASETS: Dict[str, str] = {
    "1": "test_policies_1.csv",
    "20": "test_policies_20.csv",
    "10000": "test_policies_10000.csv",
    "50000": "test_policies_50000.csv",
    "200000": "test_policies_200000.csv",
    "5m": "test_policies_5m.parquet",
}


def _load_dataset(size: str) -> pd.DataFrame:
    if size not in DATASETS:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{size}' not found. Available: {list(DATASETS)}",
        )
    path = _POLICY_DIR / DATASETS[size]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {DATASETS[size]}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    if filters.get("sex"):
        df = df[df["sex"].str.lower() == filters["sex"].lower()]
    if filters.get("db_opt") is not None:
        df = df[df["db_opt"] == filters["db_opt"]]
    if filters.get("prem_freq") is not None:
        df = df[df["prem_freq"] == filters["prem_freq"]]
    if filters.get("age_min") is not None:
        df = df[df["age_at_entry"] >= filters["age_min"]]
    if filters.get("age_max") is not None:
        df = df[df["age_at_entry"] <= filters["age_max"]]
    if filters.get("sum_assd_min") is not None:
        df = df[df["sum_assd"] >= filters["sum_assd_min"]]
    if filters.get("sum_assd_max") is not None:
        df = df[df["sum_assd"] <= filters["sum_assd_max"]]
    return df


@router.get("", summary="List available policy datasets")
async def list_datasets() -> dict:
    available = []
    for key, filename in DATASETS.items():
        path = _POLICY_DIR / filename
        available.append({"key": key, "filename": filename, "exists": path.exists()})
    return {"datasets": available}


@router.get("/{size}", summary="Get policy rows with optional filters")
async def get_policies(
    size: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
    sex: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    db_opt: Optional[int] = Query(None),
    prem_freq: Optional[int] = Query(None),
    sum_assd_min: Optional[float] = Query(None),
    sum_assd_max: Optional[float] = Query(None),
) -> dict:
    df = _load_dataset(size)
    df = _apply_filters(
        df,
        {
            "sex": sex,
            "db_opt": db_opt,
            "prem_freq": prem_freq,
            "age_min": age_min,
            "age_max": age_max,
            "sum_assd_min": sum_assd_min,
            "sum_assd_max": sum_assd_max,
        },
    )
    total = len(df)
    page = df.iloc[skip : skip + limit]
    return {"total": total, "skip": skip, "limit": limit, "data": page.to_dict("records")}


@router.get("/{size}/summary", summary="Descriptive statistics for a dataset")
async def dataset_summary(size: str) -> dict:
    df = _load_dataset(size)
    return {"size": size, "n_rows": len(df), "stats": df.describe().to_dict()}


@router.get("/{size}/policy/{policy_id}", summary="Get a single policy record")
async def get_policy(size: str, policy_id: int) -> dict:
    df = _load_dataset(size)
    match = df[df["policy_id"] == policy_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    return match.iloc[0].to_dict()


@router.get("/{size}/sex-distribution", summary="Count policies by sex")
async def sex_distribution(size: str) -> dict:
    df = _load_dataset(size)
    return df.groupby("sex").size().to_dict()


@router.get("/{size}/age-distribution", summary="Count policies by age band")
async def age_distribution(size: str, band: int = Query(5, ge=1)) -> dict:
    df = _load_dataset(size)
    df["age_band"] = (df["age_at_entry"] // band) * band
    return df.groupby("age_band").size().to_dict()
