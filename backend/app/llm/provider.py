"""Switchable mock, remote, and local OpenAI-compatible model providers."""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal
from time import monotonic
from typing import Any, Literal, Protocol
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings, get_settings
from app.llm.contracts import (
    CancellationToken,
    ModelCompletion,
    ModelHealth,
    ModelMessage,
    ModelProviderError,
    ModelRequest,
    ModelToolCall,
    TokenUsage,
)

ScriptedResponse = ModelCompletion | Callable[[ModelRequest], ModelCompletion]

_MONTH_PATTERN = re.compile(r"(20\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月")
_YUAN_PATTERN = re.compile(r"(\d+(?:\.\d{1,2})?)\s*元")
_QUOTED_MERCHANT_PATTERN = re.compile(r"[“\"']([^”\"']{1,120})[”\"']")


class ModelProvider(Protocol):
    provider: str
    model: str

    def health(self) -> ModelHealth: ...

    def complete(
        self,
        request: ModelRequest,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelCompletion: ...


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _format_yuan(minor: int) -> str:
    return f"{Decimal(minor) / Decimal(100):.2f}"


def _validated_base_url(value: str, mode: Literal["remote", "local"]) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "LLM_BASE_URL 必须是 HTTP(S) 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "LLM_BASE_URL 不能包含认证信息、查询或片段")
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if mode == "local" and parsed.hostname not in loopback_hosts:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "local Provider 只允许连接回环地址")
    if mode == "remote" and parsed.scheme != "https" and parsed.hostname not in loopback_hosts:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "remote Provider 的非回环地址必须使用 HTTPS")
    return value.rstrip("/")


