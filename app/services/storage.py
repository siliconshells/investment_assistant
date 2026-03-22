"""S3 storage service for structured investment data.

In local/dev mode, falls back to filesystem storage so the app
runs without AWS credentials during development.
"""

import json
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)

LOCAL_DATA_DIR = Path("data")


def _use_local() -> bool:
    s = get_settings()
    return s.app_env == "development" or not s.s3_bucket_name


def save_prices(ticker: str, data: list[dict]) -> str:
    """Persist daily price data. Returns the storage key."""
    key = f"prices/{ticker.upper()}.json"
    payload = json.dumps(data, indent=2)

    if _use_local():
        path = LOCAL_DATA_DIR / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
        logger.info("Saved %s locally → %s", ticker, path)
        return str(path)

    s = get_settings()
    s3 = boto3.client("s3", region_name=s.aws_region)
    s3.put_object(Bucket=s.s3_bucket_name, Key=key, Body=payload)
    logger.info("Saved %s → s3://%s/%s", ticker, s.s3_bucket_name, key)
    return f"s3://{s.s3_bucket_name}/{key}"


def load_prices(ticker: str) -> list[dict] | None:
    """Load stored price data for a ticker. Returns None if missing."""
    key = f"prices/{ticker.upper()}.json"

    if _use_local():
        path = LOCAL_DATA_DIR / key
        if not path.exists():
            return None
        return json.loads(path.read_text())

    s = get_settings()
    s3 = boto3.client("s3", region_name=s.aws_region)
    try:
        obj = s3.get_object(Bucket=s.s3_bucket_name, Key=key)
        return json.loads(obj["Body"].read().decode())
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        raise
