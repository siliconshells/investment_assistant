"""Stock price fetcher using Alpha Vantage.

Tries the paid API key first. If that returns no data, falls back to
the free API key. Returns both the prices and which tier was used.

Used by both the Airflow DAG and the FastAPI app for on-demand fetches.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


async def _fetch_with_key(ticker: str, apikey: str) -> list[dict]:
    """Attempt a fetch with the given API key. Returns empty list on failure."""
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker.upper(),
        "apikey": apikey,
        "outputsize": "compact",  # last 100 days
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    time_series = data.get("Time Series (Daily)", {})
    if not time_series:
        logger.warning("No data returned for %s — response: %s", ticker, data)
        return []

    prices = []
    for date_str, values in sorted(time_series.items()):
        prices.append(
            {
                "date": date_str,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(values["5. volume"]),
            }
        )

    logger.info("Fetched %d price points for %s", len(prices), ticker)
    return prices


async def fetch_daily_prices(ticker: str) -> tuple[list[dict], str]:
    """Fetch daily prices for a ticker.

    Tries the paid key first, falls back to the free key if it fails.

    Returns:
        (prices, api_tier) where api_tier is "paid" or "free".
        prices is an empty list if both keys fail.
    """
    settings = get_settings()

    # Try paid key first
    if settings.alpha_vantage_api_key and settings.alpha_vantage_api_key != "demo":
        prices = await _fetch_with_key(ticker, settings.alpha_vantage_api_key)
        if prices:
            return prices, "paid"
        logger.warning("Paid key returned no data for %s, trying free key", ticker)

    # Fall back to free key
    if settings.alpha_vantage_free_api_key:
        prices = await _fetch_with_key(ticker, settings.alpha_vantage_free_api_key)
        if prices:
            return prices, "free"

    return [], "free"
