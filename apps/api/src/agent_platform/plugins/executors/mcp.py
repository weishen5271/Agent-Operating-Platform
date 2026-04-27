"""声明式 MCP capability 执行器。

当前 MCP 执行器基于 httpx 支持 HTTP 系列传输。业务包仍只声明 binding，
租户通过 plugin_config 提供 server endpoint、headers 和凭据。

Binding 形态::

    {
        "mcp_server": "$config.mcp_server",
        "mcp_tool": "create_issue",
        "argument_map": {"title": "$input.title"},
        "response_map": {"url": "$response.body.structuredContent.html_url"}
    }

租户配置形态::

    {
        "mcp_server": "github",
        "mcp_servers": {
            "github": {
                "transport": "streamable-http",
                "endpoint": "https://mcp.example.test/mcp",
                "headers": {"Authorization": "Bearer $secret.github_token"}
            }
        },
        "secrets": {"github_token": "..."}
    }
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from agent_platform.domain.models import CapabilityDefinition, SourceReference
from agent_platform.plugins.base import CapabilityPlugin
from agent_platform.plugins.executors.dsl import BindingContext, render_mapping, render_template
from agent_platform.plugins.executors.outbound_guard import validate_http_endpoint

_DEFAULT_TIMEOUT_MS = 10000
_JSON_RPC_VERSION = "2.0"
_MCP_PROTOCOL_VERSION = "2025-03-26"
_MAX_RESPONSE_BYTES = 1 * 1024 * 1024


class McpExecutorError(RuntimeError):
    """MCP 调用无法完成时抛出，错误码会进入 capability 调用结果链路。"""

    def __init__(self, code: str, status: int | None, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status
        self.detail = detail


class McpExecutor(CapabilityPlugin):
    """通过 MCP tools/call binding 执行单个 capability。"""

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
        self._client_factory = client_factory

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.invoke_with_config(payload, tenant_config=None)

    def invoke_with_config(
        self,
        payload: dict[str, Any],
        *,
        tenant_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = BindingContext(inputs=dict(payload), config=self._merge_config(tenant_config))
        # server 可以来自显式 mcp_server、租户 mcp_servers 注册表或直连 endpoint。
        server = self._resolve_server(ctx)
        transport = str(server.get("transport") or "streamable-http").lower()
        if transport not in {"streamable-http", "http"}:
            raise McpExecutorError(
                "UNSUPPORTED_TRANSPORT",
                None,
                f"MCP executor currently supports streamable-http/http, got {transport}",
            )
        endpoint = str(server.get("endpoint") or "").strip()
        if not endpoint:
            raise McpExecutorError("MISSING_CONFIG", None, "MCP server endpoint 未配置。")
        validate_http_endpoint(endpoint, executor_label="MCP", error_factory=McpExecutorError)
        if str(server.get("status") or "active").lower() != "active":
            raise McpExecutorError("MCP_SERVER_DISABLED", None, "MCP server 当前未启用。")

        mcp_tool = render_template(str(self._binding.get("mcp_tool") or ""), ctx)
        if not isinstance(mcp_tool, str) or not mcp_tool.strip():
            raise McpExecutorError("INVALID_BINDING", None, "binding.mcp_tool 未配置。")

        arguments = render_mapping(self._binding.get("argument_map") or {}, ctx)
        if not isinstance(arguments, dict):
            raise McpExecutorError("INVALID_BINDING", None, "binding.argument_map 必须渲染为对象。")

        headers = self._resolve_headers(ctx, server)
        timeout_seconds = self._resolve_timeout(ctx)
        try:
            with self._open_client(timeout_seconds) as client:
                # MCP HTTP 调用需要先 initialize，再发送 initialized 通知，最后执行 tools/call。
                initialize_result = self._post_json_rpc(
                    client,
                    endpoint=endpoint,
                    headers=headers,
                    request_id=1,
                    method="initialize",
                    params={
                        "protocolVersion": _MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {
                            "name": "agent-operating-platform",
                            "version": "0.1.0",
                        },
                    },
                )
                session_headers = self._session_headers(initialize_result)
                self._post_json_rpc(
                    client,
                    endpoint=endpoint,
                    headers={**headers, **session_headers},
                    request_id=None,
                    method="notifications/initialized",
                    params={},
                    expect_response=False,
                )
                tool_result = self._post_json_rpc(
                    client,
                    endpoint=endpoint,
                    headers={**headers, **session_headers},
                    request_id=2,
                    method="tools/call",
                    params={"name": mcp_tool, "arguments": arguments},
                )
        except httpx.TimeoutException as exc:
            raise McpExecutorError("MCP_TIMEOUT", None, str(exc)) from exc
        except httpx.RequestError as exc:
            raise McpExecutorError("MCP_UNREACHABLE", None, str(exc)) from exc

        ctx.response = {"body": tool_result}
        # response_map 把 MCP 原始结果收敛成平台 capability 的稳定输出结构。
        result = render_mapping(self._binding.get("response_map") or {}, ctx)
        if not isinstance(result, dict):
            result = {"data": result}
        if not result:
            result = {"mcp_result": tool_result}
        result.setdefault(
            "sources",
            [
                SourceReference(
                    id=f"mcp::{self.package_id}::{self.plugin_name}",
                    title=f"业务包 MCP · {self.plugin_name}",
                    snippet=f"tools/call {mcp_tool}",
                    source_type="plugin",
                )
            ],
        )
        result.setdefault(
            "_meta",
            {
                "executor": "mcp",
                "package_id": self.package_id,
                "plugin": self.plugin_name,
                "mcp_tool": mcp_tool,
            },
        )
        return result

    def _merge_config(self, tenant_config: dict[str, Any] | None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self._defaults)
        if tenant_config:
            merged.update(tenant_config)
        return merged

    def _resolve_server(self, ctx: BindingContext) -> dict[str, Any]:
        # 优先按名称查租户配置，便于同一业务包在不同租户绑定不同 MCP Server。
        rendered = render_template(str(self._binding.get("mcp_server") or "$config.mcp_server"), ctx)
        if isinstance(rendered, dict):
            return rendered
        server_name = str(rendered or "").strip()
        servers = ctx.config.get("mcp_servers")
        if isinstance(servers, dict) and server_name in servers and isinstance(servers[server_name], dict):
            return dict(servers[server_name])
        if server_name.startswith("http://") or server_name.startswith("https://"):
            return {"transport": "streamable-http", "endpoint": server_name}
        endpoint = ctx.config.get("mcp_endpoint")
        if endpoint:
            return {
                "transport": ctx.config.get("mcp_transport", "streamable-http"),
                "endpoint": endpoint,
            }
        raise McpExecutorError("MISSING_CONFIG", None, "plugin_config.mcp_server 或 mcp_endpoint 未配置。")

    def _resolve_headers(self, ctx: BindingContext, server: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, Any] = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        server_headers = server.get("headers")
        if isinstance(server_headers, dict):
            headers.update(render_mapping(server_headers, ctx))
        binding_headers = self._binding.get("headers")
        if isinstance(binding_headers, dict):
            headers.update(render_mapping(binding_headers, ctx))
        return {key: str(value) for key, value in headers.items() if value is not None}

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

    def _open_client(self, timeout_seconds: float) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory(timeout=timeout_seconds)
        return httpx.Client(timeout=timeout_seconds, follow_redirects=False)

    def _post_json_rpc(
        self,
        client: httpx.Client,
        *,
        endpoint: str,
        headers: dict[str, str],
        request_id: int | None,
        method: str,
        params: dict[str, Any],
        expect_response: bool = True,
    ) -> dict[str, Any]:
        # 所有 MCP 请求走 JSON-RPC，通知类请求不要求响应体。
        request: dict[str, Any] = {
            "jsonrpc": _JSON_RPC_VERSION,
            "method": method,
            "params": params,
        }
        if request_id is not None:
            request["id"] = request_id
        response = client.post(endpoint, headers=headers, json=request)
        if not expect_response and response.status_code in {200, 202, 204}:
            return {}
        if int(response.headers.get("content-length") or 0) > _MAX_RESPONSE_BYTES:
            raise McpExecutorError("RESPONSE_TOO_LARGE", response.status_code, "")
        body_text = response.text or ""
        if len(body_text.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            raise McpExecutorError("RESPONSE_TOO_LARGE", response.status_code, "")
        if response.status_code >= 400:
            raise McpExecutorError(f"MCP_HTTP_{response.status_code}", response.status_code, body_text[:500])
        payload = self._parse_response(response)
        if not isinstance(payload, dict):
            raise McpExecutorError("INVALID_RESPONSE", response.status_code, "MCP response must be a JSON object.")
        if payload.get("error"):
            raise McpExecutorError("MCP_ERROR", response.status_code, json.dumps(payload["error"], ensure_ascii=False))
        result = payload.get("result")
        normalized = result if isinstance(result, dict) else {"value": result}
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            # streamable-http transport 会通过响应头返回会话 ID，后续请求需要带回去。
            normalized["_mcp_session_id"] = session_id
        return normalized

    @staticmethod
    def _parse_response(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if not data or data == "[DONE]":
                    continue
                return json.loads(data)
            return {}
        return response.json() if response.text.strip() else {}

    @staticmethod
    def _session_headers(initialize_result: dict[str, Any]) -> dict[str, str]:
        session_id = initialize_result.get("_mcp_session_id") or initialize_result.get("sessionId")
        if isinstance(session_id, str) and session_id:
            return {"Mcp-Session-Id": session_id}
        return {}
