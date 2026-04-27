from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from agent_platform.api.deps import AuthContext
from agent_platform.bootstrap.container import chat_service, wiki_service

router = APIRouter(prefix="/admin", tags=["admin"])


class LLMRuntimeUpdateRequest(BaseModel):
    provider: Literal["openai-compatible", "openai", "azure", "anthropic"] = Field(default="openai-compatible")
    base_url: str = Field(default="")
    model: str = Field(default="")
    api_key: str = Field(default="")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    system_prompt: str = Field(default="")
    # Embedding 子配置；为空表示不修改对应字段。
    embedding_provider: Literal["openai-compatible", "openai", "azure"] | None = Field(default=None)
    embedding_base_url: str | None = Field(default=None)
    embedding_model: str | None = Field(default=None)
    embedding_api_key: str | None = Field(default=None)
    embedding_dimensions: int | None = Field(default=None, ge=8, le=8192)
    embedding_enabled: bool | None = Field(default=None)


class TenantCreateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    package: str = Field(..., max_length=255)
    environment: str = Field(..., max_length=64)
    budget: str = Field(..., max_length=64)


class TenantUpdateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    package: str = Field(..., max_length=255)
    environment: str = Field(..., max_length=64)
    budget: str = Field(..., max_length=64)
    active: bool = Field(default=True)


class UserCreateRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(default="Aa111111", min_length=6, max_length=128)
    role: str = Field(..., max_length=64)
    scopes: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    role: str = Field(..., max_length=64)
    scopes: list[str] = Field(default_factory=list)


class TenantPackagesUpdateRequest(BaseModel):
    primary_package: str = Field(..., max_length=255)
    common_packages: list[str] = Field(default_factory=list)


class PluginConfigUpdateRequest(BaseModel):
    config: dict[str, object] = Field(default_factory=dict)


class ToolOverrideUpdateRequest(BaseModel):
    tenant_id: str = Field(..., max_length=64)
    tool_name: str = Field(..., max_length=128)
    quota: int | None = Field(default=None, ge=0)
    timeout: int | None = Field(default=None, ge=0)
    disabled: bool = Field(default=False)


class OutputGuardRuleUpdateRequest(BaseModel):
    rule_id: str = Field(..., min_length=1, max_length=128)
    package_id: str = Field(..., min_length=1, max_length=255)
    pattern: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1, max_length=128)
    source: str = Field(..., min_length=1, max_length=128)
    enabled: bool = Field(default=True)


class ReleasePlanUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=64)
    rollout_percent: int = Field(..., ge=0, le=100)


