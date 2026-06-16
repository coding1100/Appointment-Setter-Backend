"""
Shared non-streaming Gemini text generation for one-shot API tasks.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import CHATBOT_STREAM_TIMEOUT_SECONDS, CHATBOT_TEXT_MODEL, GOOGLE_API_KEY


def extract_text_from_response(payload: Dict[str, Any]) -> str:
    texts: List[str] = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
    return "".join(texts)


async def generate_text(
    *,
    user_message: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.4,
    max_output_tokens: int = 4096,
) -> str:
    if not GOOGLE_API_KEY:
        raise ValueError("Gemini is not configured (missing GOOGLE_API_KEY).")

    message = user_message.strip()
    if not message:
        raise ValueError("Prompt message cannot be empty.")

    model = CHATBOT_TEXT_MODEL.strip() or "gemini-2.5-flash-lite"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GOOGLE_API_KEY,
    }

    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    timeout = httpx.Timeout(float(CHATBOT_STREAM_TIMEOUT_SECONDS), connect=10.0)
    max_attempts = 3
    last_error = "Failed to generate text with Gemini."

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(endpoint, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"Gemini request failed: {exc}"
                if attempt < max_attempts:
                    await asyncio.sleep(float(attempt * 1.5))
                    continue
                raise ValueError(last_error) from exc

            if response.status_code >= 400:
                error_body = response.text[:300]
                if response.status_code in {429, 500, 502, 503, 504} and attempt < max_attempts:
                    await asyncio.sleep(float(attempt * 1.5))
                    continue
                if response.status_code == 429:
                    raise ValueError("Prompt enhancement is temporarily rate-limited. Please try again shortly.")
                raise ValueError(f"Gemini request failed ({response.status_code}): {error_body}")

            try:
                response_payload = response.json()
            except ValueError as exc:
                raise ValueError("Gemini returned an invalid response.") from exc

            text = extract_text_from_response(response_payload).strip()
            if text:
                return text

            last_error = "Gemini returned an empty response."
            if attempt < max_attempts:
                await asyncio.sleep(float(attempt * 1.5))

    raise ValueError(last_error)
