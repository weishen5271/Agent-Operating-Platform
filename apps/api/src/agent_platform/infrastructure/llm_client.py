from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent_platform.domain.models import LLMRuntimeConfig


@dataclass(frozen=True, slots=True)
class LLMRequestSpec:
    url: str
    headers: dict[str, str]
    payload: dict[str, object]
    response_format: str


class OpenAICompatibleLLMClient:
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

        try:
            with request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 404:
                detail = (
                    f"{detail}\n"
                    "请检查 LLM Base URL 是否与当前 Provider 匹配："
                    "OpenAI Compatible 通常填写到 /v1，Azure 需要包含 api-version，"
                    "Anthropic 通常填写 https://api.anthropic.com。"
                )
            raise ValueError(f"LLM request failed: {exc.code} {detail}") from exc
        except error.URLError as exc:
            raise ValueError(f"LLM request failed: {exc.reason}") from exc

        data = json.loads(body)
        if spec.response_format == "anthropic":
            return self._extract_anthropic_content(data)
        return self._extract_openai_content(data)

    def _build_request_spec(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        user_message: str,
        context_blocks: list[str],
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

    @staticmethod
    def _build_prompt(*, user_message: str, context_blocks: list[str]) -> str:
        if not context_blocks:
            return user_message
        joined = "\n\n".join(f"[上下文 {index + 1}]\n{block}" for index, block in enumerate(context_blocks))
        return f"用户问题：{user_message}\n\n可用上下文：\n{joined}\n\n请基于上下文回答，若上下文不足要明确说明。"
