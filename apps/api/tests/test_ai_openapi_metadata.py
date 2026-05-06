from __future__ import annotations

from agent_platform.main import app


def test_ai_routes_have_chinese_openapi_metadata() -> None:
    schema = app.openapi()

    assert {"name": "AI 动作", "description": "结构化 AI Action、AI Run 和业务对象动作执行接口"} in schema["tags"]

    actions = schema["paths"]["/api/v1/ai/actions"]["get"]
    run_action = schema["paths"]["/api/v1/ai/actions/{action_id}/run"]["post"]
    runs = schema["paths"]["/api/v1/ai/runs"]["get"]
    run_detail = schema["paths"]["/api/v1/ai/runs/{run_id}"]["get"]
    run_trace = schema["paths"]["/api/v1/ai/runs/{run_id}/trace"]["get"]

    assert actions["tags"] == ["AI 动作"]
    assert actions["summary"] == "查询 AI 动作列表"
    assert run_action["summary"] == "执行 AI 动作"
    assert runs["summary"] == "查询 AI Run 列表"
    assert run_detail["summary"] == "查询 AI Run 详情"
    assert run_trace["summary"] == "查询 AI Run Trace"

    request_ref = run_action["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request_schema_name = request_ref.rsplit("/", 1)[-1]
    request_schema = schema["components"]["schemas"][request_schema_name]
    assert request_schema["properties"]["package_id"]["description"] == "业务包 ID，例如 industry.mfg_maintenance。"
    assert request_schema["properties"]["inputs"]["description"] == "AI 动作参数，例如 fault_code、last_n、query。"
