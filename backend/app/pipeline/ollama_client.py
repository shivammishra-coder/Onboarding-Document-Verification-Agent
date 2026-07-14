"""
Shared Ollama HTTP helpers: retry/backoff and <think> block stripping.
Both Stage 1 (classification) and Stage 3 (extraction) call the same
Ollama endpoint, so this logic lives here once instead of being copied
into each stage file.
"""
import asyncio
import re
from typing import Optional, Tuple

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_USERNAME, OLLAMA_PASSWORD, OLLAMA_MODEL

OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 3
THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking_blocks(content: str) -> str:
    """qwen3/gpt-oss-style models can prepend <think>...</think> even in
    JSON mode - strip it so json.loads doesn't choke. No-op for llama3.1."""
    stripped = THINK_BLOCK_PATTERN.sub("", content).strip()
    return stripped if stripped else content


def build_payload(prompt: str) -> dict:
    return {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }


def get_auth_tuple() -> Optional[Tuple[str, str]]:
    if OLLAMA_USERNAME and OLLAMA_PASSWORD:
        return (OLLAMA_USERNAME, OLLAMA_PASSWORD)
    return None


async def call_ollama_with_retry(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    """Retries on 429/5xx and connection errors, with exponential backoff,
    respecting Retry-After when the server sends it."""
    last_exception: Optional[Exception] = None
    response: Optional[httpx.Response] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = await client.post(OLLAMA_CHAT_URL, json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as err:
            last_exception = err
            wait_seconds = BASE_BACKOFF_SECONDS * (2 ** attempt)
            print(f"  [connection issue] {err!r} - waiting {wait_seconds:.1f}s (retry {attempt + 1}/{MAX_RETRIES})...")
            await asyncio.sleep(wait_seconds)
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            wait_seconds = float(retry_after) if retry_after else BASE_BACKOFF_SECONDS * (2 ** attempt)
            print(f"  [rate limited] waiting {wait_seconds:.1f}s (retry {attempt + 1}/{MAX_RETRIES})...")
            await asyncio.sleep(wait_seconds)
            continue

        if response.status_code >= 500:
            print(f"  [server error {response.status_code}] waiting before retry {attempt + 1}/{MAX_RETRIES}...")
            await asyncio.sleep(BASE_BACKOFF_SECONDS * (2 ** attempt))
            continue

        response.raise_for_status()
        return response

    if last_exception:
        raise last_exception
    raise httpx.HTTPStatusError(
        f"Ollama API failed after {MAX_RETRIES} retries", request=response.request, response=response,
    )