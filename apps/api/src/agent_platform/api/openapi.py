from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


TAG_NAMES = {
    "chat": "对话与执行",
    "workspace": "工作台",
    "outputs": "业务成果",
    "admin": "管理后台",
    "auth": "认证",
    "system": "系统",
}


TAG_METADATA = [
    {"name": "对话与执行", "description": "对话、会话、Trace 和高风险动作确认接口"},
    {"name": "工作台", "description": "控制台首页和工作台聚合数据接口"},
    {"name": "业务成果", "description": "业务成果的创建、查询和更新接口"},
    {"name": "管理后台", "description": "业务包、系统配置、租户、知识库、安全和 Wiki 管理接口"},
    {"name": "认证", "description": "登录、注册和当前用户接口"},
    {"name": "系统", "description": "健康检查等系统接口"},
]


OPERATION_SUMMARIES = {
    ("POST", "/api/v1/chat/completions"): "创建同步对话回复",
    ("POST", "/api/v1/chat/completions/stream"): "创建流式对话回复",
    ("GET", "/api/v1/chat/conversations"): "查询会话列表",
    ("POST", "/api/v1/chat/conversations"): "创建会话",
    ("GET", "/api/v1/chat/conversations/{conversation_id}"): "查询会话详情",
    ("DELETE", "/api/v1/chat/conversations/{conversation_id}"): "删除会话",
    ("GET", "/api/v1/chat/traces/{trace_id}"): "查询执行 Trace 详情",
    ("POST", "/api/v1/chat/actions/draft"): "创建高风险动作草稿",
    ("POST", "/api/v1/chat/actions/{draft_id}/confirm"): "确认执行动作草稿",
    ("GET", "/api/v1/workspace/home"): "查询工作台首页数据",
    ("GET", "/api/v1/outputs"): "查询业务成果列表",
    ("POST", "/api/v1/outputs"): "创建业务成果",
    ("GET", "/api/v1/outputs/{output_id}"): "查询业务成果详情",
    ("PATCH", "/api/v1/outputs/{output_id}"): "更新业务成果",
    ("GET", "/api/v1/admin/packages"): "查询业务包列表",
    ("GET", "/api/v1/admin/packages/impact"): "查询业务包影响分析",
    ("POST", "/api/v1/admin/packages/import"): "导入业务包 Bundle",
    ("DELETE", "/api/v1/admin/packages/{package_id}/bundle"): "卸载业务包 Bundle",
    ("POST", "/api/v1/admin/packages/knowledge/import"): "导入业务包知识",
    ("POST", "/api/v1/admin/packages/knowledge/preview"): "预览业务包知识文件",
    ("GET", "/api/v1/admin/packages/{package_id}"): "查询业务包详情",
    ("GET", "/api/v1/admin/plugins/{plugin_name}/config-schema"): "查询插件配置 Schema",
    ("PUT", "/api/v1/admin/plugins/{plugin_name}/config"): "更新插件配置",
    ("GET", "/api/v1/admin/mcp-servers"): "查询 MCP Server 列表",
    ("POST", "/api/v1/admin/mcp-servers"): "新增或更新 MCP Server",
    ("PUT", "/api/v1/admin/mcp-servers/{server_name}"): "更新 MCP Server",
    ("DELETE", "/api/v1/admin/mcp-servers/{server_name}"): "删除 MCP Server",
    ("GET", "/api/v1/admin/system"): "查询系统概览",
    ("GET", "/api/v1/admin/releases"): "查询发布计划列表",
    ("PUT", "/api/v1/admin/releases/{release_id}"): "更新发布计划",
    ("GET", "/api/v1/admin/llm-runtime"): "查询 LLM 运行配置",
    ("POST", "/api/v1/admin/llm-runtime"): "更新 LLM 运行配置",
    ("GET", "/api/v1/admin/tenants"): "查询租户列表",
    ("POST", "/api/v1/admin/tenants"): "创建租户",
    ("PUT", "/api/v1/admin/tenants/{target_tenant_id}"): "更新租户",
    ("DELETE", "/api/v1/admin/tenants/{target_tenant_id}"): "删除租户",
    ("GET", "/api/v1/admin/tenants/{target_tenant_id}/packages"): "查询租户绑定业务包",
    ("PUT", "/api/v1/admin/tenants/{target_tenant_id}/packages"): "更新租户绑定业务包",
    ("GET", "/api/v1/admin/tenants/{tenant_id}/users"): "查询租户用户列表",
    ("POST", "/api/v1/admin/tenants/{tenant_id}/users"): "创建租户用户",
    ("PUT", "/api/v1/admin/tenants/{tenant_id}/users/{user_id}"): "更新租户用户",
    ("DELETE", "/api/v1/admin/tenants/{tenant_id}/users/{user_id}"): "删除租户用户",
    ("GET", "/api/v1/admin/security"): "查询安全治理概览",
    ("PUT", "/api/v1/admin/security/tool-overrides"): "更新工具覆盖策略",
    ("PUT", "/api/v1/admin/security/redlines"): "更新输出红线规则",
    ("GET", "/api/v1/admin/knowledge"): "查询知识源列表",
    ("GET", "/api/v1/admin/knowledge/{source_id}"): "查询知识源详情",
    ("GET", "/api/v1/admin/knowledge/sources/{source_id}/attributes"): "查询知识源属性",
    ("GET", "/api/v1/admin/knowledge-bases"): "查询知识库列表",
    ("POST", "/api/v1/admin/knowledge-bases"): "创建知识库",
    ("PUT", "/api/v1/admin/knowledge-bases/{knowledge_base_code}"): "更新知识库",
    ("DELETE", "/api/v1/admin/knowledge-bases/{knowledge_base_code}"): "删除知识库",
    ("GET", "/api/v1/admin/wiki/pages"): "查询 Wiki 页面列表",
    ("GET", "/api/v1/admin/wiki/pages/{page_id}"): "查询 Wiki 页面详情",
    ("GET", "/api/v1/admin/wiki/pages/{page_id}/revisions"): "查询 Wiki 页面版本列表",
    ("GET", "/api/v1/admin/wiki/search"): "搜索 Wiki",
    ("POST", "/api/v1/admin/wiki/compile"): "编译 Wiki 内容",
    ("GET", "/api/v1/admin/wiki/compile-runs"): "查询 Wiki 编译任务列表",
    ("GET", "/api/v1/admin/wiki/compile-runs/{compile_run_id}"): "查询 Wiki 编译任务详情",
    ("GET", "/api/v1/admin/wiki/file-distribution/overview"): "查询 Wiki 文件分布概览",
    ("GET", "/api/v1/admin/wiki/file-distribution"): "查询 Wiki 文件分布列表",
    ("GET", "/api/v1/admin/wiki/file-distribution/{source_id}"): "查询 Wiki 文件分布详情",
    ("POST", "/api/v1/admin/wiki/sources/ingest"): "写入 Wiki 知识源",
    ("GET", "/api/v1/admin/wiki/sources/{source_id}"): "查询 Wiki 知识源详情",
    ("POST", "/api/v1/admin/knowledge/reembed"): "重新生成知识向量",
    ("POST", "/api/v1/admin/knowledge/ingest"): "写入知识源",
    ("GET", "/api/v1/admin/traces"): "查询 Trace 列表",
    ("POST", "/api/v1/auth/login"): "登录",
    ("POST", "/api/v1/auth/register"): "注册",
    ("GET", "/api/v1/auth/me"): "查询当前用户",
    ("GET", "/healthz"): "健康检查",
}


def configure_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description="Agent Operating Platform 后端接口文档",
            routes=app.routes,
        )
        schema["tags"] = TAG_METADATA

        for path, methods in schema.get("paths", {}).items():
            for method, operation in methods.items():
                if not isinstance(operation, dict):
                    continue
                summary = OPERATION_SUMMARIES.get((method.upper(), path))
                if summary:
                    operation["summary"] = summary
                    operation.setdefault("description", summary)
                if path == "/healthz":
                    operation["tags"] = ["system"]
                operation["tags"] = [TAG_NAMES.get(tag, tag) for tag in operation.get("tags", [])]

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
