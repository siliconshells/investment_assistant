"""Pytest configuration and shared fixtures."""

import os

# Force test settings before any app imports
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ALPHA_VANTAGE_API_KEY", "demo")
