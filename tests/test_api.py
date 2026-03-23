"""Tests for the AI Investment Research Assistant API.

Demonstrates well-tested, maintainable backend patterns:
- Unit tests for services with mocked external dependencies
- Integration tests for API endpoints via TestClient
- Fixtures for repeatable test data
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ---- Fixtures ----


@pytest.fixture
def sample_prices():
    """Representative price data for testing."""
    return [
        {
            "date": "2024-09-16",
            "open": 216.5,
            "high": 217.0,
            "low": 213.6,
            "close": 216.3,
            "volume": 59312000,
        },
        {
            "date": "2024-09-17",
            "open": 215.8,
            "high": 216.9,
            "low": 214.5,
            "close": 216.8,
            "volume": 45210000,
        },
        {
            "date": "2024-09-18",
            "open": 217.5,
            "high": 222.5,
            "low": 217.1,
            "close": 220.7,
            "volume": 78432000,
        },
    ]


# ---- Health Endpoint ----


class TestHealth:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "environment" in data
        assert "llm_provider" in data


# ---- Price Endpoint ----


class TestPrices:
    @patch("app.routers.prices.storage.load_prices")
    def test_get_prices_from_storage(self, mock_load, sample_prices):
        """Returns stored data without calling external API."""
        mock_load.return_value = sample_prices

        response = client.get("/prices/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert len(data["prices"]) == 3
        assert data["prices"][0]["date"] == "2024-09-16"

    @patch("app.routers.prices.storage.save_prices")
    @patch(
        "app.routers.prices.stock_fetcher.fetch_daily_prices", new_callable=AsyncMock
    )
    @patch("app.routers.prices.storage.load_prices")
    def test_get_prices_fetches_when_not_stored(
        self, mock_load, mock_fetch, mock_save, sample_prices
    ):
        """Fetches from Alpha Vantage and stores when no cached data exists."""
        mock_load.return_value = None
        mock_fetch.return_value = (sample_prices, "paid")

        response = client.get("/prices/MSFT")

        assert response.status_code == 200
        mock_fetch.assert_called_once_with("MSFT")
        mock_save.assert_called_once_with("MSFT", sample_prices)

    @patch(
        "app.routers.prices.stock_fetcher.fetch_daily_prices", new_callable=AsyncMock
    )
    @patch("app.routers.prices.storage.load_prices")
    def test_get_prices_404_when_no_data(self, mock_load, mock_fetch):
        """Returns 404 when ticker has no data anywhere."""
        mock_load.return_value = None
        mock_fetch.return_value = ([], "free")

        response = client.get("/prices/ZZZZZ")
        assert response.status_code == 404

    @patch("app.routers.prices.storage.save_prices")
    @patch(
        "app.routers.prices.stock_fetcher.fetch_daily_prices", new_callable=AsyncMock
    )
    def test_refresh_forces_fresh_fetch(self, mock_fetch, mock_save, sample_prices):
        """POST /prices/{ticker}/refresh bypasses cache and fetches fresh data."""
        mock_fetch.return_value = (sample_prices, "paid")

        response = client.post("/prices/AAPL/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert "refreshed" in data["source"]
        mock_fetch.assert_called_once_with("AAPL")
        mock_save.assert_called_once()

    @patch(
        "app.routers.prices.stock_fetcher.fetch_daily_prices", new_callable=AsyncMock
    )
    def test_refresh_502_when_fetch_fails(self, mock_fetch):
        """POST /prices/{ticker}/refresh returns 502 when upstream fails."""
        mock_fetch.return_value = ([], "free")

        response = client.post("/prices/NVDA/refresh")
        assert response.status_code == 502


# ---- Pipeline Webhook ----


class TestPipelineWebhook:
    def test_pipeline_complete_returns_client_count(self):
        """POST /pipeline/complete succeeds even with no SSE clients."""
        response = client.post("/pipeline/complete")
        assert response.status_code == 200
        assert "notified_clients" in response.json()


# ---- Analyze Endpoint ----


class TestAnalyze:
    @patch("app.routers.analysis.llm_service.analyze", new_callable=AsyncMock)
    @patch("app.routers.analysis.storage.load_prices")
    def test_analyze_returns_summary(self, mock_load, mock_analyze, sample_prices):
        """Full round-trip: load data → call LLM → return analysis."""
        mock_load.return_value = sample_prices
        mock_analyze.return_value = (
            "AAPL is trending upward with strong momentum.",
            "anthropic",
        )

        response = client.post(
            "/analyze",
            json={
                "ticker": "AAPL",
                "question": "What is the trend?",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["llm_provider"] == "anthropic"
        assert "trending upward" in data["analysis"]
        assert data["price_points_used"] == 3

    @patch("app.routers.analysis.llm_service.analyze", new_callable=AsyncMock)
    @patch("app.routers.analysis.storage.load_prices")
    def test_analyze_handles_llm_error(self, mock_load, mock_analyze, sample_prices):
        """Returns 502 when the LLM provider fails."""
        mock_load.return_value = sample_prices
        mock_analyze.side_effect = Exception("Rate limited")

        response = client.post("/analyze", json={"ticker": "AAPL"})
        assert response.status_code == 502
        assert "LLM provider error" in response.json()["detail"]

    @patch(
        "app.routers.analysis.stock_fetcher.fetch_daily_prices", new_callable=AsyncMock
    )
    @patch("app.routers.analysis.storage.load_prices")
    def test_analyze_404_no_data(self, mock_load, mock_fetch):
        """Returns 404 when no price data is available."""
        mock_load.return_value = None
        mock_fetch.return_value = ([], "free")

        response = client.post("/analyze", json={"ticker": "NOPE"})
        assert response.status_code == 404


# ---- LLM Service Unit Tests ----


class TestLLMService:
    def test_format_price_context(self, sample_prices):
        """Price data is formatted as a compact text table."""
        from app.services.llm_service import _format_price_context

        result = _format_price_context(sample_prices)
        assert "2024-09-16" in result
        assert "216.5" in result
        lines = result.strip().split("\n")
        assert len(lines) == 4  # header + 3 data rows

    def test_format_price_context_includes_all_rows(self):
        """Includes all rows so the LLM has full price history."""
        from app.services.llm_service import _format_price_context

        big_data = [
            {
                "date": f"2024-01-{i:02d}",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1000,
            }
            for i in range(1, 60)
        ]
        result = _format_price_context(big_data)
        lines = result.strip().split("\n")
        assert len(lines) == len(big_data) + 1  # header + all data rows
