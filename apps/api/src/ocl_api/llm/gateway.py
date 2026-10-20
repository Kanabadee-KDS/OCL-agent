"""Thin LLM gateway.

Written in-house instead of LangChain because every Ollama request must carry the
exact options the shared server requires (num_ctx, keep_alive, think=false) and
those must be visible and testable here, not buried in a framework.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from ocl_api.config import Settings, get_settings

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


@dataclass
class LLMUsage:
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    calls: int = 0
    retries: int = 0

    def add(self, other: LLMUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.seconds += other.seconds
        self.calls += other.calls
        self.retries += other.retries

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LLMResult:
    data: Any
    raw: str
    usage: LLMUsage = field(default_factory=lambda: LLMUsage("none", "none"))


class LLMError(RuntimeError):
    pass


class LLMTruncated(LLMError):
    """The model hit max_tokens before finishing; usage is attached for accounting."""

    def __init__(self, msg: str, usage: LLMUsage | None = None):
        super().__init__(msg)
        self.usage = usage


def parse_json_text(text: str) -> Any:
    """Parse a model reply that should be JSON; tolerate code fences and leading prose."""
    s = _FENCE.sub("", text.strip())
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (s.find("{"), s.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError(f"no JSON in reply: {text[:200]!r}")
    end = max(s.rfind("}"), s.rfind("]"))
    return json.loads(s[start : end + 1])


class LLMGateway:
    """`chat_json(system, user)` -> parsed JSON + usage, for the configured provider."""

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self._client = client or httpx.Client(timeout=httpx.Timeout(900.0, connect=10.0))

    @property
    def provider(self) -> str:
        return self.settings.llm_provider

    @property
    def model(self) -> str:
        return self.settings.ollama_model if self.provider == "ollama" else "gemini"

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 4096,
        retries: int = 1,
    ) -> LLMResult:
        if self.provider == "gemini":
            raise LLMError("Gemini provider is not configured yet (interface reserved)")
        usage = LLMUsage(self.provider, self.model)
        last_err: Exception | None = None
        prompt_user = user
        for _attempt in range(retries + 1):
            raw, u, done_reason = self._ollama_chat(system, prompt_user, schema, max_tokens)
            usage.add(u)
            if done_reason == "length":
                # Retrying the same prompt cannot help; the caller must send less text.
                raise LLMTruncated(f"reply truncated at max_tokens={max_tokens}", usage)
            try:
                data = parse_json_text(raw)
                return LLMResult(data=data, raw=raw, usage=usage)
            except (LLMError, json.JSONDecodeError) as e:
                last_err = e
                usage.retries += 1
                prompt_user = user + "\n\nตอบเป็น JSON ที่ถูกต้องเท่านั้น ห้ามมีข้อความอื่น"
        raise LLMError(f"model did not return valid JSON after {retries + 1} attempts: {last_err}")

    # ---------- providers ----------

    def _ollama_chat(
        self, system: str, user: str, schema: dict[str, Any] | None, max_tokens: int
    ) -> tuple[str, LLMUsage, str | None]:
        s = self.settings
        body: dict[str, Any] = {
            "model": s.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": s.ollama_think,
            "format": schema if schema else "json",
            "options": {"num_predict": max_tokens, "temperature": 0},
        }
        # Shared-server rules (docs/server-constraints.md rule 2) are enforced by Settings:
        # OCL models always send num_ctx + a short keep_alive; the HRIS model sends -1 and no ctx.
        if s.ollama_num_ctx is not None:
            body["options"]["num_ctx"] = s.ollama_num_ctx
        if s.ollama_keep_alive is not None:
            ka = s.ollama_keep_alive.strip()
            body["keep_alive"] = -1 if ka == "-1" else ka  # -1 must be numeric for Ollama
        t0 = time.perf_counter()
        try:
            r = self._client.post(f"{s.ollama_base_url.rstrip('/')}/api/chat", json=body)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"ollama request failed: {e}") from e
        data = r.json()
        usage = LLMUsage(
            provider="ollama",
            model=s.ollama_model,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
            seconds=round(time.perf_counter() - t0, 3),
            calls=1,
        )
        content = (data.get("message") or {}).get("content") or ""
        return content, usage, data.get("done_reason")
