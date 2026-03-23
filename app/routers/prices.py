"""Routes for stock price data retrieval."""

from datetime import date, timedelta
from fastapi import APIRouter, HTTPException

from app.models.schemas import PricePoint, PriceResponse
from app.services import stock_fetcher, storage

router = APIRouter(tags=["prices"])


def _last_trading_day() -> date:
    """Return the most recent trading day (Mon–Fri), excluding today."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        d -= timedelta(days=1)
    return d


@router.get("/prices/{ticker}", response_model=PriceResponse)
async def get_prices(ticker: str):
    """Return stored price data for a ticker.

    Fetches fresh data from Alpha Vantage if no data is stored or if
    the stored data doesn't include the most recent trading day.
    """
    ticker = ticker.upper()

    prices = storage.load_prices(ticker)

    needs_fetch = prices is None
    if prices:
        latest_stored = date.fromisoformat(prices[-1]["date"])
        needs_fetch = latest_stored < _last_trading_day()

    api_tier = "free"
    if needs_fetch:
        fresh, api_tier = await stock_fetcher.fetch_daily_prices(ticker)
        if fresh:
            storage.save_prices(ticker, fresh)
            prices = fresh
        elif prices is None:
            raise HTTPException(
                status_code=404,
                detail=f"No price data found for ticker '{ticker}'",
            )
        # If fetch failed but we have stale data, return what we have

    return PriceResponse(
        ticker=ticker,
        prices=[PricePoint(**p) for p in prices],
        api_tier=api_tier,
    )


@router.post("/prices/{ticker}/refresh", response_model=PriceResponse)
async def refresh_prices(ticker: str):
    """Force-fetch fresh data from Alpha Vantage, bypassing cache.

    Used by the dashboard's manual refresh button and useful for
    ad-hoc research on tickers outside the daily pipeline schedule.
    """
    ticker = ticker.upper()

    prices, api_tier = await stock_fetcher.fetch_daily_prices(ticker)
    if not prices:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch fresh data for '{ticker}'",
        )

    storage.save_prices(ticker, prices)

    return PriceResponse(
        ticker=ticker,
        prices=[PricePoint(**p) for p in prices],
        source="alpha_vantage (refreshed)",
        api_tier=api_tier,
    )
