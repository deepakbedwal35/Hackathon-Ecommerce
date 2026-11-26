from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Any, Callable

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger("agent.llm")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(ABC):
    @abstractmethod
    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Executes a chat completion turn with native tool calling."""
        pass


class GeminiClient(LLMClient):
    """Native Google Gemini API adapter using REST endpoint over httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL or "gemini-1.5-flash"
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        # Convert OpenAI-style tools to Gemini function declarations
        gemini_tools = []
        if tools:
            func_decls = []
            for t in tools:
                fn = t.get("function", t)
                func_decls.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                })
            gemini_tools.append({"function_declarations": func_decls})

        # Format contents
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "customer") else "model"
            parts = []
            if "content" in m and m["content"]:
                parts.append({"text": m["content"]})
            if "tool_calls" in m:
                for tc in m["tool_calls"]:
                    parts.append({
                        "functionCall": {
                            "name": tc["name"],
                            "args": tc["arguments"],
                        }
                    })
            if "tool_call_id" in m or m.get("role") == "tool":
                role = "user"
                fn_name = m.get("name", "tool_result")
                content_val = m.get("content", "{}")
                try:
                    resp_dict = json.loads(content_val) if isinstance(content_val, str) else content_val
                except Exception:
                    resp_dict = {"raw": content_val}
                parts.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": resp_dict,
                    }
                })
            if parts:
                contents.append({"role": role, "parts": parts})

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.0},
        }
        if gemini_tools:
            payload["tools"] = gemini_tools

        with httpx.Client(timeout=float(self.timeout)) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error("gemini_api_error", status_code=resp.status_code, body=resp.text)
                raise RuntimeError(f"Gemini API returned status {resp.status_code}: {resp.text}")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return LLMResponse(text="")

            first_cand = candidates[0].get("content", {})
            parts = first_cand.get("parts", [])
            text_chunks = []
            tool_calls = []

            for idx, p in enumerate(parts):
                if "text" in p:
                    text_chunks.append(p["text"])
                if "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{idx}_{fc['name']}",
                            name=fc["name"],
                            arguments=fc.get("args", {}),
                        )
                    )

            return LLMResponse(
                text=" ".join(text_chunks).strip() if text_chunks else None,
                tool_calls=tool_calls,
            )


class OpenAIClient(LLMClient):
    """OpenAI-compatible chat completion client with native tool calling."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL or "gpt-4o"
        self.base_url = (
            base_url
            or getattr(settings, "LLM_BASE_URL", None)
            or "https://api.openai.com/v1/chat/completions"
        )
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        formatted_messages = [{"role": "system", "content": system}]
        for m in messages:
            msg_copy = dict(m)
            if "tool_calls" in msg_copy and msg_copy["tool_calls"]:
                clean_tool_calls = []
                for tc in msg_copy["tool_calls"]:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name") or tc.get("name", "")
                    fn_args = fn.get("arguments") if "arguments" in fn else tc.get("arguments", {})
                    if isinstance(fn_args, dict):
                        fn_args = json.dumps(fn_args)
                    clean_tool_calls.append({
                        "id": tc.get("id", f"call_{fn_name}"),
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": fn_args,
                        },
                    })
                msg_copy = {
                    "role": msg_copy.get("role", "assistant"),
                    "content": msg_copy.get("content") or None,
                    "tool_calls": clean_tool_calls,
                }
            elif msg_copy.get("role") == "tool":
                msg_copy = {
                    "role": "tool",
                    "tool_call_id": msg_copy.get("tool_call_id", ""),
                    "name": msg_copy.get("name", ""),
                    "content": msg_copy.get("content", ""),
                }
            else:
                msg_copy = {
                    "role": msg_copy.get("role", "user"),
                    "content": msg_copy.get("content", ""),
                }
            formatted_messages.append(msg_copy)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": 0.0,
        }
        if tools:
            payload["tools"] = tools

        with httpx.Client(timeout=float(self.timeout)) as client:
            resp = client.post(self.base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error("openai_api_error", status_code=resp.status_code, body=resp.text)
                raise RuntimeError(f"OpenAI API returned status {resp.status_code}: {resp.text}")

            data = resp.json()
            choice = data["choices"][0]["message"]
            text_resp = choice.get("content")
            raw_calls = choice.get("tool_calls") or []
            tool_calls = []
            for rc in raw_calls:
                fn = rc["function"]
                args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                tool_calls.append(ToolCall(id=rc["id"], name=fn["name"], arguments=args))

            return LLMResponse(text=text_resp, tool_calls=tool_calls)


class GroqClient(OpenAIClient):
    """
    Groq API client using OpenAI-compatible chat completions with native tool calling.
    Supports openai/gpt-oss-120b and other open-source models with reasoning and tool calling.
    """

    MODEL_ALIASES = {
        "oss-120b": "openai/gpt-oss-120b",
        "gpt-oss-120b": "openai/gpt-oss-120b",
        "openai/gpt-oss-120b": "openai/gpt-oss-120b",
        "oss-20b": "openai/gpt-oss-20b",
        "gpt-oss-20b": "openai/gpt-oss-20b",
        "openai/gpt-oss-20b": "openai/gpt-oss-20b",
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "llama-70b": "llama-3.3-70b-versatile",
    }

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        base_url: str | None = None,
    ):
        raw_key = api_key or getattr(settings, "GROQ_API_KEY", None) or settings.LLM_API_KEY
        raw_model = model or getattr(settings, "LLM_MODEL", None) or "openai/gpt-oss-120b"
        resolved_model = self.MODEL_ALIASES.get(raw_model.lower(), raw_model)
        resolved_base_url = (
            base_url
            or getattr(settings, "LLM_BASE_URL", None)
            or "https://api.groq.com/openai/v1/chat/completions"
        )
        super().__init__(
            api_key=raw_key,
            model=resolved_model,
            base_url=resolved_base_url,
            timeout=timeout,
        )


class FakeLLMClient(LLMClient):
    """
    Deterministic mock client for testing.
    Pops responses from an in-memory queue.
    """

    def __init__(
        self,
        responses: list[LLMResponse | Callable[[list[dict[str, Any]]], LLMResponse]] | None = None,
    ):
        self.responses: list[LLMResponse | Callable[[list[dict[str, Any]]], LLMResponse]] = list(responses or [])
        self.call_history: list[dict[str, Any]] = []

    def queue_response(self, resp: LLMResponse | Callable[[list[dict[str, Any]]], LLMResponse]) -> None:
        self.responses.append(resp)

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.call_history.append({
            "system": system,
            "messages": list(messages),
            "tools": tools,
        })
        if not self.responses:
            return LLMResponse(text="I am here to assist you.")
        next_item = self.responses.pop(0)
        if callable(next_item):
            return next_item(messages)
        return next_item


def get_default_llm_client() -> LLMClient:
    """Factory creating the configured LLMClient based on settings."""
    provider = getattr(settings, "LLM_PROVIDER", "").lower()
    api_key = (
        getattr(settings, "GROQ_API_KEY", None)
        or getattr(settings, "LLM_API_KEY", "")
    )
    model = getattr(settings, "LLM_MODEL", "").lower()

    if (
        provider in ("groq", "groqcloud")
        or api_key.startswith("gsk_")
        or "oss" in model
        or getattr(settings, "GROQ_API_KEY", None)
    ):
        return GroqClient()

    if provider == "openai":
        return OpenAIClient()

    return GeminiClient()
