from __future__ import annotations

from typing import Any

import httpx
import pytest

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.executors.http import HttpExecutor, HttpExecutorError


class RecordingHttpClient:
    """协议级测试夹具：只记录请求，不连接真实业务系统。"""

    def __init__(self, *, responses: list[httpx.Response | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __enter__(self) -> "RecordingHttpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def request(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str],
        json: Any,
    ) -> httpx.Response:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "params": dict(params),
                "headers": dict(headers),
                "json": json,
            }
        )
        if not self.responses:
            raise AssertionError("No HTTP response configured for request")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def capability() -> CapabilityDefinition:
    return CapabilityDefinition(
        name="test.http.capability",
        description="Protocol-level HTTP executor test capability",
        risk_level="low",
        side_effect_level="read",
        required_scope="http:read",
        input_schema={"required": ["equipment_id"]},
        output_schema={"required": ["items"]},
        source="package",
        package_id="pkg.test_http",
    )


def build_executor(client: RecordingHttpClient, binding: dict[str, Any]) -> HttpExecutor:
    executor = HttpExecutor(
        capability(),
        package_id="pkg.test_http",
        plugin_name="http.test",
        binding=binding,
        client_factory=lambda timeout: client,
    )
    executor._sleep_before_retry = lambda attempt, retry_policy: None  # type: ignore[method-assign]
    return executor


def base_binding() -> dict[str, Any]:
    return {
        "method": "POST",
        "path": "/api/items/$input.equipment_id",
        "headers": {"Authorization": "Bearer $secret.token"},
        "body": {"summary": "$input.summary"},
        "response_map": {"items": "$response.body.data", "status": "$response.status"},
        "error_translation": {
            "400": "BAD_REQUEST",
            "5xx": "UPSTREAM_5XX",
        },
    }


@pytest.fixture(autouse=True)
def clear_http_executor_state(monkeypatch: pytest.MonkeyPatch) -> None:
    # 单测使用 RecordingHttpClient，不应受本机 config.toml 的本地联调 allowlist 影响。
    monkeypatch.setattr(settings, "http_executor_allowlist", [])
    HttpExecutor.clear_idempotency_cache()
    HttpExecutor.clear_rate_limit_buckets()


