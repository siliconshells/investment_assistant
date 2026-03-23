"""LLM integration service supporting OpenAI and Anthropic Claude.

Abstracts provider differences behind a single `analyze()` call.
Includes token-aware prompt construction for cost efficiency.
"""

import logging

import anthropic
import openai

from app.config import get_settings

logger = logging.getLogger(__name__)

# System prompt shared across providers
SYSTEM_PROMPT = (
    "You are a concise investment research analyst. You are given recent stock "
    "price data and a question from a researcher. Answer the question directly "
    "and specifically, using the price data as evidence. Keep responses under "
    "200 words and avoid generic summaries unless explicitly asked for one."
)


def _format_price_context(prices: list[dict]) -> str:
    """Convert price data into a compact text table for the LLM."""
    lines = ["Date       | Open   | High   | Low    | Close  | Volume"]
    for p in prices[-30:]:  # cap at 30 days to control token usage
        lines.append(
            f"{p['date']} | {p['open']:>6} | {p['high']:>6} | "
            f"{p['low']:>6} | {p['close']:>6} | {p['volume']}"
        )
    return "\n".join(lines)


async def analyze_with_openai(ticker: str, prices: list[dict], question: str) -> str:
    """Call OpenAI chat completion."""
    settings = get_settings()
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    price_context = _format_price_context(prices)
    user_msg = (
        f"Ticker: {ticker}\n\n"
        f"Recent price data:\n{price_context}\n\n"
        f"Question: {question}"
    )

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=512,
        temperature=0.3,
    )
    return response.choices[0].message.content


async def analyze_with_anthropic(ticker: str, prices: list[dict], question: str) -> str:
    """Call Anthropic Claude messages API."""
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    price_context = _format_price_context(prices)
    user_msg = (
        f"Ticker: {ticker}\n\n"
        f"Recent price data:\n{price_context}\n\n"
        f"Question: {question}"
    )

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text


async def analyze(ticker: str, prices: list[dict], question: str) -> tuple[str, str]:
    """Route to the configured LLM provider.

    Returns:
        (analysis_text, provider_name)
    """
    provider = get_settings().llm_provider.lower()
    logger.info("Running analysis for %s via %s", ticker, provider)

    if provider == "openai":
        text = await analyze_with_openai(ticker, prices, question)
        return text, "openai"
    else:
        text = await analyze_with_anthropic(ticker, prices, question)
        return text, "anthropic"
