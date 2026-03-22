# AI Investment Research Assistant

A lightweight, end-to-end platform that demonstrates modern data engineering and AI infrastructure skills for investment research teams.

## What It Does

1. **Airflow DAG** runs daily → fetches stock prices from a free API → stores structured JSON in S3
2. **FastAPI backend** serves the data and provides an `/analyze` endpoint that calls an LLM (OpenAI or Anthropic Claude) to generate plain-English investment summaries
3. **Docker + Kubernetes** containerize and orchestrate everything
4. **Terraform** provisions all AWS infrastructure (EKS, S3, ECR, IAM)
5. **GitHub Actions CI/CD** runs tests, builds images, and deploys on push

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Airflow DAG │────▶│   S3 Bucket  │◀────│  FastAPI Server  │
│  (daily ETL) │     │ (stock data) │     │  /prices /analyze│
└──────────────┘     └──────────────┘     └────────┬─────────┘
                                                   │
                                          ┌────────▼─────────┐
                                          │   LLM API Call   │
                                          │ (OpenAI/Anthropic)│
                                          └──────────────────┘
```

## Tech Stack Mapping

| Skill Area | Implementation |
|---|---|
| Data pipelines & orchestration | Airflow DAG (`airflow/dags/stock_etl.py`) |
| Docker & Kubernetes on AWS | `Dockerfile`, `docker-compose.yml`, `k8s/` manifests |
| RESTful APIs with FastAPI | `app/main.py`, `app/routers/` |
| LLM API integration | `app/services/llm_service.py` (OpenAI + Anthropic) |
| CI/CD & Infrastructure-as-Code | `.github/workflows/ci.yml`, `terraform/` |
| Cross-functional collaboration | Typed schemas, tests, OpenAPI docs at `/docs` |

## Quick Start (Local)

```bash
# 1. Clone and configure
cp .env.example .env          # add your API keys
pip install -r requirements.txt

# 2. Run locally
uvicorn app.main:app --reload

# 3. Or use Docker Compose (includes Airflow)
docker compose up --build
```

## Deploy to AWS

```bash
# 1. Provision infrastructure
cd terraform
terraform init
terraform plan -out=plan.tfplan
terraform apply plan.tfplan

# 2. Configure kubectl
$(terraform output -raw configure_kubectl)

# 3. Deploy to Kubernetes
kubectl apply -k ../k8s/overlays/prod
```

See `terraform/README.md` and `k8s/README.md` for full details.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/prices/{ticker}` | Get stored price data for a ticker |
| POST | `/prices/{ticker}/refresh` | Force-fetch fresh data from Alpha Vantage |
| POST | `/analyze` | Send ticker + timeframe, get LLM-generated summary |
| GET | `/pipeline/status` | Pipeline health derived from data freshness |
| POST | `/pipeline/complete` | Webhook called by Airflow to notify dashboards |
| GET | `/events/pipeline` | SSE stream — dashboards auto-refresh on pipeline events |
| GET | `/docs` | Interactive Swagger UI |

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
ai-investment-assistant/
├── airflow/dags/          # Airflow DAG for intraday stock ETL
├── app/
│   ├── main.py            # FastAPI entrypoint + SSE stream
│   ├── config.py          # Settings via pydantic-settings
│   ├── routers/           # API route handlers
│   ├── services/          # LLM + S3 service layers
│   └── models/            # Pydantic request/response schemas
├── dashboard/             # React frontend (Vite)
│   └── src/Dashboard.jsx  # Main dashboard component
├── k8s/                   # Kubernetes (Kustomize)
│   ├── base/              # Shared manifests — valid YAML, no template vars
│   └── overlays/          # dev (1 replica) and prod (ECR, IRSA, ALB)
├── terraform/             # AWS infrastructure as code
├── tests/                 # Pytest suite
├── .github/workflows/     # CI/CD pipeline
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
