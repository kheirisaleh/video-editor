"""One small interface over the supported model providers: ask for JSON, get a dict.

* anthropic: the Claude API through the official SDK, with structured outputs and
  server side refusal fallback.
* openai: any OpenAI compatible server, e.g. Ollama on the gaming PC
  (http://<ip>:11434/v1), LM Studio, vLLM or llama.cpp.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import httpx

from studio.ai.settings import AiSettings

log = logging.getLogger(__name__)

# Models that accept the server side refusal fallback (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AiError(RuntimeError):
    """The model could not be reached or did not return a usable answer."""


@dataclass(frozen=True)
class Image:
    data: bytes
    media_type: str = "image/jpeg"

    @property
    def b64(self) -> str:
        return base64.standard_b64encode(self.data).decode("ascii")


Part = str | Image


@dataclass
class Usage:
    """Tokens of one call, as reported by the provider."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class AiClient(Protocol):
    name: str

    def json(
        self,
        *,
        system: str,
        parts: list[Part],
        schema: dict[str, Any],
        vision: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]: ...


def make_client(settings: AiSettings) -> AiClient | None:
    if settings.provider == "anthropic":
        return ClaudeClient(settings)
    if settings.provider == "openai":
        if not settings.base_url:
            raise AiError("the OpenAI compatible provider needs a base URL")
        return OpenAICompatibleClient(settings)
    return None


class ClaudeClient:
    def __init__(self, settings: AiSettings) -> None:
        self.settings = settings
        self.last_usage: Usage | None = None
        self.name = f"Claude ({settings.model_for(False)})"
        self.client = anthropic.Anthropic(
            api_key=settings.resolved_api_key(),
            base_url=settings.base_url or None,
            timeout=settings.timeout,
            max_retries=2,
        )

    def json(
        self,
        *,
        system: str,
        parts: list[Part],
        schema: dict[str, Any],
        vision: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        model = self.settings.model_for(vision)
        content: list[dict[str, Any]] = []
        for part in parts:
            if isinstance(part, Image):
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": part.media_type,
                            "data": part.b64,
                        },
                    }
                )
            else:
                content.append({"type": "text", "text": part})
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "effort": self.settings.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        try:
            if model in FALLBACK_MODELS:
                response = self.client.beta.messages.create(
                    **request, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self.client.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise AiError("the Claude API key was rejected") from exc
        except anthropic.PermissionDeniedError as exc:
            raise AiError(f"the API key may not use {model}") from exc
        except anthropic.NotFoundError as exc:
            raise AiError(f"model {model} not found") from exc
        except anthropic.RateLimitError as exc:
            raise AiError("rate limited by the Claude API, try again later") from exc
        except anthropic.BadRequestError as exc:
            raise AiError(f"request rejected: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise AiError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AiError("cannot reach the Claude API") from exc

        u = response.usage
        self.last_usage = Usage(
            model=response.model or model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        if response.stop_reason == "refusal":
            raise AiError("the model declined this request")
        if response.stop_reason == "max_tokens":
            raise AiError("the answer was cut off (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), "")
        return parse_json(text)


class OpenAICompatibleClient:
    def __init__(self, settings: AiSettings) -> None:
        self.settings = settings
        self.base = settings.base_url.rstrip("/")
        self.name = f"{settings.model_for(False) or 'model'} at {self.base}"
        headers = {}
        if key := settings.resolved_api_key():
            headers["Authorization"] = f"Bearer {key}"
        self.http = httpx.Client(timeout=settings.timeout, headers=headers)
        self._json_schema_supported = True
        self.last_usage: Usage | None = None

    def json(
        self,
        *,
        system: str,
        parts: list[Part],
        schema: dict[str, Any],
        vision: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        model = self.settings.model_for(vision)
        if not model:
            raise AiError("no model name configured")
        content: list[dict[str, Any]] = []
        for part in parts:
            if isinstance(part, Image):
                url = f"data:{part.media_type};base64,{part.b64}"
                content.append({"type": "image_url", "image_url": {"url": url}})
            else:
                content.append({"type": "text", "text": part})
        schema_hint = (
            "\n\nAnswer with one JSON object that matches this JSON schema, and nothing else:\n"
            + json.dumps(schema)
        )
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": system + schema_hint},
                {"role": "user", "content": content},
            ],
        }
        if self._json_schema_supported:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            }
        else:
            body["response_format"] = {"type": "json_object"}

        data = self._post(body)
        u = data.get("usage") or {}
        self.last_usage = Usage(
            model=model,
            input_tokens=int(u.get("prompt_tokens") or 0),
            output_tokens=int(u.get("completion_tokens") or 0),
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AiError(f"unexpected answer from {self.base}") from exc
        if data["choices"][0].get("finish_reason") == "length":
            raise AiError("the answer was cut off (max_tokens)")
        return parse_json(text)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base}/chat/completions"
        try:
            res = self.http.post(url, json=body)
            if (
                res.status_code == 400
                and self._json_schema_supported
                and "response_format" in res.text
            ):
                # Older servers know only json_object; the schema is in the prompt anyway.
                self._json_schema_supported = False
                body["response_format"] = {"type": "json_object"}
                res = self.http.post(url, json=body)
        except httpx.ConnectError as exc:
            raise AiError(f"cannot reach {self.base} (is the model server running?)") from exc
        except httpx.TimeoutException as exc:
            raise AiError(f"{self.base} did not answer in {self.settings.timeout:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise AiError(f"connection to {self.base} failed: {exc}") from exc
        if res.status_code == 401:
            raise AiError("the API key was rejected")
        if res.status_code == 404:
            raise AiError(f"model or endpoint not found at {self.base}: {res.text[:200]}")
        if res.status_code >= 400:
            raise AiError(f"{self.base} answered {res.status_code}: {res.text[:300]}")
        try:
            return res.json()
        except ValueError as exc:
            raise AiError(f"{self.base} did not answer with JSON") from exc


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating code fences or chatter around it."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        value = json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise AiError("the model did not answer with JSON") from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except ValueError as exc:
            raise AiError("the model answered with broken JSON") from exc
    if not isinstance(value, dict):
        raise AiError("the model answered with JSON that is not an object")
    return value
