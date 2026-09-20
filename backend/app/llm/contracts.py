"""Provider-neutral model request, response, and error contracts."""

from __future__ import annotations

from threading import Event
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any]


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["developer", "system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


class StructuredOutputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    json_schema: dict[str, Any] = Field(alias="schema")
    strict: bool = True


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=64)
    messages: list[ModelMessage] = Field(min_length=1)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    response_format: StructuredOutputSpec | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelCompletion(BaseModel):
    provider: str
    model: str
    content: str | None = None
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = Field(default=0, ge=0)
    attempt_count: int = Field(default=1, ge=1)


class ModelHealth(BaseModel):
    provider: str
    model: str
    available: bool
    message: str
    latency_ms: int = Field(default=0, ge=0)


class CancellationToken:
    """Thread-safe cooperative cancellation shared by API and runtime."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def wait(self, seconds: float) -> bool:
        return self._event.wait(seconds)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ModelProviderError("MODEL_CANCELLED", "模型调用已取消", retryable=False)


class ModelProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status
