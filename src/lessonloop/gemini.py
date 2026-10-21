"""Gemini adapter; credentials are read only when a live run is requested."""

import asyncio
import os

from google import genai
from google.genai import types

from lessonloop.generation import Lesson


class GeminiModel:
    def __init__(self, *, api_key: str, model: str):
        self.model = model
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)),
        )

    @classmethod
    def from_environment(cls) -> "GeminiModel":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        model = os.environ.get("GEMINI_MODEL", "").strip()
        if not key or not model:
            raise ValueError("Set GEMINI_API_KEY and GEMINI_MODEL in your environment before using --live.")
        return cls(api_key=key, model=model)

    async def complete(self, *, system: str, user: str) -> str:
        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=Lesson,
                        max_output_tokens=6000,
                    ),
                ), timeout=65,
            )
            if not response.text:
                raise RuntimeError("Empty response")
            return response.text
        except Exception:
            raise RuntimeError("Gemini generation failed. Check model access, quota, credentials, and connectivity.") from None

    async def close(self) -> None:
        await self.client.aio.aclose()
        self.client.close()
