# SCOUT: Smart Crisis Observation & Understanding Technology

**Multimodal Disaster Intelligence & Response Platform**

SCOUT is an AI-powered disaster intelligence platform engineered to detect, monitor, forecast, and support response efforts for catastrophic natural events. Starting with wildfire observation and spread forecasting, SCOUT combines computer vision, geospatial intelligence, time-series forecasting, and multimodal generative AI within a scalable modular architecture.

---

## Architecture Overview

SCOUT follows a monorepo modular-monolith structure:

- `backend/`: FastAPI core service providing RESTful APIs, configuration, and data transport.
- `ml/`: Independent machine learning pipelines, geospatial raster analysis, and computer vision models (introduced in later blocks).
- `genai/`: Retrieval-Augmented Generation (RAG) and multi-agent crisis response systems (introduced in later blocks).
- `data/`: Segregated raw, processed, and external geospatial datasets.
- `docs/`: System documentation and Architecture Decision Records (ADRs).
- `infrastructure/`: Database migrations, Docker configs, and deployment scripts.

---

## Getting Started (Backend Foundation)

### Prerequisites

- Python 3.11+
- Git

### 1. Set Up Virtual Environment

From the project root:

```bash
# Create a local virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate
```

### 2. Install Foundation Dependencies

```bash
pip install -r backend/requirements.txt
```

### 3. Environment Configuration

Copy the example environment blueprint:

```bash
cp .env.example .env
```

### 4. Run Automated Tests

Execute the automated test suite from the `backend/` directory:

```bash
cd backend
pytest -v
```

### 5. Launch Local Development Server

Run the FastAPI application via Uvicorn:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Once running:
- **Interactive OpenAPI Documentation (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Liveness Health Check**: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)
