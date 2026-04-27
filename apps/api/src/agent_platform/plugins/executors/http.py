"""Declarative HTTP capability executor.

Bundles ship a JSON ``binding`` block per capability; the executor reads
``tenant_config`` (endpoint / secrets / timeout) from the platform's
``plugin_config`` table and synthesises a real HTTP call without any code
upload. The DSL is intentionally minimal:

Reference syntax (anywhere in binding string values):
    ``$input.<dot.path>``     payload supplied by the planner
    ``$config.<dot.path>``    tenant-scoped plugin config
    ``$secret.<name>``        ``tenant_config['secrets'][<name>]``
    ``$response.<dot.path>``  HTTP response body — only valid in ``response_map``

Binding shape::

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

import re
from typing import Any
from urllib.parse import urljoin

import httpx

from agent_platform.domain.models import CapabilityDefinition, SourceReference
from agent_platform.plugins.base import CapabilityPlugin

_REF_PATTERN = re.compile(r"\$(input|config|secret|response)(?:\.([A-Za-z0-9_.\-]+))?")
_DEFAULT_TIMEOUT_MS = 5000
_MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB


class HttpExecutorError(RuntimeError):
    """Raised when an HTTP capability invocation fails after translation."""

    def __init__(self, code: str, status: int | None, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status
        self.detail = detail


class HttpExecutor(CapabilityPlugin):
    """Run a single capability via a declarative HTTP binding."""

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
        # The base class abstract demands this; HTTP executor needs tenant
        # config so we route through ``invoke_with_config``.
        return self.invoke_with_config(payload, tenant_config=None)

    def invoke_with_config(
        self,
        payload: dict[str, Any],
        *,
        tenant_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = _BindingContext(
            inputs=dict(payload),
            config=self._merge_config(tenant_config),
        )
        method = str(self._binding.get("method") or "GET").upper()
        endpoint = ctx.require_config("endpoint")
        path = self._render_template(self._binding.get("path") or "", ctx)
        url = self._join_url(endpoint, path)

        query = self._render_mapping(self._binding.get("query") or {}, ctx)
        headers = self._render_mapping(self._binding.get("headers") or {}, ctx)
        timeout_seconds = self._resolve_timeout(ctx)
        body = self._binding.get("body")
        json_body = self._render_mapping(body, ctx) if isinstance(body, (dict, list)) else None

        try:
            with self._open_client(timeout_seconds) as client:
                response = client.request(
                    method=method,
                    url=url,
                    params=_drop_none(query),
                    headers=_stringify_headers(headers),
                    json=json_body,
                )
        except httpx.TimeoutException as exc:
            raise HttpExecutorError("UPSTREAM_TIMEOUT", None, str(exc)) from exc
        except httpx.RequestError as exc:
            raise HttpExecutorError("UPSTREAM_UNREACHABLE", None, str(exc)) from exc

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
        result = self._render_mapping(self._binding.get("response_map") or {}, ctx)
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

    def _resolve_timeout(self, ctx: "_BindingContext") -> float:
        raw = self._binding.get("timeout_ms")
        if isinstance(raw, str):
            raw = self._render_template(raw, ctx)
        if raw is None:
            raw = ctx.config.get("timeout_ms", _DEFAULT_TIMEOUT_MS)
        try:
            return max(int(raw) / 1000.0, 0.1)
        except (TypeError, ValueError):
            return _DEFAULT_TIMEOUT_MS / 1000.0

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

    # ---------- DSL rendering -------------------------------------------------
    def _render_mapping(self, value: Any, ctx: "_BindingContext") -> Any:
        if isinstance(value, dict):
            return {key: self._render_mapping(item, ctx) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render_mapping(item, ctx) for item in value]
        if isinstance(value, str):
            return self._render_template(value, ctx)
        return value

    @staticmethod
    def _render_template(template: str, ctx: "_BindingContext") -> Any:
        # Pure single-token template (e.g. "$input.equipment_id") preserves the
        # original Python type instead of stringifying.
        match = _REF_PATTERN.fullmatch(template.strip())
        if match:
            return ctx.resolve(match.group(1), match.group(2))

        # Otherwise inline-substitute every $... reference as a string.
        def _replace(match: re.Match[str]) -> str:
            value = ctx.resolve(match.group(1), match.group(2))
            return "" if value is None else str(value)

        return _REF_PATTERN.sub(_replace, template)


class _BindingContext:
    __slots__ = ("inputs", "config", "response")

    def __init__(self, *, inputs: dict[str, Any], config: dict[str, Any]) -> None:
        self.inputs = inputs
        self.config = config
        self.response: dict[str, Any] | None = None

    def require_config(self, key: str) -> str:
        value = self.config.get(key)
        if not value:
            raise HttpExecutorError(
                "MISSING_CONFIG",
                None,
                f"plugin_config.{key} 未配置；请先在「业务包管理 → 能力 → 插件配置」填入。",
            )
        return str(value)

    def resolve(self, scope: str, dotted_path: str | None) -> Any:
        if scope == "secret":
            secrets = self.config.get("secrets") or {}
            if not isinstance(secrets, dict):
                return None
            return secrets.get(dotted_path or "")
        source: Any
        if scope == "input":
            source = self.inputs
        elif scope == "config":
            source = self.config
        elif scope == "response":
            source = self.response or {}
        else:
            return None
        if not dotted_path:
            return source
        return _walk_path(source, dotted_path)


def _walk_path(source: Any, dotted_path: str) -> Any:
    cursor: Any = source
    for segment in dotted_path.split("."):
        if cursor is None:
            return None
        if isinstance(cursor, dict):
            cursor = cursor.get(segment)
            continue
        if isinstance(cursor, list) and segment.isdigit():
            index = int(segment)
            cursor = cursor[index] if 0 <= index < len(cursor) else None
            continue
        return None
    return cursor


def _drop_none(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def _stringify_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in headers.items() if value is not None}


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "...(truncated)"
