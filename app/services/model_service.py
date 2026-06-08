"""
Model execution service.

Runs the ULP actuarial model in a background thread so the FastAPI event
loop stays responsive.  Replicates the orchestration from run_model.py
without any subprocess spawning or stdout streaming.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.schemas.model import (
    JobStatus,
    OutputFile,
    RunModelRequest,
    ScenarioMetrics,
)
from app.services.job_store import job_store

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ulp_model imports work correctly
_project_root = Path(settings.base_dir)
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_job(job_id: str, request: RunModelRequest) -> None:
    """Create a job record and launch it in a daemon thread."""
    job_store.create(job_id)
    t = threading.Thread(
        target=_execute,
        args=(job_id, request),
        daemon=True,
        name=f"model-job-{job_id[:8]}",
    )
    t.start()


# ---------------------------------------------------------------------------
# Internal execution (runs in background thread)
# ---------------------------------------------------------------------------

def _execute(job_id: str, request: RunModelRequest) -> None:
    logger.info("Job %s starting", job_id)
    job_store.mark_running(job_id, "Initialising model")

    wall_start = time.perf_counter()

    try:
        # ----------------------------------------------------------------
        # 1. Import model components (deferred to avoid slow startup cost
        #    on workers that never run a job)
        # ----------------------------------------------------------------
        import torch
        from ulp_model.config import load_config
        from ulp_model.loader import load_param_tables, PolicyBatchIterator
        from ulp_model.sensitivity import (
            load_sensitivity_scenarios,
            apply_sensitivity_factors,
        )
        from ulp_model.model import ULPModel
        from ulp_model.outputs import (
            compute_ape,
            compute_metrics,
            write_summary_outputs,
        )

        # ----------------------------------------------------------------
        # 2. Load and patch config
        # ----------------------------------------------------------------
        config_path = _project_root / settings.default_config_yaml
        config = load_config(str(config_path))

        if request.policy_file:
            config.policy_inputs_file = str(
                _resolve(request.policy_file)
            )
        if request.scenario_file:
            config.scenario_file = str(_resolve(request.scenario_file))
        if request.batch_size:
            config.batch_size = request.batch_size
        config.compute_device = request.device.value
        config.output_mode = request.output_mode.value

        # Output directory: <base_output_dir>/<job_id>
        base_out = request.output_dir or config.output_dir
        output_dir = _resolve(base_out) / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        config.output_dir = str(output_dir)

        # ----------------------------------------------------------------
        # 3. Load sensitivity scenarios
        # ----------------------------------------------------------------
        job_store.update_progress(job_id, "Loading scenarios")
        try:
            scenarios = load_sensitivity_scenarios(config.scenario_file)
        except Exception:
            logger.warning("Job %s: could not load scenarios, using base case", job_id)
            scenarios = {1: None}

        if request.scenario_id is not None:
            if request.scenario_id not in scenarios:
                raise ValueError(
                    f"Scenario ID {request.scenario_id} not found in scenario file"
                )
            scenarios = {request.scenario_id: scenarios[request.scenario_id]}

        # ----------------------------------------------------------------
        # 4. Run each scenario
        # ----------------------------------------------------------------
        device = torch.device(config.compute_device)
        dtype = (
            torch.float64
            if getattr(config, "float_precision", "float64") == "float64"
            else torch.float32
        )
        n_scenarios = len(scenarios)
        scenario_results: List[ScenarioMetrics] = []
        total_n_policies: Optional[int] = None

        for scen_idx, (scen_id, sensitivity) in enumerate(scenarios.items(), 1):
            msg = f"Running scenario {scen_id} ({scen_idx}/{n_scenarios})"
            logger.info("Job %s: %s", job_id, msg)
            job_store.update_progress(job_id, msg)

            scen_start = time.perf_counter()

            # Fresh param tables for each scenario (sensitivity applied in-place)
            param_tables = load_param_tables(config)
            if sensitivity is not None:
                apply_sensitivity_factors(param_tables, sensitivity, device, dtype)

            model = ULPModel(config)

            if config.output_mode in ("per_policy", "both"):
                # Single-batch run with full tensor retention
                iterator = PolicyBatchIterator(
                    config, config.batch_size, device, dtype
                )
                policies, _, start_row, end_row = next(iter(iterator))
                results = model.run(
                    policies, param_tables, retain_full_outputs=True
                )
                ape = float(compute_ape(policies))
                n_policies_this = int(policies.policy_id.shape[0])
            else:
                # Batched portfolio run (memory-efficient)
                results = model.run_portfolio(
                    retain_full_outputs=False,
                    param_tables=param_tables,
                )
                ape = float(results["ape"])
                n_policies_this = int(results.get("n_policies", 0))

            if total_n_policies is None:
                total_n_policies = n_policies_this

            metrics_raw = compute_metrics(results["summary"], ape)
            scen_elapsed = time.perf_counter() - scen_start

            # Write scenario output files
            if config.output_mode in ("summary", "both"):
                write_summary_outputs(
                    results["summary"], scen_id, output_dir, n_scenarios
                )

            scenario_results.append(
                ScenarioMetrics(
                    scenario_id=scen_id,
                    ape=ape,
                    pv_cf=metrics_raw.get("pv_cf"),
                    pv_prem=metrics_raw.get("pv_prem"),
                    pvcf_over_ape=metrics_raw.get("pvcf_over_ape"),
                    pvcf_over_pv_prem=metrics_raw.get("pvcf_over_pv_prem"),
                    elapsed_seconds=scen_elapsed,
                )
            )

        # ----------------------------------------------------------------
        # 5. Write consolidated metrics CSV
        # ----------------------------------------------------------------
        _write_metrics_csv(scenario_results, output_dir)

        # ----------------------------------------------------------------
        # 6. Enumerate output files for the results endpoint
        # ----------------------------------------------------------------
        output_files = _enumerate_output_files(output_dir, job_id)

        total_elapsed = time.perf_counter() - wall_start
        logger.info(
            "Job %s completed in %.2fs across %d scenario(s)",
            job_id,
            total_elapsed,
            n_scenarios,
        )

        job_store.mark_completed(
            job_id,
            output_dir=str(output_dir),
            scenarios=scenario_results,
            output_files=output_files,
            total_elapsed=total_elapsed,
            n_policies=total_n_policies,
        )

    except Exception as exc:
        elapsed = time.perf_counter() - wall_start
        logger.exception("Job %s failed after %.2fs: %s", job_id, elapsed, exc)
        job_store.mark_failed(job_id, str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = _project_root / p
    return p


def _write_metrics_csv(
    results: List[ScenarioMetrics], output_dir: Path
) -> None:
    import csv

    path = output_dir / "scenario_metrics_summary.csv"
    fields = [
        "scenario_id", "ape", "pv_cf", "pv_prem",
        "pvcf_over_ape", "pvcf_over_pv_prem", "elapsed_seconds",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "scenario_id": r.scenario_id,
                    "ape": r.ape,
                    "pv_cf": r.pv_cf,
                    "pv_prem": r.pv_prem,
                    "pvcf_over_ape": r.pvcf_over_ape,
                    "pvcf_over_pv_prem": r.pvcf_over_pv_prem,
                    "elapsed_seconds": r.elapsed_seconds,
                }
            )


_SCEN_RE = re.compile(r"scen(\d+)", re.IGNORECASE)


def _enumerate_output_files(output_dir: Path, job_id: str) -> List[OutputFile]:
    files: List[OutputFile] = []
    for f in sorted(output_dir.iterdir()):
        if not f.is_file():
            continue
        m = _SCEN_RE.search(f.stem)
        scen_id = int(m.group(1)) if m else None

        if "per_policy" in f.stem:
            ftype = "per_policy"
        elif "metrics_summary" in f.stem:
            ftype = "metrics"
        else:
            ftype = "summary"

        files.append(
            OutputFile(
                filename=f.name,
                file_type=ftype,
                scenario_id=scen_id,
                size_bytes=f.stat().st_size,
                download_url=f"/api/v1/results/{job_id}/download/{f.name}",
            )
        )
    return files
