import pytest

from agent_platform.domain.models import LLMRuntimeConfig
from agent_platform.infrastructure.embedding_client import OpenAICompatibleEmbeddingClient


def _config(provider: str = "openai-compatible", *, base_url: str = "https://emb.example/v1") -> LLMRuntimeConfig:
    return LLMRuntimeConfig(
        provider="openai-compatible",
        base_url="",
        model="",
        api_key_configured=True,
        temperature=0.2,
        system_prompt="",
        enabled=True,
        embedding_provider=provider,
        embedding_base_url=base_url,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        embedding_api_key_configured=True,
        embedding_enabled=True,
    )


def test_openai_compatible_request_uses_embeddings_endpoint() -> None:
    client = OpenAICompatibleEmbeddingClient()

    spec = client._build_request_spec(
        config=_config(),
        api_key="emb-key",
        texts=["hello", "world"],
    )

    assert spec.url == "https://emb.example/v1/embeddings"
    assert spec.headers["Authorization"] == "Bearer emb-key"
    assert spec.payload == {"model": "text-embedding-3-small", "input": ["hello", "world"]}


def test_openai_compatible_keeps_full_endpoint() -> None:
    client = OpenAICompatibleEmbeddingClient()

    spec = client._build_request_spec(
        config=_config(base_url="https://emb.example/v1/embeddings"),
        api_key="k",
        texts=["x"],
    )
    assert spec.url == "https://emb.example/v1/embeddings"


def test_azure_request_builds_deployment_path() -> None:
    client = OpenAICompatibleEmbeddingClient()

    spec = client._build_request_spec(
        config=_config(
            provider="azure",
            base_url="https://t.openai.azure.com?api-version=2024-02-15-preview",
        ),
        api_key="azure-key",
        texts=["foo"],
    )

    assert spec.url == (
        "https://t.openai.azure.com/openai/deployments/text-embedding-3-small/"
        "embeddings?api-version=2024-02-15-preview"
    )
    assert spec.headers["api-key"] == "azure-key"
    assert spec.payload == {"input": ["foo"]}


def test_azure_request_requires_api_version() -> None:
    client = OpenAICompatibleEmbeddingClient()

    with pytest.raises(ValueError, match="api-version"):
        client._build_request_spec(
            config=_config(provider="azure", base_url="https://t.openai.azure.com"),
            api_key="azure-key",
            texts=["foo"],
        )


def test_unsupported_provider_raises() -> None:
    client = OpenAICompatibleEmbeddingClient()

    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        client._build_request_spec(
            config=_config(provider="anthropic"),
            api_key="k",
            texts=["foo"],
        )


def test_extract_embeddings_orders_by_index() -> None:
    payload = {
        "data": [
            {"index": 1, "embedding": [0.2, 0.3]},
            {"index": 0, "embedding": [0.0, 0.1]},
        ]
    }
    vectors = OpenAICompatibleEmbeddingClient._extract_embeddings(payload, expected=2)
    assert vectors == [[0.0, 0.1], [0.2, 0.3]]


def test_extract_embeddings_validates_count() -> None:
    payload = {"data": [{"index": 0, "embedding": [0.0]}]}
    with pytest.raises(ValueError, match="count mismatch"):
        OpenAICompatibleEmbeddingClient._extract_embeddings(payload, expected=2)


def test_embed_rejects_when_disabled() -> None:
    client = OpenAICompatibleEmbeddingClient()
    config = _config()
    object.__setattr__(config, "embedding_enabled", False)

    with pytest.raises(ValueError, match="not enabled"):
        client.embed(config=config, api_key="k", texts=["x"])


def test_embed_rejects_missing_api_key() -> None:
    client = OpenAICompatibleEmbeddingClient()
    with pytest.raises(ValueError, match="API key is missing"):
        client.embed(config=_config(), api_key="", texts=["x"])
