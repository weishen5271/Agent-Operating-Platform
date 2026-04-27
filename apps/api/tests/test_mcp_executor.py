from __future__ import annotations

from typing import Any

import pytest
import httpx

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.executors.mcp import McpExecutor, McpExecutorError


class RecordingMcpClient:
    """协议级测试夹具：只记录 JSON-RPC 请求，不连接真实 MCP Server。"""

    def __init__(self, *, responses: list[httpx.Response]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __enter__(self) -> "RecordingMcpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, endpoint: str, *, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
        self.requests.append({"endpoint": endpoint, "headers": dict(headers), "json": dict(json)})
        if not self.responses:
            raise AssertionError("No MCP response configured for request")
        return self.responses.pop(0)


def capability() -> CapabilityDefinition:
    return CapabilityDefinition(
        name="test.mcp.tool",
        description="Protocol-level MCP executor test capability",
        risk_level="low",
        side_effect_level="read",
        required_scope="mcp:read",
        input_schema={"required": ["query"]},
        output_schema={"required": ["answer"]},
        source="package",
        package_id="pkg.test_mcp",
    )


def json_rpc_response(payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, json=payload, headers=headers or {})


def build_executor(client: RecordingMcpClient) -> McpExecutor:
    return McpExecutor(
        capability(),
        package_id="pkg.test_mcp",
        plugin_name="mcp.test",
        binding={
            "mcp_server": "$config.mcp_server",
            "mcp_tool": "search",
            "argument_map": {"q": "$input.query", "limit": "$config.limit"},
            "response_map": {"answer": "$response.body.structuredContent.answer"},
            "headers": {"X-Tenant": "$config.tenant_slug"},
        },
        client_factory=lambda timeout: client,
    )


def test_mcp_executor_calls_initialize_initialized_and_tool_call() -> None:
    client = RecordingMcpClient(
        responses=[
            json_rpc_response(
                {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-03-26"}},
                headers={"Mcp-Session-Id": "session-test"},
            ),
            httpx.Response(202),
            json_rpc_response(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"structuredContent": {"answer": "protocol-result"}},
                }
            ),
        ]
    )
    executor = build_executor(client)

    result = executor.invoke_with_config(
        {"query": "status"},
        tenant_config={
            "mcp_server": "registered",
            "mcp_servers": {
                "registered": {
                    "transport": "streamable-http",
                    "endpoint": "https://mcp.test/mcp",
                    "headers": {"Authorization": "Bearer $secret.token"},
                    "status": "active",
                }
            },
            "secrets": {"token": "secret-token"},
            "tenant_slug": "tenant-a",
            "limit": 3,
        },
    )

    assert result["answer"] == "protocol-result"
    assert result["_meta"]["executor"] == "mcp"
    assert [item["json"]["method"] for item in client.requests] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert client.requests[0]["endpoint"] == "https://mcp.test/mcp"
    assert client.requests[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert client.requests[1]["headers"]["Mcp-Session-Id"] == "session-test"
    assert client.requests[2]["json"]["params"] == {
        "name": "search",
        "arguments": {"q": "status", "limit": 3},
    }
    assert client.requests[2]["headers"]["X-Tenant"] == "tenant-a"


def test_mcp_executor_parses_sse_json_rpc_response() -> None:
    client = RecordingMcpClient(
        responses=[
            json_rpc_response({"jsonrpc": "2.0", "id": 1, "result": {}}),
            httpx.Response(204),
            httpx.Response(
                200,
                text='event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"structuredContent":{"answer":"from-sse"}}}\n\n',
                headers={"content-type": "text/event-stream"},
            ),
        ]
    )
    executor = build_executor(client)

    result = executor.invoke_with_config(
        {"query": "status"},
        tenant_config={
            "mcp_server": "https://mcp.test/mcp",
            "tenant_slug": "tenant-a",
            "limit": 1,
        },
    )

    assert result["answer"] == "from-sse"


def test_mcp_executor_rejects_disabled_server_before_calling_network() -> None:
    client = RecordingMcpClient(responses=[])
    executor = build_executor(client)

    with pytest.raises(McpExecutorError) as exc:
        executor.invoke_with_config(
            {"query": "status"},
            tenant_config={
                "mcp_server": "registered",
                "mcp_servers": {
                    "registered": {
                        "transport": "streamable-http",
                        "endpoint": "https://mcp.test/mcp",
                        "status": "disabled",
                    }
                },
            },
        )

    assert exc.value.code == "MCP_SERVER_DISABLED"
    assert client.requests == []


def test_mcp_executor_blocks_metadata_ip_before_request() -> None:
    client = RecordingMcpClient(responses=[])
    executor = build_executor(client)

    with pytest.raises(McpExecutorError) as exc:
        executor.invoke_with_config(
            {"query": "status"},
            tenant_config={
                "mcp_server": "registered",
                "mcp_servers": {
                    "registered": {
                        "transport": "streamable-http",
                        "endpoint": "http://169.254.169.254/mcp",
                        "status": "active",
                    }
                },
            },
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []


def test_mcp_executor_blocks_localhost_before_request() -> None:
    client = RecordingMcpClient(responses=[])
    executor = build_executor(client)

    with pytest.raises(McpExecutorError) as exc:
        executor.invoke_with_config(
            {"query": "status"},
            tenant_config={
                "mcp_server": "http://localhost:18080/mcp",
                "tenant_slug": "tenant-a",
                "limit": 1,
            },
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []


def test_mcp_executor_allowlist_can_permit_private_cidr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "http_executor_allowlist", ["10.0.0.0/8"])
    client = RecordingMcpClient(
        responses=[
            json_rpc_response({"jsonrpc": "2.0", "id": 1, "result": {}}),
            httpx.Response(204),
            json_rpc_response(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"structuredContent": {"answer": "private-ok"}},
                }
            ),
        ]
    )
    executor = build_executor(client)

    result = executor.invoke_with_config(
        {"query": "status"},
        tenant_config={
            "mcp_server": "http://10.2.3.4/mcp",
            "tenant_slug": "tenant-a",
            "limit": 1,
        },
    )

    assert result["answer"] == "private-ok"
    assert client.requests[0]["endpoint"] == "http://10.2.3.4/mcp"


def test_mcp_executor_allowlist_restricts_public_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "http_executor_allowlist", ["*.allowed.test"])
    client = RecordingMcpClient(responses=[])
    executor = build_executor(client)

    with pytest.raises(McpExecutorError) as exc:
        executor.invoke_with_config(
            {"query": "status"},
            tenant_config={
                "mcp_server": "https://mcp.test/mcp",
                "tenant_slug": "tenant-a",
                "limit": 1,
            },
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []


def test_mcp_executor_translates_json_rpc_error() -> None:
    client = RecordingMcpClient(
        responses=[
            json_rpc_response({"jsonrpc": "2.0", "id": 1, "result": {}}),
            httpx.Response(204),
            json_rpc_response({"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "invalid params"}}),
        ]
    )
    executor = build_executor(client)

    with pytest.raises(McpExecutorError) as exc:
        executor.invoke_with_config(
            {"query": "status"},
            tenant_config={
                "mcp_server": "https://mcp.test/mcp",
                "tenant_slug": "tenant-a",
                "limit": 1,
            },
        )

    assert exc.value.code == "MCP_ERROR"
    assert "invalid params" in exc.value.detail
