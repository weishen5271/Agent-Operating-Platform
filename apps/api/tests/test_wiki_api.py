import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_platform.bootstrap.settings import settings


if not settings.database_url:
    pytest.skip("AOP_DATABASE_URL / config.toml 未配置数据库，跳过 Wiki 集成测试。", allow_module_level=True)

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from agent_platform.main import app

client = TestClient(app)
_created_knowledge_base_codes: set[str] = set()


@pytest.fixture(autouse=True)
def cleanup_created_knowledge_bases() -> Iterator[None]:
    yield
    for knowledge_base_code in _created_knowledge_base_codes:
        response = client.delete(f"/api/v1/admin/knowledge-bases/{knowledge_base_code}")
        assert response.status_code in {200, 404}
    _created_knowledge_base_codes.clear()


def create_real_source(*, knowledge_base_code: str | None = None, name: str = "测试知识源") -> tuple[str, str]:
    resolved_knowledge_base_code = knowledge_base_code or f"kb-{uuid4().hex[:8]}"
    create_kb_response = client.post(
        "/api/v1/admin/knowledge-bases",
        json={
          "knowledge_base_code": resolved_knowledge_base_code,
          "name": f"{name}知识库-{resolved_knowledge_base_code}",
          "description": "测试期间动态创建的真实知识库。",
        },
    )
    assert create_kb_response.status_code == 200
    _created_knowledge_base_codes.add(resolved_knowledge_base_code)

    ingest_response = client.post(
        "/api/v1/admin/wiki/sources/ingest",
        json={
            "knowledge_base_code": resolved_knowledge_base_code,
            "name": name,
            "content": f"{name}的真实测试内容，用于编译 Wiki 页面和文件分布。",
            "source_type": "Markdown",
            "owner": "测试组",
        },
    )
    assert ingest_response.status_code == 200
    source_id = ingest_response.json()["source"]["source_id"]
    return resolved_knowledge_base_code, source_id


def test_wiki_compile_creates_pages_and_compile_run() -> None:
    knowledge_base_code, source_id = create_real_source(name="编译测试源")
    response = client.post("/api/v1/admin/wiki/compile", json={"source_id": source_id, "space_code": knowledge_base_code})

    assert response.status_code == 200
    payload = response.json()
    assert payload["compile_run"]["status"] == "completed"
    assert payload["compile_run"]["scope_type"] == "source"
    assert payload["compile_run"]["scope_value"] == source_id
    assert payload["pages"]
    assert payload["pages"][0]["page"]["status"] == "published"
    assert payload["pages"][0]["page"]["source_count"] >= 1
    assert payload["pages"][0]["citations"]


def test_wiki_pages_detail_and_revisions_return_compiled_content() -> None:
    knowledge_base_code, source_id = create_real_source(name="详情测试源")
    compile_response = client.post("/api/v1/admin/wiki/compile", json={"source_id": source_id, "space_code": knowledge_base_code})
    assert compile_response.status_code == 200
    compiled_page = compile_response.json()["pages"][0]["page"]
    page_id = compiled_page["page_id"]

    list_response = client.get(f"/api/v1/admin/wiki/pages?space_code={knowledge_base_code}")
    assert list_response.status_code == 200
    pages = list_response.json()["pages"]
    assert any(page["page_id"] == page_id for page in pages)

    detail_response = client.get(f"/api/v1/admin/wiki/pages/{page_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["page"]["page_id"] == page_id
    assert "Wiki 总览" in detail_payload["page"]["title"]
    assert detail_payload["citations"]
    assert detail_payload["citations"][0]["source_id"] == source_id

    revisions_response = client.get(f"/api/v1/admin/wiki/pages/{page_id}/revisions")
    assert revisions_response.status_code == 200
    revisions = revisions_response.json()["revisions"]
    assert revisions
    assert revisions[0]["page_id"] == page_id
    assert revisions[0]["revision_no"] >= 1


def test_wiki_compile_runs_endpoint_returns_latest_runs() -> None:
    knowledge_base_code, source_id = create_real_source(name="运行记录测试源")
    compile_response = client.post("/api/v1/admin/wiki/compile", json={"source_id": source_id, "space_code": knowledge_base_code})
    assert compile_response.status_code == 200
    compile_run_id = compile_response.json()["compile_run"]["compile_run_id"]

    runs_response = client.get("/api/v1/admin/wiki/compile-runs")
    assert runs_response.status_code == 200
    items = runs_response.json()["items"]
    assert any(item["compile_run_id"] == compile_run_id for item in items)

    detail_response = client.get(f"/api/v1/admin/wiki/compile-runs/{compile_run_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["compile_run_id"] == compile_run_id
    assert detail_payload["status"] == "completed"


def test_wiki_file_distribution_endpoints_return_source_coverage() -> None:
    knowledge_base_code, source_id = create_real_source(name="分布测试源")
    compile_response = client.post("/api/v1/admin/wiki/compile", json={"source_id": source_id, "space_code": knowledge_base_code})
    assert compile_response.status_code == 200

    distribution_response = client.get(f"/api/v1/admin/wiki/file-distribution?space_code={knowledge_base_code}")
    assert distribution_response.status_code == 200
    distribution_payload = distribution_response.json()
    assert distribution_payload["overview"]["total_sources"] >= 1
    assert distribution_payload["items"]

    item = next((entry for entry in distribution_payload["items"] if entry["source_id"] == source_id), None)
    assert item is not None
    assert item["coverage_status"] in {"已进入页面", "高影响"}
    assert item["compiled"] is True

    detail_response = client.get(f"/api/v1/admin/wiki/file-distribution/{source_id}?space_code={knowledge_base_code}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["item"]["source_id"] == source_id
    assert detail_payload["related_pages"]


def test_knowledge_base_crud_and_filtered_sources() -> None:
    knowledge_base_code = f"ops-{uuid4().hex[:8]}"
    create_response = client.post(
        "/api/v1/admin/knowledge-bases",
        json={
            "knowledge_base_code": knowledge_base_code,
            "name": f"运维知识库-{knowledge_base_code}",
            "description": "用于验证知识库隔离与 CRUD。",
        },
    )
    assert create_response.status_code == 200
    _created_knowledge_base_codes.add(knowledge_base_code)
    assert create_response.json()["knowledge_base_code"] == knowledge_base_code

    ingest_response = client.post(
        "/api/v1/admin/knowledge/ingest",
        json={
            "knowledge_base_code": knowledge_base_code,
            "name": "运维手册",
            "content": "运维知识库用于故障处理与值班流程。",
            "source_type": "Markdown",
            "owner": "运维组",
        },
    )
    assert ingest_response.status_code == 200
    assert ingest_response.json()["source"]["knowledge_base_code"] == knowledge_base_code

    list_response = client.get(f"/api/v1/admin/knowledge?knowledge_base_code={knowledge_base_code}")
    assert list_response.status_code == 200
    assert any(item["knowledge_base_code"] == knowledge_base_code for item in list_response.json()["sources"])

    delete_response = client.delete(f"/api/v1/admin/knowledge-bases/{knowledge_base_code}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    _created_knowledge_base_codes.discard(knowledge_base_code)

    deleted_source_response = client.get(f"/api/v1/admin/knowledge?knowledge_base_code={knowledge_base_code}")
    assert deleted_source_response.status_code == 200
    assert deleted_source_response.json()["sources"] == []
