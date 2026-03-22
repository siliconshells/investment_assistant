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
cd terraform
terraform init
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

See `terraform/README.md` for full details.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/prices/{ticker}` | Get stored price data for a ticker |
| POST | `/analyze` | Send ticker + timeframe, get LLM-generated summary |
| GET | `/docs` | Interactive Swagger UI |

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
ai-investment-assistant/
├── airflow/dags/          # Airflow DAG for daily stock ETL
├── app/
│   ├── main.py            # FastAPI entrypoint
│   ├── config.py          # Settings via pydantic-settings
│   ├── routers/           # API route handlers
│   ├── services/          # LLM + S3 service layers
│   └── models/            # Pydantic request/response schemas
├── k8s/                   # Kubernetes deployment manifests
├── terraform/             # AWS infrastructure as code
├── tests/                 # Pytest suite
├── .github/workflows/     # CI/CD pipeline
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
