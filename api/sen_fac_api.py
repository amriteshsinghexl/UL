"""
FastAPI service for UL sen_fac directory.
Serves sensitivity factor scenario CSV files.
"""

from pathlib import Path
from typing import Optional, List

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

DATA_DIR = Path(__file__).resolve().parent.parent / "sen_fac"

app = FastAPI(
    title="UL Sensitivity Factors API",
    description="REST API for Universal Life sensitivity factor scenarios",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Available scenario files
# ---------------------------------------------------------------------------

SCENARIO_FILES = {
    "base": "base_scen.csv",
    "scenarios": "scenarios.csv",
    "scenarios_2": "scenarios_2.csv",
    "scenarios_3": "scenarios_3.csv",
}

# All sensitivity factor columns
SENSITIVITY_COLUMNS = [
    "ie_pp_sen", "ie_pc_sen", "re_pp_sen", "re_pc_sen",
    "op_exp_sen", "inf_sen", "fme_sen", "comm_sen", "ovrd_sen",
    "mort_sen", "ulp_fer_sen", "sh_fer_sen", "lapse_sen",
    "rdr_sen", "vir_sen", "fmc_sen",
]


def _load_scenario(file_key: str) -> pd.DataFrame:
    if file_key not in SCENARIO_FILES:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario file '{file_key}' not found. Available: {list(SCENARIO_FILES.keys())}",
        )
    path = DATA_DIR / SCENARIO_FILES[file_key]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {SCENARIO_FILES[file_key]}")
    return pd.read_csv(path)


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
        "message": "UL Sensitivity Factors API",
        "scenario_files": list(SCENARIO_FILES.keys()),
        "sensitivity_columns": SENSITIVITY_COLUMNS,
    }


@app.get("/scenarios", summary="List available scenario files")
def list_scenarios():
    available = []
    for key, filename in SCENARIO_FILES.items():
        path = DATA_DIR / filename
        row_count = None
        if path.exists():
            df = pd.read_csv(path)
            row_count = len(df)
        available.append({
            "key": key,
            "filename": filename,
            "exists": path.exists(),
            "scenario_count": row_count,
        })
    return {"scenario_files": available}


@app.get("/scenarios/{file_key}", summary="Get all scenarios from a file")
def get_scenarios(
    file_key: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    df = _load_scenario(file_key)
    return _df_to_response(df, skip, limit)


@app.get("/scenarios/{file_key}/scenario/{scen_id}", summary="Get a single scenario by Scen ID")
def get_scenario_by_id(file_key: str, scen_id: str):
    df = _load_scenario(file_key)
    id_col = next((c for c in df.columns if "scen" in c.lower() and "id" in c.lower()), None)
    if id_col is None:
        raise HTTPException(status_code=400, detail="No 'Scen ID' column found in this file")
    row = df[df[id_col].astype(str) == str(scen_id)]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{scen_id}' not found in '{file_key}'",
        )
    return {"data": row.to_dict(orient="records")}


@app.get("/scenarios/{file_key}/factor/{factor_name}", summary="Get values of a specific sensitivity factor across all scenarios")
def get_factor_values(file_key: str, factor_name: str):
    if factor_name not in SENSITIVITY_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown factor '{factor_name}'. Available: {SENSITIVITY_COLUMNS}",
        )
    df = _load_scenario(file_key)
    if factor_name not in df.columns:
        raise HTTPException(
            status_code=404,
            detail=f"Factor '{factor_name}' not present in file '{file_key}'",
        )
    id_col = next((c for c in df.columns if "scen" in c.lower()), df.columns[0])
    result = df[[id_col, factor_name]].to_dict(orient="records")
    return {"file": file_key, "factor": factor_name, "data": result}


@app.get("/scenarios/all/combined", summary="Get all scenarios from all files combined")
def get_all_scenarios_combined(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
):
    frames = []
    for key, filename in SCENARIO_FILES.items():
        path = DATA_DIR / filename
        if path.exists():
            df = pd.read_csv(path)
            df["_source_file"] = key
            frames.append(df)
    if not frames:
        raise HTTPException(status_code=404, detail="No scenario files found")
    combined = pd.concat(frames, ignore_index=True)
    return _df_to_response(combined, skip, limit)


@app.get("/scenarios/{file_key}/summary", summary="Get summary statistics for sensitivity factors in a scenario file")
def get_scenario_summary(file_key: str):
    df = _load_scenario(file_key)
    present_factors = [c for c in SENSITIVITY_COLUMNS if c in df.columns]
    if not present_factors:
        return {"file": file_key, "scenario_count": len(df), "summary": {}}
    summary = df[present_factors].describe().round(4).to_dict()
    return {
        "file": file_key,
        "scenario_count": len(df),
        "factors_present": present_factors,
        "summary": summary,
    }


@app.get("/factors", summary="List all known sensitivity factor names")
def list_factors():
    return {"sensitivity_factors": SENSITIVITY_COLUMNS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sen_fac_api:app", host="0.0.0.0", port=8003, reload=True)
