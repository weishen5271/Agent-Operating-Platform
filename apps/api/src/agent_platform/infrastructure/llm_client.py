from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib import error, request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Iterator

from agent_platform.domain.models import LLMRuntimeConfig


@dataclass(frozen=True, slots=True)
class LLMRequestSpec:
    url: str
    headers: dict[str, str]
    payload: dict[str, object]
    response_format: str


class OpenAICompatibleLLMClient:
    _RETRYABLE_STATUS_CODES = {429, 529}
    _MAX_ATTEMPTS = 3
    _RETRY_BASE_DELAY_SECONDS = 0.8

    def complete(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        user_message: str,
        context_blocks: list[str],
    ) -> str:
        if not config.enabled:
            raise ValueError("LLM runtime is not enabled")
        if not api_key:
            raise ValueError("LLM API key is missing")

        spec = self._build_request_spec(
            config=config,
            api_key=api_key,
            user_message=user_message,
            context_blocks=context_blocks,
        )
        req = request.Request(
            spec.url,
            data=json.dumps(spec.payload).encode("utf-8"),
            headers=spec.headers,
            method="POST",
        )

        body = self._read_response_with_retry(req, timeout=30, error_prefix="LLM request failed")

        data = json.loads(body)
        if spec.response_format == "anthropic":
            return self._extract_anthropic_content(data)
        return self._extract_openai_content(data)

    def stream_complete(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        user_message: str,
        context_blocks: list[str],
    ) -> Iterator[str]:
        if not config.enabled:
            raise ValueError("LLM runtime is not enabled")
        if not api_key:
            raise ValueError("LLM API key is missing")

        spec = self._build_request_spec(
            config=config,
            api_key=api_key,
            user_message=user_message,
            context_blocks=context_blocks,
            stream=True,
        )
        req = request.Request(
            spec.url,
            data=json.dumps(spec.payload).encode("utf-8"),
            headers=spec.headers,
            method="POST",
        )

        with self._open_with_retry(req, timeout=60, error_prefix="LLM stream request failed") as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                chunk = self._extract_stream_delta(json.loads(data), spec.response_format)
                if chunk:
                    yield chunk

    def _build_request_spec(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        user_message: str,
        context_blocks: list[str],
        stream: bool = False,
    ) -> LLMRequestSpec:
        provider = config.provider.strip().lower()
        prompt = self._build_prompt(user_message=user_message, context_blocks=context_blocks)
        if provider == "azure":
            return LLMRequestSpec(
                url=self._azure_chat_completions_url(config.base_url, config.model),
                headers={
                    "Content-Type": "application/json",
                    "api-key": api_key,
                },
                payload={
                    "temperature": config.temperature,
                    "stream": stream,
                    "messages": [
                        {"role": "system", "content": config.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                },
                response_format="openai",
            )
        if provider == "anthropic":
            return LLMRequestSpec(
                url=self._anthropic_messages_url(config.base_url),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                payload={
                    "model": config.model,
                    "max_tokens": 1024,
                    "temperature": config.temperature,
                    "stream": stream,
                    "system": config.system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                },
                response_format="anthropic",
            )
        if provider not in {"openai-compatible", "openai"}:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")

        return LLMRequestSpec(
            url=self._openai_chat_completions_url(config.base_url),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload={
                "model": config.model,
                "temperature": config.temperature,
                "stream": stream,
                "messages": [
                    {"role": "system", "content": config.system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
            response_format="openai",
        )

    @staticmethod
    def _extract_openai_content(data: dict[str, object]) -> str:
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("LLM response did not include choices")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ValueError("LLM response content is empty")
        return str(content)

    @staticmethod
    def _extract_anthropic_content(data: dict[str, object]) -> str:
        content_items = data.get("content", [])
        if not isinstance(content_items, list):
            raise ValueError("Anthropic response content is invalid")
        text_blocks = [
            item.get("text", "")
            for item in content_items
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        content = "\n".join(block for block in text_blocks if block)
        if not content:
            raise ValueError("Anthropic response content is empty")
        return content

    @staticmethod
    def _extract_stream_delta(data: dict[str, object], response_format: str) -> str:
        if response_format == "anthropic":
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if isinstance(delta, dict) and delta.get("type") == "text_delta":
                    return str(delta.get("text") or "")
            return ""
        choices = data.get("choices", [])
        if not choices:
            return ""
        delta = choices[0].get("delta", {})
        if not isinstance(delta, dict):
            return ""
        return str(delta.get("content") or "")

    @staticmethod
    def _openai_chat_completions_url(base_url: str) -> str:
        normalized = OpenAICompatibleLLMClient._strip_url(base_url)
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    @staticmethod
    def _anthropic_messages_url(base_url: str) -> str:
        normalized = OpenAICompatibleLLMClient._strip_url(base_url)
        if normalized.endswith("/v1/messages"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/messages"
        return f"{normalized}/v1/messages"

    @staticmethod
    def _azure_chat_completions_url(base_url: str, deployment: str) -> str:
        parsed = urlsplit(base_url.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Azure OpenAI Base URL must be an absolute URL")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "api-version" not in query or not query["api-version"]:
            raise ValueError("Azure OpenAI Base URL must include api-version query parameter")

        path = parsed.path.rstrip("/")
        if path.endswith("/chat/completions"):
            return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query), ""))
        if "/openai/deployments/" in path:
            path = f"{path}/chat/completions"
        else:
            if not deployment:
                raise ValueError("Azure OpenAI model must be set to the deployment name")
            path = f"{path}/openai/deployments/{deployment}/chat/completions"
        return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query), ""))

    @staticmethod
    def _strip_url(url: str) -> str:
        return url.strip().rstrip("/")

    @classmethod
    def _read_response_with_retry(cls, req: request.Request, *, timeout: int, error_prefix: str) -> str:
        with cls._open_with_retry(req, timeout=timeout, error_prefix=error_prefix) as response:
            return response.read().decode("utf-8")

    @classmethod
    def _open_with_retry(cls, req: request.Request, *, timeout: int, error_prefix: str):
        last_exc: error.HTTPError | error.URLError | None = None
        for attempt in range(1, cls._MAX_ATTEMPTS + 1):
            try:
                return request.urlopen(req, timeout=timeout)
            except error.HTTPError as exc:
                last_exc = exc
                if not cls._should_retry_http_error(exc) or attempt == cls._MAX_ATTEMPTS:
                    detail = cls._read_http_error_detail(exc)
                    raise ValueError(f"{error_prefix}: {exc.code} {detail}") from exc
                cls._sleep_before_retry(attempt)
            except error.URLError as exc:
                last_exc = exc
                if attempt == cls._MAX_ATTEMPTS:
                    raise ValueError(f"{error_prefix}: {exc.reason}") from exc
                cls._sleep_before_retry(attempt)
        if isinstance(last_exc, error.HTTPError):
            detail = cls._read_http_error_detail(last_exc)
            raise ValueError(f"{error_prefix}: {last_exc.code} {detail}") from last_exc
        if isinstance(last_exc, error.URLError):
            raise ValueError(f"{error_prefix}: {last_exc.reason}") from last_exc
        raise ValueError(f"{error_prefix}: unknown error")

    @classmethod
    def _should_retry_http_error(cls, exc: error.HTTPError) -> bool:
        return exc.code in cls._RETRYABLE_STATUS_CODES or 500 <= exc.code < 600

    @staticmethod
    def _read_http_error_detail(exc: error.HTTPError) -> str:
        detail = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 404:
            detail = (
                f"{detail}\n"
                "请检查 LLM Base URL 是否与当前 Provider 匹配："
                "OpenAI Compatible 通常填写到 /v1，Azure 需要包含 api-version，"
                "Anthropic 通常填写 https://api.anthropic.com。"
            )
        return detail

    @classmethod
    def _sleep_before_retry(cls, attempt: int) -> None:
        time.sleep(cls._RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))

    @staticmethod
    def _build_prompt(*, user_message: str, context_blocks: list[str]) -> str:
        if not context_blocks:
            return user_message
        joined = "\n\n".join(f"[参考资料 {index + 1}]\n{block}" for index, block in enumerate(context_blocks))
        instructions = (
            "回答要求：\n"
            "1. 严格基于以上参考资料作答；资料未涵盖的内容请明确说明“资料未提及”，禁止编造。\n"
            "2. 引用资料时使用 [1][2] 这样的角标，与参考资料编号一一对应。\n"
            "3. 对“如何设计 / 怎么实现 / 分析”等开放性问题，请按以下结构组织答案：\n"
            "   一、背景与目标\n"
            "   二、关键模块与职责\n"
            "   三、设计要点（含取舍与依赖）\n"
            "   四、风险与开放问题\n"
            "4. 不要直接复述原文，要做归纳、提炼与解释，必要时给出表格或要点。\n"
            "5. 结尾用一句话给出“下一步建议”。"
        )
        return (
            f"用户问题：{user_message}\n\n"
            f"参考资料：\n{joined}\n\n"
            f"{instructions}"
        )
