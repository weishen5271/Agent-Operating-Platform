from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
from typing import AsyncIterator, Awaitable, Callable, Literal
from uuid import uuid4

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import (
    BusinessOutput,
    CapabilityDefinition,
    Conversation,
    DraftAction,
    KnowledgeBase,
    LLMRuntimeConfig,
    McpServer,
    OutputGuardRule,
    PluginConfig,
    ReleasePlan,
    SecurityEvent,
    SkillDefinition,
    SourceReference,
    TenantProfile,
    ToolOverride,
    TraceRecord,
    TraceStep,
    UserContext,
    utc_now,
)
from agent_platform.infrastructure.auth import get_password_hash, verify_password
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.infrastructure.repositories import (
    BusinessOutputRepository,
    ConversationRepository,
    DraftRepository,
    KnowledgeRepository,
    KnowledgeBaseRepository,
    LLMConfigRepository,
    McpServerRepository,
    OutputGuardRuleRepository,
    PluginConfigRepository,
    ReleasePlanRepository,
    SecurityRepository,
    TenantRepository,
    ToolOverrideRepository,
    TraceRepository,
    UserRepository,
)
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.package_loader import PackageLoader
from agent_platform.runtime.package_router import PackageRouter
from agent_platform.runtime.skill_executor import SkillExecutor
from agent_platform.runtime.skill_registry import SkillRegistry, ToolRegistry
from agent_platform.wiki.service import WikiService


TENANT_MANAGE_SCOPE = "tenant:manage"
BUSINESS_OUTPUT_TYPES = {"report", "chart", "recommendation", "action_plan"}
BUSINESS_OUTPUT_STATUSES = {"draft", "reviewing", "approved", "exported", "archived"}
OUTPUT_GUARD_ACTIONS = {
    "prepend_safety_warning",
    "append_warning",
    "block_or_escalate",
    "mask_sensitive_data",
    "downgrade_answer",
}
PLATFORM_INTENTS = {
    "general_chat",
    "knowledge_query",
    "wiki_query",
    "report_compose",
    "tool.time_now",
    "tool.json_path",
    "tool.http_fetch",
}
TraceStepCallback = Callable[[TraceRecord, TraceStep], Awaitable[None]]
AnswerDeltaCallback = Callable[[str], Awaitable[None]]


