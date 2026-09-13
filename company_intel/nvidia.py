"""Async NVIDIA API Catalog adapter for the extractor's small messages interface.

Only this module knows NVIDIA's wire format. The rest of the pipeline retains the
same Pydantic schema, evidence validation, retry policy and per-domain usage ledger.
"""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx2

from .retry_policy import retry_after_seconds

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaAPIError(RuntimeError):
    def __init__(self, status_code: int, request_id: str = "", retry_after: str | None = None):
        self.status_code = status_code
        self.retry_after = retry_after_seconds(retry_after)
        super().__init__(f"NVIDIA API HTTP {status_code}" + (f" (request {request_id})" if request_id else ""))


@dataclass
class ToolBlock:
    id: str
    name: str
    input: Any
    type: str = field(default="tool_use", init=False)

    def model_dump(self, **_kwargs) -> dict:
        return {"type": self.type, "id": self.id, "name": self.name, "input": self.input}


@dataclass
class TextBlock:
    text: str
    type: str = field(default="text", init=False)

    def model_dump(self, **_kwargs) -> dict:
        return {"type": self.type, "text": self.text}


def convert_messages(system: str, messages: list[dict]) -> list[dict]:
    """Translate tool calls/results without losing IDs or leaking raw page content."""
    wire: list[dict] = [{"role": "system", "content": system}]
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            wire.append({"role": message["role"], "content": content})
        elif message["role"] == "assistant":
            calls, texts = [], []
            for block in content:
                if block["type"] == "tool_use":
                    calls.append({"id": block["id"], "type": "function", "function": {
                        "name": block["name"], "arguments": json.dumps(block["input"], ensure_ascii=False),
                    }})
                elif block["type"] == "text":
                    texts.append(block["text"])
            entry: dict = {"role": "assistant", "content": "\n".join(texts) or None}
            if calls:
                entry["tool_calls"] = calls
            wire.append(entry)
        else:
            for block in content:
                if block["type"] == "tool_result":
                    wire.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": block["content"]})
                elif block["type"] == "text":
                    wire.append({"role": "user", "content": block["text"]})
    return wire


def inline_schema(schema: dict) -> dict:
    """Inline Pydantic's local refs: NVIDIA's forced-tool grammar rejects $defs refs."""
    def visit(node, trail: tuple[str, ...] = ()):
        if isinstance(node, dict):
            if "$ref" in node:
                reference = node["$ref"]
                if not reference.startswith("#/$defs/") or reference in trail:
                    raise ValueError("Only acyclic local Pydantic schema references are supported")
                return visit(schema["$defs"][reference.split("/")[-1]], trail + (reference,))
            return {key: visit(value, trail) for key, value in node.items() if key != "$defs"}
        if isinstance(node, list):
            return [visit(value, trail) for value in node]
        return node
    return visit(schema)


def build_payload(*, model: str, system: str, messages: list[dict], tools: list[dict], tool_choice: dict,
                  max_tokens: int = 3000) -> dict:
    wire_tools = [{"type": "function", "function": {
        "name": tool["name"], "description": tool["description"],
        "parameters": inline_schema(tool["input_schema"]), "strict": True,
    }} for tool in tools]
    choice = ({"type": "function", "function": {"name": tool_choice["name"]}}
              if tool_choice["type"] == "tool" else "auto")
    payload = {"model": model, "messages": convert_messages(system, messages), "tools": wire_tools,
               "tool_choice": choice, "max_tokens": max_tokens, "temperature": 0, "stream": False}
    if "nemotron-3-" in model:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return payload


class NvidiaClient:
    """NVIDIA hosted inference; no credentials are included in saved request metadata."""

    def __init__(self, api_key: str, *, transport=None):
        self.messages = self
        self.http = httpx2.AsyncClient(
            base_url=NVIDIA_BASE_URL,
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            timeout=httpx2.Timeout(120, connect=20), follow_redirects=False, transport=transport,
        )

    async def count_tokens(self, **kwargs):
        # The hosted API has no documented count-tokens endpoint. Use UTF-8 bytes of
        # the whole wire request plus a chat-template allowance, a deliberately
        # conservative estimate rather than mislabeling chars/4 as a measured count.
        payload = build_payload(**kwargs)
        estimate = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 1024
        return SimpleNamespace(input_tokens=estimate)

    async def create(self, **kwargs):
        payload = build_payload(**kwargs)
        response = await self.http.post("/chat/completions", json=payload)
        if response.status_code != 200:
            # Do not put the request headers/body or provider error body in logs.
            raise NvidiaAPIError(response.status_code, response.headers.get("x-request-id", ""),
                                 response.headers.get("retry-after"))
        raw = response.json()
        usage = raw.get("usage") or {}
        if not all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
            raise ValueError("NVIDIA response omitted measured token usage; cannot report an accurate cost")
        choice = next(iter(raw.get("choices") or []), {})
        message = choice.get("message") or {}
        blocks = []
        for tool in message.get("tool_calls") or []:
            function = tool.get("function") or {}
            arguments = function.get("arguments", "")
            try:
                parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
            except ValueError:
                # Keep the failed payload for Pydantic to reject after usage is recorded.
                parsed = arguments
            blocks.append(ToolBlock(tool.get("id", ""), function.get("name", ""), parsed))
        if message.get("content"):
            blocks.append(TextBlock(message["content"]))
        finish = choice.get("finish_reason", "missing_choices")
        return SimpleNamespace(
            id=raw.get("id", response.headers.get("x-request-id", "unreported")),
            usage=SimpleNamespace(input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"]),
            stop_reason="tool_use" if finish == "tool_calls" else finish,
            content=blocks,
        )

    async def close(self) -> None:
        await self.http.aclose()
