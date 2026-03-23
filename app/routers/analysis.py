"""Routes for LLM-powered investment analysis."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import AnalysisResponse, AnalyzeRequest
from app.services import llm_service, stock_fetcher, storage

router = APIRouter(tags=["analysis"])


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_ticker(req: AnalyzeRequest):
    """Generate an AI-powered analysis of a stock's recent price action.

    Loads stored data (or fetches fresh), sends it to the configured
    LLM provider, and returns a plain-English summary.
    """
    ticker = req.ticker.upper()

    # Load or fetch prices
    prices = storage.load_prices(ticker)
    if prices is None:
        prices, _ = await stock_fetcher.fetch_daily_prices(ticker)
        if not prices:
            raise HTTPException(
                status_code=404,
                detail=f"No price data available for '{ticker}'",
            )
        storage.save_prices(ticker, prices)

    # Optional date filtering
    if req.start_date:
        prices = [p for p in prices if p["date"] >= str(req.start_date)]
    if req.end_date:
        prices = [p for p in prices if p["date"] <= str(req.end_date)]

    if not prices:
        raise HTTPException(
            status_code=404,
            detail="No price data in the requested date range",
        )

    # Call LLM
    try:
        analysis_text, provider = await llm_service.analyze(
            ticker, prices, req.question
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {e}",
        )

    return AnalysisResponse(
        ticker=ticker,
        llm_provider=provider,
        analysis=analysis_text,
        price_points_used=len(prices),
    )
