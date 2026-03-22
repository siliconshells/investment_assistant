"""Daily Stock Price ETL DAG.

Orchestrates the daily pipeline:
  1. Fetch prices from Alpha Vantage for a watchlist of tickers
  2. Validate the data (schema + freshness checks)
  3. Store structured JSON to S3 (or local filesystem in dev)

Schedule: daily at 6:30 PM ET (after US market close).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# -- Watchlist (easily extended by research team) --
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def fetch_and_store(ticker: str, **kwargs):
    """Fetch daily prices and persist to storage."""
    import asyncio
    from app.services.stock_fetcher import fetch_daily_prices
    from app.services.storage import save_prices

    prices = asyncio.run(fetch_daily_prices(ticker))
    if not prices:
        raise ValueError(f"No data returned for {ticker}")

    save_prices(ticker, prices)
    return f"Stored {len(prices)} price points for {ticker}"


def validate_data(ticker: str, **kwargs):
    """Basic quality checks on stored data."""
    from app.services.storage import load_prices
    from datetime import date

    prices = load_prices(ticker)
    assert prices is not None, f"No stored data for {ticker}"
    assert len(prices) > 0, f"Empty dataset for {ticker}"

    # Check that the latest data point is reasonably recent (within 5 days)
    latest = prices[-1]["date"]
    days_old = (date.today() - date.fromisoformat(latest)).days
    assert days_old <= 5, f"Data for {ticker} is {days_old} days stale"

    return f"Validation passed for {ticker}: {len(prices)} points, latest={latest}"


with DAG(
    dag_id="daily_stock_etl",
    default_args=default_args,
    description="Fetch, validate, and store daily stock prices",
    schedule_interval="30 18 * * 1-5",  # 6:30 PM ET, weekdays
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["investment", "etl", "production"],
) as dag:

    for ticker in TICKERS:
        fetch_task = PythonOperator(
            task_id=f"fetch_{ticker.lower()}",
            python_callable=fetch_and_store,
            op_kwargs={"ticker": ticker},
        )

        validate_task = PythonOperator(
            task_id=f"validate_{ticker.lower()}",
            python_callable=validate_data,
            op_kwargs={"ticker": ticker},
        )

        fetch_task >> validate_task
