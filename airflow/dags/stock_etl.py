"""Intraday Stock Price ETL DAG.

Orchestrates the pipeline every 3 hours during US market hours:
  1. Fetch prices from Alpha Vantage for a watchlist of tickers
  2. Validate the data (schema + freshness checks)
  3. Store structured JSON to S3 (or local filesystem in dev)
  4. Notify the API server so connected dashboards auto-refresh

Schedule: 9:30, 12:30, 3:30, 6:30 ET — weekdays only.
The 6:30 run captures the final closing prices after market close.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# -- Watchlist (easily extended by research team) --
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

# -- API server URL (override via Airflow Variable in production) --
API_BASE_URL = "http://api:8000"


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

    prices, api_tier = asyncio.run(fetch_daily_prices(ticker))
    if not prices:
        raise ValueError(f"No data returned for {ticker}")

    save_prices(ticker, prices)
    return f"Stored {len(prices)} price points for {ticker} via {api_tier} key"


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


def notify_dashboard(**kwargs):
    """Hit the API webhook so connected dashboards auto-refresh via SSE."""
    import requests

    try:
        resp = requests.post(f"{API_BASE_URL}/pipeline/complete", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return f"Notified {data.get('notified_clients', 0)} dashboard clients"
    except Exception as e:
        # Non-fatal — data is already stored, notification is best-effort
        print(f"Dashboard notification failed (non-fatal): {e}")
        return "Notification skipped"


with DAG(
    dag_id="intraday_stock_etl",
    default_args=default_args,
    description="Fetch, validate, and store stock prices every 3h during market hours",
    schedule_interval="30 9,12,15,18 * * 1-5",  # 9:30, 12:30, 3:30, 6:30 ET weekdays
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["investment", "etl", "intraday", "production"],
) as dag:

    all_validate_tasks = []

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
        all_validate_tasks.append(validate_task)

    # After ALL tickers are fetched and validated, notify dashboards
    notify_task = PythonOperator(
        task_id="notify_dashboard",
        python_callable=notify_dashboard,
        trigger_rule="all_done",  # run even if some tickers failed
    )

    all_validate_tasks >> notify_task
