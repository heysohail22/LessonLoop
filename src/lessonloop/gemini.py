"""Gemini adapter; credentials are read only when a live run is requested."""

import asyncio
import os

from google import genai
from google.genai import errors, types
import httpx
from pydantic import BaseModel

from lessonloop.generation import Lesson


class GenerationError(RuntimeError):
    """A credential-safe explanation that can be displayed to the user."""


class GeminiModel:
    def __init__(self, *, api_key: str, model: str, response_type: type[BaseModel] = Lesson):
        self.model = model
        self.response_type = response_type
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
                        response_json_schema=getattr(self, "response_type", Lesson).model_json_schema(),
                        max_output_tokens=6000,
                    ),
                ), timeout=65,
            )
            if not response.text:
                raise GenerationError("Gemini returned no lesson text. The response may have been blocked or incomplete. Try again.")
            return response.text
        except GenerationError:
            raise
        except errors.APIError as error:
            messages = {
                400: "Gemini rejected the request (400). Check that the API key is valid and the selected model supports structured JSON output.",
                401: "Gemini authentication failed (401). Replace GEMINI_API_KEY with a valid key.",
                403: "Gemini denied access (403). Check the API key restrictions and access to this model.",
                404: "Gemini model was not found (404). Set GEMINI_MODEL to an available model ID that supports generateContent.",
                429: "Gemini quota or rate limit reached (429). Check your project's quota and billing, or wait before retrying.",
            }
            message = messages.get(error.code, "Gemini is temporarily unavailable. Try again shortly.")
            raise GenerationError(message) from None
        except (TimeoutError, httpx.TimeoutException):
            raise GenerationError("Gemini took too long to respond. Try again or use a faster model.") from None
        except (httpx.TransportError, OSError):
            raise GenerationError("Could not connect to Gemini. Check your internet connection, proxy, and firewall.") from None
        except Exception:
            raise GenerationError("The Gemini request failed unexpectedly. Check the model configuration and try again.") from None

    async def close(self) -> None:
        await self.client.aio.aclose()
        self.client.close()