class KnowledgeIngestRequest(BaseModel):
    knowledge_base_code: str = Field(default="knowledge", max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source_type: str = Field(default="Markdown", max_length=64)
    owner: str = Field(default="知识平台组", max_length=255)


class WikiCompileRequest(BaseModel):
    source_id: str | None = Field(default=None, max_length=64)
    space_code: str = Field(default="knowledge", max_length=64)


class WikiSourceIngestRequest(BaseModel):
    knowledge_base_code: str = Field(default="knowledge", max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source_type: str = Field(default="Markdown", max_length=64)
    owner: str = Field(default="知识平台组", max_length=255)


class KnowledgeBaseCreateRequest(BaseModel):
    knowledge_base_code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")


class KnowledgeBaseUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    status: str = Field(default="active", max_length=32)


@router.get("/packages")
async def list_packages(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_admin_packages(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/packages/impact")
async def package_impact(
    auth: AuthContext,
    target: str = Query(..., min_length=3, pattern=r"^[A-Za-z0-9_./:-]+@[A-Za-z0-9_.+-]+$"),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.get_package_impact(target=target, tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/packages/import")
async def import_package_bundle(
    auth: AuthContext,
    file: UploadFile = File(...),
    overwrite: bool = Query(default=False),
) -> dict[str, object]:
    tenant_id, user_id = auth
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Bundle must be a .zip file")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        return await chat_service.install_package_bundle(
            zip_bytes=payload,
            overwrite=overwrite,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "already installed" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.delete("/packages/{package_id:path}/bundle")
async def uninstall_package_bundle(package_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.uninstall_package_bundle(
            package_id=package_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/packages/{package_id:path}")
async def package_detail(package_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.get_package_detail(package_id=package_id, tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/plugins/{plugin_name:path}/config-schema")
async def plugin_config_schema(plugin_name: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.get_plugin_config_schema(
            plugin_name=plugin_name,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Plugin not found") from exc


@router.put("/plugins/{plugin_name:path}/config")
async def update_plugin_config(
    plugin_name: str,
    payload: PluginConfigUpdateRequest,
    auth: AuthContext,
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_plugin_config(
            plugin_name=plugin_name,
            config=payload.config,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Plugin not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/system")
async def system_overview(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_system_overview(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/releases")
async def list_releases(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_release_plans(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/releases/{release_id}")
async def update_release(release_id: str, payload: ReleasePlanUpdateRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_release_plan(
            release_id,
            status=payload.status,
            rollout_percent=payload.rollout_percent,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/llm-runtime")
async def llm_runtime(auth: AuthContext) -> dict[str, object]:
    tenant_id, _ = auth
    return await chat_service.get_llm_runtime(tenant_id=tenant_id)


@router.post("/llm-runtime")
async def update_llm_runtime(payload: LLMRuntimeUpdateRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, _ = auth
    return await chat_service.update_llm_runtime(
        tenant_id=tenant_id,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
        temperature=payload.temperature,
        system_prompt=payload.system_prompt,
        embedding_provider=payload.embedding_provider,
        embedding_base_url=payload.embedding_base_url,
        embedding_model=payload.embedding_model,
        embedding_api_key=payload.embedding_api_key,
        embedding_dimensions=payload.embedding_dimensions,
        embedding_enabled=payload.embedding_enabled,
    )


# Tenant CRUD
@router.get("/tenants")
async def list_tenants(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        tenants = await chat_service.list_tenants(tenant_id=tenant_id, user_id=user_id)
        return {"tenants": [asdict(item) for item in tenants]}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/tenants")
async def create_tenant(payload: TenantCreateRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        tenant = await chat_service.create_tenant(
            name=payload.name,
            package=payload.package,
            environment=payload.environment,
            budget=payload.budget,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return asdict(tenant)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/tenants/{target_tenant_id}")
async def update_tenant(target_tenant_id: str, payload: TenantUpdateRequest, auth: AuthContext) -> dict[str, object]:
    auth_tenant_id, user_id = auth
    try:
        tenant = await chat_service.update_tenant(
            tenant_id=target_tenant_id,
            name=payload.name,
            package=payload.package,
            environment=payload.environment,
            budget=payload.budget,
            active=payload.active,
            auth_tenant_id=auth_tenant_id,
            user_id=user_id,
        )
        return asdict(tenant)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/tenants/{target_tenant_id}/packages")
async def list_tenant_packages(target_tenant_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_tenant_packages(
            target_tenant_id=target_tenant_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/tenants/{target_tenant_id}/packages")
async def update_tenant_packages(
    target_tenant_id: str,
    payload: TenantPackagesUpdateRequest,
    auth: AuthContext,
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_tenant_packages(
            target_tenant_id=target_tenant_id,
            primary_package=payload.primary_package,
            common_packages=payload.common_packages,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/tenants/{target_tenant_id}")
async def delete_tenant(target_tenant_id: str, auth: AuthContext) -> dict[str, object]:
    auth_tenant_id, user_id = auth
    try:
        success = await chat_service.delete_tenant(
            target_tenant_id,
            auth_tenant_id=auth_tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"deleted": True}


# User CRUD
@router.get("/tenants/{tenant_id}/users")
async def list_tenant_users(tenant_id: str) -> dict[str, object]:
    users = await chat_service.list_tenant_users(tenant_id)
    return {"users": [asdict(u) for u in users]}


@router.post("/tenants/{tenant_id}/users")
async def create_user(tenant_id: str, payload: UserCreateRequest) -> dict[str, object]:
    try:
        user = await chat_service.create_user(
            tenant_id=tenant_id,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            scopes=payload.scopes,
        )
        return asdict(user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/tenants/{tenant_id}/users/{user_id}")
async def update_user(tenant_id: str, user_id: str, payload: UserUpdateRequest) -> dict[str, object]:
    try:
        user = await chat_service.update_user(
            tenant_id=tenant_id,
            user_id=user_id,
            role=payload.role,
            scopes=payload.scopes,
        )
        return asdict(user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tenants/{tenant_id}/users/{user_id}")
async def delete_user(tenant_id: str, user_id: str) -> dict[str, object]:
    success = await chat_service.delete_user(tenant_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deleted": True}


@router.get("/security")
async def security_overview(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_security_overview(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/security/tool-overrides")
async def update_tool_override(payload: ToolOverrideUpdateRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_tool_override(
            target_tenant_id=payload.tenant_id,
            tool_name=payload.tool_name,
            quota=payload.quota,
            timeout=payload.timeout,
            disabled=payload.disabled,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.put("/security/redlines")
async def update_output_guard_rule(payload: OutputGuardRuleUpdateRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_output_guard_rule(
            rule_id=payload.rule_id,
            package_id=payload.package_id,
            pattern=payload.pattern,
            action=payload.action,
            source=payload.source,
            enabled=payload.enabled,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/knowledge")
async def knowledge_sources(
    auth: AuthContext,
    knowledge_base_code: str | None = Query(default=None),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_knowledge_sources(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_code=knowledge_base_code,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/knowledge/{source_id}")
async def knowledge_source_detail(source_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.get_knowledge_source_detail(
            source_id=source_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/knowledge/sources/{source_id}/attributes")
async def knowledge_source_attributes(source_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.get_knowledge_source_attributes(
            source_id=source_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/knowledge-bases")
async def list_knowledge_bases(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_knowledge_bases(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge-bases")
async def create_knowledge_base(payload: KnowledgeBaseCreateRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.create_knowledge_base(
            knowledge_base_code=payload.knowledge_base_code,
            name=payload.name,
            description=payload.description,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/knowledge-bases/{knowledge_base_code}")
async def update_knowledge_base(
    knowledge_base_code: str,
    payload: KnowledgeBaseUpdateRequest,
    auth: AuthContext,
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_knowledge_base(
            knowledge_base_code=knowledge_base_code,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/knowledge-bases/{knowledge_base_code}")
async def delete_knowledge_base(knowledge_base_code: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.delete_knowledge_base(
            knowledge_base_code=knowledge_base_code,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wiki/pages")
async def list_wiki_pages(
    auth: AuthContext,
    status: str | None = Query(default=None),
    page_type: str | None = Query(default=None),
    space_code: str | None = Query(default=None),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.list_pages(
            tenant_id=tenant_id,
            user_id=user_id,
            status=status,
            page_type=page_type,
            space_code=space_code,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/wiki/pages/{page_id}")
async def get_wiki_page(page_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.get_page_detail(page_id=page_id, tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/wiki/pages/{page_id}/revisions")
async def get_wiki_page_revisions(page_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.list_page_revisions(page_id=page_id, tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/wiki/search")
async def search_wiki(
    auth: AuthContext,
    query: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    space_code: str | None = Query(default=None),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.search(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            top_k=top_k,
            space_code=space_code,
            scope_mode="admin",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/wiki/compile")
async def compile_wiki(payload: WikiCompileRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.compile_sources(
            tenant_id=tenant_id,
            user_id=user_id,
            source_id=payload.source_id,
            space_code=payload.space_code,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wiki/compile-runs")
async def list_wiki_compile_runs(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.list_compile_runs(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/wiki/compile-runs/{compile_run_id}")
async def get_wiki_compile_run(compile_run_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.get_compile_run(
            compile_run_id=compile_run_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/wiki/file-distribution/overview")
async def get_wiki_file_distribution_overview(
    auth: AuthContext,
    space_code: str | None = Query(default=None),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.get_file_distribution_overview(
            tenant_id=tenant_id,
            user_id=user_id,
            space_code=space_code,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/wiki/file-distribution")
async def list_wiki_file_distribution(
    auth: AuthContext,
    space_code: str | None = Query(default=None),
    group_by: str = Query(default="source_type"),
    coverage_status: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.list_file_distribution(
            tenant_id=tenant_id,
            user_id=user_id,
            space_code=space_code,
            group_by=group_by,
            coverage_status=coverage_status,
            source_type=source_type,
            owner=owner,
            keyword=keyword,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/wiki/file-distribution/{source_id}")
async def get_wiki_file_distribution_detail(
    source_id: str,
    auth: AuthContext,
    space_code: str | None = Query(default=None),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.get_file_distribution_detail(
            source_id=source_id,
            tenant_id=tenant_id,
            user_id=user_id,
            space_code=space_code,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/wiki/sources/ingest")
async def ingest_wiki_source(payload: WikiSourceIngestRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.ingest_source(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_code=payload.knowledge_base_code,
            name=payload.name,
            content=payload.content,
            source_type=payload.source_type,
            owner=payload.owner,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wiki/sources/{source_id}")
async def get_wiki_source_detail(source_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await wiki_service.get_source_detail(
            source_id=source_id, tenant_id=tenant_id, user_id=user_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class KnowledgeReembedRequest(BaseModel):
    batch_size: int = Field(default=32, ge=1, le=128)
    limit: int | None = Field(default=None, ge=1, le=10000)


@router.post("/knowledge/reembed")
async def reembed_knowledge(payload: KnowledgeReembedRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.reembed_knowledge(
            tenant_id=tenant_id,
            user_id=user_id,
            batch_size=payload.batch_size,
            limit=payload.limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/knowledge/ingest")
async def ingest_knowledge_source(payload: KnowledgeIngestRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.ingest_knowledge_source(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_code=payload.knowledge_base_code,
            name=payload.name,
            content=payload.content,
            source_type=payload.source_type,
            owner=payload.owner,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/traces")
async def list_traces(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return {"items": await chat_service.list_traces(tenant_id=tenant_id, user_id=user_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
