"""FastAPI application entrypoint.

Serves AI-powered investment data and analysis to internal research teams.
Interactive docs available at /docs (Swagger UI).
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import analysis, prices
from app.services.storage import load_prices

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Investment Research Assistant",
    description=(
        "Internal API for structured investment data and LLM-powered analysis. "
        "Built for research teams to access daily price feeds and AI summaries."
    ),
    version="1.0.0",
)

# --- CORS for React dashboard ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---
app.include_router(prices.router)
app.include_router(analysis.router)

# Watchlist shared with Airflow DAG
WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

# --- SSE: connected dashboard clients ---
# Each client gets an asyncio.Queue; when a pipeline event fires,
# we push to every queue and each SSE stream picks it up.
_sse_clients: list[asyncio.Queue] = []


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "environment": settings.app_env,
        "llm_provider": settings.llm_provider,
    }


@app.get("/watchlist")
async def get_watchlist():
    """Return the tickers tracked by the pipeline."""
    return {"tickers": WATCHLIST}


@app.get("/pipeline/status")
async def pipeline_status():
    """Pipeline health overview for the dashboard.

    In production this would query the Airflow REST API.
    For now, derives status from data freshness in storage.
    """
    statuses = []
    for ticker in WATCHLIST:
        price_data = load_prices(ticker)
        if price_data:
            latest = price_data[-1]["date"]
            days_old = (date.today() - date.fromisoformat(latest)).days
            status = "healthy" if days_old <= 3 else "stale"
            statuses.append({
                "ticker": ticker,
                "status": status,
                "last_data_date": latest,
                "data_points": len(price_data),
                "days_old": days_old,
            })
        else:
            statuses.append({
                "ticker": ticker,
                "status": "no_data",
                "last_data_date": None,
                "data_points": 0,
                "days_old": None,
            })

    healthy = sum(1 for s in statuses if s["status"] == "healthy")
    return {
        "overall": "healthy" if healthy == len(WATCHLIST) else "degraded",
        "healthy_count": healthy,
        "total_count": len(WATCHLIST),
        "tickers": statuses,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# -------------------------------------------------------------------------
# SSE stream — dashboards connect here to get push notifications
# -------------------------------------------------------------------------

@app.get("/events/pipeline")
async def pipeline_events(request: Request):
    """Server-Sent Events stream for pipeline notifications.

    The dashboard opens an EventSource to this endpoint. When the
    Airflow DAG completes and hits POST /pipeline/complete, every
    connected client receives a 'pipeline_complete' event and can
    auto-refresh its data.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _sse_clients.append(queue)
    logger.info("SSE client connected (%d total)", len(_sse_clients))

    async def event_generator():
        try:
            # Send an initial heartbeat so the client knows it's connected
            yield "event: connected\ndata: {}\n\n"
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: {event['type']}\ndata: {event['data']}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive every 30s to prevent proxy/browser timeout
                    yield ": keepalive\n\n"
        finally:
            _sse_clients.remove(queue)
            logger.info("SSE client disconnected (%d remaining)", len(_sse_clients))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# -------------------------------------------------------------------------
# Webhook — called by Airflow DAG on completion
# -------------------------------------------------------------------------

@app.post("/pipeline/complete")
async def pipeline_complete():
    """Webhook called by the Airflow DAG after all tasks finish.

    Broadcasts a 'pipeline_complete' event to all connected SSE clients
    so dashboards can auto-refresh their data.
    """
    import json

    event = {
        "type": "pipeline_complete",
        "data": json.dumps({
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "tickers": WATCHLIST,
        }),
    }

    client_count = len(_sse_clients)
    for queue in _sse_clients:
        await queue.put(event)

    logger.info("Pipeline complete — notified %d dashboard clients", client_count)
    return {"notified_clients": client_count}


# -------------------------------------------------------------------------
# Dashboard static files (served from Docker build)
# -------------------------------------------------------------------------
# In production, the Dockerfile builds the React dashboard into ./static/.
# In local dev, this directory won't exist — the React dev server at :3000
# handles it instead, proxying /api/* back to this server.

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if STATIC_DIR.is_dir():
    # Serve Vite's bundled assets (JS, CSS, images)
    app.mount(
        "/assets",
        StaticFiles(directory=STATIC_DIR / "assets"),
        name="static-assets",
    )

    # SPA catch-all: any route not matched by the API returns index.html
    # so client-side routing works on page refresh.
    @app.get("/{path:path}", include_in_schema=False)
    async def serve_spa(path: str):
        # If a real static file exists (favicon, etc.), serve it
        file_path = STATIC_DIR / path
        if file_path.is_file():
            return FileResponse(file_path)
        # Otherwise, serve the SPA entry point
        return FileResponse(STATIC_DIR / "index.html")
else:
    logger.info(
        "No static/ directory found — dashboard not bundled. "
        "Run 'npm run build' in dashboard/ or use Docker to include it."
    )
