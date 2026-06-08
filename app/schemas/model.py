from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class OutputMode(str, Enum):
    summary = "summary"
    per_policy = "per_policy"
    both = "both"


class DeviceType(str, Enum):
    cpu = "cpu"
    cuda = "cuda"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class RunModelRequest(BaseModel):
    policy_file: Optional[str] = Field(
        default=None,
        description="Path to policy CSV/Parquet (relative to project root). "
                    "Defaults to value in config.yaml.",
    )
    scenario_file: Optional[str] = Field(
        default=None,
        description="Path to scenario CSV. Defaults to value in config.yaml.",
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Base output directory. Defaults to config.yaml value.",
    )
    output_mode: OutputMode = Field(default=OutputMode.summary)
    device: DeviceType = Field(default=DeviceType.cpu)
    batch_size: Optional[int] = Field(default=None, ge=1)
    scenario_id: Optional[int] = Field(
        default=None,
        description="Run a single scenario ID only. Runs all if omitted.",
    )


# ---------------------------------------------------------------------------
# Job tracking
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None
    progress: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class ScenarioMetrics(BaseModel):
    scenario_id: int
    ape: Optional[float] = None
    pv_cf: Optional[float] = None
    pv_prem: Optional[float] = None
    pvcf_over_ape: Optional[float] = None
    pvcf_over_pv_prem: Optional[float] = None
    elapsed_seconds: Optional[float] = None


class OutputFile(BaseModel):
    filename: str
    file_type: str  # "summary" | "per_policy" | "metrics"
    scenario_id: Optional[int] = None
    size_bytes: int
    download_url: str


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    output_dir: str
    scenarios: List[ScenarioMetrics] = []
    output_files: List[OutputFile] = []
    total_elapsed_seconds: Optional[float] = None
    n_policies: Optional[int] = None


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------

class AvailableFile(BaseModel):
    key: str
    path: str
    size_bytes: int


class AvailableFilesResponse(BaseModel):
    files: List[AvailableFile]