class ChatService:
    def __init__(
        self,
        registry: CapabilityRegistry,
        skills: SkillRegistry,
        tools: ToolRegistry,
        conversations: ConversationRepository,
        traces: TraceRepository,
        tenants: TenantRepository,
        tool_overrides: ToolOverrideRepository,
        output_guard_rules: OutputGuardRuleRepository,
        plugin_configs: PluginConfigRepository,
        releases: ReleasePlanRepository,
        users: UserRepository,
        drafts: DraftRepository,
        security_events: SecurityRepository,
        knowledge_sources: KnowledgeRepository,
        knowledge_bases: KnowledgeBaseRepository,
        wiki_service: WikiService,
        llm_config: LLMConfigRepository,
        llm_client: OpenAICompatibleLLMClient,
        business_outputs: "BusinessOutputRepository | None" = None,
        mcp_servers: McpServerRepository | None = None,
    ) -> None:
        self._registry = registry
        self._skills = skills
        self._tools = tools
        self._conversations = conversations
        self._traces = traces
        self._tenants = tenants
        self._tool_overrides = tool_overrides
        self._output_guard_rules = output_guard_rules
        self._plugin_configs = plugin_configs
        self._mcp_servers = mcp_servers
        self._releases = releases
        self._users = users
        self._drafts = drafts
        self._security_events = security_events
        self._knowledge_sources = knowledge_sources
        self._knowledge_bases = knowledge_bases
        self._wiki_service = wiki_service
        self._llm_config = llm_config
        self._llm_client = llm_client
        self._business_outputs = business_outputs

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
        primary_package: str | None = None,
        common_packages: list[str] | None = None,
    ) -> dict[str, object]:
        return await self._complete_core(
            message=message,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            retrieval_mode=retrieval_mode,
            primary_package=primary_package,
            common_packages=common_packages,
        )

    async def stream_complete(
        self,
        message: str,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        retrieval_mode: Literal["auto", "rag", "wiki"] = "auto",
        primary_package: str | None = None,
        common_packages: list[str] | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def emit_step(trace: TraceRecord, step: TraceStep) -> None:
            # _complete_core 仍按同步主链路执行；这里把 Trace step 旁路推入队列供 SSE 消费。
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
                primary_package=primary_package,
                common_packages=common_packages,
                on_step=emit_step,
                on_answer_delta=emit_answer_delta,
            )
        )

        while not task.done() or not queue.empty():
            try:
                # 短超时轮询让服务端能持续让出事件循环，同时不阻塞后续增量事件。
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
            "routing": response.get("routing"),
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
        primary_package: str | None = None,
        common_packages: list[str] | None = None,
        on_step: TraceStepCallback | None = None,
        on_answer_delta: AnswerDeltaCallback | None = None,
    ) -> dict[str, object]:
        """对话运行主链路：上下文解析、规划、治理、执行、输出审查与持久化都在这里串联。"""

        # 请求先落到用户/租户上下文，后续权限、业务包路由和配置加载都依赖这个边界。
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        tenant = await self._tenants.get(context.tenant_id)
        if tenant is None:
            raise ValueError("Tenant context not found")
        if primary_package:
            # 前端业务包切换只影响本次请求上下文，不直接修改租户的持久绑定关系。
            tenant = TenantProfile(
                tenant_id=tenant.tenant_id,
                name=tenant.name,
                package=primary_package,
                environment=tenant.environment,
                budget=tenant.budget,
                enabled_common_packages=list(common_packages if common_packages is not None else tenant.enabled_common_packages),
                active=tenant.active,
            )
        active_packages = self._active_packages_for_tenant(tenant)
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
            # Trace 是审计和前端执行过程展示的共同来源，所有关键节点都通过这里追加。
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

        await add_step(TraceStep(name="received", status="completed", summary="请求已进入 Supervisor。", node_type="runtime"))

        # 输入检查先于规划，避免明显不合规内容继续进入工具调用或知识检索阶段。
        input_findings = self._inspect_input(message)
        await add_step(
            TraceStep(
                name="input_guard",
                status="completed",
                summary="输入安全检查完成。" if not input_findings else f"输入安全检查完成，识别到 {', '.join(input_findings)}。",
                node_type="guard",
            )
        )

        # 短期记忆用于当前会话上下文，长期摘要用于提示已有知识范围，两者都不改变用户输入。
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
                node_type="runtime",
            )
        )

        # Planner 可用时优先给出意图判断；不可用或返回异常时才进入规则分类。
        planner_decision = await self._plan_intent_with_llm(
            tenant_id=context.tenant_id,
            message=message,
            retrieval_mode=retrieval_mode,
            active_packages=active_packages,
        )
        if planner_decision is not None:
            await add_step(
                TraceStep(
                    name="react_planner",
                    status="completed",
                    summary=f"LLM Planner 决策为 {planner_decision['intent']}。",
                    node_type="runtime",
                )
            )
        else:
            await add_step(
                TraceStep(
                    name="react_planner",
                    status="skipped",
                    summary="LLM Planner 未启用或未返回有效决策，使用规则兜底。",
                    node_type="runtime",
                )
            )
        intent = (
            str(planner_decision["intent"])
            if planner_decision
            else self._classify_intent(
                message,
                retrieval_mode=retrieval_mode,
                active_packages=active_packages,
            )
        )
        strategy = "plan_execute" if intent in {"hr_query", "procurement_draft"} else "direct_answer"
        trace.intent = intent
        trace.strategy = strategy
        await add_step(TraceStep(name="classified", status="completed", summary=f"识别意图为 {intent}，策略为 {strategy}。", node_type="runtime"))

        # 候选能力先按当前用户上下文过滤，后续命中 capability 时再做精确权限与配额校验。
        candidate_capabilities = self._select_candidate_capabilities(context, active_packages=active_packages)
        await add_step(
            TraceStep(
                name="capability_candidates",
                status="completed",
                summary=f"当前可用 capability 共 {len(candidate_capabilities)} 个。",
                node_type="runtime",
            )
        )

        sources: list[SourceReference] = []
        warnings: list[str] = []
        capability = None
        if intent == "general_chat":
            # 日常对话不进入工具规划，直接走 LLM，并仍保留治理和 Trace 节点。
            self._ensure_scope(context=context, required_scope="chat:read")
            self._check_quota(message)
            await add_step(TraceStep(name="planned", status="completed", summary="命中模型直答链路: model.direct_chat。", node_type="runtime"))
            await add_step(TraceStep(name="risk", status="completed", summary="风险等级 low，自主度上限：auto_execute。", node_type="guard"))
            await add_step(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。", node_type="guard"))
            answer, used_model = await self._generate_direct_llm_answer(
                tenant_id=context.tenant_id,
                message=message,
                short_memory=short_memory,
                on_delta=None,
            )
            await add_step(TraceStep(name="executed", status="completed", summary="model.direct_chat 执行完成。", node_type="runtime"))
            await add_step(
                TraceStep(
                    name="model",
                    status="completed" if used_model else "failed",
                    summary="已通过 OpenAI-compatible 模型生成日常对话回答。" if used_model else "LLM Runtime 未启用，无法生成日常对话回答。",
                    node_type="skill",
                    ref="model.direct_chat",
                    ref_source="_platform",
                )
            )
            if not used_model:
                warnings.append("LLM 运行时未启用，已退化到内置文案。请在「设置 → LLM 配置」中启用模型。")
        else:
            tool_plan = self._plan_platform_tool(message, intent, planner_decision=planner_decision)
            if tool_plan is not None:
                # 平台内置 tool 优先于业务包 skill，适合会话列表、系统概览等固定平台能力。
                tool_name, tool_payload = tool_plan
                await add_step(TraceStep(name="planned", status="completed", summary=f"命中平台 Tool: {tool_name}。", node_type="runtime"))
                await add_step(TraceStep(name="risk", status="completed", summary="风险等级 low，自主度上限：auto_execute。", node_type="guard"))
                self._ensure_scope(context=context, required_scope="chat:read")
                self._check_quota(message)
                await add_step(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。", node_type="guard"))
                result = await self._invoke_tool_with_trace(
                    tool_name=tool_name,
                    payload=tool_payload,
                    add_step=add_step,
                )
                answer, sources = self._compose_tool_answer(tool_name, result)
            else:
                selected_skill = self._select_skill_for_intent(
                    intent=intent,
                    tenant=tenant,
                    active_packages=active_packages,
                )
                if selected_skill is not None:
                    await add_step(
                        TraceStep(
                            name="skill_selected",
                            status="completed",
                            summary=f"命中 Skill: {selected_skill.name}。",
                            node_type="skill",
                            ref=selected_skill.name,
                            ref_source=selected_skill.source,
                            ref_version=selected_skill.version,
                        )
                    )

                capability_name, payload = self._plan(message, intent)
                if selected_skill is not None and selected_skill.steps:
                    payload = await self._fill_skill_inputs_with_llm(
                        tenant_id=context.tenant_id,
                        message=message,
                        skill=selected_skill,
                        payload=payload,
                        add_step=add_step,
                    )
                    missing_inputs = self._missing_skill_inputs(selected_skill, payload)
                    if missing_inputs:
                        await add_step(
                            TraceStep(
                                name="planned",
                                status="skipped",
                                summary=(
                                    f"Skill {selected_skill.name} 缺少必填入参："
                                    f"{', '.join(missing_inputs)}，已暂停调用外部能力。"
                                ),
                                node_type="runtime",
                            )
                        )
                        answer = self._compose_missing_skill_inputs_answer(selected_skill, missing_inputs)
                        sources = []
                        warnings.append(
                            f"当前问题缺少 {', '.join(missing_inputs)}，未调用业务包 API。"
                        )
                        capability = None
                        continue_to_post_model = False
                    else:
                        continue_to_post_model = True
                else:
                    continue_to_post_model = True

                if selected_skill is not None and selected_skill.steps and continue_to_post_model:
                    # 声明式 skill.steps 由 SkillExecutor 编排，每一步都会单独写 Trace 便于追踪。
                    await add_step(TraceStep(name="planned", status="completed", summary=f"命中 Skill steps: {selected_skill.name}。", node_type="runtime"))
                    await add_step(TraceStep(name="risk", status="completed", summary="Skill steps 将逐步执行，每步按 capability/tool 自身治理约束处理。", node_type="guard"))
                    self._check_quota(message)
                    await add_step(TraceStep(name="governance", status="completed", summary="请求配额校验通过，进入 Skill steps 编排。", node_type="guard"))
                    result = await self._run_declarative_skill(
                        skill=selected_skill,
                        inputs=payload,
                        tenant_id=context.tenant_id,
                        add_step=add_step,
                    )
                    await add_step(
                        TraceStep(
                            name="executed",
                            status="completed",
                            summary=f"Skill {selected_skill.name} steps 执行完成。",
                            node_type="skill",
                            ref=selected_skill.name,
                            ref_source=selected_skill.source,
                            ref_version=selected_skill.version,
                        )
                    )
                    answer, sources = self._compose_skill_answer(selected_skill, result)
                    capability = None
                    continue_to_post_model = False

                if continue_to_post_model and capability_name not in {item.name for item in candidate_capabilities}:
                    raise PermissionError(f"Missing scope for capability: {capability_name}")
                if continue_to_post_model:
                    # 传统 capability 链路仍保留风险评估、权限校验和必要时的草稿确认。
                    await add_step(TraceStep(name="planned", status="completed", summary=f"命中 capability: {capability_name}。", node_type="runtime"))
                    capability = self._registry.get(capability_name)
                    autonomy = self._evaluate_risk(capability)
                    await add_step(
                        TraceStep(
                            name="risk",
                            status="completed",
                            summary=f"风险等级 {capability.risk_level}，自主度上限：{autonomy}。",
                            node_type="guard",
                        )
                    )
                    self._ensure_scope(context=context, required_scope=capability.required_scope)
                    self._check_quota(message)
                    await add_step(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。", node_type="guard"))

                    if selected_skill is not None and selected_skill.name == "report_compose":
                        result = await self._run_report_compose_skill(
                            tenant_id=context.tenant_id,
                            query=payload["query"],
                            add_step=add_step,
                        )
                    elif intent == "knowledge_query":
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
                        tenant_config = await self._load_capability_tenant_config(
                            tenant_id=context.tenant_id,
                            capability_name=capability_name,
                        )
                        result = self._registry.invoke(
                            capability_name,
                            payload,
                            tenant_config=tenant_config,
                        )
                    await add_step(
                        TraceStep(
                            name="executed",
                            status="completed",
                            summary=self._execution_summary(capability_name, result),
                            node_type="capability",
                            ref=capability_name,
                            ref_source="package",
                        )
                    )

                    answer, sources = self._compose_answer(intent, result)
            if intent == "knowledge_query":
                llm_answer = await self._generate_rag_llm_answer(
                    tenant_id=context.tenant_id,
                    message=message,
                    sources=sources,
                    short_memory=short_memory,
                    on_delta=None,
                )
                if llm_answer:
                    answer = llm_answer
                    await add_step(TraceStep(name="model", status="completed", summary="已通过 OpenAI-compatible 模型生成最终回答。", node_type="skill", ref="kb_grounded_qa", ref_source="_platform"))
                elif not sources:
                    await add_step(TraceStep(name="model", status="completed", summary="未命中检索来源，跳过模型生成。", node_type="runtime"))
                    warnings.append("未在已发布知识库中检索到相关内容，请尝试更换关键词或上传相关文档。")
                else:
                    await add_step(TraceStep(name="model", status="failed", summary="LLM Runtime 未启用，保留检索拼装回答。", node_type="skill", ref="kb_grounded_qa", ref_source="_platform"))
                    warnings.append("LLM 运行时未启用，当前回答为检索片段拼接。请在「设置 → LLM 配置」中启用模型以获得分析型答案。")
            elif intent == "wiki_query":
                llm_answer = await self._generate_wiki_llm_answer(
                    tenant_id=context.tenant_id,
                    message=message,
                    sources=sources,
                    short_memory=short_memory,
                    on_delta=None,
                )
                if llm_answer:
                    answer = llm_answer
                    await add_step(TraceStep(name="model", status="completed", summary="已通过 OpenAI-compatible 模型基于 Wiki 页面与引用生成最终回答。", node_type="skill", ref="wiki_grounded_qa", ref_source="_platform"))
                elif not sources:
                    await add_step(TraceStep(name="model", status="completed", summary="未命中 Wiki 来源，跳过模型生成。", node_type="runtime"))
                    warnings.append("未在 Wiki 中检索到相关页面，请尝试更换关键词或检查权限范围。")
                else:
                    await add_step(TraceStep(name="model", status="failed", summary="LLM Runtime 未启用，保留 Wiki 检索拼装回答。", node_type="skill", ref="wiki_grounded_qa", ref_source="_platform"))
                    warnings.append("LLM 运行时未启用，当前回答为 Wiki 片段拼接。请在「设置 → LLM 配置」中启用模型以获得分析型答案。")
        if intent not in {"knowledge_query", "wiki_query", "general_chat"}:
            await add_step(TraceStep(name="model", status="completed", summary="当前能力无需模型生成。", node_type="runtime"))
        answer = self._review_output(answer)
        output_guard_rules = await self._output_guard_rules.list_enabled()
        guard_result = await self._apply_output_guard(
            tenant_id=context.tenant_id,
            answer=answer,
            rules=output_guard_rules,
        )
        answer = guard_result["answer"]
        warnings.extend(guard_result["warnings"])
        conversation_title = (
            await self._generate_conversation_title(
                tenant_id=context.tenant_id,
                user_message=message,
                assistant_message=answer,
            )
            if not short_memory.messages
            else None
        )
        if on_answer_delta is not None and not answer_streamed:
            await self._emit_text_deltas(answer, stream_answer)
        await add_step(
            TraceStep(
                name="output_guard",
                status="completed",
                summary=guard_result["summary"],
                node_type="guard",
            )
        )
        trace.answer = answer
        trace.sources = sources
        await add_step(TraceStep(name="completed", status="completed", summary="响应已组装并返回。", node_type="runtime"))
        await self._traces.save(trace)

        conversation = await self._conversations.append_message(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=conversation_id,
            user_message=message,
            assistant_message=answer,
            title=conversation_title,
        )

        routing = self._build_routing_decision(tenant=tenant, intent=intent, message=message)
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
            "routing": routing,
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
            for item in await self._conversations.list_recent(context.tenant_id, context.user_id, limit=30)
        ]

    async def create_conversation(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        conversation = await self._conversations.create(context.tenant_id, context.user_id)
        return {
            "conversation_id": conversation.conversation_id,
            "title": conversation.title,
            "updated_at": conversation.updated_at.isoformat(),
        }

    async def get_conversation(
        self,
        conversation_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> Conversation | None:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        return await self._conversations.get(context.tenant_id, context.user_id, conversation_id)

    async def delete_conversation(
        self,
        conversation_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        return await self._conversations.delete(context.tenant_id, context.user_id, conversation_id)

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

    async def list_business_outputs(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        type_filter: str | None = None,
        package_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        if self._business_outputs is None:
            return {"items": []}
        if type_filter and type_filter not in BUSINESS_OUTPUT_TYPES:
            raise ValueError("Unsupported output type")
        if status and status not in BUSINESS_OUTPUT_STATUSES:
            raise ValueError("Unsupported output status")
        items = await self._business_outputs.list_for_tenant(
            context.tenant_id,
            type_filter=type_filter,
            package_id=package_id,
            status=status,
        )
        return {"items": [self._serialize_business_output(item) for item in items]}

    async def get_business_output(
        self,
        output_id: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        if self._business_outputs is None:
            raise ValueError("Business output store not configured")
        record = await self._business_outputs.get(context.tenant_id, output_id)
        if record is None:
            raise ValueError("Business output not found")
        return self._serialize_business_output(record)

    async def create_business_output(
        self,
        *,
        type: str,
        title: str,
        package_id: str,
        payload: dict[str, object] | None = None,
        citations: list[str] | None = None,
        conversation_id: str | None = None,
        trace_id: str | None = None,
        summary: str = "",
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        if self._business_outputs is None:
            raise ValueError("Business output store not configured")
        if type not in BUSINESS_OUTPUT_TYPES:
            raise ValueError("Unsupported output type")
        if not title.strip():
            raise ValueError("title is required")
        if not package_id.strip():
            raise ValueError("package_id is required")
        record = BusinessOutput(
            output_id=f"out-{uuid4().hex[:12]}",
            tenant_id=context.tenant_id,
            package_id=package_id.strip(),
            type=type,
            title=title.strip(),
            status="draft",
            payload=payload or {},
            citations=list(citations or []),
            conversation_id=conversation_id,
            trace_id=trace_id,
            summary=summary,
            created_by=context.user_id,
        )
        saved = await self._business_outputs.create(record)
        return self._serialize_business_output(saved)

    async def update_business_output(
        self,
        output_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        payload: dict[str, object] | None = None,
        citations: list[str] | None = None,
        summary: str | None = None,
        linked_draft_group_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        if self._business_outputs is None:
            raise ValueError("Business output store not configured")
        existing = await self._business_outputs.get(context.tenant_id, output_id)
        if existing is None:
            raise ValueError("Business output not found")
        if status is not None and status not in BUSINESS_OUTPUT_STATUSES:
            raise ValueError("Unsupported output status")
        next_record = BusinessOutput(
            output_id=existing.output_id,
            tenant_id=existing.tenant_id,
            package_id=existing.package_id,
            type=existing.type,
            title=title.strip() if title is not None else existing.title,
            status=status or existing.status,
            payload=payload if payload is not None else existing.payload,
            citations=list(citations) if citations is not None else list(existing.citations),
            conversation_id=existing.conversation_id,
            trace_id=existing.trace_id,
            linked_draft_group_id=linked_draft_group_id if linked_draft_group_id is not None else existing.linked_draft_group_id,
            summary=summary if summary is not None else existing.summary,
            created_by=existing.created_by,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
        saved = await self._business_outputs.update(next_record)
        return self._serialize_business_output(saved)

    @staticmethod
    def _serialize_business_output(item: BusinessOutput) -> dict[str, object]:
        return {
            "output_id": item.output_id,
            "tenant_id": item.tenant_id,
            "package_id": item.package_id,
            "type": item.type,
            "title": item.title,
            "status": item.status,
            "payload": item.payload,
            "citations": list(item.citations),
            "conversation_id": item.conversation_id,
            "trace_id": item.trace_id,
            "linked_draft_group_id": item.linked_draft_group_id,
            "summary": item.summary,
            "created_by": item.created_by,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

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
        skills = [item for item in self._skills.list_skills() if item.enabled]
        tools = [item for item in self._tools.list_tools() if item.enabled]
        packages = self._admin_package_catalog()
        return {
            "packages": packages,
            "package_diagnostics": self._registry.list_diagnostics(),
            "capabilities": [
                {
                    "name": item.name,
                    "risk_level": item.risk_level,
                    "side_effect_level": item.side_effect_level,
                    "required_scope": item.required_scope,
                    "source": item.source,
                    "package_id": item.package_id,
                }
                for item in capabilities
            ],
            "skills": [
                {
                    "name": item.name,
                    "description": item.description,
                    "version": item.version,
                    "source": item.source,
                    "package_id": item.package_id,
                    "depends_on_capabilities": list(item.depends_on_capabilities),
                    "depends_on_tools": list(item.depends_on_tools),
                    "steps": list(item.steps),
                    "outputs_mapping": dict(item.outputs_mapping),
                }
                for item in skills
            ],
            "tools": [
                {
                    "name": item.name,
                    "description": item.description,
                    "version": item.version,
                    "source": item.source,
                    "timeout_ms": item.timeout_ms,
                    "quota_per_minute": item.quota_per_minute,
                }
                for item in tools
            ],
        }

    async def list_tenant_packages(self, target_tenant_id: str, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        tenant = await self._tenants.get(target_tenant_id)
        if tenant is None:
            raise ValueError("Tenant not found")
        packages = self._admin_package_catalog()
        industry_packages = [item for item in packages if item["domain"] == "industry"]
        industry_ids = {str(item["package_id"]) for item in industry_packages}
        if tenant.primary_package in industry_ids:
            primary_package = tenant.primary_package
        elif industry_packages:
            primary_package = str(industry_packages[0]["package_id"])
        else:
            primary_package = ""
        return {
            "primary_package": primary_package,
            "common_packages": list(tenant.enabled_common_packages),
            "available_packages": [
                {
                    "package_id": item["package_id"],
                    "name": item["name"],
                    "domain": item["domain"],
                    "version": item["version"],
                    "status": item["status"],
                }
                for item in packages
            ],
        }

    async def update_tenant_packages(
        self,
        target_tenant_id: str,
        primary_package: str,
        common_packages: list[str],
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        tenant = await self._tenants.get(target_tenant_id)
        if tenant is None:
            raise ValueError("Tenant not found")

        catalog = self._admin_package_catalog()
        known_ids = {str(item["package_id"]) for item in catalog}
        industry_ids = {str(item["package_id"]) for item in catalog if item["domain"] == "industry"}
        common_ids = {str(item["package_id"]) for item in catalog if item["domain"] == "common"}

        normalized_primary = primary_package.strip()
        normalized_commons = [item.strip() for item in common_packages if item.strip()]
        if normalized_primary not in industry_ids:
            raise ValueError("主业务包不存在或不是行业包")
        unknown_commons = [item for item in normalized_commons if item not in known_ids or item not in common_ids]
        if unknown_commons:
            raise ValueError(f"通用包不存在或不是通用包: {', '.join(unknown_commons)}")

        updated = replace(
            tenant,
            package=normalized_primary,
            enabled_common_packages=list(dict.fromkeys(normalized_commons)),
        )
        await self._tenants.update(updated)
        return await self.list_tenant_packages(target_tenant_id, tenant_id=tenant_id, user_id=user_id)

    async def install_package_bundle(
        self,
        zip_bytes: bytes,
        *,
        overwrite: bool = False,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        from agent_platform.runtime.package_installer import (
            PackageInstaller,
            PackageInstallError,
        )

        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        installer = PackageInstaller.default()
        try:
            result = installer.install_zip(zip_bytes, overwrite=overwrite)
        except PackageInstallError as exc:
            raise ValueError(str(exc)) from exc
        # Skill + capability registries cache at construction — refresh so the
        # new bundle's private skills and stub capabilities become visible
        # without a process restart.
        self._skills.refresh()
        self._registry.refresh_package_capabilities()
        return result

    async def uninstall_package_bundle(
        self,
        package_id: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        from agent_platform.runtime.package_installer import PackageInstaller

        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        removed = PackageInstaller.default().uninstall(package_id)
        if not removed:
            raise ValueError("Package bundle not found")
        self._skills.refresh()
        self._registry.refresh_package_capabilities()
        return {"package_id": package_id, "removed": True}

    async def get_package_detail(self, package_id: str, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        package = self._find_package(package_id)
        if package is None:
            raise ValueError("Package not found")

        dependencies = list(package.get("dependencies", []))
        return {
            **package,
            "dependencies": dependencies,
            "dependency_summary": {
                "platform_skills": sum(1 for item in dependencies if item.get("kind") == "platform_skill"),
                "common_packages": sum(1 for item in dependencies if item.get("kind") == "common_package"),
                "plugins": sum(1 for item in dependencies if item.get("kind") == "plugin"),
                "tools": sum(1 for item in dependencies if item.get("kind") == "platform_tool"),
            },
        }

    async def get_package_impact(self, target: str, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        target_name, target_version = self._parse_dependency_target(target)
        affected_packages = []
        for package in self._admin_package_catalog():
            for dependency in package.get("dependencies", []):
                if not isinstance(dependency, dict) or dependency.get("name") != target_name:
                    continue
                version_range = str(dependency.get("version_range", ""))
                compatible = self._version_satisfies(target_version, version_range)
                affected_packages.append(
                    {
                        "package_id": package["package_id"],
                        "name": package["name"],
                        "version": package["version"],
                        "dependency": dependency,
                        "risk": "low" if compatible else "high",
                        "compatible": compatible,
                        "reason": "目标版本满足依赖范围" if compatible else f"目标版本不满足依赖范围 {version_range}",
                    }
                )
        return {
            "target": {
                "name": target_name,
                "version": target_version,
            },
            "affected_packages": affected_packages,
        }

    async def _load_capability_tenant_config(
        self,
        *,
        tenant_id: str,
        capability_name: str,
    ) -> dict[str, object]:
        """Resolve the tenant-scoped plugin config for a capability.

        HttpExecutor needs ``endpoint`` / ``secrets`` / ``timeout_ms`` from
        ``plugin_config``; built-in plugins ignore the kwarg, so this is safe
        to call unconditionally.
        """
        plugin_name = self._registry.get_plugin_name_for_capability(capability_name)
        record = await self._plugin_configs.get(tenant_id, plugin_name)
        if record is None:
            return {"tenant_id": tenant_id}
        config = dict(record.config) if record.config else {}
        config["tenant_id"] = tenant_id
        mcp_servers = getattr(self, "_mcp_servers", None)
        if mcp_servers is not None:
            server_name = str(config.get("mcp_server") or "").strip()
            if server_name:
                server = await mcp_servers.get(server_name)
                if server is not None:
                    servers = config.get("mcp_servers")
                    if not isinstance(servers, dict):
                        servers = {}
                    servers[server.name] = self._serialize_mcp_server_for_executor(server)
                    config["mcp_servers"] = servers
        return config

    async def list_mcp_servers(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        mcp_servers = getattr(self, "_mcp_servers", None)
        if mcp_servers is None:
            return {"servers": []}
        servers = await mcp_servers.list_all()
        return {"servers": [self._serialize_mcp_server(item) for item in servers]}

    async def upsert_mcp_server(
        self,
        *,
        name: str,
        transport: str,
        endpoint: str,
        auth_ref: str = "",
        headers: dict[str, object] | None = None,
        status: str = "active",
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        mcp_servers = getattr(self, "_mcp_servers", None)
        if mcp_servers is None:
            raise ValueError("MCP server registry is not configured")
        normalized_name = name.strip()
        normalized_transport = transport.strip().lower()
        normalized_endpoint = endpoint.strip()
        normalized_auth_ref = auth_ref.strip()
        normalized_status = status.strip().lower()
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]+", normalized_name):
            raise ValueError("name only supports letters, numbers, dot, underscore, colon and hyphen")
        if normalized_transport not in {"streamable-http", "http"}:
            raise ValueError("Unsupported MCP transport")
        if not normalized_endpoint.startswith(("http://", "https://")):
            raise ValueError("endpoint must start with http:// or https://")
        if normalized_status not in {"active", "disabled"}:
            raise ValueError("Unsupported MCP server status")
        normalized_headers = headers or {}
        if not isinstance(normalized_headers, dict):
            raise ValueError("headers must be an object")
        for key, value in normalized_headers.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("headers keys must be non-empty strings")
            if not isinstance(value, str):
                raise ValueError("headers values must be strings")

        existing = await mcp_servers.get(normalized_name)
        server = await mcp_servers.upsert(
            McpServer(
                server_id=existing.server_id if existing else f"mcp-{uuid4().hex[:12]}",
                name=normalized_name,
                transport=normalized_transport,
                endpoint=normalized_endpoint,
                auth_ref=normalized_auth_ref,
                headers=dict(normalized_headers),
                status=normalized_status,
            )
        )
        await self._record_admin_audit_event(
            context=context,
            title=f"MCP Server 已更新：{normalized_name}",
            status="已记录",
        )
        return self._serialize_mcp_server(server)

    async def delete_mcp_server(
        self,
        name: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        mcp_servers = getattr(self, "_mcp_servers", None)
        if mcp_servers is None:
            raise ValueError("MCP server registry is not configured")
        normalized_name = name.strip()
        removed = await mcp_servers.delete(normalized_name)
        if not removed:
            raise ValueError("MCP server not found")
        await self._record_admin_audit_event(
            context=context,
            title=f"MCP Server 已删除：{normalized_name}",
            status="已记录",
        )
        return {"name": normalized_name, "deleted": True}

    async def get_plugin_config_schema(self, plugin_name: str, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        plugin = self._registry.get_plugin(plugin_name)
        schema = self._normalize_plugin_config_schema(plugin.config_schema or {})
        saved_config = await self._plugin_configs.get(context.tenant_id, plugin_name)
        config = dict(saved_config.config) if saved_config else {}
        return {
            "plugin_name": plugin_name,
            "capability": asdict(plugin.capability),
            "config_schema": schema,
            "config": self._mask_plugin_config(config, schema),
            "auth_refs": self._available_auth_refs(plugin.auth_ref),
        }

    async def update_plugin_config(
        self,
        plugin_name: str,
        config: dict[str, object],
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        plugin = self._registry.get_plugin(plugin_name)
        schema = self._normalize_plugin_config_schema(plugin.config_schema or {})
        existing_config = await self._plugin_configs.get(context.tenant_id, plugin_name)
        normalized = self._validate_plugin_config(
            config,
            schema,
            self._available_auth_refs(plugin.auth_ref),
            existing_config=dict(existing_config.config) if existing_config else None,
        )
        saved_config = await self._plugin_configs.upsert(
            PluginConfig(
                tenant_id=context.tenant_id,
                plugin_name=plugin_name,
                config=normalized,
            )
        )
        await self._record_admin_audit_event(
            context=context,
            title=f"插件配置已更新：{plugin_name}",
            status="已记录",
        )
        return {
            "plugin_name": plugin_name,
            "config": self._mask_plugin_config(dict(saved_config.config), schema),
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
        events = [asdict(item) for item in await self._security_events.list_recent(context.tenant_id)]
        tenants = await self._tenants.list_all()
        tools = [item for item in self._tools.list_tools() if item.enabled]
        overrides = {
            (item.tenant_id, item.tool_name): item
            for item in await self._tool_overrides.list_all()
        }
        guard_rules = await self._output_guard_rules.list_all()
        if not guard_rules:
            guard_rules = self._default_output_guard_rules()
        return {
            "events": events,
            "drafts": [self._serialize_draft(item) for item in await self._drafts.list_recent(context.tenant_id)],
            "tool_overrides": [
                self._serialize_tool_override(
                    tenant_id=tenant.tenant_id,
                    tool_name=tool.name,
                    default_quota=tool.quota_per_minute,
                    default_timeout=tool.timeout_ms,
                    override=overrides.get((tenant.tenant_id, tool.name)),
                )
                for tool in tools
                for tenant in tenants
            ],
            "redlines": [self._serialize_output_guard_rule(rule, events) for rule in guard_rules],
        }

    async def update_output_guard_rule(
        self,
        *,
        rule_id: str,
        package_id: str,
        pattern: str,
        action: str,
        source: str,
        enabled: bool,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        normalized_rule_id = rule_id.strip()
        normalized_package_id = package_id.strip()
        normalized_pattern = pattern.strip()
        normalized_action = action.strip()
        normalized_source = source.strip()
        if not normalized_rule_id:
            raise ValueError("rule_id is required")
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]+", normalized_rule_id):
            raise ValueError("rule_id only supports letters, numbers, dot, underscore, colon and hyphen")
        if not normalized_package_id:
            raise ValueError("package_id is required")
        known_package_ids = {str(item["package_id"]) for item in self._admin_package_catalog()}
        if normalized_package_id not in known_package_ids:
            raise ValueError("Package not found")
        if not normalized_pattern:
            raise ValueError("pattern is required")
        if normalized_action not in OUTPUT_GUARD_ACTIONS:
            raise ValueError("Unsupported output guard action")
        if not normalized_source:
            raise ValueError("source is required")

        rule = await self._output_guard_rules.upsert(
            OutputGuardRule(
                rule_id=normalized_rule_id,
                package_id=normalized_package_id,
                pattern=normalized_pattern,
                action=normalized_action,
                source=normalized_source,
                enabled=enabled,
            )
        )
        await self._record_admin_audit_event(
            context=context,
            title=f"OutputGuard 红线已更新：{normalized_rule_id}",
            status="已记录",
        )
        events = [asdict(item) for item in await self._security_events.list_recent(context.tenant_id)]
        return self._serialize_output_guard_rule(rule, events)

    async def list_release_plans(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        releases = await self._releases.list_recent()
        return {"releases": [self._serialize_release_plan(item) for item in releases]}

    async def update_release_plan(
        self,
        release_id: str,
        *,
        status: str,
        rollout_percent: int,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        normalized_status = status.strip()
        if normalized_status not in {"待发布", "灰度中", "已完成", "已回滚"}:
            raise ValueError("Unsupported release status")
        if rollout_percent < 0 or rollout_percent > 100:
            raise ValueError("rollout_percent must be between 0 and 100")
        if normalized_status == "已完成" and rollout_percent != 100:
            raise ValueError("completed release must use 100 percent rollout")
        if normalized_status == "已回滚" and rollout_percent != 0:
            raise ValueError("rolled back release must use 0 percent rollout")

        release = await self._releases.update_status(
            release_id,
            status=normalized_status,
            rollout_percent=rollout_percent,
        )
        if release is None:
            raise ValueError("Release not found")
        await self._record_admin_audit_event(
            context=context,
            title=f"发布计划已更新：{release_id} -> {normalized_status}/{rollout_percent}%",
            status="已记录",
        )
        return self._serialize_release_plan(release)

    async def update_tool_override(
        self,
        *,
        target_tenant_id: str,
        tool_name: str,
        quota: int | None,
        timeout: int | None,
        disabled: bool,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_tenant_management_scope(context)
        tenant = await self._tenants.get(target_tenant_id)
        if tenant is None:
            raise ValueError("Tenant not found")
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError("Tool not found")
        if quota is not None and quota < 0:
            raise ValueError("quota must be greater than or equal to 0")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be greater than or equal to 0")

        override = await self._tool_overrides.upsert(
            ToolOverride(
                tenant_id=target_tenant_id,
                tool_name=tool_name,
                quota=quota,
                timeout=timeout,
                disabled=disabled,
            )
        )
        await self._record_admin_audit_event(
            context=context,
            title=f"Tool 覆盖配置已更新：{target_tenant_id}/{tool_name}",
            status="已记录",
        )
        return self._serialize_tool_override(
            tenant_id=target_tenant_id,
            tool_name=tool_name,
            default_quota=tool.quota_per_minute,
            default_timeout=tool.timeout_ms,
            override=override,
        )

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

    async def get_knowledge_source_attributes(
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

        schema = self._chunk_attributes_schema_for_source(detail.source)
        total = len(detail.chunks)
        fields = []
        for field_name, config in schema.items():
            hit_count = sum(
                1
                for chunk in detail.chunks
                if self._chunk_attribute_value(chunk.metadata_json, field_name) is not None
            )
            fields.append(
                {
                    "field": field_name,
                    "type": config["type"],
                    "indexed": config["indexed"],
                    "filter": config.get("filter", ""),
                    "hit_count": hit_count,
                    "chunk_count": total,
                    "hit_rate": round(hit_count / total, 4) if total else 0,
                }
            )
        return {
            "source_id": source_id,
            "schema": schema,
            "fields": fields,
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
        attributes: dict[str, object] | None = None,
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
            attributes=attributes,
        )
        return {"source": asdict(source)}

    async def import_package_knowledge(
        self,
        package_id: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        auto_only: bool = False,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")

        package = self._find_package(package_id)
        if package is None:
            raise ValueError("Package not found")
        bundle_path = package.get("bundle_path")
        if not bundle_path:
            raise ValueError("Package is not an installed bundle")

        imports = package.get("knowledge_imports", [])
        if not isinstance(imports, list):
            raise ValueError("Package knowledge_imports is invalid")

        imported: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        bundle_dir = Path(str(bundle_path))
        for item in imports:
            if not isinstance(item, dict):
                continue
            rel_path = str(item.get("file", "")).strip()
            if auto_only and not bool(item.get("auto_import", False)):
                skipped.append({"file": rel_path, "reason": "auto_import is false"})
                continue
            knowledge_path = PackageLoader._safe_join(bundle_dir, rel_path)
            if not knowledge_path.exists():
                raise ValueError(f"Knowledge file not found: {rel_path}")
            content = knowledge_path.read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError(f"Knowledge file is empty: {rel_path}")
            attributes = item.get("attributes", {})
            if attributes is not None and not isinstance(attributes, dict):
                raise ValueError(f"Knowledge attributes must be an object: {rel_path}")
            source = await self._knowledge_sources.ingest_text(
                tenant_id=context.tenant_id,
                name=str(item.get("name") or knowledge_path.name),
                content=content,
                source_type=str(item.get("source_type") or "Markdown"),
                owner=str(item.get("owner") or f"bundle:{package_id}"),
                knowledge_base_code=str(item.get("knowledge_base_code") or "knowledge"),
                attributes=dict(attributes or {}),
            )
            imported.append(
                {
                    "file": rel_path,
                    "source": asdict(source),
                }
            )

        return {
            "package_id": package_id,
            "imported_count": len(imported),
            "skipped_count": len(skipped),
            "imported": imported,
            "skipped": skipped,
        }

    async def preview_package_knowledge(
        self,
        package_id: str,
        *,
        file: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")

        package = self._find_package(package_id)
        if package is None:
            raise ValueError("Package not found")
        bundle_path = package.get("bundle_path")
        if not bundle_path:
            raise ValueError("Package is not an installed bundle")

        imports = package.get("knowledge_imports", [])
        if not isinstance(imports, list):
            raise ValueError("Package knowledge_imports is invalid")
        normalized_file = file.strip()
        declaration = next(
            (
                item
                for item in imports
                if isinstance(item, dict) and str(item.get("file", "")).strip() == normalized_file
            ),
            None,
        )
        if declaration is None:
            raise ValueError("Knowledge file is not declared by package")

        bundle_dir = Path(str(bundle_path))
        knowledge_path = PackageLoader._safe_join(bundle_dir, normalized_file)
        if not knowledge_path.exists() or not knowledge_path.is_file():
            raise ValueError(f"Knowledge file not found: {normalized_file}")
        content = knowledge_path.read_text(encoding="utf-8")
        attributes = declaration.get("attributes", {})
        if attributes is not None and not isinstance(attributes, dict):
            raise ValueError(f"Knowledge attributes must be an object: {normalized_file}")
        return {
            "package_id": package_id,
            "file": normalized_file,
            "name": str(declaration.get("name") or knowledge_path.name),
            "source_type": str(declaration.get("source_type") or "Markdown"),
            "knowledge_base_code": str(declaration.get("knowledge_base_code") or "knowledge"),
            "owner": str(declaration.get("owner") or f"bundle:{package_id}"),
            "auto_import": bool(declaration.get("auto_import", False)),
            "attributes": dict(attributes or {}),
            "content": content,
        }

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
    def _active_packages_for_tenant(tenant: TenantProfile | None) -> list[dict[str, object]]:
        if tenant is None:
            return []
        packages = PackageLoader.default().list_packages()
        by_id = {str(package.get("package_id") or ""): package for package in packages}
        by_name = {str(package.get("name") or ""): package for package in packages}
        active_ids: set[str] = set()

        def add_identifier(value: str) -> None:
            normalized = value.strip()
            if not normalized:
                return
            if normalized == "通用业务包":
                active_ids.update(
                    str(package.get("package_id") or "")
                    for package in packages
                    if str(package.get("domain") or "") == "common"
                )
                return
            package = by_id.get(normalized) or by_name.get(normalized)
            if package is not None:
                active_ids.add(str(package.get("package_id") or ""))

        add_identifier(tenant.package)
        for package_id in tenant.enabled_common_packages:
            add_identifier(package_id)

        expanded = True
        while expanded:
            expanded = False
            for package_id in list(active_ids):
                package = by_id.get(package_id)
                if package is None:
                    continue
                for dependency in package.get("dependencies", []):
                    if not isinstance(dependency, dict) or dependency.get("kind") != "common_package":
                        continue
                    dependency_id = str(dependency.get("name") or "").strip()
                    if dependency_id and dependency_id in by_id and dependency_id not in active_ids:
                        active_ids.add(dependency_id)
                        expanded = True
        return [package for package in packages if str(package.get("package_id") or "") in active_ids]

    @staticmethod
    def _package_ids(packages: list[dict[str, object]]) -> set[str]:
        return {str(package.get("package_id") or "") for package in packages if str(package.get("package_id") or "")}

    @staticmethod
    def _package_intent_names(packages: list[dict[str, object]]) -> set[str]:
        return {
            str(rule.get("name") or "").strip()
            for package in packages
            for rule in package.get("intents", [])
            if isinstance(rule, dict) and str(rule.get("name") or "").strip()
        }

    @classmethod
    def _allowed_planner_intents(cls, active_packages: list[dict[str, object]]) -> set[str]:
        return {*PLATFORM_INTENTS, *cls._package_intent_names(active_packages)}

    @classmethod
    def _skill_intent_map(cls, active_packages: list[dict[str, object]]) -> dict[str, str]:
        mapping = {
            "kb_grounded_qa": "knowledge_query",
            "report_compose": "report_compose",
        }
        for package in active_packages:
            package_id = str(package.get("package_id") or "").strip()
            intents = [
                str(rule.get("name") or "").strip()
                for rule in package.get("intents", [])
                if isinstance(rule, dict) and str(rule.get("name") or "").strip()
            ]
            if not intents:
                continue
            primary_intent = intents[0]
            source_kind = str(package.get("source_kind") or "catalog")
            for skill in package.get("skills", []):
                if not isinstance(skill, dict):
                    continue
                skill_name = str(skill.get("name") or "").strip()
                if not skill_name:
                    continue
                declared_intents = [
                    str(item).strip()
                    for item in skill.get("intents", [])
                    if str(item).strip()
                ]
                skill_intent = declared_intents[0] if declared_intents else primary_intent
                mapping[skill_name] = skill_intent
                if package_id and str(skill.get("source") or ("package" if source_kind == "bundle" else "")) == "package":
                    mapping[f"{package_id}::{skill_name}"] = skill_intent
        return mapping

    @classmethod
    def _candidate_skill_names_from_packages(cls, packages: list[dict[str, object]]) -> list[str]:
        names: list[str] = []
        for package in packages:
            package_id = str(package.get("package_id") or "").strip()
            source_kind = str(package.get("source_kind") or "catalog")
            names.extend(
                (
                    f"{package_id}::{str(skill.get('name'))}"
                    if (
                        package_id
                        and str(skill.get("source") or ("package" if source_kind == "bundle" else "")) == "package"
                    )
                    else str(skill.get("name"))
                )
                for skill in package.get("skills", [])
                if isinstance(skill, dict) and str(skill.get("name", "")).strip()
            )
            names.extend(
                str(dependency.get("name"))
                for dependency in package.get("dependencies", [])
                if isinstance(dependency, dict)
                and dependency.get("kind") == "platform_skill"
                and str(dependency.get("name", "")).strip()
            )
        return list(dict.fromkeys(names))

    @staticmethod
    def _skill_is_active(
        skill: SkillDefinition,
        active_skill_names: set[str],
        active_package_ids: set[str],
    ) -> bool:
        if skill.name in active_skill_names:
            return True
        if skill.package_id and skill.package_id in active_package_ids:
            return True
        return skill.source == "_platform" and skill.package_id is None and skill.name in active_skill_names

    @staticmethod
    def _capability_is_active(capability: CapabilityDefinition, active_package_ids: set[str]) -> bool:
        return capability.source != "package" or bool(capability.package_id and capability.package_id in active_package_ids)

    @staticmethod
    def _classify_intent(
        message: str,
        retrieval_mode: Literal["auto", "rag", "wiki"] = "auto",
        active_packages: list[dict[str, object]] | None = None,
    ) -> str:
        normalized = message.lower()
        if "json_path" in normalized or "jsonpath" in normalized:
            return "tool.json_path"
        if re.search(r"https?://[^\s，。]+", message) and any(keyword in message for keyword in ("抓取", "访问", "读取", "请求")):
            return "tool.http_fetch"
        package_intents = ChatService._package_intent_names(active_packages or [])
        if (
            "procurement_draft" in package_intents
            and ("采购" in message or "审批草稿" in message or "草稿" in message)
        ):
            return "procurement_draft"
        if "hr_query" in package_intents and ("年假" in message or "假期" in message):
            return "hr_query"
        if retrieval_mode == "wiki":
            return "wiki_query"
        if retrieval_mode == "rag":
            return "knowledge_query"
        catalog_intent = ChatService._classify_catalog_intent(message, active_packages=active_packages or [])
        if catalog_intent:
            return catalog_intent
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
            "根据知识",
            "根据资料",
            "根据文档",
            "按文档",
            "查文档",
            "检索",
            "专业",
            "行业",
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

    async def _plan_intent_with_llm(
        self,
        *,
        tenant_id: str,
        message: str,
        retrieval_mode: Literal["auto", "rag", "wiki"],
        active_packages: list[dict[str, object]],
    ) -> dict[str, object] | None:
        if retrieval_mode == "rag":
            return {"intent": "knowledge_query", "reason": "用户显式选择 RAG 模式"}
        if retrieval_mode == "wiki":
            return {"intent": "wiki_query", "reason": "用户显式选择 Wiki 模式"}
        try:
            config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        except Exception:
            return None
        if not config.enabled or not api_key:
            return None
        context_blocks = [self._planner_context_block(active_packages=active_packages)]
        prompt = (
            "你是 ReAct Planner，只负责选择下一步动作，不回答用户问题。\n"
            "根据用户问题和可用资产，选择一个 action，并只返回 JSON。\n"
            "JSON 格式：{\"intent\":\"...\",\"action_type\":\"tool|skill|capability|chat\",\"action_name\":\"...\",\"arguments\":{},\"reason\":\"...\"}。\n"
            "如果用户只是普通聊天或开放闲聊，intent=general_chat, action_type=chat。\n"
            "当选择 Tool 时，必须根据用户问题填写 arguments；不要让服务端猜参数。\n"
            "如果用户要求查询、查看、获取业务系统记录或业务对象状态，且当前业务包存在匹配的 Skill/Capability，"
            "必须选择 skill 或 capability；不要选择 knowledge_query 去解释 API 文档。\n"
            "time_now 参数使用 IANA timezone：北京时间用 Asia/Shanghai；美国时间若未指定城市/州，返回美国主要时区 "
            "[America/New_York, America/Chicago, America/Denver, America/Los_Angeles]；"
            "纽约用 America/New_York，洛杉矶用 America/Los_Angeles，芝加哥用 America/Chicago，丹佛用 America/Denver。\n"
            "只有用户明确要求查文档/知识库/资料/引用，或问题明显属于专业/行业资料问答时，才选择 knowledge_query。\n"
            f"用户问题：{message}"
        )
        try:
            raw = self._llm_client.complete(
                config=config,
                api_key=api_key,
                user_message=prompt,
                context_blocks=context_blocks,
            )
        except Exception:
            return None
        return self._parse_planner_decision(
            raw,
            allowed_intents=self._allowed_planner_intents(active_packages),
            skill_intent_by_name=self._skill_intent_map(active_packages),
        )

    def _planner_context_block(self, *, active_packages: list[dict[str, object]]) -> str:
        active_skill_names = set(self._candidate_skill_names_from_packages(active_packages))
        active_package_ids = self._package_ids(active_packages)
        tools = [
            {
                "name": item.name,
                "description": item.description,
                "version": item.version,
            }
            for item in self._tools.list_tools()
            if item.enabled
        ]
        skills = [
            {
                "name": item.name,
                "description": item.description,
                "source": item.source,
                "package_id": item.package_id,
                "intents": item.intents,
                "depends_on_capabilities": item.depends_on_capabilities,
                "depends_on_tools": item.depends_on_tools,
                "steps": item.steps,
                "outputs_mapping": item.outputs_mapping,
            }
            for item in self._skills.list_skills()
            if item.enabled and self._skill_is_active(item, active_skill_names, active_package_ids)
        ]
        capabilities = [
            {
                "name": item.name,
                "description": item.description,
                "risk_level": item.risk_level,
                "side_effect_level": item.side_effect_level,
            }
            for item in self._registry.list_capabilities()
            if item.enabled and self._capability_is_active(item, active_package_ids)
        ]
        package_intents = [
            {
                "package_id": str(package.get("package_id") or ""),
                "intent": str(rule.get("name") or ""),
                "keywords": [str(item) for item in rule.get("keywords", [])] if isinstance(rule, dict) else [],
                "score": rule.get("score", 0.5) if isinstance(rule, dict) else 0.5,
            }
            for package in active_packages
            for rule in package.get("intents", [])
            if isinstance(rule, dict) and str(rule.get("name") or "").strip()
        ]
        return json.dumps(
            {
                "当前业务包": [
                    {
                        "package_id": str(package.get("package_id") or ""),
                        "name": str(package.get("name") or ""),
                        "source_kind": str(package.get("source_kind") or "catalog"),
                    }
                    for package in active_packages
                ],
                "当前业务包Intent": package_intents,
                "可用Tool": tools,
                "可用Skill": skills,
                "可用Capability": capabilities,
                "intent说明": {
                    "tool.time_now": "用户询问当前时间、日期或现在几点时使用 time_now。arguments 支持 timezone 或 timezones。",
                    "tool.json_path": "用户要求对 JSON 执行 JSONPath 查询时使用 json_path。",
                    "tool.http_fetch": "用户要求抓取或读取 URL 时使用 http_fetch。",
                    "knowledge_query": "用户明确要求基于文档、知识库、资料、依据、引用或专业行业资料回答时使用 kb_grounded_qa。",
                    "work_order_query": "用户要求查看、查询设备维修工单、历史工单或维修记录时使用 work_order_history_query。",
                    "report_compose": "用户要求报告、汇总、总结或导出时使用 report_compose。",
                    "general_chat": "普通聊天、解释、闲聊、未要求外部事实或工具时使用。",
                },
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _parse_planner_decision(
        raw: str,
        *,
        allowed_intents: set[str] | None = None,
        skill_intent_by_name: dict[str, str] | None = None,
    ) -> dict[str, object] | None:
        cleaned = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start:end + 1]
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        action_type = str(parsed.get("action_type", ""))
        action_name = str(parsed.get("action_name", ""))
        intent = str(parsed.get("intent", ""))
        arguments = parsed.get("arguments")
        if arguments is None:
            parsed["arguments"] = {}
        elif not isinstance(arguments, dict):
            return None
        if action_type == "tool" and action_name:
            tool_intent = {
                "time_now": "tool.time_now",
                "json_path": "tool.json_path",
                "http_fetch": "tool.http_fetch",
            }.get(action_name)
            if tool_intent:
                parsed["intent"] = tool_intent
                return parsed
        if action_type == "skill" and action_name:
            skill_intent = (skill_intent_by_name or {}).get(action_name)
            if skill_intent:
                parsed["intent"] = skill_intent
                return parsed
        allowed_intents = allowed_intents or set(PLATFORM_INTENTS)
        if intent in allowed_intents:
            return parsed
        return None

    @staticmethod
    def _classify_catalog_intent(
        message: str,
        *,
        active_packages: list[dict[str, object]] | None = None,
    ) -> str | None:
        scored: list[tuple[float, str]] = []
        lowered = message.lower()
        for package in active_packages or []:
            for rule in package.get("intents", []):
                if not isinstance(rule, dict):
                    continue
                intent = str(rule.get("name", "")).strip()
                if not intent:
                    continue
                keywords = [str(item) for item in rule.get("keywords", []) if str(item).strip()]
                hits = [keyword for keyword in keywords if keyword.lower() in lowered]
                if not hits:
                    continue
                score = float(rule.get("score", 0.5)) + min(0.2, len(hits) * 0.05)
                scored.append((score, intent))
        if not scored:
            return None
        return max(scored, key=lambda item: item[0])[1]

    @staticmethod
    def _extract_employee_name(message: str) -> str:
        for name in ("张三", "李四", "王五"):
            if name in message:
                return name
        return "张三"

    def _plan(
        self,
        message: str,
        intent: str,
    ) -> tuple[str, dict[str, object]]:
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
        if intent == "report_compose":
            return "knowledge.search", {"query": message}
        if intent == "fault_diagnosis":
            return "knowledge.search", {
                "query": message,
                "last_n": 5,
            }
        return "knowledge.search", {"query": message}

    async def _fill_skill_inputs_with_llm(
        self,
        *,
        tenant_id: str,
        message: str,
        skill: SkillDefinition,
        payload: dict[str, object],
        add_step: Callable[[TraceStep], Awaitable[None]] | None = None,
    ) -> dict[str, object]:
        payload = self._apply_skill_input_defaults(skill, payload)
        missing_inputs = self._missing_skill_inputs(skill, payload)
        if not missing_inputs:
            return payload
        try:
            config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        except Exception:
            config, api_key = None, ""
        if config is None or not getattr(config, "enabled", False) or not api_key:
            if add_step is not None:
                await add_step(
                    TraceStep(
                        name="slot_fill",
                        status="skipped",
                        summary="LLM Runtime 未启用，无法自动抽取 Skill 必填入参。",
                        node_type="runtime",
                    )
                )
            return payload

        input_contract = {
            name: schema
            for name, schema in skill.inputs.items()
            if isinstance(schema, dict)
        }
        prompt = (
            "你是业务包 Skill 的参数抽取器，只从用户原文抽取字段，不回答问题。\n"
            "根据 Skill 输入合同，从用户问题中抽取可明确识别的参数，返回 JSON 对象。\n"
            "要求：\n"
            "1. 只返回 JSON 对象，不要 Markdown，不要解释。\n"
            "2. 不确定或原文未出现的字段不要返回，禁止猜测或补默认业务数据。\n"
            "3. 保留原文中的业务编号、设备编号、故障码、日期等关键值，不要改写。\n"
            "4. 已有参数不要覆盖，除非用户原文有更明确的同名字段。\n\n"
            f"Skill: {skill.name}\n"
            f"输入合同: {json.dumps(input_contract, ensure_ascii=False)}\n"
            f"已有参数: {json.dumps(payload, ensure_ascii=False, default=str)}\n"
            f"用户问题: {message}"
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
            if add_step is not None:
                await add_step(
                    TraceStep(
                        name="slot_fill",
                        status="failed",
                        summary="LLM 参数抽取失败，保留已有参数并进入必填校验。",
                        node_type="runtime",
                    )
                )
            return payload

        extracted = self._parse_slot_fill_payload(raw)
        allowed_names = set(input_contract)
        enriched = dict(payload)
        for name, value in extracted.items():
            if name not in allowed_names or value in (None, "", []):
                continue
            enriched[name] = value
        if add_step is not None:
            filled = sorted(
                name
                for name in allowed_names
                if payload.get(name) in (None, "", []) and enriched.get(name) not in (None, "", [])
            )
            await add_step(
                TraceStep(
                    name="slot_fill",
                    status="completed" if filled else "skipped",
                    summary=(
                        f"已基于 Skill 输入合同抽取参数：{', '.join(filled)}。"
                        if filled
                        else "未从用户问题中抽取到新的 Skill 入参。"
                    ),
                    node_type="runtime",
                )
            )
        return enriched

    @staticmethod
    def _apply_skill_input_defaults(skill: SkillDefinition, payload: dict[str, object]) -> dict[str, object]:
        enriched = dict(payload)
        for name, schema in skill.inputs.items():
            if not isinstance(schema, dict) or "default" not in schema:
                continue
            if enriched.get(name) in (None, "", []):
                enriched[name] = schema["default"]
        return enriched

    @staticmethod
    def _parse_slot_fill_payload(raw: str) -> dict[str, object]:
        cleaned = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start:end + 1]
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @staticmethod
    def _missing_skill_inputs(skill: SkillDefinition, payload: dict[str, object]) -> list[str]:
        missing: list[str] = []
        for name, schema in skill.inputs.items():
            if not isinstance(schema, dict) or not schema.get("required"):
                continue
            if payload.get(name) in (None, "", []):
                missing.append(str(name))
        return missing

    @staticmethod
    def _compose_missing_skill_inputs_answer(skill: SkillDefinition, missing_inputs: list[str]) -> str:
        labels = {
            "equipment_id": "设备编号或设备名称",
            "fault_code": "故障码",
            "last_n": "历史记录数量",
        }
        readable = "、".join(labels.get(item, item) for item in missing_inputs)
        return (
            f"要执行 {skill.name}，还需要补充：{readable}。\n"
            "请把缺少的信息补充到问题里，我再调用对应业务包 API 和知识资料。"
        )

    def _plan_platform_tool(
        self,
        message: str,
        intent: str,
        *,
        planner_decision: dict[str, object] | None = None,
    ) -> tuple[str, dict[str, object]] | None:
        planner_arguments = planner_decision.get("arguments") if planner_decision else None
        arguments = dict(planner_arguments) if isinstance(planner_arguments, dict) else {}
        if intent == "tool.time_now":
            if arguments:
                return "time_now", arguments
            timezone = "Asia/Shanghai"
            timezone_match = re.search(r"(UTC[+-]\d{1,2}|Asia/[A-Za-z_]+|America/[A-Za-z_]+|Europe/[A-Za-z_]+)", message)
            if timezone_match:
                timezone = timezone_match.group(1).replace("UTC+8", "Asia/Shanghai")
            return "time_now", {"timezone": timezone}
        if intent == "tool.http_fetch":
            if arguments.get("url"):
                return "http_fetch", arguments
            match = re.search(r"https?://[^\s，。]+", message)
            if not match:
                raise ValueError("未找到可抓取的 http(s) URL")
            return "http_fetch", {"url": match.group(0)}
        if intent == "tool.json_path":
            if arguments.get("document") is not None:
                return "json_path", arguments
            return "json_path", self._extract_json_path_payload(message)
        return None

    @staticmethod
    def _extract_json_path_payload(message: str) -> dict[str, object]:
        path_match = re.search(r"(\$(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)", message)
        path = path_match.group(1) if path_match else "$"
        search_from = path_match.end() if path_match else 0
        object_start = message.find("{", search_from)
        array_start = message.find("[", search_from)
        if object_start >= 0 and (array_start == -1 or object_start < array_start):
            json_start = object_start
        elif array_start >= 0:
            json_start = array_start
        else:
            raise ValueError("JSONPath Tool 需要在消息中提供 JSON 对象或数组")
        json_text = message[json_start:].strip()
        return {
            "document": json.loads(json_text),
            "path": path,
        }

    def _select_skill_for_intent(
        self,
        *,
        intent: str,
        tenant: TenantProfile | None,
        active_packages: list[dict[str, object]],
    ) -> SkillDefinition | None:
        candidates = self._candidate_skill_names_for_intent(intent, active_packages=active_packages)
        for skill_name in candidates:
            skill = self._skills.get(skill_name)
            if skill is None or not skill.enabled:
                continue
            if skill.source in {"_platform", "package"}:
                return skill
            if skill.source == "_common" and self._common_skill_available(skill, tenant):
                return skill
        return None

    @classmethod
    def _candidate_skill_names_for_intent(
        cls,
        intent: str,
        *,
        active_packages: list[dict[str, object]],
    ) -> list[str]:
        names: list[str] = []
        for package in active_packages:
            package_intents = {
                str(rule.get("name", ""))
                for rule in package.get("intents", [])
                if isinstance(rule, dict)
            }
            if intent not in package_intents:
                continue
            package_id = str(package.get("package_id") or "").strip()
            source_kind = str(package.get("source_kind") or "catalog")
            names.extend(
                (
                    f"{package_id}::{str(skill.get('name'))}"
                    if (
                        package_id
                        and str(skill.get("source") or ("package" if source_kind == "bundle" else "")) == "package"
                    )
                    else str(skill.get("name"))
                )
                for skill in package.get("skills", [])
                if isinstance(skill, dict) and str(skill.get("name", "")).strip()
                and cls._skill_matches_intent(skill, intent)
            )
            names.extend(
                str(dependency.get("name"))
                for dependency in package.get("dependencies", [])
                if isinstance(dependency, dict)
                and dependency.get("kind") == "platform_skill"
                and str(dependency.get("name", "")).strip()
            )
        if intent == "knowledge_query":
            names.append("kb_grounded_qa")
        if intent == "report_compose":
            names.append("report_compose")
        return list(dict.fromkeys(names))

    @staticmethod
    def _skill_matches_intent(skill: dict[str, object], intent: str) -> bool:
        declared = [
            str(item).strip()
            for item in skill.get("intents", [])
            if str(item).strip()
        ]
        return not declared or intent in declared

    @staticmethod
    def _common_skill_available(skill: SkillDefinition, tenant: TenantProfile | None) -> bool:
        if not skill.package_id:
            return True
        if tenant is None:
            return False
        active_ids = {tenant.package, *tenant.enabled_common_packages}
        if skill.package_id in active_ids or tenant.package == "通用业务包":
            return True
        package = PackageLoader.default().get_package(tenant.package)
        if package is None:
            return False
        return any(
            dependency.get("kind") == "common_package" and dependency.get("name") == skill.package_id
            for dependency in package.get("dependencies", [])
            if isinstance(dependency, dict)
        )

    async def _invoke_tool_with_trace(
        self,
        *,
        tool_name: str,
        payload: dict[str, object],
        add_step: Callable[[TraceStep], Awaitable[None]],
    ) -> dict[str, object]:
        result = self._tools.invoke(tool_name, payload)
        await add_step(
            TraceStep(
                name="tool_executed",
                status="completed",
                summary=f"平台 Tool {tool_name} 执行完成。",
                node_type="tool",
                ref=tool_name,
                ref_source="_platform",
                ref_version=self._tools.get(tool_name).version if self._tools.get(tool_name) else None,
            )
        )
        return result

    async def _run_declarative_skill(
        self,
        *,
        skill: SkillDefinition,
        inputs: dict[str, object],
        tenant_id: str,
        add_step: Callable[[TraceStep], Awaitable[None]],
    ) -> dict[str, object]:
        """执行业务包声明式 skill，并把租户配置、权限校验和 Trace 写入连接起来。"""

        async def load_tenant_config(capability_name: str) -> dict[str, object]:
            capability = self._registry.get(capability_name)
            # skill 内部 capability 仍复用平台权限模型，不能绕过 capability 自身声明的 scope。
            self._ensure_scope(
                context=UserContext(
                    tenant_id=tenant_id,
                    user_id="skill_executor",
                    role="runtime",
                    scopes=[],
                ),
                required_scope=capability.required_scope,
            )
            # HTTP/MCP 等执行器需要租户级 endpoint、密钥和超时配置，由 service 统一加载。
            return await self._load_capability_tenant_config(
                tenant_id=tenant_id,
                capability_name=capability_name,
            )

        executor = SkillExecutor(
            registry=self._registry,
            tools=self._tools,
            load_tenant_config=load_tenant_config,
            add_step=add_step,
        )
        result = await executor.execute(skill, inputs)
        return result.outputs

    async def _run_report_compose_skill(
        self,
        *,
        tenant_id: str,
        query: str,
        add_step: Callable[[TraceStep], Awaitable[None]],
    ) -> dict[str, object]:
        search_result = await self._run_knowledge_search(tenant_id, query, add_step=add_step)
        matches = list(search_result.get("matches", []))
        tool_result = await self._invoke_tool_with_trace(
            tool_name="json_path",
            payload={
                "document": {
                    "matches": [
                        {"title": item.title, "snippet": item.snippet}
                        for item in matches
                        if isinstance(item, SourceReference)
                    ]
                },
                "path": "$.matches",
            },
            add_step=add_step,
        )
        return {
            "summary": "已基于通用报告 Skill 汇总检索事实、引用和建议。",
            "matches": matches,
            "report": {
                "title": "业务资料汇总报告",
                "fact_count": int(tool_result.get("match_count", 0)),
            },
            "retrieval": search_result.get("retrieval", {}),
        }

    @staticmethod
    def _compose_tool_answer(tool_name: str, result: dict[str, object]) -> tuple[str, list[SourceReference]]:
        if tool_name == "time_now":
            items = result.get("items")
            if isinstance(items, list) and len(items) > 1:
                lines = [
                    f"- {item['timezone']}：{item['iso']}"
                    for item in items
                    if isinstance(item, dict) and item.get("timezone") and item.get("iso")
                ]
                return (
                    "当前时间：\n" + "\n".join(lines),
                    [],
                )
            return (
                f"当前时间：{result['iso']}（{result['timezone']}）。",
                [],
            )
        if tool_name == "json_path":
            return (
                f"JSONPath {result['path']} 查询完成，命中 {result['match_count']} 项：{json.dumps(result['matches'], ensure_ascii=False)}",
                [],
            )
        if tool_name == "http_fetch":
            text = str(result.get("text", ""))
            preview = text[:500].replace("\n", " ")
            return (
                f"HTTP 抓取完成，状态码 {result['status']}，内容类型 {result['content_type']}。\n{preview}",
                [
                    SourceReference(
                        id=str(result["url"]),
                        title=str(result["url"]),
                        snippet=preview,
                        source_type="tool",
                    )
                ],
            )
        return (f"Tool {tool_name} 执行完成。", [])

    @staticmethod
    def _compose_skill_answer(skill: SkillDefinition, result: dict[str, object]) -> tuple[str, list[SourceReference]]:
        sources = [item for item in result.get("sources", []) if isinstance(item, SourceReference)]
        if skill.name == "work_order_history_query":
            return ChatService._compose_work_order_history_answer(result), sources
        summary = result.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary, sources
        visible_items = {
            key: value
            for key, value in result.items()
            if key not in {"sources", "step_results"} and value not in (None, "", [], {})
        }
        if visible_items:
            return (
                f"Skill {skill.name} 执行完成：{json.dumps(visible_items, ensure_ascii=False, default=str)}",
                sources,
            )
        return (f"Skill {skill.name} 执行完成。", sources)

    @staticmethod
    def _compose_work_order_history_answer(result: dict[str, object]) -> str:
        equipment_id = str(result.get("equipment_id") or "").strip()
        workorders = result.get("workorders")
        if not isinstance(workorders, list) or not workorders:
            return f"未查询到设备 {equipment_id or '指定设备'} 的维修工单。"

        lines = [f"已查询到设备 {equipment_id or '指定设备'} 的维修工单 {len(workorders)} 条："]
        for index, item in enumerate(workorders[:8], start=1):
            if not isinstance(item, dict):
                continue
            order_id = item.get("work_order_id") or item.get("id") or f"#{index}"
            status = item.get("status") or "未知状态"
            priority = item.get("priority") or "未知优先级"
            created_at = item.get("created_at") or item.get("created_time") or ""
            symptom = item.get("symptom") or item.get("summary") or item.get("title") or ""
            root_cause = item.get("root_cause") or ""
            actions = item.get("actions")
            action_text = ""
            if isinstance(actions, list) and actions:
                action_text = "；处置：" + "、".join(str(action) for action in actions[:3])
            lines.append(
                f"{index}. {order_id}｜状态：{status}｜优先级：{priority}"
                f"{f'｜创建：{created_at}' if created_at else ''}"
                f"{f'｜现象：{symptom}' if symptom else ''}"
                f"{f'｜原因：{root_cause}' if root_cause else ''}"
                f"{action_text}"
            )
        if len(workorders) > 8:
            lines.append(f"其余 {len(workorders) - 8} 条未展开。")
        return "\n".join(lines)

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
        if intent == "report_compose":
            matches = list(result["matches"])
            if not matches:
                return f"{result['summary']}\n暂无可引用事实，请先补充或发布相关知识资料。", []
            bullets = "\n".join(f"- {item.title}: {item.snippet}" for item in matches)
            fact_count = result.get("report", {}).get("fact_count", len(matches)) if isinstance(result.get("report"), dict) else len(matches)
            answer = f"{result['summary']}\n引用事实 {fact_count} 项：\n{bullets}"
            return answer, matches

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

    def _select_candidate_capabilities(
        self,
        context: UserContext,
        *,
        active_packages: list[dict[str, object]],
    ) -> list[CapabilityDefinition]:
        _ = context
        active_package_ids = self._package_ids(active_packages)
        return [
            capability
            for capability in self._registry.list_capabilities()
            if capability.enabled and self._capability_is_active(capability, active_package_ids)
        ]

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
    def _admin_package_catalog() -> list[dict[str, object]]:
        return PackageLoader.default().list_packages()

    @staticmethod
    def _find_package(package_id: str) -> dict[str, object] | None:
        return PackageLoader.default().get_package(package_id)

    @staticmethod
    def _parse_dependency_target(target: str) -> tuple[str, str]:
        normalized = target.strip()
        if "@" not in normalized:
            raise ValueError("target must be '<name>@<version>'")
        name, version = normalized.rsplit("@", 1)
        if not name or not version:
            raise ValueError("target must be '<name>@<version>'")
        return name, version

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, int, int]:
        parts = version.strip().lstrip("v").split(".")
        numbers: list[int] = []
        for part in parts[:3]:
            digits = "".join(char for char in part if char.isdigit())
            numbers.append(int(digits or "0"))
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers)  # type: ignore[return-value]

    @staticmethod
    def _version_satisfies(version: str, version_range: str) -> bool:
        target = ChatService._version_tuple(version)
        constraints = version_range.strip()
        if not constraints:
            return True
        if constraints.startswith("~"):
            base = ChatService._version_tuple(constraints[1:])
            upper = (base[0], base[1] + 1, 0)
            return target >= base and target < upper
        for constraint in constraints.split():
            if constraint.startswith(">="):
                if target < ChatService._version_tuple(constraint[2:]):
                    return False
                continue
            if constraint.startswith(">"):
                if target <= ChatService._version_tuple(constraint[1:]):
                    return False
                continue
            if constraint.startswith("<="):
                if target > ChatService._version_tuple(constraint[2:]):
                    return False
                continue
            if constraint.startswith("<"):
                if target >= ChatService._version_tuple(constraint[1:]):
                    return False
                continue
            if constraint[0].isdigit() and target != ChatService._version_tuple(constraint):
                return False
        return True

    @staticmethod
    def _chunk_attributes_schema_for_source(source: KnowledgeSource) -> dict[str, dict[str, str]]:
        return source.chunk_attributes_schema

    @staticmethod
    def _chunk_attribute_value(metadata_json: dict[str, object], field_name: str) -> object | None:
        attributes = metadata_json.get("attributes")
        if isinstance(attributes, dict) and field_name in attributes:
            return attributes[field_name]
        return metadata_json.get(field_name)

    @staticmethod
    def _normalize_plugin_config_schema(schema: dict[str, object]) -> dict[str, object]:
        def normalize_field(field_name: str, raw_config: dict[str, object]) -> dict[str, object]:
            field_config = dict(raw_config)
            if "array<" in str(field_config.get("type")):
                field_config["type"] = "array"
                field_config.setdefault("items", {"type": "string"})
            if field_config.pop("secret", False):
                field_config["format"] = "secret-ref"
            if field_config.get("type") == "object":
                nested_properties: dict[str, object] = {}
                nested_required: list[str] = []
                raw_nested = field_config.get("properties")
                if isinstance(raw_nested, dict):
                    for nested_name, nested_config in raw_nested.items():
                        if not isinstance(nested_config, dict):
                            continue
                        normalized_nested = normalize_field(str(nested_name), nested_config)
                        if normalized_nested.pop("required", False):
                            nested_required.append(str(nested_name))
                        nested_properties[str(nested_name)] = normalized_nested
                if isinstance(field_config.get("required"), list):
                    nested_required.extend(str(item) for item in field_config["required"])  # type: ignore[index]
                field_config["properties"] = nested_properties
                field_config["required"] = list(dict.fromkeys(nested_required))
                field_config.setdefault("additionalProperties", field_name == "secrets" and not nested_properties)
            return field_config

        properties: dict[str, object] = {}
        required: list[str] = []
        raw_properties = schema.get("properties") if "properties" in schema else schema
        if not isinstance(raw_properties, dict):
            raw_properties = {}
        for field_name, raw_config in raw_properties.items():
            if not isinstance(raw_config, dict):
                continue
            field_config = normalize_field(str(field_name), raw_config)
            if field_config.pop("required", False):
                required.append(str(field_name))
            properties[str(field_name)] = field_config
        if isinstance(schema.get("required"), list):
            required.extend(str(item) for item in schema["required"])
        return {
            "type": "object",
            "properties": properties,
            "required": list(dict.fromkeys(required)),
            "additionalProperties": False,
        }

    @staticmethod
    def _available_auth_refs(default_ref: str | None) -> list[str]:
        refs = [
            "secrets/hr_demo_token",
            "secrets/workflow_sandbox_token",
            "secrets/erp_factoryA_token",
            "secrets/erp_factoryB_token",
        ]
        if default_ref and default_ref not in refs:
            refs.insert(0, default_ref)
        return refs

    @staticmethod
    def _validate_plugin_config(
        config: dict[str, object],
        schema: dict[str, object],
        auth_refs: list[str],
        *,
        existing_config: dict[str, object] | None = None,
    ) -> dict[str, object]:
        properties = schema.get("properties")
        required = schema.get("required", [])
        if not isinstance(properties, dict):
            properties = {}
        if not isinstance(required, list):
            required = []
        normalized: dict[str, object] = {}
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                continue
            value = config.get(field_name, field_schema.get("default"))
            existing_value = (existing_config or {}).get(field_name)
            if field_name in required and value in (None, ""):
                raise ValueError(f"Missing required config field: {field_name}")
            if value in (None, ""):
                continue
            field_type = field_schema.get("type")
            if field_type == "object":
                if not isinstance(value, dict):
                    raise ValueError(f"Invalid object config field: {field_name}")
                normalized[field_name] = ChatService._validate_object_config(
                    field_name=field_name,
                    value=value,
                    schema=field_schema,
                    auth_refs=auth_refs,
                    existing_value=existing_value if isinstance(existing_value, dict) else None,
                )
                continue
            if field_schema.get("format") == "secret-ref":
                if not isinstance(value, str) or value not in auth_refs:
                    raise ValueError(f"Invalid secret reference for field: {field_name}")
                normalized[field_name] = value
                continue
            if field_type == "integer":
                normalized[field_name] = int(value)  # type: ignore[arg-type]
            elif field_type == "number":
                normalized[field_name] = float(value)  # type: ignore[arg-type]
            elif field_type == "boolean":
                normalized[field_name] = bool(value)
            elif field_type == "array":
                normalized[field_name] = value if isinstance(value, list) else [value]
            else:
                normalized[field_name] = str(value)
        unknown_fields = set(config) - set(properties)
        if unknown_fields:
            raise ValueError(f"Unknown config fields: {', '.join(sorted(unknown_fields))}")
        return normalized

    @staticmethod
    def _validate_object_config(
        *,
        field_name: str,
        value: dict[str, object],
        schema: dict[str, object],
        auth_refs: list[str],
        existing_value: dict[str, object] | None = None,
    ) -> dict[str, object]:
        properties = schema.get("properties")
        required = schema.get("required", [])
        if not isinstance(properties, dict):
            properties = {}
        if not isinstance(required, list):
            required = []

        if not properties:
            if not schema.get("additionalProperties", False):
                if value:
                    raise ValueError(f"Unknown config fields under {field_name}: {', '.join(sorted(value))}")
                return {}
            return {
                key: ChatService._normalize_secret_value(key, raw_value, (existing_value or {}).get(key))
                for key, raw_value in value.items()
                if raw_value not in (None, "")
            }

        normalized: dict[str, object] = {}
        for nested_name, nested_schema in properties.items():
            if not isinstance(nested_schema, dict):
                continue
            raw_value = value.get(nested_name, nested_schema.get("default"))
            existing_nested = (existing_value or {}).get(nested_name)
            dotted_name = f"{field_name}.{nested_name}"
            if nested_name in required and raw_value in (None, ""):
                if existing_nested not in (None, ""):
                    normalized[str(nested_name)] = existing_nested
                    continue
                raise ValueError(f"Missing required config field: {dotted_name}")
            if raw_value in (None, ""):
                continue
            if field_name == "secrets":
                normalized[str(nested_name)] = ChatService._normalize_secret_value(
                    dotted_name,
                    raw_value,
                    existing_nested,
                )
                continue
            if nested_schema.get("format") == "secret-ref":
                if not isinstance(raw_value, str) or raw_value not in auth_refs:
                    raise ValueError(f"Invalid secret reference for field: {dotted_name}")
                normalized[str(nested_name)] = raw_value
                continue
            nested_type = nested_schema.get("type")
            if nested_type == "integer":
                normalized[str(nested_name)] = int(raw_value)  # type: ignore[arg-type]
            elif nested_type == "number":
                normalized[str(nested_name)] = float(raw_value)  # type: ignore[arg-type]
            elif nested_type == "boolean":
                normalized[str(nested_name)] = bool(raw_value)
            elif nested_type == "array":
                normalized[str(nested_name)] = raw_value if isinstance(raw_value, list) else [raw_value]
            else:
                normalized[str(nested_name)] = str(raw_value)
        unknown_fields = set(value) - set(properties)
        if unknown_fields and not schema.get("additionalProperties", False):
            raise ValueError(f"Unknown config fields under {field_name}: {', '.join(sorted(unknown_fields))}")
        if schema.get("additionalProperties", False):
            for nested_name in sorted(unknown_fields):
                raw_value = value[nested_name]
                if raw_value in (None, ""):
                    continue
                normalized[str(nested_name)] = ChatService._normalize_secret_value(
                    f"{field_name}.{nested_name}",
                    raw_value,
                    (existing_value or {}).get(nested_name),
                )
        return normalized

    @staticmethod
    def _normalize_secret_value(field_name: str, value: object, existing_value: object | None) -> str:
        if not isinstance(value, str):
            raise ValueError(f"Invalid secret value for field: {field_name}")
        if ChatService._is_masked_secret(value) and isinstance(existing_value, str) and existing_value:
            return existing_value
        return value

    @staticmethod
    def _mask_plugin_config(config: dict[str, object], schema: dict[str, object]) -> dict[str, object]:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return dict(config)
        masked: dict[str, object] = {}
        for field_name, value in config.items():
            field_schema = properties.get(field_name)
            if isinstance(field_schema, dict) and field_schema.get("type") == "object" and isinstance(value, dict):
                masked[field_name] = ChatService._mask_object_config(field_name, value, field_schema)
            else:
                masked[field_name] = value
        return masked

    @staticmethod
    def _mask_object_config(field_name: str, value: dict[str, object], schema: dict[str, object]) -> dict[str, object]:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        masked: dict[str, object] = {}
        for nested_name, nested_value in value.items():
            nested_schema = properties.get(nested_name)
            if field_name == "secrets":
                masked[nested_name] = ChatService._mask_secret(str(nested_value))
            else:
                masked[nested_name] = nested_value
        return masked

    @staticmethod
    def _mask_secret(value: str) -> str:
        if not value:
            return ""
        return f"***{value[-4:]}" if len(value) > 4 else "***"

    @staticmethod
    def _is_masked_secret(value: str) -> bool:
        return value == "***" or (value.startswith("***") and len(value) > 3)

    @staticmethod
    def _build_routing_decision(tenant: TenantProfile | None, intent: str, message: str = "") -> dict[str, object]:
        return PackageRouter.default().route(tenant=tenant, intent=intent, message=message)

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

    async def _apply_output_guard(
        self,
        *,
        tenant_id: str,
        answer: str,
        rules: list[OutputGuardRule],
    ) -> dict[str, object]:
        """按租户输出红线规则处理回答，并记录命中安全事件。"""

        if not answer or not rules:
            return {
                "answer": answer,
                "warnings": [],
                "summary": "输出脱敏与内容审查完成，未命中红线规则。",
            }

        guarded_answer = answer
        warnings: list[str] = []
        matched_rules: list[OutputGuardRule] = []
        blocked = False

        for rule in rules:
            if not rule.enabled or not self._output_guard_matches(rule.pattern, guarded_answer):
                continue
            matched_rules.append(rule)
            # 规则动作按风险递增处理：提示、脱敏、降级、阻断；阻断后立即停止后续输出加工。
            if rule.action == "prepend_safety_warning":
                prefix = "安全提示：执行设备、能量源或现场作业相关操作前，请先确认断电、泄压、挂牌上锁和人员资质。"
                if not guarded_answer.startswith(prefix):
                    guarded_answer = f"{prefix}\n\n{guarded_answer}"
            elif rule.action == "append_warning":
                suffix = "安全提示：以上内容仅用于辅助判断，涉及现场作业请遵循企业 SOP 与审批流程。"
                if suffix not in guarded_answer:
                    guarded_answer = f"{guarded_answer}\n\n{suffix}"
            elif rule.action == "mask_sensitive_data":
                guarded_answer = self._mask_sensitive_output(guarded_answer)
            elif rule.action == "downgrade_answer":
                guarded_answer = (
                    "该问题命中安全治理规则，我只能提供原则性说明，不能给出可直接执行的高风险操作步骤。\n\n"
                    f"{self._summarize_guarded_answer(guarded_answer)}"
                )
                warnings.append(f"OutputGuard 已降级回答：{rule.rule_id}")
            elif rule.action == "block_or_escalate":
                guarded_answer = (
                    "该回答命中安全红线，已停止输出具体操作建议。请联系安全治理组或具备资质的现场负责人复核。"
                )
                blocked = True
                warnings.append(f"OutputGuard 已拦截回答：{rule.rule_id}")
                break

        for rule in matched_rules:
            # 命中红线不仅影响本次回答，也落安全事件，供治理页面和审计链路追踪。
            await self._security_events.save(
                SecurityEvent(
                    event_id=f"sec-og-{uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    category="safety",
                    severity="critical" if rule.action == "block_or_escalate" else "high",
                    title=f"OutputGuard 命中 {rule.rule_id}",
                    status="已阻断" if blocked and rule.action == "block_or_escalate" else "已处理",
                    owner="安全治理组",
                )
            )

        if not matched_rules:
            return {
                "answer": guarded_answer,
                "warnings": warnings,
                "summary": "输出脱敏与内容审查完成，未命中红线规则。",
            }
        return {
            "answer": guarded_answer,
            "warnings": warnings,
            "summary": f"输出治理命中 {len(matched_rules)} 条红线规则：{', '.join(rule.rule_id for rule in matched_rules)}。",
        }

    async def _record_admin_audit_event(self, *, context: UserContext, title: str, status: str) -> None:
        await self._security_events.save(
            SecurityEvent(
                event_id=f"sec-audit-{uuid4().hex[:12]}",
                tenant_id=context.tenant_id,
                category="audit",
                severity="medium",
                title=f"{title}（操作者：{context.user_id}）",
                status=status,
                owner="平台治理组",
            )
        )

    @staticmethod
    def _output_guard_matches(pattern: str, answer: str) -> bool:
        try:
            return re.search(pattern, answer, flags=re.IGNORECASE) is not None
        except re.error:
            return pattern.lower() in answer.lower()

    @staticmethod
    def _mask_sensitive_output(answer: str) -> str:
        masked = re.sub(r"\b1[3-9]\d{3}(\d{4})\d{4}\b", r"1****\1****", answer)
        return re.sub(r"\b[A-Z]{1,4}\d{4,10}\b", "***", masked)

    @staticmethod
    def _summarize_guarded_answer(answer: str) -> str:
        first_line = next((line.strip() for line in answer.splitlines() if line.strip()), "")
        if len(first_line) > 120:
            return f"{first_line[:120]}..."
        return first_line or "请补充业务背景后由具备权限的人员复核。"

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

    async def _generate_conversation_title(
        self,
        *,
        tenant_id: str,
        user_message: str,
        assistant_message: str,
    ) -> str:
        fallback = self._normalize_conversation_title(user_message)
        config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        if not config.enabled:
            return fallback
        prompt = (
            "请基于下面第一轮问答生成一个中文会话标题。\n"
            "要求：不超过 16 个汉字；不要引号；不要句号；只输出标题。\n\n"
            f"用户：{user_message}\n"
            f"助手：{assistant_message[:800]}"
        )
        try:
            title = self._llm_client.complete(
                config=config,
                api_key=api_key,
                user_message=prompt,
                context_blocks=[],
            )
        except Exception:
            return fallback
        return self._normalize_conversation_title(title) or fallback

    @staticmethod
    def _normalize_conversation_title(value: str) -> str:
        title = re.sub(r"[\r\n\t]+", " ", value).strip().strip("\"'“”‘’")
        title = re.sub(r"\s+", " ", title)
        return (title[:16] or "新会话").rstrip("。.!！?")

    async def _generate_rag_llm_answer(
        self,
        *,
        tenant_id: str,
        message: str,
        sources: list[SourceReference],
        short_memory: Conversation,
        on_delta: AnswerDeltaCallback | None = None,
    ) -> str | None:
        """把知识库召回结果组装为 LLM 上下文，生成带来源约束的回答。"""

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
    def _serialize_tool_override(
        *,
        tenant_id: str,
        tool_name: str,
        default_quota: int,
        default_timeout: int,
        override: ToolOverride | None,
    ) -> dict[str, object]:
        return {
            "tool_name": tool_name,
            "tenant_id": tenant_id,
            "quota": override.quota if override and override.quota is not None else default_quota,
            "timeout": override.timeout if override and override.timeout is not None else default_timeout,
            "disabled": override.disabled if override else False,
            "overridden": override is not None,
            "default_quota": default_quota,
            "default_timeout": default_timeout,
        }

    @staticmethod
    def _serialize_mcp_server(server: McpServer) -> dict[str, object]:
        return {
            "server_id": server.server_id,
            "name": server.name,
            "transport": server.transport,
            "endpoint": server.endpoint,
            "auth_ref": server.auth_ref,
            "headers": dict(server.headers),
            "status": server.status,
        }

    @staticmethod
    def _serialize_mcp_server_for_executor(server: McpServer) -> dict[str, object]:
        payload = {
            "transport": server.transport,
            "endpoint": server.endpoint,
            "headers": dict(server.headers),
            "status": server.status,
        }
        if server.auth_ref:
            payload["auth_ref"] = server.auth_ref
        return payload

    @staticmethod
    def _serialize_output_guard_rule(rule: OutputGuardRule, events: list[dict[str, object]]) -> dict[str, object]:
        recent_triggers = sum(
            1
            for item in events
            if item.get("category") == "safety" or item.get("severity") in {"critical", "high"}
        )
        return {
            "rule_id": rule.rule_id,
            "package_id": rule.package_id,
            "pattern": rule.pattern,
            "action": rule.action,
            "source": rule.source,
            "enabled": rule.enabled,
            "recent_triggers": recent_triggers,
        }

    @staticmethod
    def _serialize_release_plan(release: ReleasePlan) -> dict[str, object]:
        return {
            "release_id": release.release_id,
            "package_id": release.package_id,
            "package_name": release.package_name,
            "skill": release.skill,
            "version": release.version,
            "status": release.status,
            "rollout_percent": release.rollout_percent,
            "metric_delta": release.metric_delta,
            "started_at": release.started_at.strftime("%Y-%m-%d %H:%M"),
        }

    @staticmethod
    def _default_output_guard_rules() -> list[OutputGuardRule]:
        return [
            OutputGuardRule(
                rule_id="mfg.output_guard.power_off",
                package_id="industry.mfg",
                pattern="断电|停机|挂牌上锁",
                action="prepend_safety_warning",
                source="industry.mfg",
            ),
            OutputGuardRule(
                rule_id="mfg.output_guard.pressure_release",
                package_id="industry.mfg",
                pattern="泄压|有限空间|登高",
                action="block_or_escalate",
                source="industry.mfg",
            ),
        ]

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
