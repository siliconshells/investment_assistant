"""Stock price fetcher using Alpha Vantage (free tier).

Used by both the Airflow DAG and the FastAPI app for on-demand fetches.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"


async def fetch_daily_prices(ticker: str) -> list[dict]:
    """Fetch daily adjusted prices for a ticker.

    Returns a list of dicts sorted by date ascending:
        [{"date": "2024-01-02", "open": 150.0, ...}, ...]
    """
    settings = get_settings()
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker.upper(),
        "apikey": settings.alpha_vantage_api_key,
        "outputsize": "compact",  # last 100 days
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    time_series = data.get("Time Series (Daily)", {})
    if not time_series:
        logger.warning("No data returned for %s — check API key / ticker", ticker)
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
