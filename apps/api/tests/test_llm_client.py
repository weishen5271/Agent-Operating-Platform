import pytest

from agent_platform.domain.models import LLMRuntimeConfig
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient


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
