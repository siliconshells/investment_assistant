"""Routes for stock price data retrieval."""

from fastapi import APIRouter, HTTPException

from app.models.schemas import PricePoint, PriceResponse
from app.services import stock_fetcher, storage

router = APIRouter(tags=["prices"])


@router.get("/prices/{ticker}", response_model=PriceResponse)
async def get_prices(ticker: str):
    """Return stored price data for a ticker.

    If no stored data exists, fetches fresh data from Alpha Vantage
    and persists it for future requests.
    """
    ticker = ticker.upper()

    # Try stored data first
    prices = storage.load_prices(ticker)

    if prices is None:
        # Fetch on demand and store
        prices = await stock_fetcher.fetch_daily_prices(ticker)
        if not prices:
            raise HTTPException(
                status_code=404,
                detail=f"No price data found for ticker '{ticker}'",
            )
        storage.save_prices(ticker, prices)

    return PriceResponse(
        ticker=ticker,
        prices=[PricePoint(**p) for p in prices],
    )
