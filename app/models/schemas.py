"""Pydantic models for API requests and responses.

These typed schemas serve as a contract between the backend and
internal research teams — self-documenting and enforced at runtime.
"""

from datetime import date
from pydantic import BaseModel, Field


# --- Requests ---

class AnalyzeRequest(BaseModel):
    """Request body for the /analyze endpoint."""
    ticker: str = Field(..., example="AAPL", description="Stock ticker symbol")
    start_date: date | None = Field(None, description="Start of analysis window")
    end_date: date | None = Field(None, description="End of analysis window")
    question: str = Field(
        "Summarize recent price action and suggest what to watch next.",
        description="Free-text question for the LLM analyst",
    )


# --- Responses ---

class HealthResponse(BaseModel):
    status: str = "ok"
    environment: str


class PricePoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceResponse(BaseModel):
    ticker: str
    prices: list[PricePoint]
    source: str = "alpha_vantage"
    api_tier: str = "free"


class AnalysisResponse(BaseModel):
    ticker: str
    llm_provider: str
    analysis: str
    price_points_used: int

