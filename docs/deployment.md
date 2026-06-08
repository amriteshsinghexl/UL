# Deployment Guide

## Development Workflow

### Backend

```bash
# From project root (C:\projects\UL\)
pip install -r requirements-backend.txt
python start_backend.py --reload        # auto-reloads on file changes
```

### Frontend

```bash
cd client
npm install
npm run dev                             # Vite dev server on :5173
```

Vite proxies all `/api` and `/health` requests to `http://localhost:8000`, so no CORS configuration is needed during development.

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed frontend origins |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`) |
| `LOG_DIR` | `logs` | Log file directory |

---

## Production Build

### Frontend (static assets)

```bash
cd client
npm run build                           # outputs to client/dist/
```

Serve `client/dist/` with any static file server, CDN, or configure the FastAPI backend to serve it:

```python
# Add to app/main.py for single-server deployment
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="client/dist", html=True), name="static")
```

### Backend (production server)

```bash
# Single process (development)
python start_backend.py

# Multiple workers (production — use when NOT running background model jobs)
python start_backend.py --workers 4

# Or with gunicorn (Linux/macOS)
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

> **Note:** The in-memory job store does not share state between workers. For multi-worker production use, replace `app/services/job_store.py` with a Redis-backed store and run model jobs in a dedicated task queue (e.g., Celery or ARQ).

---

## GPU Deployment

```bash
# Install GPU dependencies
pip install -r requirements-gpu.txt
pip install fastapi "uvicorn[standard]" pydantic-settings

# Start backend (the API will use cpu by default; GPU is selected per-request)
python start_backend.py

# Frontend: select "GPU (CUDA)" in the device dropdown
```

Verify CUDA is available:

```python
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

---

## Docker (example)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements-backend.txt .
RUN pip install --no-cache-dir -r requirements-backend.txt

COPY . .

EXPOSE 8000
CMD ["python", "start_backend.py", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t ulp-backend .
docker run -p 8000:8000 -v $(pwd)/results:/app/results ulp-backend
```

---

## Health Check

```bash
curl http://localhost:8000/health
# → {"status": "ok", "version": "2.0.0", "base_dir": "/app"}
```

---

## Job Persistence

The current job store is in-memory and does not survive server restarts. Completed jobs (and their output CSVs in `results/`) persist on disk and can be browsed via the `/api/v1/outputs/` endpoints even after a restart.

For persistent job history, implement a SQLite or PostgreSQL backed store in `app/services/job_store.py`.

---

## Reverse Proxy (nginx example)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend static files
    location / {
        root /path/to/client/dist;
        try_files $uri /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 600s;        # Allow long model runs
    }

    location /health {
        proxy_pass http://localhost:8000;
    }

    location /docs {
        proxy_pass http://localhost:8000;
    }
}
```
