"""
Script browser/editor routes.
Serves .py files from the ulp_model directory for the UI code editor.
Mounted at /api/v1/scripts.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/api/v1/scripts", tags=["Scripts"])

_MODEL_DIR = Path(settings.base_dir) / "ulp_model"


def _resolve_script(filename: str) -> Path:
    """Resolve a script path with path-traversal protection."""
    if not filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are allowed")
    path = (_MODEL_DIR / filename).resolve()
    if not str(path).startswith(str(_MODEL_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


@router.get("", summary="List all scripts in ulp_model")
async def list_scripts() -> dict:
    if not _MODEL_DIR.exists():
        raise HTTPException(status_code=404, detail="ulp_model directory not found")
    files = [
        {"filename": f.name, "size_bytes": f.stat().st_size}
        for f in sorted(_MODEL_DIR.glob("*.py"))
    ]
    return {"scripts": files}


@router.get("/{filename}", summary="Get script content")
async def get_script(filename: str) -> dict:
    path = _resolve_script(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Script '{filename}' not found")
    return {"filename": filename, "content": path.read_text(encoding="utf-8")}


class ScriptBody(BaseModel):
    content: str


class CreateScriptBody(BaseModel):
    filename: str
    content: str = ""


@router.post("", summary="Create a new script", status_code=201)
async def create_script(body: CreateScriptBody) -> dict:
    path = _resolve_script(body.filename)
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Script '{body.filename}' already exists")
    path.write_text(body.content, encoding="utf-8")
    return {"filename": body.filename, "size_bytes": path.stat().st_size}


@router.put("/{filename}", summary="Update script content")
async def update_script(filename: str, body: ScriptBody) -> dict:
    path = _resolve_script(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Script '{filename}' not found")
    path.write_text(body.content, encoding="utf-8")
    return {"filename": filename, "size_bytes": path.stat().st_size}


@router.delete("/{filename}", summary="Delete a script")
async def delete_script(filename: str) -> dict:
    path = _resolve_script(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Script '{filename}' not found")
    path.unlink()
    return {"deleted": filename}
