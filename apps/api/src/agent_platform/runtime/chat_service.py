from __future__ import annotations

import asyncio
from dataclasses import asdict
import re
from typing import AsyncIterator, Awaitable, Callable, Literal
from uuid import uuid4

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import (
    CapabilityDefinition,
    Conversation,
    DraftAction,
    KnowledgeBase,
    LLMRuntimeConfig,
    SourceReference,
    TenantProfile,
    TraceRecord,
    TraceStep,
    UserContext,
    utc_now,
)
from agent_platform.infrastructure.auth import get_password_hash, verify_password
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.infrastructure.repositories import (
    ConversationRepository,
    DraftRepository,
    KnowledgeRepository,
    KnowledgeBaseRepository,
    LLMConfigRepository,
    SecurityRepository,
    TenantRepository,
    TraceRepository,
    UserRepository,
)
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.wiki.service import WikiService


TENANT_MANAGE_SCOPE = "tenant:manage"
TraceStepCallback = Callable[[TraceRecord, TraceStep], Awaitable[None]]
AnswerDeltaCallback = Callable[[str], Awaitable[None]]


class ChatService:
    def __init__(
        self,
        registry: CapabilityRegistry,
        conversations: ConversationRepository,
        traces: TraceRepository,
        tenants: TenantRepository,
        users: UserRepository,
        drafts: DraftRepository,
        security_events: SecurityRepository,
        knowledge_sources: KnowledgeRepository,
        knowledge_bases: KnowledgeBaseRepository,
        wiki_service: WikiService,
        llm_config: LLMConfigRepository,
        llm_client: OpenAICompatibleLLMClient,
    ) -> None:
        self._registry = registry
        self._conversations = conversations
        self._traces = traces
        self._tenants = tenants
        self._users = users
        self._drafts = drafts
        self._security_events = security_events
        self._knowledge_sources = knowledge_sources
        self._knowledge_bases = knowledge_bases
        self._wiki_service = wiki_service
        self._llm_config = llm_config
        self._llm_client = llm_client

    async def home_snapshot(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        tenant = await self._tenants.get(context.tenant_id)
        return {
            "tenant": {
                "id": context.tenant_id,
                "name": tenant.name if tenant else "Unknown Tenant",
                "package": tenant.package if tenant else "未绑定业务包",
            },
            "llm_runtime": await self.get_llm_runtime(tenant_id=context.tenant_id),
            "enabled_capabilities": [
                {
                    "name": capability.name,
                    "description": capability.description,
                    "risk_level": capability.risk_level,
                    "required_scope": capability.required_scope,
                }
                for capability in self._registry.list_capabilities()
            ],
            "recent_conversations": [
                {
                    "conversation_id": conversation.conversation_id,
                    "title": conversation.title,
                    "updated_at": conversation.updated_at.isoformat(),
                }
                for conversation in await self._conversations.list_recent(context.tenant_id, context.user_id)
            ],
        }

    async def complete(
        self,
        message: str,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        retrieval_mode: Literal["auto", "rag", "wiki"] = "auto",
    ) -> dict[str, object]:
        return await self._complete_core(
            message=message,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            retrieval_mode=retrieval_mode,
        )

    async def stream_complete(
        self,
        message: str,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        retrieval_mode: Literal["auto", "rag", "wiki"] = "auto",
    ) -> AsyncIterator[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def emit_step(trace: TraceRecord, step: TraceStep) -> None:
            await queue.put(
                {
                    "event": "trace_step",
                    "trace_id": trace.trace_id,
                    "step": asdict(step),
                }
            )

        async def emit_answer_delta(chunk: str) -> None:
            await queue.put({"event": "message_delta", "content": chunk})

        task = asyncio.create_task(
            self._complete_core(
                message=message,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                retrieval_mode=retrieval_mode,
                on_step=emit_step,
                on_answer_delta=emit_answer_delta,
            )
        )

        while not task.done() or not queue.empty():
            try:
                yield await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                continue

        response = task.result()
        yield {
            "event": "response_meta",
            "trace_id": response["trace_id"],
            "conversation_id": response["conversation_id"],
            "intent": response["intent"],
            "strategy": response["strategy"],
            "sources": response["sources"],
            "warnings": response.get("warnings", []),
            "draft_action": response.get("draft_action"),
        }
        answer = str(response["message"]["content"])
        yield {"event": "message_done", "content": answer}
        yield {"event": "done"}

    async def _complete_core(
        self,
        message: str,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        retrieval_mode: Literal["auto", "rag", "wiki"] = "auto",
        on_step: TraceStepCallback | None = None,
        on_answer_delta: AnswerDeltaCallback | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        tenant = await self._tenants.get(context.tenant_id)
        if tenant is None:
            raise ValueError("Tenant context not found")
        trace_id = str(uuid4())
        trace = TraceRecord(
            trace_id=trace_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            message=message,
            intent="unknown",
            strategy="direct_answer",
        )

        async def add_step(step: TraceStep) -> None:
            trace.steps.append(step)
            if on_step is not None:
                await on_step(trace, step)

        answer_streamed = False

        async def stream_answer(answer_chunk: str) -> None:
            nonlocal answer_streamed
            if on_answer_delta is None or not answer_chunk:
                return
            answer_streamed = True
            await on_answer_delta(answer_chunk)

        await add_step(TraceStep(name="received", status="completed", summary="请求已进入 Supervisor。"))

        input_findings = self._inspect_input(message)
        await add_step(
            TraceStep(
                name="input_guard",
                status="completed",
                summary="输入安全检查完成。" if not input_findings else f"输入安全检查完成，识别到 {', '.join(input_findings)}。",
            )
        )

        short_memory = await self._load_short_memory(context.tenant_id, context.user_id, conversation_id)
        long_memory_summary = await self._load_long_memory_summary(context.tenant_id)
        await add_step(
            TraceStep(
                name="memory",
                status="completed",
                summary=(
                    f"已读取短期记忆 {len(short_memory.messages)} 条消息，"
                    f"长期知识摘要：{long_memory_summary}"
                ),
            )
        )

        intent = self._classify_intent(message, retrieval_mode=retrieval_mode)
        strategy = "plan_execute" if intent in {"hr_query", "procurement_draft"} else "direct_answer"
        trace.intent = intent
        trace.strategy = strategy
        await add_step(TraceStep(name="classified", status="completed", summary=f"识别意图为 {intent}，策略为 {strategy}。"))

        candidate_capabilities = self._select_candidate_capabilities(context)
        await add_step(
            TraceStep(
                name="capability_candidates",
                status="completed",
                summary=f"当前可用 capability 共 {len(candidate_capabilities)} 个。",
            )
        )

        sources: list[SourceReference] = []
        warnings: list[str] = []
        capability = None
        if intent == "general_chat":
            self._ensure_scope(context=context, required_scope="chat:read")
            self._check_quota(message)
            await add_step(TraceStep(name="planned", status="completed", summary="命中模型直答链路: model.direct_chat。"))
            await add_step(TraceStep(name="risk", status="completed", summary="风险等级 low，自主度上限：auto_execute。"))
            await add_step(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。"))
            answer, used_model = await self._generate_direct_llm_answer(
                tenant_id=context.tenant_id,
                message=message,
                short_memory=short_memory,
                on_delta=stream_answer if on_answer_delta is not None else None,
            )
            await add_step(TraceStep(name="executed", status="completed", summary="model.direct_chat 执行完成。"))
            await add_step(
                TraceStep(
                    name="model",
                    status="completed" if used_model else "failed",
                    summary="已通过 OpenAI-compatible 模型生成日常对话回答。" if used_model else "LLM Runtime 未启用，无法生成日常对话回答。",
                )
            )
            if not used_model:
                warnings.append("LLM 运行时未启用，已退化到内置文案。请在「设置 → LLM 配置」中启用模型。")
        else:
            capability_name, payload = self._plan(message, intent)
            if capability_name not in {item.name for item in candidate_capabilities}:
                raise PermissionError(f"Missing scope for capability: {capability_name}")
            await add_step(TraceStep(name="planned", status="completed", summary=f"命中 capability: {capability_name}。"))
            capability = self._registry.get(capability_name)
            autonomy = self._evaluate_risk(capability)
            await add_step(
                TraceStep(
                    name="risk",
                    status="completed",
                    summary=f"风险等级 {capability.risk_level}，自主度上限：{autonomy}。",
                )
            )
            self._ensure_scope(context=context, required_scope=capability.required_scope)
            self._check_quota(message)
            await add_step(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。"))

            if intent == "knowledge_query":
                result = await self._run_knowledge_search(
                    context.tenant_id, payload["query"], add_step=add_step
                )
            elif intent == "wiki_query":
                result = await self._run_wiki_search(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    query=payload["query"],
                )
            else:
                result = self._registry.invoke(capability_name, payload)
            await add_step(TraceStep(name="executed", status="completed", summary=self._execution_summary(capability_name, result)))

            answer, sources = self._compose_answer(intent, result)
            if intent == "knowledge_query":
                llm_answer = await self._generate_rag_llm_answer(
                    tenant_id=context.tenant_id,
                    message=message,
                    sources=sources,
                    short_memory=short_memory,
                    on_delta=stream_answer if on_answer_delta is not None else None,
                )
                if llm_answer:
                    answer = llm_answer
                    await add_step(TraceStep(name="model", status="completed", summary="已通过 OpenAI-compatible 模型生成最终回答。"))
                elif not sources:
                    await add_step(TraceStep(name="model", status="completed", summary="未命中检索来源，跳过模型生成。"))
                    warnings.append("未在已发布知识库中检索到相关内容，请尝试更换关键词或上传相关文档。")
                else:
                    await add_step(TraceStep(name="model", status="failed", summary="LLM Runtime 未启用，保留检索拼装回答。"))
                    warnings.append("LLM 运行时未启用，当前回答为检索片段拼接。请在「设置 → LLM 配置」中启用模型以获得分析型答案。")
            elif intent == "wiki_query":
                llm_answer = await self._generate_wiki_llm_answer(
                    tenant_id=context.tenant_id,
                    message=message,
                    sources=sources,
                    short_memory=short_memory,
                    on_delta=stream_answer if on_answer_delta is not None else None,
                )
                if llm_answer:
                    answer = llm_answer
                    await add_step(TraceStep(name="model", status="completed", summary="已通过 OpenAI-compatible 模型基于 Wiki 页面与引用生成最终回答。"))
                elif not sources:
                    await add_step(TraceStep(name="model", status="completed", summary="未命中 Wiki 来源，跳过模型生成。"))
                    warnings.append("未在 Wiki 中检索到相关页面，请尝试更换关键词或检查权限范围。")
                else:
                    await add_step(TraceStep(name="model", status="failed", summary="LLM Runtime 未启用，保留 Wiki 检索拼装回答。"))
                    warnings.append("LLM 运行时未启用，当前回答为 Wiki 片段拼接。请在「设置 → LLM 配置」中启用模型以获得分析型答案。")
        if intent not in {"knowledge_query", "wiki_query", "general_chat"}:
            await add_step(TraceStep(name="model", status="completed", summary="当前能力无需模型生成。"))
        answer = self._review_output(answer)
        if on_answer_delta is not None and not answer_streamed:
            await self._emit_text_deltas(answer, stream_answer)
        await add_step(TraceStep(name="output_guard", status="completed", summary="输出脱敏与内容审查完成。"))
        trace.answer = answer
        trace.sources = sources
        await add_step(TraceStep(name="completed", status="completed", summary="响应已组装并返回。"))
        await self._traces.save(trace)

        conversation = await self._conversations.append_message(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=conversation_id,
            user_message=message,
            assistant_message=answer,
        )

        response = {
            "trace_id": trace.trace_id,
            "conversation_id": conversation.conversation_id,
            "intent": intent,
            "strategy": strategy,
            "message": {
                "role": "assistant",
                "content": answer,
            },
            "sources": [
                self._serialize_source(source)
                for source in sources
            ],
            "warnings": warnings,
        }
        if capability and capability.side_effect_level in {"write", "irreversible"}:
            draft = await self.create_draft(
                capability_name=capability.name,
                payload=payload,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
            )
            response["draft_action"] = self._serialize_draft(draft)
        return response

    async def list_conversations(self, tenant_id: str | None = None, user_id: str | None = None) -> list[dict[str, object]]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        return [
            {
                "conversation_id": item.conversation_id,
                "title": item.title,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in await self._conversations.list_recent(context.tenant_id, context.user_id)
        ]

    async def get_conversation(
        self,
        conversation_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> Conversation | None:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        return await self._conversations.get(context.tenant_id, context.user_id, conversation_id)

    async def get_trace(
        self,
        trace_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> TraceRecord | None:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        trace = await self._traces.get(trace_id)
        if trace is None or trace.tenant_id != context.tenant_id or trace.user_id != context.user_id:
            return None
        return trace

    async def list_traces(self, tenant_id: str | None = None, user_id: str | None = None) -> list[dict[str, object]]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        return [
            {
                "trace_id": item.trace_id,
                "user_id": item.user_id,
                "intent": item.intent,
                "strategy": item.strategy,
                "message": item.message,
                "answer": item.answer,
                "created_at": item.created_at.isoformat(),
            }
            for item in await self._traces.list_recent(context.tenant_id)
        ]

    async def create_draft(
        self,
        capability_name: str,
        payload: dict[str, object],
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> DraftAction:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        capability = self._registry.get(capability_name)
        self._ensure_scope(context=context, required_scope=capability.required_scope)
        result = self._registry.invoke(capability_name, payload)
        draft = DraftAction(
            draft_id=str(uuid4()),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            capability_name=capability_name,
            title=capability.description,
            risk_level=capability.risk_level,
            status="awaiting_confirmation",
            payload=payload,
            summary=str(result["summary"]),
            approval_hint=str(result["approval_hint"]),
        )
        return await self._drafts.save(draft)

    async def confirm_draft(
        self,
        draft_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="draft:confirm")
        draft = await self._drafts.confirm(
            draft_id=draft_id,
            tenant_id=context.tenant_id,
            confirmed_at=utc_now(),
        )
        if draft is None:
            raise ValueError("Draft not found")
        return self._serialize_draft(draft)

    async def list_admin_packages(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        capabilities = [item for item in self._registry.list_capabilities() if item.enabled]
        return {
            "packages": [
                {
                    "name": "通用知识包",
                    "version": "v1.0.3",
                    "owner": "知识平台组",
                    "status": "运行中",
                },
                {
                    "name": "HR 业务包",
                    "version": "v1.2.0",
                    "owner": "人力共享中心",
                    "status": "运行中",
                },
                {
                    "name": "财务业务包",
                    "version": "v0.9.8",
                    "owner": "财务运营组",
                    "status": "灰度中",
                },
            ],
            "capabilities": [
                {
                    "name": item.name,
                    "risk_level": item.risk_level,
                    "side_effect_level": item.side_effect_level,
                    "required_scope": item.required_scope,
                }
                for item in capabilities
            ],
        }

    async def list_system_overview(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        self._ensure_tenant_management_scope(context)
        return {
            "tenants": [asdict(item) for item in await self._tenants.list_all()],
            "roles": [
                {"name": "platform_admin", "scope_count": 7, "member_count": 12},
                {"name": "auditor", "scope_count": 3, "member_count": 16},
                {"name": "business_admin", "scope_count": 4, "member_count": 48},
            ],
            "llm_runtime": await self.get_llm_runtime(tenant_id=context.tenant_id),
        }

    async def list_security_overview(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        return {
            "events": [asdict(item) for item in await self._security_events.list_recent(context.tenant_id)],
            "drafts": [self._serialize_draft(item) for item in await self._drafts.list_recent(context.tenant_id)],
        }

    async def list_knowledge_sources(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        knowledge_base_code: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        return {
            "sources": [
                asdict(item)
                for item in await self._knowledge_sources.list_recent(
                    context.tenant_id,
                    knowledge_base_code=knowledge_base_code,
                )
            ]
        }

    async def get_knowledge_source_detail(
        self,
        source_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        detail = await self._knowledge_sources.get_detail(context.tenant_id, source_id)
        if detail is None:
            raise ValueError("Knowledge source not found")
        return {
            "source": asdict(detail.source),
            "chunks": [asdict(item) for item in detail.chunks],
            "content": detail.content,
        }

    async def list_knowledge_bases(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        return {"items": [asdict(item) for item in await self._knowledge_bases.list_by_tenant(context.tenant_id)]}

    async def reembed_knowledge(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        batch_size: int = 32,
        limit: int | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        reembed = getattr(self._knowledge_sources, "reembed_pending", None)
        if reembed is None:
            return {"total": 0, "updated": 0, "failed": 0, "skipped": True}
        stats = await reembed(
            tenant_id=context.tenant_id,
            batch_size=batch_size,
            limit=limit,
        )
        return dict(stats)

    async def ingest_knowledge_source(
        self,
        *,
        name: str,
        content: str,
        source_type: str,
        owner: str,
        knowledge_base_code: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        source = await self._knowledge_sources.ingest_text(
            tenant_id=context.tenant_id,
            name=name,
            content=content,
            source_type=source_type,
            owner=owner,
            knowledge_base_code=knowledge_base_code,
        )
        return {"source": asdict(source)}

    async def create_knowledge_base(
        self,
        *,
        knowledge_base_code: str,
        name: str,
        description: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        existing_items = await self._knowledge_bases.list_by_tenant(context.tenant_id)
        normalized_code = knowledge_base_code.strip()
        normalized_name = name.strip()
        if any(item.knowledge_base_code == normalized_code for item in existing_items):
            raise ValueError("知识库编码已存在，请更换后重试")
        if any(item.name == normalized_name for item in existing_items):
            raise ValueError("知识库名称已存在，请更换后重试")
        entity = KnowledgeBase(
            knowledge_base_id=f"kb-{uuid4().hex[:12]}",
            knowledge_base_code=normalized_code,
            tenant_id=context.tenant_id,
            name=normalized_name,
            description=description,
            status="active",
            created_by=context.user_id,
            updated_by=context.user_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return asdict(await self._knowledge_bases.create(entity))

    async def update_knowledge_base(
        self,
        *,
        knowledge_base_code: str,
        name: str,
        description: str,
        status: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        existing = next(
            (
                item
                for item in await self._knowledge_bases.list_by_tenant(context.tenant_id)
                if item.knowledge_base_code == knowledge_base_code
            ),
            None,
        )
        if existing is None:
            raise ValueError("Knowledge base not found")
        existing.name = name
        existing.description = description
        existing.status = status
        existing.updated_by = context.user_id
        existing.updated_at = utc_now()
        return asdict(await self._knowledge_bases.update(existing))

    async def delete_knowledge_base(
        self,
        *,
        knowledge_base_code: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        deleted = await self._knowledge_bases.delete(context.tenant_id, knowledge_base_code)
        if not deleted:
            raise ValueError("Knowledge base not found")
        return {"deleted": True}

    async def get_llm_runtime(self, tenant_id: str | None = None) -> dict[str, object]:
        config, _api_key = await self._llm_config.get(tenant_id=tenant_id)
        return self._serialize_llm_runtime(config)

    @staticmethod
    def _serialize_llm_runtime(config: LLMRuntimeConfig) -> dict[str, object]:
        return {
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "api_key_configured": config.api_key_configured,
            "temperature": config.temperature,
            "system_prompt": config.system_prompt,
            "enabled": config.enabled,
            "embedding_provider": config.embedding_provider,
            "embedding_base_url": config.embedding_base_url,
            "embedding_model": config.embedding_model,
            "embedding_dimensions": config.embedding_dimensions,
            "embedding_api_key_configured": config.embedding_api_key_configured,
            "embedding_enabled": config.embedding_enabled,
        }

    async def get_tenant(self, tenant_id: str) -> TenantProfile | None:
        return await self._tenants.get(tenant_id)

    async def update_llm_runtime(
        self,
        tenant_id: str | None,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float,
        system_prompt: str,
        embedding_provider: str | None = None,
        embedding_base_url: str | None = None,
        embedding_model: str | None = None,
        embedding_api_key: str | None = None,
        embedding_dimensions: int | None = None,
        embedding_enabled: bool | None = None,
    ) -> dict[str, object]:
        config, _ = await self._llm_config.create_or_update_for_tenant(
            tenant_id=tenant_id,
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
            temperature=temperature,
            system_prompt=system_prompt,
            embedding_provider=embedding_provider,
            embedding_base_url=embedding_base_url,
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_dimensions=embedding_dimensions,
            embedding_enabled=embedding_enabled,
        )
        return self._serialize_llm_runtime(config)

    # Tenant CRUD
    async def list_tenants(self, tenant_id: str | None = None, user_id: str | None = None) -> list[TenantProfile]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        return await self._tenants.list_all()

    async def create_tenant(
        self,
        name: str,
        package: str,
        environment: str,
        budget: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> TenantProfile:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        normalized_name = name.strip()
        normalized_package = package.strip()
        normalized_environment = environment.strip()
        normalized_budget = budget.strip()
        if not normalized_name or not normalized_package:
            raise ValueError("租户名称和业务包不能为空")

        existing_tenants = await self._tenants.list_all()
        if any(item.name == normalized_name for item in existing_tenants):
            raise ValueError("租户名称已存在，请更换后重试")

        tenant = TenantProfile(
            tenant_id=f"tenant-{uuid4().hex[:12]}",
            name=normalized_name,
            package=normalized_package,
            environment=normalized_environment,
            budget=normalized_budget,
            active=True,
        )
        return await self._tenants.create(tenant)

    async def update_tenant(
        self,
        tenant_id: str,
        name: str,
        package: str,
        environment: str,
        budget: str,
        active: bool,
        auth_tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> TenantProfile:
        context = await self._require_context(tenant_id=auth_tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        normalized_name = name.strip()
        normalized_package = package.strip()
        normalized_environment = environment.strip()
        normalized_budget = budget.strip()
        if not normalized_name or not normalized_package:
            raise ValueError("租户名称和业务包不能为空")

        existing_tenants = await self._tenants.list_all()
        if any(item.tenant_id != tenant_id and item.name == normalized_name for item in existing_tenants):
            raise ValueError("租户名称已存在，请更换后重试")

        tenant = TenantProfile(
            tenant_id=tenant_id,
            name=normalized_name,
            package=normalized_package,
            environment=normalized_environment,
            budget=normalized_budget,
            active=active,
        )
        return await self._tenants.update(tenant)

    async def delete_tenant(
        self,
        tenant_id: str,
        auth_tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        context = await self._require_context(tenant_id=auth_tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        return await self._tenants.delete(tenant_id)

    # User CRUD
    async def get_user(self, tenant_id: str, user_id: str) -> UserContext | None:
        return await self._users.get(tenant_id=tenant_id, user_id=user_id)

    async def list_tenant_users(self, tenant_id: str) -> list[UserContext]:
        return await self._users.list_by_tenant(tenant_id)

    async def create_user(
        self,
        tenant_id: str,
        email: str,
        password: str,
        role: str,
        scopes: list[str],
    ) -> UserContext:
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise ValueError("用户邮箱不能为空")
        if await self._tenants.get(tenant_id) is None:
            raise ValueError("租户不存在")
        if await self._users.get_by_email(normalized_email) is not None:
            raise ValueError("用户邮箱已存在，请更换后重试")

        user = UserContext(
            user_id=f"user-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            role=role,
            scopes=scopes,
            email=normalized_email,
        )
        return await self._users.create(user, get_password_hash(password))

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> tuple[UserContext, str] | None:
        result = await self._users.get_by_email(email)
        if result is None:
            return None
        user_context, password_hash = result
        if not verify_password(password, password_hash):
            return None
        return (user_context, password_hash)

    async def register_user(
        self,
        email: str,
        password: str,
        tenant_id: str,
        role: str,
    ) -> tuple[UserContext, str] | None:
        # Check if email already exists
        existing = await self._users.get_by_email(email)
        if existing is not None:
            return None

        # Verify tenant exists
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            return None

        # Generate user_id from email
        import hashlib
        user_id = hashlib.sha256(email.encode()).hexdigest()[:16]
        password_hash = get_password_hash(password)

        default_scopes = ["chat:read", "knowledge:read"]
        user = UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            scopes=default_scopes,
            email=email,
        )
        created_user = await self._users.create(user, password_hash)
        return (created_user, password_hash)

    async def update_user(
        self,
        tenant_id: str,
        user_id: str,
        role: str,
        scopes: list[str],
    ) -> UserContext:
        user = UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            scopes=scopes,
        )
        return await self._users.update(user)

    async def delete_user(self, tenant_id: str, user_id: str) -> bool:
        return await self._users.delete(tenant_id, user_id)

    @staticmethod
    def _classify_intent(message: str, retrieval_mode: Literal["auto", "rag", "wiki"] = "auto") -> str:
        if "采购" in message or "审批草稿" in message or "草稿" in message:
            return "procurement_draft"
        if "年假" in message or "假期" in message:
            return "hr_query"
        if retrieval_mode == "wiki":
            return "wiki_query"
        if retrieval_mode == "rag":
            return "knowledge_query"
        wiki_keywords = (
            "wiki",
            "Wiki",
            "维基",
            "知识页",
            "编译页",
            "引用证据",
            "citation",
        )
        if any(keyword in message for keyword in wiki_keywords):
            return "wiki_query"
        knowledge_keywords = (
            "知识库",
            "文档",
            "资料",
            "引用",
            "依据",
            "制度",
            "流程",
            "平台",
            "架构",
            "技术文档",
            "PRD",
            "P0",
            "P0a",
            "第六节",
            "标准查询链路",
            "检索增强",
            "RAG",
        )
        if any(keyword in message for keyword in knowledge_keywords):
            return "knowledge_query"
        return "general_chat"

    @staticmethod
    def _extract_employee_name(message: str) -> str:
        for name in ("张三", "李四", "王五"):
            if name in message:
                return name
        return "张三"

    def _plan(self, message: str, intent: str) -> tuple[str, dict[str, str]]:
        if intent == "procurement_draft":
            return (
                "workflow.procurement.request.create",
                {
                    "request_title": "办公设备采购申请",
                    "amount": "¥ 18,600",
                    "owner": "运营采购组",
                },
            )
        if intent == "hr_query":
            return "hr.leave.balance.query", {"employee_name": self._extract_employee_name(message)}
        if intent == "wiki_query":
            return "wiki.search", {"query": message}
        return "knowledge.search", {"query": message}

    async def _run_knowledge_search(
        self,
        tenant_id: str,
        query: str,
        *,
        add_step: Callable[[TraceStep], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        if not hasattr(self._knowledge_sources, "search"):
            return self._registry.invoke("knowledge.search", {"query": query})

        try:
            config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        except Exception:
            config, api_key = None, ""

        use_llm = (
            config is not None
            and getattr(config, "enabled", False)
            and bool(api_key)
            and len(query.strip()) >= 4
        )

        variants: list[str] = [query]
        if use_llm:
            try:
                rewritten = await self._rewrite_query(config=config, api_key=api_key, query=query)
            except Exception:
                rewritten = []
            seen = {query.strip().lower()}
            for variant in rewritten:
                normalized = variant.strip()
                if not normalized or normalized.lower() in seen:
                    continue
                variants.append(normalized)
                seen.add(normalized.lower())
            if add_step is not None:
                await add_step(
                    TraceStep(
                        name="query_rewrite",
                        status="completed" if len(variants) > 1 else "skipped",
                        summary=(
                            f"Query 改写产生 {len(variants)} 个检索变体: " + " | ".join(variants[:5])
                            if len(variants) > 1
                            else "Query 改写未返回有效变体，沿用原始问题。"
                        ),
                    )
                )

        recall_top_k = 20 if use_llm else 8
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, SourceReference] = {}
        aggregate_keyword = 0
        aggregate_vector = 0
        aggregate_candidates = 0
        backend = "postgres_json_hybrid"
        for variant in variants:
            result = await self._knowledge_sources.search(
                tenant_id=tenant_id, query=variant, top_k=recall_top_k
            )
            backend = result.backend or backend
            aggregate_keyword += result.keyword_match_count
            aggregate_vector += result.vector_match_count
            aggregate_candidates = max(aggregate_candidates, result.candidate_count)
            for rank, match in enumerate(result.matches, start=1):
                chunk_map.setdefault(match.id, match)
                rrf_scores[match.id] = rrf_scores.get(match.id, 0.0) + 1.0 / (60 + rank)

        ordered_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
        merged: list[SourceReference] = [chunk_map[cid] for cid in ordered_ids]

        final_top_k = 8
        rerank_applied = False
        if use_llm and len(merged) > final_top_k:
            try:
                reranked = await self._rerank_candidates(
                    config=config, api_key=api_key, query=query, candidates=merged
                )
            except Exception:
                reranked = None
            if reranked:
                merged = reranked
                rerank_applied = True

        matches = merged[:final_top_k]

        if add_step is not None and use_llm:
            await add_step(
                TraceStep(
                    name="rerank",
                    status="completed" if rerank_applied else "skipped",
                    summary=(
                        f"LLM rerank 重排 {len(merged)} 候选，保留前 {len(matches)}。"
                        if rerank_applied
                        else f"未触发 rerank（候选 {len(merged)} ≤ {final_top_k} 或调用失败）。"
                    ),
                )
            )

        summary = (
            "已从已发布知识切片中整理出与你问题最相关的要点。"
            if matches
            else "未在当前已发布知识源中检索到相关内容。"
        )
        return {
            "summary": summary,
            "matches": matches,
            "retrieval": {
                "backend": backend,
                "query": query,
                "matched": bool(matches),
                "candidate_count": aggregate_candidates,
                "match_count": len(matches),
                "keyword_match_count": aggregate_keyword,
                "vector_match_count": aggregate_vector,
                "variants": variants,
                "rerank_applied": rerank_applied,
            },
        }

    async def _rewrite_query(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        query: str,
    ) -> list[str]:
        """让 LLM 把原始问题改写为 2-3 个检索友好的变体。失败返回 []."""
        prompt = (
            "你是企业搜索助手。请将下列用户问题改写为 2-3 个语义等价但表述不同的检索语句，"
            "用于关键词与向量混合检索互补。\n"
            "要求：\n"
            "1. 仅输出 JSON 数组，例如 [\"变体1\", \"变体2\", \"变体3\"]，不要任何额外说明。\n"
            "2. 保留关键名词与技术术语；去除\"如何 / 怎样 / 分析一下 / 帮我\"等口语化前缀。\n"
            "3. 不要复述用户原句。\n\n"
            f"用户问题：{query}"
        )
        try:
            raw = await asyncio.to_thread(
                self._llm_client.complete,
                config=config,
                api_key=api_key,
                user_message=prompt,
                context_blocks=[],
            )
        except Exception:
            return []
        return self._parse_query_variants(raw)

    @staticmethod
    def _parse_query_variants(raw: str) -> list[str]:
        if not raw:
            return []
        snippet = raw.strip()
        # 兜底：截取 [...] 之间的 JSON 数组
        match = re.search(r"\[[^\[\]]*\]", snippet, flags=re.DOTALL)
        if match:
            snippet = match.group(0)
        try:
            import json as _json

            data = _json.loads(snippet)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        variants: list[str] = []
        for item in data:
            if isinstance(item, str) and item.strip():
                variants.append(item.strip())
        return variants[:5]

    async def _rerank_candidates(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        query: str,
        candidates: list[SourceReference],
    ) -> list[SourceReference] | None:
        """让 LLM 对候选片段按相关度 1-5 打分并重排。失败返回 None."""
        if not candidates:
            return None
        truncated = candidates[:20]
        block_lines: list[str] = []
        for index, item in enumerate(truncated, start=1):
            title = (item.title or "未命名").strip()
            snippet = (item.snippet or "").strip().replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:280] + "..."
            block_lines.append(f"[{index}] 标题: {title} | 片段: {snippet}")
        prompt = (
            "对下列候选片段按与\"用户问题\"的相关度打 1-5 分（5 最相关，1 最无关）。\n"
            "要求：\n"
            "- 仅输出 JSON 数组，元素形如 {\"index\": 1, \"score\": 5}，覆盖全部候选编号。\n"
            "- 不要解释、不要任何额外文本。\n\n"
            f"用户问题：{query}\n\n候选：\n" + "\n".join(block_lines)
        )
        try:
            raw = await asyncio.to_thread(
                self._llm_client.complete,
                config=config,
                api_key=api_key,
                user_message=prompt,
                context_blocks=[],
            )
        except Exception:
            return None
        scores = self._parse_rerank_scores(raw, expected=len(truncated))
        if not scores:
            return None
        # 按得分降序，保留 score>=2 的；同分保持原顺序
        scored = [
            (idx, scores.get(idx, 0))
            for idx in range(1, len(truncated) + 1)
        ]
        scored.sort(key=lambda x: (-x[1], x[0]))
        reordered = [truncated[idx - 1] for idx, score in scored if score >= 2]
        # 把没参与排序的尾部候选附在后面，避免丢候选
        tail = candidates[len(truncated):]
        if not reordered:
            return None
        return reordered + tail

    @staticmethod
    def _parse_rerank_scores(raw: str, *, expected: int) -> dict[int, int]:
        if not raw:
            return {}
        snippet = raw.strip()
        match = re.search(r"\[.*\]", snippet, flags=re.DOTALL)
        if match:
            snippet = match.group(0)
        try:
            import json as _json

            data = _json.loads(snippet)
        except Exception:
            return {}
        if not isinstance(data, list):
            return {}
        scores: dict[int, int] = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("index"))
                score = int(entry.get("score"))
            except (TypeError, ValueError):
                continue
            if 1 <= idx <= expected:
                scores[idx] = max(1, min(5, score))
        return scores

    async def _run_wiki_search(
        self,
        *,
        tenant_id: str,
        user_id: str,
        query: str,
    ) -> dict[str, object]:
        return await self._wiki_service.search(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            top_k=3,
            scope_mode="chat",
        )

    @staticmethod
    def _compose_answer(intent: str, result: dict[str, object]) -> tuple[str, list[SourceReference]]:
        if intent == "procurement_draft":
            answer = f"{result['summary']}\n{result['approval_hint']}"
            return answer, []
        if intent == "hr_query":
            sources = result["sources"]
            answer = f"{result['summary']} 数据来源为 HR 示例插件。"
            return answer, list(sources)
        if intent == "wiki_query":
            hits = list(result["hits"])
            if not hits:
                return str(result["summary"]), []
            sources = [
                SourceReference(
                    id=item["citation_id"] or item["page_id"],
                    title=item["title"],
                    snippet=item["snippet"],
                    source_type="wiki",
                    page_id=item["page_id"],
                    revision_id=item["revision_id"],
                    citation_id=item["citation_id"],
                    claim_text=item["claim_text"],
                    source_id=item["source_id"],
                    chunk_id=item["chunk_id"],
                    locator=item["locator"],
                )
                for item in hits
            ]
            bullets = "\n".join(
                f"- {item['title']}: {item['claim_text'] or item['snippet']}"
                for item in hits
            )
            answer = f"{result['summary']}\n{bullets}"
            return answer, sources

        matches = list(result["matches"])
        if not matches:
            return str(result["summary"]), []
        bullets = "\n".join(f"- {item.title}: {item.snippet}" for item in matches)
        answer = f"{result['summary']}\n{bullets}"
        return answer, matches

    @staticmethod
    def _inspect_input(message: str) -> list[str]:
        findings = []
        if re.search(r"\b\d{17}[\dXx]\b", message):
            findings.append("身份证号")
        if re.search(r"\b1[3-9]\d{9}\b", message):
            findings.append("手机号")
        return findings

    async def _load_short_memory(self, tenant_id: str, user_id: str, conversation_id: str | None) -> Conversation:
        if conversation_id is None:
            return Conversation(conversation_id="", title="新会话", tenant_id=tenant_id, user_id=user_id)
        conversation = await self._conversations.get(tenant_id, user_id, conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found")
        return conversation

    async def _load_long_memory_summary(self, tenant_id: str) -> str:
        sources = await self._knowledge_sources.list_recent(tenant_id)
        active_sources = [item for item in sources if item.status == "运行中"]
        if not active_sources:
            return "当前租户暂无运行中的知识源"
        names = "、".join(item.name for item in active_sources[:3])
        return f"{len(active_sources)} 个运行中知识源（{names}）"

    @staticmethod
    def _conversation_context_blocks(short_memory: Conversation, limit: int = 12) -> list[str]:
        if not short_memory.messages:
            return []
        recent_messages = short_memory.messages[-limit:]
        lines = []
        for item in recent_messages:
            role = "用户" if item.role == "user" else "助手"
            lines.append(f"{role}: {item.content}")
        return ["会话历史（按时间从旧到新）:\n" + "\n".join(lines)]

    def _select_candidate_capabilities(self, context: UserContext) -> list[CapabilityDefinition]:
        _ = context
        return [capability for capability in self._registry.list_capabilities() if capability.enabled]

    @staticmethod
    def _evaluate_risk(capability: CapabilityDefinition) -> str:
        if capability.side_effect_level in {"write", "irreversible"} or capability.risk_level == "high":
            return "draft_required"
        return "auto_execute"

    @staticmethod
    def _check_quota(message: str) -> None:
        if len(message) > 2000:
            raise ValueError("Message exceeds quota")

    @staticmethod
    def _execution_summary(capability_name: str, result: dict[str, object]) -> str:
        retrieval = result.get("retrieval")
        if isinstance(retrieval, dict):
            backend = retrieval.get("backend", "unknown")
            match_count = retrieval.get("match_count", 0)
            candidate_count = retrieval.get("candidate_count", 0)
            return f"{capability_name} 执行完成，检索后端 {backend}，命中 {match_count}/{candidate_count}。"
        return f"{capability_name} 执行完成。"

    @staticmethod
    def _review_output(answer: str) -> str:
        return re.sub(r"\b1[3-9]\d{3}(\d{4})\d{4}\b", r"1****\1****", answer)

    @staticmethod
    def _chunk_answer(answer: str, chunk_size: int = 6) -> list[str]:
        if not answer:
            return []
        chunks: list[str] = []
        buffer = ""
        for char in answer:
            buffer += char
            if char in {"。", "！", "？", "\n"} or len(buffer) >= chunk_size:
                chunks.append(buffer)
                buffer = ""
        if buffer:
            chunks.append(buffer)
        return chunks

    async def _emit_text_deltas(self, answer: str, on_delta: AnswerDeltaCallback) -> None:
        for chunk in self._chunk_answer(answer):
            await on_delta(chunk)
            await asyncio.sleep(0.018)

    async def _generate_direct_llm_answer(
        self,
        *,
        tenant_id: str,
        message: str,
        short_memory: Conversation,
        on_delta: AnswerDeltaCallback | None = None,
    ) -> tuple[str, bool]:
        config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        if not config.enabled:
            return (
                "LLM Runtime 未启用，当前无法生成日常对话回答。请先在系统设置中配置 OpenAI-compatible base_url、model 和 api_key。",
                False,
            )
        if on_delta is not None:
            try:
                answer = await self._stream_llm_answer(
                    config=config,
                    api_key=api_key,
                    user_message=message,
                    context_blocks=self._conversation_context_blocks(short_memory),
                    on_delta=on_delta,
                )
                return answer, True
            except (AttributeError, NotImplementedError):
                pass
        answer = self._llm_client.complete(
            config=config,
            api_key=api_key,
            user_message=message,
            context_blocks=self._conversation_context_blocks(short_memory),
        )
        return answer, True

    async def _generate_rag_llm_answer(
        self,
        *,
        tenant_id: str,
        message: str,
        sources: list[SourceReference],
        short_memory: Conversation,
        on_delta: AnswerDeltaCallback | None = None,
    ) -> str | None:
        config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        if not config.enabled:
            return None
        context_blocks = self._conversation_context_blocks(short_memory)
        if not sources:
            # 空召回兜底：给 LLM 一段说明，让它给开放回答 + 引导上传文档
            context_blocks.append(
                "[空召回提示]\n"
                "未在已发布知识库中检索到与该问题直接相关的资料。\n"
                "请按以下要求回答：\n"
                "1. 先用一句话坦诚说明\"目前知识库未收录直接相关资料\"。\n"
                "2. 基于通用专业经验给出 3-5 条可参考的方向或建议。\n"
                "3. 结尾用一句话引导用户：\"如需更精准的答案，请在「设置 → 知识库」中上传相关文档。\""
            )
            if on_delta is not None:
                try:
                    return await self._stream_llm_answer(
                        config=config,
                        api_key=api_key,
                        user_message=message,
                        context_blocks=context_blocks,
                        on_delta=on_delta,
                    )
                except (AttributeError, NotImplementedError):
                    pass
            try:
                return self._llm_client.complete(
                    config=config,
                    api_key=api_key,
                    user_message=message,
                    context_blocks=context_blocks,
                )
            except Exception:
                return None
        for index, item in enumerate(sources, start=1):
            parts = [
                f"[{index}] 文档《{item.title}》",
                f"来源ID: {item.source_id or item.id}",
            ]
            if item.locator:
                parts.append(f"章节: {item.locator}")
            # 优先使用完整 chunk 正文；snippet 仅做兜底（旧数据 / Wiki 路径）。
            body = (item.content or item.snippet or "").strip()
            parts.append("正文:\n" + body)
            context_blocks.append("\n".join(parts))
        if on_delta is not None:
            try:
                return await self._stream_llm_answer(
                    config=config,
                    api_key=api_key,
                    user_message=message,
                    context_blocks=context_blocks,
                    on_delta=on_delta,
                )
            except (AttributeError, NotImplementedError):
                pass
        return self._llm_client.complete(
            config=config,
            api_key=api_key,
            user_message=message,
            context_blocks=context_blocks,
        )

    async def _generate_wiki_llm_answer(
        self,
        *,
        tenant_id: str,
        message: str,
        sources: list[SourceReference],
        short_memory: Conversation,
        on_delta: AnswerDeltaCallback | None = None,
    ) -> str | None:
        config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        if not config.enabled or not sources:
            return None
        context_blocks = self._conversation_context_blocks(short_memory)
        context_blocks.extend([
            "\n".join(
                part
                for part in (
                    f"Wiki页面: {item.title}",
                    f"定位: {item.locator}" if item.locator else "",
                    f"主张: {item.claim_text}" if item.claim_text else "",
                    f"证据: {item.snippet}",
                )
                if part
            )
            for item in sources
        ])
        if on_delta is not None:
            try:
                return await self._stream_llm_answer(
                    config=config,
                    api_key=api_key,
                    user_message=message,
                    context_blocks=context_blocks,
                    on_delta=on_delta,
                )
            except (AttributeError, NotImplementedError):
                pass
        return self._llm_client.complete(
            config=config,
            api_key=api_key,
            user_message=message,
            context_blocks=context_blocks,
        )

    async def _stream_llm_answer(
        self,
        *,
        config: LLMRuntimeConfig,
        api_key: str,
        user_message: str,
        context_blocks: list[str],
        on_delta: AnswerDeltaCallback,
    ) -> str:
        stream = self._llm_client.stream_complete(
            config=config,
            api_key=api_key,
            user_message=user_message,
            context_blocks=context_blocks,
        )
        answer_parts: list[str] = []
        while True:
            chunk = await asyncio.to_thread(self._next_chunk, stream)
            if chunk is None:
                break
            answer_parts.append(chunk)
            await on_delta(chunk)
        answer = "".join(answer_parts)
        if not answer:
            raise ValueError("LLM response content is empty")
        return answer

    @staticmethod
    def _next_chunk(stream) -> str | None:
        try:
            return next(stream)
        except StopIteration:
            return None

    @staticmethod
    def _serialize_draft(draft: DraftAction) -> dict[str, object]:
        return {
            "draft_id": draft.draft_id,
            "title": draft.title,
            "capability_name": draft.capability_name,
            "risk_level": draft.risk_level,
            "status": draft.status,
            "summary": draft.summary,
            "approval_hint": draft.approval_hint,
            "payload": draft.payload,
            "created_at": draft.created_at.isoformat(),
        }

    @staticmethod
    def _serialize_source(source: SourceReference) -> dict[str, object]:
        return {
            "id": source.id,
            "title": source.title,
            "snippet": source.snippet,
            "source_type": source.source_type,
            "page_id": source.page_id,
            "revision_id": source.revision_id,
            "citation_id": source.citation_id,
            "claim_text": source.claim_text,
            "source_id": source.source_id,
            "chunk_id": source.chunk_id,
            "locator": source.locator,
        }

    async def _require_context(self, tenant_id: str | None, user_id: str | None) -> UserContext:
        resolved_tenant_id = tenant_id or settings.default_tenant_id
        resolved_user_id = user_id or settings.default_user_id
        context = await self._users.get(resolved_tenant_id, resolved_user_id)
        if context is None:
            raise ValueError("User context not found")
        return context

    @staticmethod
    def _ensure_scope(context: UserContext, required_scope: str) -> None:
        # 临时关闭现有 scope 校验，后续统一替换为新的权限模型。
        _ = (context, required_scope)
        return None

    @staticmethod
    def _ensure_tenant_management_scope(context: UserContext) -> None:
        if TENANT_MANAGE_SCOPE not in context.scopes:
            raise PermissionError(f"Missing scope: {TENANT_MANAGE_SCOPE}")
