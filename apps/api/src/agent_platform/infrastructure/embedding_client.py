"""OpenAI-compatible embedding client.

设计目标
--------
- 与 ``OpenAICompatibleLLMClient`` 对称：基于 urllib 同步实现，便于在 FastAPI
  请求线程内直接调用；高并发场景下未来可改为 httpx async。
- 支持三类提供方：
    * ``openai`` / ``openai-compatible``：``POST {base_url}/embeddings``，
      Authorization: Bearer
    * ``azure``：``POST {base_url}/openai/deployments/{model}/embeddings?api-version=...``，
      ``api-key`` 头
    * 通义、Moonshot、本地 vLLM、Ollama 等只要兼容 OpenAI Embedding 协议都走 ``openai-compatible``。
- 单条与批量调用统一为 ``embed(texts)``，调用方自行决定是否并行/分批。
- 维度由 LLMRuntimeConfig.embedding_dimensions 提供，调用方负责截断 / 校验。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from urllib import error, request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent_platform.domain.models import LLMRuntimeConfig

logger = logging.getLogger("agent_platform.infrastructure.embedding_client")


@dataclass(frozen=True, slots=True)
class EmbeddingRequestSpec:
    url: str
    headers: dict[str, str]
    payload: dict[str, object]


class OpenAICompatibleEmbeddingClient:
    """同步 embedding 客户端。"""

    requires_runtime_config = True

    def embed(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        texts: list[str],
    ) -> list[list[float]]:
        if not config.embedding_enabled:
            raise ValueError("Embedding runtime is not enabled")
        if not api_key:
            raise ValueError("Embedding API key is missing")
        if not texts:
            return []

        spec = self._build_request_spec(config=config, api_key=api_key, texts=texts)
        req = request.Request(
            spec.url,
            data=json.dumps(spec.payload).encode("utf-8"),
            headers=spec.headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=60) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 404:
                detail = (
                    f"{detail}\n"
                    "请检查 Embedding Base URL 是否正确："
                    "OpenAI Compatible 通常填写到 /v1，Azure 需带 api-version。"
                )
            raise ValueError(f"Embedding request failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise ValueError(f"Embedding request failed: {exc.reason}") from exc

        data = json.loads(body)
        return self._extract_embeddings(data, expected=len(texts))

    # ---------- request building ----------

    def _build_request_spec(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        texts: list[str],
    ) -> EmbeddingRequestSpec:
        provider = config.embedding_provider.strip().lower()
        if provider == "azure":
            return EmbeddingRequestSpec(
                url=self._azure_embeddings_url(config.embedding_base_url, config.embedding_model),
                headers={
                    "Content-Type": "application/json",
                    "api-key": api_key,
                },
                payload={"input": texts},
            )
        if provider not in {"openai", "openai-compatible"}:
            raise ValueError(f"Unsupported embedding provider: {config.embedding_provider}")
        return EmbeddingRequestSpec(
            url=self._openai_embeddings_url(config.embedding_base_url),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload={"model": config.embedding_model, "input": texts},
        )

    @staticmethod
    def _extract_embeddings(data: dict[str, object], *, expected: int) -> list[list[float]]:
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise ValueError("Embedding response did not include data")
        # 按 index 排序，避免某些供应商乱序返回
        ordered = sorted(items, key=lambda item: int(item.get("index", 0)) if isinstance(item, dict) else 0)
        vectors: list[list[float]] = []
        for entry in ordered:
            if not isinstance(entry, dict):
                raise ValueError("Embedding response item is invalid")
            vector = entry.get("embedding")
            if not isinstance(vector, list):
                raise ValueError("Embedding response is missing the 'embedding' field")
            vectors.append([float(value) for value in vector])
        if len(vectors) != expected:
            raise ValueError(
                f"Embedding response count mismatch: expected {expected}, got {len(vectors)}"
            )
        return vectors

    # ---------- URL helpers ----------

    @staticmethod
    def _openai_embeddings_url(base_url: str) -> str:
        normalized = OpenAICompatibleEmbeddingClient._strip_url(base_url)
        if normalized.endswith("/embeddings"):
            return normalized
        return f"{normalized}/embeddings"

    @staticmethod
    def _azure_embeddings_url(base_url: str, deployment: str) -> str:
        parsed = urlsplit(base_url.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Azure Embedding Base URL must be an absolute URL")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "api-version" not in query or not query["api-version"]:
            raise ValueError("Azure Embedding Base URL must include api-version query parameter")
        path = parsed.path.rstrip("/")
        if path.endswith("/embeddings"):
            return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query), ""))
        if "/openai/deployments/" in path:
            path = f"{path}/embeddings"
        else:
            if not deployment:
                raise ValueError("Azure embedding model must be set to the deployment name")
            path = f"{path}/openai/deployments/{deployment}/embeddings"
        return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query), ""))

    @staticmethod
    def _strip_url(url: str) -> str:
        return url.strip().rstrip("/")


class LocalHuggingFaceEmbeddingClient:
    """本地 HuggingFace embedding 客户端。

    模型首次使用时由 sentence-transformers 从 HuggingFace 拉取并缓存；后续复用本机缓存。
    """

    requires_runtime_config = False

    def __init__(
        self,
        *,
        model_name: str,
        device: str = "cpu",
        cache_dir: str | None = None,
        normalize_embeddings: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self.normalize_embeddings = normalize_embeddings
        self._model = None
        self._lock = threading.Lock()

    def embed(
        self,
        *,
        texts: list[str],
        config: LLMRuntimeConfig | None = None,
        api_key: str = "",
    ) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in vectors]

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "本地 HuggingFace embedding 需要安装 sentence-transformers；"
                    "请先同步项目依赖。"
                ) from exc

            cache_dir = self.cache_dir or os.getenv("HF_HOME") or None
            logger.info(
                "Loading local HuggingFace embedding model model=%s device=%s cache_dir=%s",
                self.model_name,
                self.device,
                cache_dir or "",
            )
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=cache_dir,
            )
            logger.info("Local HuggingFace embedding model loaded model=%s", self.model_name)
            return self._model