def _message_payload(message: ModelMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.name and message.role != "tool":
        payload["name"] = message.name
    return payload


class MockModelProvider:
    """Deterministic scripted Provider for tests and model-free development."""

    provider = "mock"

    def __init__(
        self,
        model: str = "mock-model",
        script: Sequence[ScriptedResponse] | None = None,
    ) -> None:
        self.model = model
        self._script = deque(script or [])

    def health(self) -> ModelHealth:
        return ModelHealth(
            provider=self.provider,
            model=self.model,
            available=True,
            message="mock provider ready",
        )

    def complete(
        self,
        request: ModelRequest,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelCompletion:
        if cancellation_token:
            cancellation_token.raise_if_cancelled()
        if self._script:
            scripted = self._script.popleft()
            completion = scripted(request) if callable(scripted) else scripted
            return completion.model_copy(update={"provider": self.provider, "model": self.model})
        if request.messages[-1].role == "tool":
            return self._answer_tool_result(request.messages[-1])
        return self._select_tool(request)

    def _select_tool(self, request: ModelRequest) -> ModelCompletion:
        query = next(
            (
                message.content or ""
                for message in reversed(request.messages)
                if message.role == "user"
            ),
            "",
        )
        available = {
            item.get("function", {}).get("name") for item in request.tools if isinstance(item, dict)
        }
        tool_name = "get_spending_summary"
        if "预算" in query:
            tool_name = "get_budget_status"
        elif any(word in query for word in ("类别", "分类", "构成")):
            tool_name = "get_category_breakdown"
        elif any(word in query for word in ("趋势", "走势", "每天", "每周", "每月")):
            tool_name = "get_trend"
        elif any(word in query for word in ("大额", "超过", "高于")):
            tool_name = "get_large_transactions"
        elif any(word in query for word in ("商户排行", "商家排行", "花得最多")):
            tool_name = "get_top_merchants"
        elif "历史" in query and _QUOTED_MERCHANT_PATTERN.search(query):
            tool_name = "get_merchant_history"
        elif any(word in query for word in ("对比", "比较", "环比", "同比")):
            tool_name = "compare_periods"
        elif any(word in query for word in ("明细", "搜索", "查找", "哪几笔")):
            tool_name = "search_transactions"

        if tool_name not in available:
            return ModelCompletion(
                provider=self.provider,
                model=self.model,
                content="mock provider 没有可用的只读 Tool。",
                usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
        date_from, date_to = self._period(query)
        arguments: dict[str, Any] = {"from": date_from, "to": date_to}
        yuan_match = _YUAN_PATTERN.search(query)
        amount_minor = int(Decimal(yuan_match.group(1)) * 100) if yuan_match is not None else None
        if tool_name == "get_budget_status":
            arguments["budget_minor"] = amount_minor or 100_000
        elif tool_name == "get_category_breakdown":
            arguments["direction"] = "income" if "收入" in query else "expense"
        elif tool_name == "get_trend":
            arguments["granularity"] = (
                "day" if "每天" in query else "week" if "每周" in query else "month"
            )
        elif tool_name == "get_large_transactions":
            arguments.update(
                direction="income" if "收入" in query else "expense",
                threshold_minor=amount_minor or 10_000,
                limit=20,
            )
        elif tool_name == "get_top_merchants":
            arguments.update(
                direction="income" if "收入" in query else "expense",
                limit=10,
            )
        elif tool_name == "compare_periods":
            current_start = datetime.fromisoformat(date_from)
            current_end = datetime.fromisoformat(date_to)
            comparison_from = current_start - (current_end - current_start)
            arguments.update(
                compare_from=comparison_from.isoformat(),
                compare_to=date_from,
                mode="yoy" if "同比" in query else "previous",
            )
        elif tool_name == "search_transactions":
            arguments.update(page=1, page_size=20)
        elif tool_name == "get_merchant_history":
            merchant_match = _QUOTED_MERCHANT_PATTERN.search(query)
            arguments.update(
                merchant=merchant_match.group(1),
                page=1,
                page_size=20,
            )

        return ModelCompletion(
            provider=self.provider,
            model=self.model,
            tool_calls=[ModelToolCall(id="mock_call_1", name=tool_name, arguments=arguments)],
            finish_reason="tool_calls",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    @staticmethod
    def _period(query: str) -> tuple[str, str]:
        match = _MONTH_PATTERN.search(query)
        timezone = ZoneInfo(get_settings().app_timezone)
        if match:
            start = datetime(int(match.group(1)), int(match.group(2)), 1, tzinfo=timezone)
        else:
            now = datetime.now(timezone)
            start = datetime(now.year, now.month, 1, tzinfo=timezone)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start.isoformat(), end.isoformat()

    def _answer_tool_result(self, message: ModelMessage) -> ModelCompletion:
        try:
            result = json.loads(message.content or "{}")
            data = result["data"]
        except (ValueError, KeyError, TypeError):
            content = "无法确定：mock provider 收到的 Tool 结果无效。"
        else:
            if result.get("status") != "success" or not isinstance(data, dict):
                content = "无法确定：只读 Tool 未成功返回结果。"
            elif message.name == "get_spending_summary":
                content = (
                    f"本期支出为{_format_yuan(data['expense_minor'])}元，"
                    f"收入为{_format_yuan(data['income_minor'])}元，"
                    f"净流量为{_format_yuan(data['net_flow_minor'])}元，"
                    f"共{data['transaction_count']}笔。"
                )
            elif message.name == "get_budget_status":
                budget = data["budget"]
                content = (
                    f"本期已用{_format_yuan(budget['used_minor'])}元，"
                    f"剩余{_format_yuan(budget['remaining_minor'])}元，"
                    f"超支{_format_yuan(budget['over_budget_minor'])}元。"
                )
            else:
                content = "已完成查账，结果来自只读 Tool；请查看随答案返回的证据。"
        return ModelCompletion(
            provider=self.provider,
            model=self.model,
            content=content,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


class OpenAICompatibleProvider:
    """Small, vendor-neutral Chat Completions client.

    The response parser intentionally ignores provider-specific reasoning
    fields so hidden thinking is never persisted by this application.
    """

    def __init__(
        self,
        *,
        provider: Literal["remote", "local"],
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_retries: int,
        max_output_tokens: int,
        client: httpx.Client | None = None,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        self.provider = provider
        self.base_url = _validated_base_url(base_url, provider)
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def health(self) -> ModelHealth:
        started = monotonic()
        try:
            response = self._client.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.RequestError):
            return ModelHealth(
                provider=self.provider,
                model=self.model,
                available=False,
                message="model service unavailable",
                latency_ms=_elapsed_ms(started),
            )
        except httpx.HTTPStatusError as exc:
            return ModelHealth(
                provider=self.provider,
                model=self.model,
                available=False,
                message=f"model health returned HTTP {exc.response.status_code}",
                latency_ms=_elapsed_ms(started),
            )
        return ModelHealth(
            provider=self.provider,
            model=self.model,
            available=True,
            message="model service ready",
            latency_ms=_elapsed_ms(started),
        )

    def complete(
        self,
        request: ModelRequest,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelCompletion:
        token = cancellation_token or CancellationToken()
        started = monotonic()
        payload = self._request_payload(request)
        last_error: ModelProviderError | None = None

        for attempt in range(1, self.max_retries + 2):
            token.raise_if_cancelled()
            try:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except httpx.TimeoutException:
                last_error = ModelProviderError("MODEL_TIMEOUT", "模型调用超时", retryable=True)
            except httpx.RequestError:
                last_error = ModelProviderError(
                    "MODEL_UNAVAILABLE", "模型服务不可用", retryable=True
                )
            else:
                if 200 <= response.status_code < 300:
                    token.raise_if_cancelled()
                    return self._parse_completion(response, started, attempt)
                retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
                last_error = ModelProviderError(
                    "MODEL_HTTP_ERROR",
                    f"模型服务返回 HTTP {response.status_code}",
                    retryable=retryable,
                    http_status=response.status_code,
                )

            if not last_error.retryable or attempt > self.max_retries:
                raise last_error
            delay = min(self.retry_backoff_seconds * (2 ** (attempt - 1)), 2.0)
            if token.wait(delay):
                token.raise_if_cancelled()

        raise last_error or ModelProviderError("MODEL_ERROR", "模型调用失败")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_payload(message) for message in request.messages],
            "max_tokens": self.max_output_tokens,
        }
        if request.tools:
            payload.update(
                tools=request.tools,
                tool_choice="auto",
                parallel_tool_calls=False,
            )
        if request.response_format:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_format.name,
                    "schema": request.response_format.json_schema,
                    "strict": request.response_format.strict,
                },
            }
        return payload

    def _parse_completion(
        self, response: httpx.Response, started: float, attempt: int
    ) -> ModelCompletion:
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError(
                "MODEL_PROTOCOL_ERROR", "模型响应结构无效", retryable=False
            ) from exc
        if not isinstance(choice, dict) or not isinstance(message, dict):
            raise ModelProviderError("MODEL_PROTOCOL_ERROR", "模型响应结构无效", retryable=False)

        tool_calls: list[ModelToolCall] = []
        for item in message.get("tool_calls") or []:
            try:
                function = item["function"]
                arguments = json.loads(function.get("arguments") or "{}")
                if not isinstance(arguments, dict):
                    raise TypeError("Tool arguments must be an object")
                tool_calls.append(
                    ModelToolCall(
                        id=item["id"],
                        name=function["name"],
                        arguments=arguments,
                    )
                )
            except (AttributeError, ValueError, KeyError, TypeError) as exc:
                raise ModelProviderError(
                    "MODEL_PROTOCOL_ERROR", "模型返回了无效的 Tool 调用", retryable=False
                ) from exc

        usage_payload = payload.get("usage") or {}
        try:
            if not isinstance(usage_payload, dict):
                raise TypeError("usage must be an object")
            prompt_tokens = int(usage_payload.get("prompt_tokens") or 0)
            completion_tokens = int(usage_payload.get("completion_tokens") or 0)
            total_tokens = int(
                usage_payload.get("total_tokens") or prompt_tokens + completion_tokens
            )
            usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        except (TypeError, ValueError) as exc:
            raise ModelProviderError(
                "MODEL_PROTOCOL_ERROR", "模型 Token 用量结构无效", retryable=False
            ) from exc
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ModelProviderError(
                "MODEL_PROTOCOL_ERROR", "模型文本响应结构无效", retryable=False
            )
        return ModelCompletion(
            provider=self.provider,
            model=self.model,
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            usage=usage,
            latency_ms=_elapsed_ms(started),
            attempt_count=attempt,
        )


def create_model_provider(
    settings: Settings | None = None,
    *,
    client: httpx.Client | None = None,
) -> ModelProvider:
    settings = settings or get_settings()
    provider = settings.llm_provider.lower().strip()
    if provider == "mock":
        return MockModelProvider(settings.llm_model)
    if provider not in {"remote", "local"}:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "LLM_PROVIDER 必须是 mock、remote 或 local")
    if not settings.llm_base_url:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "当前 Provider 缺少 LLM_BASE_URL")
    if provider == "remote" and not settings.llm_api_key:
        raise ModelProviderError("MODEL_CONFIG_ERROR", "remote Provider 缺少 LLM_API_KEY")
    return OpenAICompatibleProvider(
        provider=provider,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key or ("local" if provider == "local" else None),
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_output_tokens=settings.llm_max_output_tokens,
        client=client,
    )
