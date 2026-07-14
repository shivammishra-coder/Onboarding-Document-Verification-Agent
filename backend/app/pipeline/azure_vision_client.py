"""
app/pipeline/azure_vision_client.py

Shared Azure OpenAI (GPT-5 mini, vision-capable) client used by both
Stage 1 (single-page classification) and Stage 3 (multi-page structured
extraction). Centralizes: building vision-format chat messages, base64
data-URL encoding for images, and retry/backoff on transient failures -
same pattern as your Ollama client for the OCR-based pipeline.
"""
import asyncio
import base64
from typing import Any, Dict, List, Optional

from openai import AsyncAzureOpenAI

from app.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 3

_client: Optional[AsyncAzureOpenAI] = None


def _get_client() -> AsyncAzureOpenAI:
    """Lazily creates a single shared client - not one per call."""
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _client


def image_to_data_url(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Encodes raw image bytes as a base64 data URL for the vision API."""
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def build_vision_message(prompt: str, image_urls: List[str]) -> List[Dict[str, Any]]:
    """
    Builds an OpenAI-format chat message with one text block + one or
    more image blocks, in the shape the vision-capable chat completions
    endpoint expects.
    """
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})

    return [{"role": "user", "content": content}]


async def call_vision_with_retry(
    messages: List[Dict[str, Any]],
    response_format: Optional[Dict[str, str]] = None,
) -> str:
    """
    Calls Azure OpenAI's chat completions endpoint with retry/backoff on
    rate limits (429) and transient server errors (5xx). Returns the
    assistant message's text content as a plain string.
    """
    client = _get_client()
    last_exception: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            kwargs: Dict[str, Any] = {
                "model": AZURE_OPENAI_DEPLOYMENT,
                "messages": messages
                
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content

        except Exception as err:  # noqa: BLE001
            last_exception = err
            status_code = getattr(err, "status_code", None)

            is_retryable = status_code == 429 or (status_code is not None and status_code >= 500)
            if not is_retryable or attempt == MAX_RETRIES - 1:
                raise

            wait_seconds = BASE_BACKOFF_SECONDS * (2 ** attempt)
            print(f"  [azure_vision_client] {err!r} - waiting {wait_seconds:.1f}s (retry {attempt + 1}/{MAX_RETRIES})...")
            await asyncio.sleep(wait_seconds)

    raise last_exception  # pragma: no cover - unreachable, satisfies type checkers"temperature": 0