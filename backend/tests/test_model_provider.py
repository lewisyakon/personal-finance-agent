import json

import httpx
import pytest

from app.core.config import Settings
from app.llm.contracts import (
    CancellationToken,
    ModelMessage,
    ModelProviderError,
    ModelRequest,
    StructuredOutputSpec,
)
from app.llm.provider import OpenAICompatibleProvider, create_model_provider


def _response(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "finance-model"}]})
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": "must not be retained",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_spending_summary",
                                    "arguments": json.dumps(
                                        {
                                            "from": "2026-01-01T00:00:00+08:00",
                                            "to": "2026-02-01T00:00:00+08:00",
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
            },
        },
    )


def _provider(client: httpx.Client, **overrides) -> OpenAICompatibleProvider:
    values = {
        "provider": "remote",
        "base_url": "https://model.example/v1",
        "model": "finance-model",
        "api_key": "secret-key",
        "timeout_seconds": 2,
        "max_retries": 1,
        "max_output_tokens": 512,
        "client": client,
        "retry_backoff_seconds": 0,
    }
    values.update(overrides)
    return OpenAICompatibleProvider(**values)


def test_openai_compatible_provider_health_tools_structured_output_and_usage():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _response(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = _provider(client)
    health = provider.health()
    completion = provider.complete(
        ModelRequest(
            run_id="run-1",
            messages=[ModelMessage(role="user", content="查一下")],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_spending_summary",
                        "description": "summary",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            response_format=StructuredOutputSpec(
                name="answer",
                schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            ),
        )
    )

    assert health.available is True
    assert completion.tool_calls[0].name == "get_spending_summary"
    assert completion.usage.total_tokens == 15
    assert completion.attempt_count == 1
    request_payload = json.loads(captured[-1].content)
    assert request_payload["parallel_tool_calls"] is False
    assert request_payload["tool_choice"] == "auto"
    assert request_payload["response_format"]["json_schema"]["strict"] is True
    assert captured[-1].headers["authorization"] == "Bearer secret-key"
    assert "reasoning" not in completion.model_dump_json()


def test_provider_retries_transient_status_without_falling_back():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "busy"})
        return _response(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    completion = _provider(client).complete(
        ModelRequest(run_id="run-2", messages=[ModelMessage(role="user", content="hi")])
    )

    assert calls == 2
    assert completion.provider == "remote"
    assert completion.attempt_count == 2


def test_provider_surfaces_unavailable_invalid_response_and_cancellation():
    unavailable = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(503)))
    provider = _provider(unavailable, max_retries=0)
    assert provider.health().available is False
    with pytest.raises(ModelProviderError, match="HTTP 503") as error:
        provider.complete(
            ModelRequest(run_id="run-3", messages=[ModelMessage(role="user", content="hi")])
        )
    assert error.value.code == "MODEL_HTTP_ERROR"
    assert error.value.http_status == 503

    malformed = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"bad": True}))
    )
    with pytest.raises(ModelProviderError) as protocol_error:
        _provider(malformed).complete(
            ModelRequest(run_id="run-4", messages=[ModelMessage(role="user", content="hi")])
        )
    assert protocol_error.value.code == "MODEL_PROTOCOL_ERROR"

    token = CancellationToken()
    token.cancel()
    with pytest.raises(ModelProviderError) as cancelled:
        provider.complete(
            ModelRequest(run_id="run-5", messages=[ModelMessage(role="user", content="hi")]),
            token,
        )
    assert cancelled.value.code == "MODEL_CANCELLED"


def test_factory_switches_modes_and_rejects_unsafe_configuration():
    mock_settings = Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-finance",
    )
    assert create_model_provider(mock_settings).provider == "mock"

    local_settings = Settings(
        _env_file=None,
        LLM_PROVIDER="local",
        LLM_BASE_URL="http://127.0.0.1:11434/v1",
        LLM_MODEL="qwen",
    )
    client = httpx.Client(transport=httpx.MockTransport(_response))
    assert create_model_provider(local_settings, client=client).provider == "local"

    with pytest.raises(ModelProviderError, match="回环地址"):
        create_model_provider(
            Settings(
                _env_file=None,
                LLM_PROVIDER="local",
                LLM_BASE_URL="https://model.example/v1",
                LLM_MODEL="qwen",
            ),
            client=client,
        )
    with pytest.raises(ModelProviderError, match="LLM_API_KEY"):
        create_model_provider(
            Settings(
                _env_file=None,
                LLM_PROVIDER="remote",
                LLM_BASE_URL="https://model.example/v1",
                LLM_MODEL="remote-model",
            ),
            client=client,
        )
