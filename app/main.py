"""FastAPI application entrypoint.

Serves AI-powered investment data and analysis to internal research teams.
Interactive docs available at /docs (Swagger UI).
"""

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.routers import analysis, prices

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

app = FastAPI(
    title="AI Investment Research Assistant",
    description=(
        "Internal API for structured investment data and LLM-powered analysis. "
        "Built for research teams to access daily price feeds and AI summaries."
    ),
    version="1.0.0",
)

# --- Routes ---
app.include_router(prices.router)
app.include_router(analysis.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "environment": settings.app_env,
        "llm_provider": settings.llm_provider,
    }
