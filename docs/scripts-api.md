# Scripts API

The Scripts API exposes CRUD operations for the Python source files inside the `ulp_model/` package. It is consumed by the **View Code** panel in the FIA Validation Tool UI, allowing developers to read, edit, create, and delete model scripts without leaving the browser.

All endpoints are mounted at `/api/v1/scripts` and served on **port 8000**.

---

## Security

- Only `.py` files are accessible. Requests for any other extension return `400 Bad Request`.
- All resolved paths are checked to confirm they remain inside the `ulp_model/` directory. Path-traversal attempts (e.g. `../../app/main.py`) return `400 Bad Request`.

---

## Endpoints

### GET `/api/v1/scripts`

List all `.py` files in `ulp_model/`.

**Response** `200 OK`:
```json
{
  "scripts": [
    { "filename": "__init__.py",          "size_bytes": 412  },
    { "filename": "config.py",            "size_bytes": 1024 },
    { "filename": "forward_projection.py","size_bytes": 8730 },
    { "filename": "inputs.py",            "size_bytes": 2048 },
    { "filename": "loader.py",            "size_bytes": 1536 },
    { "filename": "model.py",             "size_bytes": 4096 },
    { "filename": "outputs.py",           "size_bytes": 3200 },
    { "filename": "part3_cashflows.py",   "size_bytes": 6144 },
    { "filename": "utils.py",             "size_bytes": 2560 }
  ]
}
```

Files are returned in alphabetical order.

---

### GET `/api/v1/scripts/{filename}`

Retrieve the full text content of a single script.

**Path parameter:**

| Parameter | Description |
|-----------|-------------|
| `filename` | Exact filename including `.py` extension (e.g. `model.py`) |

**Response** `200 OK`:
```json
{
  "filename": "model.py",
  "content": "\"\"\"ULPModel orchestrator.\"\"\"\n\nimport torch\n..."
}
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| `400` | Extension is not `.py` or path traversal detected |
| `404` | File does not exist in `ulp_model/` |

---

### POST `/api/v1/scripts`

Create a new script file. The file must not already exist.

**Request body** (`application/json`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Target filename, must end with `.py` |
| `content` | string | No | Initial file content (defaults to empty string) |

**Example:**
```json
{
  "filename": "custom_decrement.py",
  "content": "# Custom decrement table logic\n"
}
```

**Response** `201 Created`:
```json
{
  "filename": "custom_decrement.py",
  "size_bytes": 38
}
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| `400` | Extension is not `.py` or path traversal detected |
| `409` | A file with that name already exists |

---

### PUT `/api/v1/scripts/{filename}`

Overwrite the content of an existing script.

**Path parameter:**

| Parameter | Description |
|-----------|-------------|
| `filename` | Filename of the script to update |

**Request body** (`application/json`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | New file content (full replacement) |

**Example:**
```json
{
  "content": "\"\"\"Updated model logic.\"\"\"\nimport torch\n..."
}
```

**Response** `200 OK`:
```json
{
  "filename": "model.py",
  "size_bytes": 4210
}
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| `400` | Extension is not `.py` or path traversal detected |
| `404` | File does not exist |

---

### DELETE `/api/v1/scripts/{filename}`

Permanently delete a script from `ulp_model/`.

**Path parameter:**

| Parameter | Description |
|-----------|-------------|
| `filename` | Filename of the script to delete |

**Response** `200 OK`:
```json
{ "deleted": "custom_decrement.py" }
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| `400` | Extension is not `.py` or path traversal detected |
| `404` | File does not exist |

---

## Router Registration

The router is registered in `app/main.py`:

```python
from app.routes import ..., scripts
app.include_router(scripts.router)
```

Source file: `app/routes/scripts.py`

---

## Target Directory

The `ulp_model/` directory is resolved from `settings.base_dir` (the project root):

```python
_MODEL_DIR = Path(settings.base_dir) / "ulp_model"
```

`settings.base_dir` defaults to the project root (`C:\projects\UL`) and can be overridden via the `BASE_DIR` environment variable or `.env` file.
