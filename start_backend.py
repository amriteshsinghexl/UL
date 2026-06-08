"""
Backend startup script.

Usage:
    python start_backend.py              # default: 0.0.0.0:8000
    python start_backend.py --port 9000
    python start_backend.py --reload     # development auto-reload

The script must be run from the project root directory (C:\\projects\\UL\\)
so that relative paths in config.yaml resolve correctly.
"""

import argparse
import sys
from pathlib import Path

# Ensure the project root is first on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the ULP FastAPI backend")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info",
    )


if __name__ == "__main__":
    main()
