"""
FastAPI service for UL param_tables directory.
Serves all CSV parameter tables and the scalar_inputs YAML.
"""

from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

DATA_DIR = Path(__file__).resolve().parent.parent / "param_tables"

app = FastAPI(
    title="UL Param Tables API",
    description="REST API for Universal Life actuarial parameter tables",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TABLES = {
    "admin_chg": "admin_chg_tbl.csv",
    "alloc_chg": "alloc_chg_tbl.csv",
    "basic_lb_rate": "basic_lb_rate_tbl.csv",
    "coi": "coi_tbl.csv",
    "comm": "comm_tbl.csv",
    "hard_g_inv": "hard_g_inv_tbl.csv",
    "lapse": "lapse_tbl.csv",
    "lien": "lien_tbl.csv",
    "mortality_select_male": "mortality_select_male.csv",
    "mortality_select_female": "mortality_select_female.csv",
    "op_exp": "op_exp_tbl.csv",
    "ovrd": "ovrd_tbl.csv",
    "reg_param": "reg_param_tbl.csv",
    "sb_acp_rate": "sb_acp_rate_tbl.csv",
    "sb_coi_rate": "sb_coi_rate_tbl.csv",
    "surr_chg": "surr_chg_tbl.csv",
    "topup_lb_rate": "topup_lb_rate_tbl.csv",
}


def _load_csv(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return pd.read_csv(path)


def _df_to_response(df: pd.DataFrame, skip: int, limit: int) -> dict:
    total = len(df)
    rows = df.iloc[skip : skip + limit].to_dict(orient="records")
    return {"total": total, "skip": skip, "limit": limit, "data": rows}


# ---------------------------------------------------------------------------
# Routes — table index
# ---------------------------------------------------------------------------


@app.get("/", summary="API root")
def root():
    return {"message": "UL Param Tables API", "tables": list(TABLES.keys())}


@app.get("/tables", summary="List available tables")
def list_tables():
    return {"tables": list(TABLES.keys())}


# ---------------------------------------------------------------------------
# Scalar inputs (YAML)
# ---------------------------------------------------------------------------


@app.get("/scalar_inputs", summary="Get scalar model inputs from YAML")
def get_scalar_inputs():
    path = DATA_DIR / "scalar_inputs.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="scalar_inputs.yaml not found")
    with open(path) as f:
        data = yaml.safe_load(f)
    return data


# ---------------------------------------------------------------------------
# Generic table endpoint
# ---------------------------------------------------------------------------


@app.get("/tables/{table_name}", summary="Get rows from any named parameter table")
def get_table(
    table_name: str,
    skip: int = Query(0, ge=0, description="Number of rows to skip"),
    limit: int = Query(100, ge=1, le=10000, description="Max rows to return"),
):
    if table_name not in TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown table '{table_name}'. Available: {list(TABLES.keys())}",
        )
    df = _load_csv(TABLES[table_name])
    return _df_to_response(df, skip, limit)


@app.get("/tables/{table_name}/columns", summary="Get column names of a table")
def get_table_columns(table_name: str):
    if table_name not in TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table '{table_name}'")
    df = _load_csv(TABLES[table_name])
    return {"table": table_name, "columns": list(df.columns), "row_count": len(df)}


# ---------------------------------------------------------------------------
# Specific table endpoints with domain-aware filtering
# ---------------------------------------------------------------------------


@app.get("/coi", summary="Get COI rates, optionally filtered by age and sex")
def get_coi(
    age: Optional[int] = Query(None, description="Filter by exact age"),
    sex: Optional[str] = Query(None, description="Filter by sex: male | female"),
    skip: int = 0,
    limit: int = 100,
):
    df = _load_csv(TABLES["coi"])
    if age is not None:
        col = next((c for c in df.columns if "age" in c.lower()), None)
        if col:
            df = df[df[col] == age]
    if sex is not None:
        col = next((c for c in df.columns if sex.lower() in c.lower()), None)
        if col is None:
            raise HTTPException(status_code=400, detail=f"Sex column for '{sex}' not found")
        df = df[["age" if "age" in c.lower() else c for c in df.columns[:1]] + [col]]
    return _df_to_response(df, skip, limit)


@app.get("/lapse", summary="Get lapse rates, optionally filtered by policy year")
def get_lapse(
    pol_year: Optional[int] = Query(None, description="Filter by policy year"),
    skip: int = 0,
    limit: int = 100,
):
    df = _load_csv(TABLES["lapse"])
    if pol_year is not None:
        df = df[df["pol_year"] == pol_year]
    return _df_to_response(df, skip, limit)


@app.get("/comm", summary="Get commission rates, optionally filtered by policy year")
def get_comm(
    pol_year: Optional[int] = Query(None, description="Filter by policy year"),
    skip: int = 0,
    limit: int = 100,
):
    df = _load_csv(TABLES["comm"])
    if pol_year is not None:
        df = df[df["pol_year"] == pol_year]
    return _df_to_response(df, skip, limit)


@app.get("/mortality/{sex}", summary="Get select mortality rates by sex (male | female)")
def get_mortality(
    sex: str,
    age: Optional[int] = Query(None, description="Filter by entry age [x]"),
    skip: int = 0,
    limit: int = 100,
):
    sex = sex.lower()
    if sex not in ("male", "female"):
        raise HTTPException(status_code=400, detail="sex must be 'male' or 'female'")
    key = f"mortality_select_{sex}"
    df = _load_csv(TABLES[key])
    if age is not None:
        age_col = df.columns[0]
        df = df[df[age_col] == age]
    return _df_to_response(df, skip, limit)


@app.get("/surr_chg", summary="Get surrender charge table")
def get_surr_chg(skip: int = 0, limit: int = 100):
    df = _load_csv(TABLES["surr_chg"])
    return _df_to_response(df, skip, limit)


@app.get("/reg_param", summary="Get regulatory parameter table")
def get_reg_param():
    df = _load_csv(TABLES["reg_param"])
    return _df_to_response(df, 0, len(df))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("param_tables_api:app", host="0.0.0.0", port=8001, reload=True)
