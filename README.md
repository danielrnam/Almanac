# 🌱 Almanac: Multi-Agent Smart Yard Watering System

Almanac is a premium, multi-tenant garden management and smart watering coordinator built on the **Google Agent Development Kit (ADK)**. 

By coordinating a team of specialized AI agents with real-time meteorological API tools and Gemini Vision analysis, Almanac compiles highly descriptive, context-aware 7-day watering plans tailored precisely to your yard's unique plants, microclimates, and local weather forecasts.

---

## 🎨 Core Architectural Features

* **Multi-Agent Orchestration**: Built on a modular 3-agent delegation hierarchy utilizing `gemini-3.6-flash`:
  * `orchestrator_agent` (Root Agent): Coordinates schedules, balances plant care guidelines with weather metrics, and hosts user chats.
  * `weather_forecast_agent` (Specialist): Executes dynamic live tool calling sequence.
  * `plant_analyst_agent` (Specialist): Summarizes health states, maturity levels, and care instructions.
* **Live Public Meteorological Tool Calls**: Pulls real-time coordinates and weekly forecasts via public geocoding and Open-Meteo REST endpoints (no API keys required!).
* **Isolated Multi-Tenant Storage**: Leverages a robust SQLite database schema partition isolating plant profiles, user locations, and historical watering logs strictly by `user_id`.
* **Vertex AI Model Armor Safety Guardrails**: Standard ADK security plugin intercepting prompts and model responses, with a local regex heuristics safety fallback for seamless offline developer environments.
* **Interactive Visual UI & Real-Time Chat**: Premium, mobile-responsive Streamlit interface with a live camera/file uploader, Gemini Multimodal plant diagnosis, interactive horizontal weekly visual calendar grids, and stateful memory-retaining chat.
* **100% Green Test Suite**: Full coverage with robust unit and e2e integration tests.

---

## 📁 Codebase Structure

```bash
Almanac/
├── app/
│   ├── app_utils/
│   │   └── services.py        # Shared process-wide ADK session & artifact registries
│   ├── plugins/
│   │   └── model_armor.py     # Vertex AI Model Armor & Local Adversarial Guardrails
│   ├── agent.py               # 3-Agent team structures & ADK application registration
│   ├── database.py            # isolated Multi-Tenant SQLite Database engine
│   ├── fast_api_app.py        # Production-grade FastAPI gateway
│   ├── tools.py               # Geocoding & Open-Meteo daily forecast tool utilities
│   └── ui.py                  # Front-end Streamlit dashboard & real-time chat
├── tests/
│   ├── unit/
│   │   └── test_almanac.py    # Unit tests (soft-deletes, isolation, geocoding)
│   └── integration/
│       └── test_server_e2e.py # End-to-end FastAPI e2e tests
├── Dockerfile                 # Multi-stage production container setup
├── pyproject.toml             # Python build metadata & dependency lock
├── agents-cli-manifest.yaml   # Deployment metadata manifest
└── GEMINI.md                  # Development guidelines and CLI operational checklists
```

---

## 🚀 Local Development Setup

Almanac is managed using the modern Python package installer `uv`.

### 1. Environment Setup
Create a `.env` file in the root directory (based on `.env.example`):
```bash
GOOGLE_CLOUD_PROJECT="almanac-505223"
GOOGLE_CLOUD_LOCATION="global"
```

### 2. Install Dependencies
Run the install command to configure the virtual environment:
```bash
agents-cli install
# or
uv sync
```

### 3. Running the Streamlit Dashboard (Local Play)
Start the headless interactive front-end. Prepend the location environment variable to ensure Vertex AI routes globally:
```bash
GOOGLE_CLOUD_LOCATION=global uv run streamlit run app/ui.py --browser.gatherUsageStats=false --server.headless=true
```
Visit **[http://localhost:8501](http://localhost:8501)** to manage your yard and compile plans!

### 4. Running the Test Suite
Ensure all unit and integration tests are passing green:
```bash
GOOGLE_CLOUD_LOCATION=global uv run pytest
```

---

## ☁️ Deployment Patterns

Almanac can be easily containerized and deployed to GCP Dev or Prod environments utilizing the standard `agents-cli` framework.

### 1. Verify Deployment Targets
Verify that your GCP project and billing are configured correctly. Verify that Vertex AI and Artifact Registry APIs are enabled.

### 2. Prototype Development Deployment
To deploy the agent application to your dev target (Cloud Run / GKE Sandbox):
```bash
agents-cli deploy
```
*(This triggers Terraform setup, builds the local `Dockerfile`, registers images on GCR/AR, and spins up the server instance).*

### 3. Production Deployment & Pipelines
For robust infrastructure provisioning and full CI/CD deployment, Almanac supports two primary strategies:

#### Option A: Simple Single-Project Infrastructure
Provision the dedicated GCP sandbox environment directly:
```bash
agents-cli infra single-project
```

#### Option B: Full Production CI/CD Pipeline
Inject a multi-stage GitHub Actions / Cloud Build pipeline target to automate lint, test, build, and deploy phases on every main-branch push:
```bash
agents-cli infra cicd
```
