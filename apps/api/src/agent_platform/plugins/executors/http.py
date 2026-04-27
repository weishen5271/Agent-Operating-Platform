"""声明式 HTTP capability 执行器。

业务包只提供 JSON binding，不上传代码。执行器从租户插件配置中读取 endpoint、secrets、
timeout 等运行参数，再把 binding 渲染成真实 HTTP 请求。

引用语法可出现在 binding 字符串中：
    ``$input.<dot.path>``     Planner 生成的入参。
    ``$config.<dot.path>``    租户级插件配置。
    ``$secret.<name>``        ``tenant_config['secrets'][<name>]``。
    ``$response.<dot.path>``  HTTP 响应体，仅允许在 ``response_map`` 中使用。

Binding 形态::

    {
        "method": "GET",
        "path": "/api/v1/foo/$input.id",
        "query":   { "k": "$input.x", "lim": 5 },
        "headers": { "Authorization": "Bearer $secret.token" },
        "body":    { "k": "$input.x" },
        "timeout_ms": 5000,
        "response_map": {
            "field_a": "$response.body.data.a",
            "items":   "$response.body.items"
        },
        "error_translation": {
            "404": "NOT_FOUND",
            "401": "AUTH_FAILED"
        }
    }
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from agent_platform.domain.models import CapabilityDefinition, SourceReference
from agent_platform.plugins.base import CapabilityPlugin
from agent_platform.plugins.executors.dsl import BindingContext, render_mapping, render_template
from agent_platform.plugins.executors.outbound_guard import validate_http_endpoint

_DEFAULT_TIMEOUT_MS = 5000
_MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB
_MAX_RETRY_ATTEMPTS = 5
_DEFAULT_RETRY_BASE_DELAY_SECONDS = 0.1
_MAX_RETRY_DELAY_SECONDS = 1.0
_IDEMPOTENCY_CACHE_TTL_SECONDS = 300
_RATE_LIMIT_WINDOW_SECONDS = 60
_MAX_RATE_LIMIT_PER_MINUTE = 10000


_IDEMPOTENCY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_IDEMPOTENCY_CACHE_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


class HttpExecutorError(RuntimeError):
    """HTTP capability 调用失败，并已转换为平台可识别错误码时抛出。"""

    def __init__(self, code: str, status: int | None, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status
        self.detail = detail


class HttpExecutor(CapabilityPlugin):
    """通过声明式 HTTP binding 执行单个 capability。"""

    def __init__(
        self,
        capability: CapabilityDefinition,
        *,
        package_id: str,
        plugin_name: str,
        binding: dict[str, Any],
        plugin_config_schema: dict[str, Any] | None = None,
        plugin_default_config: dict[str, Any] | None = None,
        client_factory: Any = None,
    ) -> None:
        self.capability = capability
        self.config_schema = plugin_config_schema
        self.auth_ref = None
        self.plugin_name = plugin_name
        self.package_id = package_id
        self._binding = binding or {}
        self._defaults: dict[str, Any] = dict(plugin_default_config or {})
        self._client_factory = client_factory  # injected by tests; default uses httpx.Client

    # ------------------------------------------------------------------ invoke
    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        # 基类要求实现 invoke；HTTP 执行需要租户配置，因此统一转到 invoke_with_config。
        return self.invoke_with_config(payload, tenant_config=None)

    def invoke_with_config(
        self,
        payload: dict[str, Any],
        *,
        tenant_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = BindingContext(
            inputs=dict(payload),
            config=self._merge_config(tenant_config),
        )
        # 先完成 binding 渲染，再做出站 URL 校验，确保最终请求地址才是安全判断对象。
        method = str(self._binding.get("method") or "GET").upper()
        endpoint = ctx.require_config("endpoint", error_factory=HttpExecutorError)
        path = render_template(self._binding.get("path") or "", ctx)
        url = self._join_url(endpoint, path)
        self._validate_url(url)

        query = render_mapping(self._binding.get("query") or {}, ctx)
        headers = render_mapping(self._binding.get("headers") or {}, ctx)
        timeout_seconds = self._resolve_timeout(ctx)
        body = self._binding.get("body")
        json_body = render_mapping(body, ctx) if isinstance(body, (dict, list)) else None
        idempotency_key = self._resolve_idempotency_key(ctx)
        idempotency_cache_key = self._idempotency_cache_key(idempotency_key) if idempotency_key else None
        if idempotency_key:
            # 幂等缓存用于保护外部写接口，重复请求直接返回短期缓存结果。
            headers["Idempotency-Key"] = idempotency_key
            cached = self._get_cached_idempotency_result(idempotency_cache_key)
            if cached is not None:
                cached.setdefault("_meta", {})
                cached["_meta"]["idempotency_cache_hit"] = True
                return cached

        rate_limit = self._resolve_rate_limit(ctx)
        if rate_limit is not None:
            # 本地限流是租户侧保护，不替代上游系统自己的 quota。
            self._check_rate_limit(rate_limit)

        retry_policy = self._resolve_retry_policy()
        last_error: HttpExecutorError | None = None
        response: httpx.Response | None = None

        with self._open_client(timeout_seconds) as client:
            for attempt in range(1, retry_policy["max_attempts"] + 1):
                try:
                    # 重试只围绕一次已渲染请求进行，不在重试期间重新读取配置或重算入参。
                    response = client.request(
                        method=method,
                        url=url,
                        params=_drop_none(query),
                        headers=_stringify_headers(headers),
                        json=json_body,
                    )
                except httpx.TimeoutException as exc:
                    last_error = HttpExecutorError("UPSTREAM_TIMEOUT", None, str(exc))
                    if self._should_retry_error(last_error.code, retry_policy, attempt):
                        self._sleep_before_retry(attempt, retry_policy)
                        continue
                    raise last_error from exc
                except httpx.RequestError as exc:
                    last_error = HttpExecutorError("UPSTREAM_UNREACHABLE", None, str(exc))
                    if self._should_retry_error(last_error.code, retry_policy, attempt):
                        self._sleep_before_retry(attempt, retry_policy)
                        continue
                    raise last_error from exc

                if response.status_code >= 400 and self._should_retry_status(
                    response.status_code,
                    retry_policy,
                    attempt,
                ):
                    self._sleep_before_retry(attempt, retry_policy)
                    continue
                break

        if response is None:
            if last_error is not None:
                raise last_error
            raise HttpExecutorError("UPSTREAM_UNREACHABLE", None, "HTTP 请求未返回响应。")

        if int(response.headers.get("content-length") or 0) > _MAX_RESPONSE_BYTES:
            raise HttpExecutorError("RESPONSE_TOO_LARGE", response.status_code, "")

        body_text = response.text or ""
        if len(body_text.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            raise HttpExecutorError("RESPONSE_TOO_LARGE", response.status_code, "")

        try:
            response_body = response.json() if body_text.strip() else None
        except ValueError:
            response_body = body_text

        if response.status_code >= 400:
            translation = self._translate_error(response.status_code, response_body)
            raise HttpExecutorError(translation, response.status_code, _truncate(body_text, 500))

        ctx.response = {"status": response.status_code, "body": response_body}
        # response_map 是业务包对平台的输出合同，未声明时保持空对象并补充执行元数据。
        result = render_mapping(self._binding.get("response_map") or {}, ctx)
        if not isinstance(result, dict):
            result = {"data": result}

        result.setdefault("sources", [
            SourceReference(
                id=f"http::{self.package_id}::{self.plugin_name}",
                title=f"业务包 HTTP · {self.plugin_name}",
                snippet=f"{method} {url} -> {response.status_code}",
                source_type="plugin",
            )
        ])
        result.setdefault("_meta", {
            "executor": "http",
            "package_id": self.package_id,
            "plugin": self.plugin_name,
            "status": response.status_code,
        })
        if idempotency_cache_key:
            self._set_cached_idempotency_result(idempotency_cache_key, result)
        return result

    # -------------------------------------------------------------- internals
    def _merge_config(self, tenant_config: dict[str, Any] | None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self._defaults)
        if tenant_config:
            merged.update(tenant_config)
        return merged

    def _open_client(self, timeout_seconds: float) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory(timeout=timeout_seconds)
        return httpx.Client(timeout=timeout_seconds, follow_redirects=False)

    def _resolve_timeout(self, ctx: BindingContext) -> float:
        raw = self._binding.get("timeout_ms")
        if isinstance(raw, str):
            raw = render_template(raw, ctx)
        if raw is None:
            raw = ctx.config.get("timeout_ms", _DEFAULT_TIMEOUT_MS)
        try:
            return max(int(raw) / 1000.0, 0.1)
        except (TypeError, ValueError):
            return _DEFAULT_TIMEOUT_MS / 1000.0

    def _resolve_retry_policy(self) -> dict[str, Any]:
        raw = self._binding.get("retry") or {}
        if not isinstance(raw, dict):
            return {"policy": "none", "max_attempts": 1, "retry_on": set()}
        try:
            max_attempts = int(raw.get("max_attempts") or 1)
        except (TypeError, ValueError):
            max_attempts = 1
        max_attempts = min(max(max_attempts, 1), _MAX_RETRY_ATTEMPTS)
        retry_on = raw.get("retry_on") or []
        if not isinstance(retry_on, list):
            retry_on = []
        return {
            "policy": str(raw.get("policy") or "none").lower(),
            "max_attempts": max_attempts,
            "retry_on": {str(item).upper() for item in retry_on if item is not None},
        }

    def _should_retry_status(self, status: int, retry_policy: dict[str, Any], attempt: int) -> bool:
        if attempt >= retry_policy["max_attempts"]:
            return False
        retry_on = retry_policy["retry_on"]
        if str(status) in retry_on:
            return True
        bucket = f"{status // 100}XX"
        return bucket in retry_on

    def _should_retry_error(self, code: str, retry_policy: dict[str, Any], attempt: int) -> bool:
        if attempt >= retry_policy["max_attempts"]:
            return False
        return code.upper() in retry_policy["retry_on"]

    def _sleep_before_retry(self, attempt: int, retry_policy: dict[str, Any]) -> None:
        if retry_policy["policy"] != "exponential":
            return
        delay = min(_DEFAULT_RETRY_BASE_DELAY_SECONDS * (2 ** max(attempt - 1, 0)), _MAX_RETRY_DELAY_SECONDS)
        time.sleep(delay)

    def _resolve_idempotency_key(self, ctx: BindingContext) -> str | None:
        raw = self._binding.get("idempotency_key")
        if not raw:
            return None
        key = render_template(str(raw), ctx)
        if key is None:
            return None
        key = str(key).strip()
        if not key:
            return None
        return key

    def _idempotency_cache_key(self, rendered_key: str) -> str:
        return f"{self.package_id}:{self.plugin_name}:{self.capability.name}:{rendered_key}"

    def _resolve_rate_limit(self, ctx: BindingContext) -> dict[str, Any] | None:
        raw = self._binding.get("rate_limit") or {}
        if not isinstance(raw, dict):
            return None
        limit_value = raw.get("requests_per_minute", raw.get("quota_per_minute"))
        if isinstance(limit_value, str):
            limit_value = render_template(limit_value, ctx)
        try:
            requests_per_minute = int(limit_value)
        except (TypeError, ValueError):
            return None
        requests_per_minute = min(max(requests_per_minute, 0), _MAX_RATE_LIMIT_PER_MINUTE)
        scope = str(raw.get("scope") or "tenant").strip().lower()
        custom_key = raw.get("key")
        rendered_key = render_template(str(custom_key), ctx) if custom_key else None
        return {
            "requests_per_minute": requests_per_minute,
            "key": self._rate_limit_key(scope=scope, tenant_id=ctx.config.get("tenant_id"), custom_key=rendered_key),
        }

    def _rate_limit_key(self, *, scope: str, tenant_id: Any, custom_key: Any = None) -> str:
        if custom_key is not None and str(custom_key).strip():
            key_suffix = str(custom_key).strip()
        elif scope == "capability":
            key_suffix = f"{tenant_id or '_default'}:{self.capability.name}"
        elif scope == "plugin":
            key_suffix = self.plugin_name
        else:
            key_suffix = f"{tenant_id or '_default'}:{self.plugin_name}"
        return f"{self.package_id}:{self.plugin_name}:{scope}:{key_suffix}"

    def _check_rate_limit(self, rate_limit: dict[str, Any]) -> None:
        limit = int(rate_limit["requests_per_minute"])
        key = str(rate_limit["key"])
        now = time.monotonic()
        cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
        with _RATE_LIMIT_LOCK:
            bucket = [timestamp for timestamp in _RATE_LIMIT_BUCKETS.get(key, []) if timestamp > cutoff]
            if len(bucket) >= limit:
                _RATE_LIMIT_BUCKETS[key] = bucket
                raise HttpExecutorError(
                    "RATE_LIMITED",
                    None,
                    f"HTTP executor rate limit exceeded: {limit}/minute",
                )
            bucket.append(now)
            _RATE_LIMIT_BUCKETS[key] = bucket

    def _get_cached_idempotency_result(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with _IDEMPOTENCY_CACHE_LOCK:
            cached = _IDEMPOTENCY_CACHE.get(key)
            if cached is None:
                return None
            expires_at, result = cached
            if expires_at <= now:
                _IDEMPOTENCY_CACHE.pop(key, None)
                return None
            return copy.deepcopy(result)

    def _set_cached_idempotency_result(self, key: str, result: dict[str, Any]) -> None:
        with _IDEMPOTENCY_CACHE_LOCK:
            _IDEMPOTENCY_CACHE[key] = (
                time.monotonic() + _IDEMPOTENCY_CACHE_TTL_SECONDS,
                copy.deepcopy(result),
            )

    @staticmethod
    def clear_idempotency_cache() -> None:
        with _IDEMPOTENCY_CACHE_LOCK:
            _IDEMPOTENCY_CACHE.clear()

    @staticmethod
    def clear_rate_limit_buckets() -> None:
        with _RATE_LIMIT_LOCK:
            _RATE_LIMIT_BUCKETS.clear()

    def _translate_error(self, status: int, body: Any) -> str:
        translation = self._binding.get("error_translation") or {}
        if not isinstance(translation, dict):
            return f"HTTP_{status}"
        if str(status) in translation:
            return str(translation[str(status)])
        bucket = f"{status // 100}xx"
        if bucket in translation:
            return str(translation[bucket])
        return f"HTTP_{status}"

    @staticmethod
    def _join_url(endpoint: str, path: str) -> str:
        endpoint = endpoint.rstrip("/")
        if not path:
            return endpoint
        if path.startswith("http://") or path.startswith("https://"):
            return path  # absolute override; rare but allow it
        if not path.startswith("/"):
            path = "/" + path
        return urljoin(endpoint + "/", path.lstrip("/"))

    @staticmethod
    def _validate_url(url: str) -> None:
        validate_http_endpoint(url, executor_label="HTTP", error_factory=HttpExecutorError)

def _drop_none(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def _stringify_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in headers.items() if value is not None}


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "...(truncated)"
