"""
Launch all three UL APIs concurrently.
Usage: python run_all.py
"""

import subprocess
import sys

apis = [
    ("param_tables_api", 8001),
    ("policy_data_api",  8002),
    ("sen_fac_api",      8003),
    ("outputs_api",      8004),
]

procs = []
for module, port in apis:
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module}:app", "--host", "0.0.0.0", "--port", str(port), "--reload"],
        cwd=str(__import__("pathlib").Path(__file__).parent),
    )
    procs.append((module, port, p))
    print(f"Started {module} on http://localhost:{port}  (docs: http://localhost:{port}/docs)")

print("\nAll APIs running. Press Ctrl+C to stop.")
try:
    for _, _, p in procs:
        p.wait()
except KeyboardInterrupt:
    print("\nStopping all APIs...")
    for _, _, p in procs:
        p.terminate()
