"""
FastAPI service for UL policy_data directory.
Serves test policy CSV and Parquet files with filtering and pagination.
"""

from pathlib import Path
from typing import Optional, List

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

DATA_DIR = Path(__file__).resolve().parent.parent / "policy_data"

app = FastAPI(
    title="UL Policy Data API",
    description="REST API for Universal Life test policy datasets",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Available datasets
# ---------------------------------------------------------------------------

DATASETS = {
    "1": "test_policies_1.csv",
    "20": "test_policies_20.csv",
    "200": "test_policies_200.csv",
    "1000": "test_policies_1000.csv",
    "10000": "test_policies_10000.csv",
    "50000": "test_policies_50000.csv",
    "200000": "test_policies_200000.csv",
    "5m": "test_policies_5m.parquet",
}

# Policy columns for reference
POLICY_COLUMNS = [
    "policy_id", "age_at_entry", "sex", "pol_term", "prem_term",
    "prem_freq", "sum_assd", "db_opt", "acp", "atp", "topup_term",
    "topup_freq", "mort_loading", "init_pols_if",
]


def _load_dataset(size: str) -> pd.DataFrame:
    if size not in DATASETS:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{size}' not found. Available: {list(DATASETS.keys())}",
        )
    path = DATA_DIR / DATASETS[size]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {DATASETS[size]}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _apply_filters(
    df: pd.DataFrame,
    sex: Optional[str],
    min_age: Optional[int],
    max_age: Optional[int],
    db_opt: Optional[int],
    prem_freq: Optional[str],
    min_sum_assd: Optional[float],
    max_sum_assd: Optional[float],
) -> pd.DataFrame:
    if sex is not None:
        df = df[df["sex"].str.upper() == sex.upper()]
    if min_age is not None:
        df = df[df["age_at_entry"] >= min_age]
    if max_age is not None:
        df = df[df["age_at_entry"] <= max_age]
    if db_opt is not None:
        df = df[df["db_opt"] == db_opt]
    if prem_freq is not None:
        df = df[df["prem_freq"].str.upper() == prem_freq.upper()]
    if min_sum_assd is not None:
        df = df[df["sum_assd"] >= min_sum_assd]
    if max_sum_assd is not None:
        df = df[df["sum_assd"] <= max_sum_assd]
    return df


def _df_to_response(df: pd.DataFrame, skip: int, limit: int) -> dict:
    total = len(df)
    rows = df.iloc[skip : skip + limit].to_dict(orient="records")
    return {"total": total, "skip": skip, "limit": limit, "data": rows}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", summary="API root")
def root():
    return {
        "message": "UL Policy Data API",
        "datasets": list(DATASETS.keys()),
        "columns": POLICY_COLUMNS,
    }


@app.get("/datasets", summary="List available policy datasets")
def list_datasets():
    available = []
    for size, filename in DATASETS.items():
        path = DATA_DIR / filename
        available.append({
            "size_key": size,
            "filename": filename,
            "exists": path.exists(),
            "format": path.suffix.lstrip("."),
        })
    return {"datasets": available}


@app.get("/policies/{size}", summary="Get policies from a dataset with optional filters")
def get_policies(
    size: str,
    skip: int = Query(0, ge=0, description="Number of rows to skip"),
    limit: int = Query(100, ge=1, le=5000, description="Max rows to return"),
    sex: Optional[str] = Query(None, description="Filter by sex: M | F"),
    min_age: Optional[int] = Query(None, ge=0, le=120, description="Minimum age at entry"),
    max_age: Optional[int] = Query(None, ge=0, le=120, description="Maximum age at entry"),
    db_opt: Optional[int] = Query(None, description="Death benefit option"),
    prem_freq: Optional[str] = Query(None, description="Premium frequency"),
    min_sum_assd: Optional[float] = Query(None, description="Minimum sum assured"),
    max_sum_assd: Optional[float] = Query(None, description="Maximum sum assured"),
):
    df = _load_dataset(size)
    df = _apply_filters(df, sex, min_age, max_age, db_opt, prem_freq, min_sum_assd, max_sum_assd)
    return _df_to_response(df, skip, limit)


@app.get("/policies/{size}/summary", summary="Get summary statistics for a dataset")
def get_policies_summary(size: str):
    df = _load_dataset(size)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    summary = df[numeric_cols].describe().round(4).to_dict()
    return {
        "size_key": size,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
        "numeric_summary": summary,
    }


@app.get("/policies/{size}/policy/{policy_id}", summary="Get a single policy by ID")
def get_policy_by_id(size: str, policy_id: str):
    df = _load_dataset(size)
    row = df[df["policy_id"].astype(str) == str(policy_id)]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found in dataset '{size}'")
    return {"data": row.to_dict(orient="records")}


@app.get("/policies/{size}/sex_distribution", summary="Get policy count by sex")
def get_sex_distribution(size: str):
    df = _load_dataset(size)
    dist = df["sex"].value_counts().to_dict()
    return {"size_key": size, "total": len(df), "distribution": dist}


@app.get("/policies/{size}/age_distribution", summary="Get policy count by age at entry")
def get_age_distribution(size: str):
    df = _load_dataset(size)
    dist = df["age_at_entry"].value_counts().sort_index().to_dict()
    return {"size_key": size, "total": len(df), "distribution": dist}


@app.get("/policies/{size}/db_opt_distribution", summary="Get policy count by death benefit option")
def get_db_opt_distribution(size: str):
    df = _load_dataset(size)
    dist = df["db_opt"].value_counts().sort_index().to_dict()
    return {"size_key": size, "total": len(df), "distribution": dist}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("policy_data_api:app", host="0.0.0.0", port=8002, reload=True)
