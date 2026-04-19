import os

import pytest
from fastapi.testclient import TestClient

if not os.getenv("AOP_DATABASE_URL"):
    pytest.skip("AOP_DATABASE_URL 未配置，跳过 PostgreSQL 集成测试。", allow_module_level=True)

from agent_platform.main import app

client = TestClient(app)


def test_healthcheck_includes_database_status() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "database" in payload


def test_home_snapshot_returns_capabilities() -> None:
    response = client.get("/api/v1/workspace/home")
    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant"]["id"] == "tenant-demo"
    assert len(payload["enabled_capabilities"]) >= 2


def test_chat_completion_returns_trace_and_sources() -> None:
    response = client.post("/api/v1/chat/completions", json={"message": "张三还有几天年假？"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "hr_query"
    assert payload["trace_id"]
    assert payload["sources"][0]["source_type"] == "plugin"


def test_trace_lookup_returns_execution_steps() -> None:
    completion = client.post("/api/v1/chat/completions", json={"message": "P0a 要交付什么？"})
    trace_id = completion.json()["trace_id"]

    response = client.get(f"/api/v1/chat/traces/{trace_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["steps"]
    assert payload["intent"] == "knowledge_query"


def test_high_risk_message_returns_draft_action() -> None:
    response = client.post("/api/v1/chat/completions", json={"message": "帮我生成采购审批草稿"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "procurement_draft"
    assert payload["draft_action"]["risk_level"] == "high"


def test_confirm_draft_flow() -> None:
    draft_response = client.post(
        "/api/v1/chat/actions/draft",
        json={
            "capability_name": "workflow.procurement.request.create",
            "payload": {
                "request_title": "服务器采购申请",
                "amount": "¥ 80,000",
                "owner": "平台基础设施组",
            },
        },
    )
    assert draft_response.status_code == 200
    draft_id = draft_response.json()["draft_id"]

    confirm_response = client.post(f"/api/v1/chat/actions/{draft_id}/confirm")
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"


def test_admin_routes_return_scoped_data() -> None:
    response = client.get("/api/v1/admin/packages")
    assert response.status_code == 200
    payload = response.json()
    assert payload["packages"]
    assert payload["capabilities"]

    traces_response = client.get("/api/v1/admin/traces")
    assert traces_response.status_code == 200
