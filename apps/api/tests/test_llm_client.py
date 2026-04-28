from io import BytesIO
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException

from agent_platform.api.deps import resolve_auth_context
from agent_platform.api.errors import ERROR_CODE_MISSING_TOKEN, http_exception_response_content
from agent_platform.domain.models import LLMRuntimeConfig
from agent_platform.infrastructure.auth import create_access_token
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient


class FakeHTTPResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(status_code: int, body: str) -> HTTPError:
    return HTTPError(
        url="https://llm.example.test/v1/chat/completions",
        code=status_code,
        msg="error",
        hdrs={},
        fp=BytesIO(body.encode("utf-8")),
    )


def test_chat_completions_url_appends_endpoint_to_api_root() -> None:
    client = OpenAICompatibleLLMClient()

    assert client._openai_chat_completions_url("https://llm.example.test/v1") == (
        "https://llm.example.test/v1/chat/completions"
    )


def test_chat_completions_url_keeps_full_endpoint() -> None:
    client = OpenAICompatibleLLMClient()

    assert client._openai_chat_completions_url("https://llm.example.test/v1/chat/completions") == (
        "https://llm.example.test/v1/chat/completions"
    )


def test_azure_request_uses_deployment_endpoint_and_api_key_header() -> None:
    client = OpenAICompatibleLLMClient()

    spec = client._build_request_spec(
        config=LLMRuntimeConfig(
            provider="azure",
            base_url="https://tenant.openai.azure.com?api-version=2024-02-15-preview",
            model="chat-deployment",
            api_key_configured=True,
            temperature=0.2,
            system_prompt="system",
            enabled=True,
        ),
        api_key="azure-key",
        user_message="hello",
        context_blocks=[],
    )

    assert spec.url == (
        "https://tenant.openai.azure.com/openai/deployments/chat-deployment/"
        "chat/completions?api-version=2024-02-15-preview"
    )
    assert spec.headers["api-key"] == "azure-key"
    assert "Authorization" not in spec.headers
    assert "model" not in spec.payload


def test_azure_request_requires_api_version() -> None:
    client = OpenAICompatibleLLMClient()

    with pytest.raises(ValueError, match="api-version"):
        client._build_request_spec(
            config=LLMRuntimeConfig(
                provider="azure",
                base_url="https://tenant.openai.azure.com",
                model="chat-deployment",
                api_key_configured=True,
                temperature=0.2,
                system_prompt="system",
                enabled=True,
            ),
            api_key="azure-key",
            user_message="hello",
            context_blocks=[],
        )


def test_build_prompt_includes_structured_instructions_for_rag() -> None:
    prompt = OpenAICompatibleLLMClient._build_prompt(
        user_message="如何设计可扩展 Agent 架构？",
        context_blocks=["[1] 文档《架构》\n来源ID: doc-1\n正文:\nFoo bar"],
    )
    assert "参考资料 1" in prompt
    assert "[1][2]" in prompt
    assert "背景与目标" in prompt
    assert "下一步建议" in prompt


def test_build_prompt_returns_user_message_when_context_empty() -> None:
    prompt = OpenAICompatibleLLMClient._build_prompt(user_message="hi", context_blocks=[])
    assert prompt == "hi"


def test_anthropic_request_uses_messages_endpoint_and_headers() -> None:
    client = OpenAICompatibleLLMClient()

    spec = client._build_request_spec(
        config=LLMRuntimeConfig(
            provider="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-3-5-sonnet-latest",
            api_key_configured=True,
            temperature=0.2,
            system_prompt="system",
            enabled=True,
        ),
        api_key="anthropic-key",
        user_message="hello",
        context_blocks=[],
    )

    assert spec.url == "https://api.anthropic.com/v1/messages"
    assert spec.headers["x-api-key"] == "anthropic-key"
    assert spec.headers["anthropic-version"] == "2023-06-01"
    assert spec.payload["max_tokens"] == 1024
    assert spec.response_format == "anthropic"


def test_complete_retries_retryable_llm_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAICompatibleLLMClient()
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _http_error(529, '{"type":"error","error":{"type":"overloaded_error"}}')
        return FakeHTTPResponse('{"choices":[{"message":{"content":"ok"}}]}')

    monkeypatch.setattr("agent_platform.infrastructure.llm_client.request.urlopen", fake_urlopen)
    monkeypatch.setattr(OpenAICompatibleLLMClient, "_sleep_before_retry", lambda attempt: None)

    result = client.complete(
        config=LLMRuntimeConfig(
            provider="openai-compatible",
            base_url="https://llm.example.test/v1",
            model="chat-model",
            api_key_configured=True,
            temperature=0.2,
            system_prompt="system",
            enabled=True,
        ),
        api_key="test-key",
        user_message="hello",
        context_blocks=[],
    )

    assert result == "ok"
    assert calls == 3


def test_complete_does_not_retry_non_retryable_llm_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAICompatibleLLMClient()
    calls = 0

    def fake_urlopen(req, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(401, '{"error":"unauthorized"}')

    monkeypatch.setattr("agent_platform.infrastructure.llm_client.request.urlopen", fake_urlopen)
    monkeypatch.setattr(OpenAICompatibleLLMClient, "_sleep_before_retry", lambda attempt: None)

    with pytest.raises(ValueError, match="LLM request failed: 401"):
        client.complete(
            config=LLMRuntimeConfig(
                provider="openai-compatible",
                base_url="https://llm.example.test/v1",
                model="chat-model",
                api_key_configured=True,
                temperature=0.2,
                system_prompt="system",
                enabled=True,
            ),
            api_key="test-key",
            user_message="hello",
            context_blocks=[],
        )

    assert calls == 1


def test_resolve_auth_context_rejects_missing_authorization() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_auth_context(authorization=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == {"code": ERROR_CODE_MISSING_TOKEN, "detail": "缺少认证令牌"}
    assert http_exception_response_content(exc_info.value) == {
        "code": ERROR_CODE_MISSING_TOKEN,
        "detail": "缺少认证令牌",
    }


def test_resolve_auth_context_rejects_blank_authorization() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_auth_context(authorization="   ")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == {"code": ERROR_CODE_MISSING_TOKEN, "detail": "缺少认证令牌"}


def test_resolve_auth_context_returns_token_identity() -> None:
    token = create_access_token({"sub": "user-auth", "tenant_id": "tenant-auth"})

    assert resolve_auth_context(authorization=f"Bearer {token}") == ("tenant-auth", "user-auth")