def test_http_executor_retries_5xx_until_success() -> None:
    client = RecordingHttpClient(
        responses=[
            httpx.Response(503, json={"error": "busy"}),
            httpx.Response(503, json={"error": "still busy"}),
            httpx.Response(200, json={"data": [{"id": "item-1"}]}),
        ]
    )
    binding = base_binding()
    binding["retry"] = {"policy": "exponential", "max_attempts": 3, "retry_on": ["5xx"]}
    executor = build_executor(client, binding)

    result = executor.invoke_with_config(
        {"equipment_id": "eq-1", "summary": "bearing noise"},
        tenant_config={"endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
    )

    assert result["items"] == [{"id": "item-1"}]
    assert result["status"] == 200
    assert len(client.requests) == 3


def test_http_executor_renders_idempotency_key_header() -> None:
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": []})])
    binding = base_binding()
    binding["idempotency_key"] = "draft:$input.equipment_id:$input.summary"
    executor = build_executor(client, binding)

    executor.invoke_with_config(
        {"equipment_id": "eq-1", "summary": "inspect pump"},
        tenant_config={"endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
    )

    assert client.requests[0]["headers"]["Idempotency-Key"] == "draft:eq-1:inspect pump"


def test_http_executor_returns_idempotency_cache_hit_without_second_request() -> None:
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": [{"id": "item-1"}]})])
    binding = base_binding()
    binding["idempotency_key"] = "draft:$input.equipment_id:$input.summary"
    executor = build_executor(client, binding)
    payload = {"equipment_id": "eq-1", "summary": "inspect pump"}
    config = {"endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}}

    first = executor.invoke_with_config(payload, tenant_config=config)
    second = executor.invoke_with_config(payload, tenant_config=config)

    assert first["items"] == [{"id": "item-1"}]
    assert second["items"] == [{"id": "item-1"}]
    assert second["_meta"]["idempotency_cache_hit"] is True
    assert len(client.requests) == 1


def test_http_executor_retries_timeout_when_declared() -> None:
    client = RecordingHttpClient(
        responses=[
            httpx.TimeoutException("timeout"),
            httpx.Response(200, json={"data": [{"id": "item-2"}]}),
        ]
    )
    binding = base_binding()
    binding["retry"] = {"policy": "exponential", "max_attempts": 2, "retry_on": ["UPSTREAM_TIMEOUT"]}
    executor = build_executor(client, binding)

    result = executor.invoke_with_config(
        {"equipment_id": "eq-2", "summary": "temperature spike"},
        tenant_config={"endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
    )

    assert result["items"] == [{"id": "item-2"}]
    assert len(client.requests) == 2


def test_http_executor_does_not_retry_4xx_by_default_and_translates_error() -> None:
    client = RecordingHttpClient(
        responses=[
            httpx.Response(400, json={"error": "bad request"}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    binding = base_binding()
    binding["retry"] = {"policy": "exponential", "max_attempts": 3, "retry_on": ["5xx"]}
    executor = build_executor(client, binding)

    with pytest.raises(HttpExecutorError) as exc:
        executor.invoke_with_config(
            {"equipment_id": "eq-3", "summary": "invalid request"},
            tenant_config={"endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
        )

    assert exc.value.code == "BAD_REQUEST"
    assert exc.value.status == 400
    assert len(client.requests) == 1


def test_http_executor_rate_limit_blocks_after_declared_quota() -> None:
    client = RecordingHttpClient(
        responses=[
            httpx.Response(200, json={"data": [{"id": "item-1"}]}),
            httpx.Response(200, json={"data": [{"id": "item-2"}]}),
        ]
    )
    binding = base_binding()
    binding["rate_limit"] = {"requests_per_minute": 1, "scope": "tenant"}
    executor = build_executor(client, binding)
    config = {"tenant_id": "tenant-a", "endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}}

    first = executor.invoke_with_config(
        {"equipment_id": "eq-1", "summary": "first request"},
        tenant_config=config,
    )
    with pytest.raises(HttpExecutorError) as exc:
        executor.invoke_with_config(
            {"equipment_id": "eq-2", "summary": "second request"},
            tenant_config=config,
        )

    assert first["items"] == [{"id": "item-1"}]
    assert exc.value.code == "RATE_LIMITED"
    assert len(client.requests) == 1


def test_http_executor_rate_limit_is_isolated_by_tenant_scope() -> None:
    client = RecordingHttpClient(
        responses=[
            httpx.Response(200, json={"data": [{"id": "tenant-a-item"}]}),
            httpx.Response(200, json={"data": [{"id": "tenant-b-item"}]}),
        ]
    )
    binding = base_binding()
    binding["rate_limit"] = {"requests_per_minute": 1, "scope": "tenant"}
    executor = build_executor(client, binding)

    tenant_a = executor.invoke_with_config(
        {"equipment_id": "eq-1", "summary": "first tenant"},
        tenant_config={"tenant_id": "tenant-a", "endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
    )
    tenant_b = executor.invoke_with_config(
        {"equipment_id": "eq-1", "summary": "second tenant"},
        tenant_config={"tenant_id": "tenant-b", "endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
    )

    assert tenant_a["items"] == [{"id": "tenant-a-item"}]
    assert tenant_b["items"] == [{"id": "tenant-b-item"}]
    assert len(client.requests) == 2


def test_http_executor_idempotency_cache_hit_does_not_consume_rate_limit() -> None:
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": [{"id": "item-1"}]})])
    binding = base_binding()
    binding["idempotency_key"] = "draft:$input.equipment_id:$input.summary"
    binding["rate_limit"] = {"requests_per_minute": 1, "scope": "tenant"}
    executor = build_executor(client, binding)
    payload = {"equipment_id": "eq-1", "summary": "same draft"}
    config = {"tenant_id": "tenant-a", "endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}}

    first = executor.invoke_with_config(payload, tenant_config=config)
    second = executor.invoke_with_config(payload, tenant_config=config)

    assert first["items"] == [{"id": "item-1"}]
    assert second["_meta"]["idempotency_cache_hit"] is True
    assert len(client.requests) == 1


def test_http_executor_blocks_metadata_ip_before_request() -> None:
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": []})])
    executor = build_executor(client, base_binding())

    with pytest.raises(HttpExecutorError) as exc:
        executor.invoke_with_config(
            {"equipment_id": "eq-1", "summary": "blocked"},
            tenant_config={"endpoint": "http://169.254.169.254", "secrets": {"token": "secret-token"}},
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []


def test_http_executor_blocks_localhost_before_request() -> None:
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": []})])
    executor = build_executor(client, base_binding())

    with pytest.raises(HttpExecutorError) as exc:
        executor.invoke_with_config(
            {"equipment_id": "eq-1", "summary": "blocked"},
            tenant_config={"endpoint": "http://localhost:18080", "secrets": {"token": "secret-token"}},
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []


def test_http_executor_allowlist_can_permit_private_cidr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "http_executor_allowlist", ["10.0.0.0/8"])
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": [{"id": "item-1"}]})])
    executor = build_executor(client, base_binding())

    result = executor.invoke_with_config(
        {"equipment_id": "eq-1", "summary": "allowed"},
        tenant_config={"endpoint": "http://10.2.3.4", "secrets": {"token": "secret-token"}},
    )

    assert result["items"] == [{"id": "item-1"}]
    assert client.requests[0]["url"] == "http://10.2.3.4/api/items/eq-1"


def test_http_executor_allowlist_can_permit_loopback_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "http_executor_allowlist", ["127.0.0.1"])
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": [{"id": "workorder-1"}]})])
    executor = build_executor(client, base_binding())

    result = executor.invoke_with_config(
        {"equipment_id": "EQ-CNC-650-01", "summary": "history"},
        tenant_config={"endpoint": "http://127.0.0.1:18081", "secrets": {"token": "secret-token"}},
    )

    assert result["items"] == [{"id": "workorder-1"}]
    assert client.requests[0]["url"] == "http://127.0.0.1:18081/api/items/EQ-CNC-650-01"


def test_http_executor_allowlist_restricts_public_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "http_executor_allowlist", ["*.allowed.test"])
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": []})])
    executor = build_executor(client, base_binding())

    with pytest.raises(HttpExecutorError) as exc:
        executor.invoke_with_config(
            {"equipment_id": "eq-1", "summary": "blocked"},
            tenant_config={"endpoint": "https://upstream.test", "secrets": {"token": "secret-token"}},
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []


def test_http_executor_validates_absolute_path_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "http_executor_allowlist", ["api.allowed.test"])
    client = RecordingHttpClient(responses=[httpx.Response(200, json={"data": []})])
    binding = base_binding()
    binding["path"] = "https://169.254.169.254/latest/meta-data"
    executor = build_executor(client, binding)

    with pytest.raises(HttpExecutorError) as exc:
        executor.invoke_with_config(
            {"equipment_id": "eq-1", "summary": "blocked"},
            tenant_config={"endpoint": "https://api.allowed.test", "secrets": {"token": "secret-token"}},
        )

    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert client.requests == []
