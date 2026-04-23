from __future__ import annotations

from dataclasses import asdict
import re
from uuid import uuid4

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import (
    CapabilityDefinition,
    Conversation,
    DraftAction,
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
    LLMConfigRepository,
    SecurityRepository,
    TenantRepository,
    TraceRepository,
    UserRepository,
)
from agent_platform.runtime.registry import CapabilityRegistry


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
                if capability.required_scope in context.scopes
            ],
            "recent_conversations": [
                {
                    "conversation_id": conversation.conversation_id,
                    "title": conversation.title,
                    "updated_at": conversation.updated_at.isoformat(),
                }
                for conversation in await self._conversations.list_recent(context.tenant_id)
            ],
        }

    async def complete(
        self,
        message: str,
        conversation_id: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
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
        trace.steps.append(TraceStep(name="received", status="completed", summary="请求已进入 Supervisor。"))

        input_findings = self._inspect_input(message)
        trace.steps.append(
            TraceStep(
                name="input_guard",
                status="completed",
                summary="输入安全检查完成。" if not input_findings else f"输入安全检查完成，识别到 {', '.join(input_findings)}。",
            )
        )

        short_memory = await self._load_short_memory(context.tenant_id, conversation_id)
        long_memory_summary = await self._load_long_memory_summary(context.tenant_id)
        trace.steps.append(
            TraceStep(
                name="memory",
                status="completed",
                summary=(
                    f"已读取短期记忆 {len(short_memory.messages)} 条消息，"
                    f"长期知识摘要：{long_memory_summary}"
                ),
            )
        )

        intent = self._classify_intent(message)
        strategy = "plan_execute" if intent in {"hr_query", "procurement_draft"} else "direct_answer"
        trace.intent = intent
        trace.strategy = strategy
        trace.steps.append(TraceStep(name="classified", status="completed", summary=f"识别意图为 {intent}，策略为 {strategy}。"))

        candidate_capabilities = self._select_candidate_capabilities(context)
        trace.steps.append(
            TraceStep(
                name="capability_candidates",
                status="completed",
                summary=f"按 scope 筛选出 {len(candidate_capabilities)} 个候选 capability。",
            )
        )

        sources: list[SourceReference] = []
        capability = None
        if intent == "general_chat":
            self._ensure_scope(context=context, required_scope="chat:read")
            self._check_quota(message)
            trace.steps.append(TraceStep(name="planned", status="completed", summary="命中模型直答链路: model.direct_chat。"))
            trace.steps.append(TraceStep(name="risk", status="completed", summary="风险等级 low，自主度上限：auto_execute。"))
            trace.steps.append(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。"))
            answer, used_model = await self._generate_direct_llm_answer(
                tenant_id=context.tenant_id,
                message=message,
            )
            trace.steps.append(TraceStep(name="executed", status="completed", summary="model.direct_chat 执行完成。"))
            trace.steps.append(
                TraceStep(
                    name="model",
                    status="completed" if used_model else "failed",
                    summary="已通过 OpenAI-compatible 模型生成日常对话回答。" if used_model else "LLM Runtime 未启用，无法生成日常对话回答。",
                )
            )
        else:
            capability_name, payload = self._plan(message, intent)
            if capability_name not in {item.name for item in candidate_capabilities}:
                raise PermissionError(f"Missing scope for capability: {capability_name}")
            trace.steps.append(TraceStep(name="planned", status="completed", summary=f"命中 capability: {capability_name}。"))
            capability = self._registry.get(capability_name)
            autonomy = self._evaluate_risk(capability)
            trace.steps.append(
                TraceStep(
                    name="risk",
                    status="completed",
                    summary=f"风险等级 {capability.risk_level}，自主度上限：{autonomy}。",
                )
            )
            self._ensure_scope(context=context, required_scope=capability.required_scope)
            self._check_quota(message)
            trace.steps.append(TraceStep(name="governance", status="completed", summary="权限与请求配额校验通过。"))

            if intent == "knowledge_query":
                result = await self._run_knowledge_search(context.tenant_id, payload["query"])
            else:
                result = self._registry.invoke(capability_name, payload)
            trace.steps.append(TraceStep(name="executed", status="completed", summary=self._execution_summary(capability_name, result)))

            answer, sources = self._compose_answer(intent, result)
            if intent == "knowledge_query":
                llm_answer = await self._generate_rag_llm_answer(
                    tenant_id=context.tenant_id,
                    message=message,
                    sources=sources,
                )
                if llm_answer:
                    answer = llm_answer
                    trace.steps.append(TraceStep(name="model", status="completed", summary="已通过 OpenAI-compatible 模型生成最终回答。"))
                elif not sources:
                    trace.steps.append(TraceStep(name="model", status="completed", summary="未命中检索来源，跳过模型生成。"))
                else:
                    trace.steps.append(TraceStep(name="model", status="failed", summary="LLM Runtime 未启用，保留检索拼装回答。"))
        if intent != "knowledge_query" and intent != "general_chat":
            trace.steps.append(TraceStep(name="model", status="completed", summary="当前能力无需模型生成。"))
        answer = self._review_output(answer)
        trace.steps.append(TraceStep(name="output_guard", status="completed", summary="输出脱敏与内容审查完成。"))
        trace.answer = answer
        trace.sources = sources
        trace.steps.append(TraceStep(name="completed", status="completed", summary="响应已组装并返回。"))
        await self._traces.save(trace)

        conversation = await self._conversations.append_message(
            tenant_id=context.tenant_id,
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
                {
                    "id": source.id,
                    "title": source.title,
                    "snippet": source.snippet,
                    "source_type": source.source_type,
                }
                for source in sources
            ],
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

    async def get_trace(self, trace_id: str) -> TraceRecord | None:
        return await self._traces.get(trace_id)

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
        capabilities = [item for item in self._registry.list_capabilities() if item.required_scope in context.scopes]
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
        return {
            "tenants": [asdict(item) for item in await self._tenants.list_all()],
            "roles": [
                {"name": "platform_admin", "scope_count": 6, "member_count": 12},
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

    async def list_knowledge_sources(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_scope(context=context, required_scope="admin:read")
        return {"sources": [asdict(item) for item in await self._knowledge_sources.list_recent(context.tenant_id)]}

    async def ingest_knowledge_source(
        self,
        *,
        name: str,
        content: str,
        source_type: str,
        owner: str,
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
        )
        return {"source": asdict(source)}

    async def get_llm_runtime(self, tenant_id: str | None = None) -> dict[str, object]:
        config, _api_key = await self._llm_config.get(tenant_id=tenant_id)
        return {
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "api_key_configured": config.api_key_configured,
            "temperature": config.temperature,
            "system_prompt": config.system_prompt,
            "enabled": config.enabled,
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
    ) -> dict[str, object]:
        config, _ = await self._llm_config.create_or_update_for_tenant(
            tenant_id=tenant_id,
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        return {
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "api_key_configured": config.api_key_configured,
            "temperature": config.temperature,
            "system_prompt": config.system_prompt,
            "enabled": config.enabled,
        }

    # Tenant CRUD
    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        package: str,
        environment: str,
        budget: str,
    ) -> TenantProfile:
        tenant = TenantProfile(
            tenant_id=tenant_id,
            name=name,
            package=package,
            environment=environment,
            budget=budget,
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
    ) -> TenantProfile:
        tenant = TenantProfile(
            tenant_id=tenant_id,
            name=name,
            package=package,
            environment=environment,
            budget=budget,
            active=active,
        )
        return await self._tenants.update(tenant)

    async def delete_tenant(self, tenant_id: str) -> bool:
        return await self._tenants.delete(tenant_id)

    # User CRUD
    async def get_user(self, tenant_id: str, user_id: str) -> UserContext | None:
        return await self._users.get(tenant_id=tenant_id, user_id=user_id)

    async def list_tenant_users(self, tenant_id: str) -> list[UserContext]:
        return await self._users.list_by_tenant(tenant_id)

    async def create_user(
        self,
        tenant_id: str,
        user_id: str,
        role: str,
        scopes: list[str],
        password_hash: str = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4grwcuhVHhphnetC",
    ) -> UserContext:
        user = UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            scopes=scopes,
        )
        return await self._users.create(user, password_hash)

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
    def _classify_intent(message: str) -> str:
        if "采购" in message or "审批草稿" in message or "草稿" in message:
            return "procurement_draft"
        if "年假" in message or "假期" in message:
            return "hr_query"
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
        return "knowledge.search", {"query": message}

    async def _run_knowledge_search(self, tenant_id: str, query: str) -> dict[str, object]:
        if not hasattr(self._knowledge_sources, "search"):
            return self._registry.invoke("knowledge.search", {"query": query})
        search_result = await self._knowledge_sources.search(tenant_id=tenant_id, query=query, top_k=3)
        summary = (
            "已从已发布知识切片中整理出与你问题最相关的要点。"
            if search_result.matches
            else "未在当前已发布知识源中检索到相关内容。"
        )
        return {
            "summary": summary,
            "matches": search_result.matches,
            "retrieval": {
                "backend": search_result.backend,
                "query": search_result.query,
                "matched": bool(search_result.matches),
                "candidate_count": search_result.candidate_count,
                "match_count": search_result.match_count,
                "keyword_match_count": search_result.keyword_match_count,
                "vector_match_count": search_result.vector_match_count,
            },
        }

    @staticmethod
    def _compose_answer(intent: str, result: dict[str, object]) -> tuple[str, list[SourceReference]]:
        if intent == "procurement_draft":
            answer = f"{result['summary']}\n{result['approval_hint']}"
            return answer, []
        if intent == "hr_query":
            sources = result["sources"]
            answer = f"{result['summary']} 数据来源为 HR 示例插件。"
            return answer, list(sources)

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

    async def _load_short_memory(self, tenant_id: str, conversation_id: str | None) -> Conversation:
        if conversation_id is None:
            return Conversation(conversation_id="", title="新会话", tenant_id=tenant_id)
        conversation = await self._conversations.get(tenant_id, conversation_id)
        if conversation is None:
            return Conversation(conversation_id=conversation_id, title="新会话", tenant_id=tenant_id)
        return conversation

    async def _load_long_memory_summary(self, tenant_id: str) -> str:
        sources = await self._knowledge_sources.list_recent(tenant_id)
        active_sources = [item for item in sources if item.status == "运行中"]
        if not active_sources:
            return "当前租户暂无运行中的知识源"
        names = "、".join(item.name for item in active_sources[:3])
        return f"{len(active_sources)} 个运行中知识源（{names}）"

    def _select_candidate_capabilities(self, context: UserContext) -> list[CapabilityDefinition]:
        return [
            capability
            for capability in self._registry.list_capabilities()
            if capability.enabled and capability.required_scope in context.scopes
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

    async def _generate_direct_llm_answer(self, *, tenant_id: str, message: str) -> tuple[str, bool]:
        config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        if not config.enabled:
            return (
                "LLM Runtime 未启用，当前无法生成日常对话回答。请先在系统设置中配置 OpenAI-compatible base_url、model 和 api_key。",
                False,
            )
        answer = self._llm_client.complete(
            config=config,
            api_key=api_key,
            user_message=message,
            context_blocks=[],
        )
        return answer, True

    async def _generate_rag_llm_answer(
        self,
        *,
        tenant_id: str,
        message: str,
        sources: list[SourceReference],
    ) -> str | None:
        config, api_key = await self._llm_config.get(tenant_id=tenant_id)
        if not config.enabled or not sources:
            return None
        context_blocks = [f"{item.title}: {item.snippet}" for item in sources]
        return self._llm_client.complete(
            config=config,
            api_key=api_key,
            user_message=message,
            context_blocks=context_blocks,
        )

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

    async def _require_context(self, tenant_id: str | None, user_id: str | None) -> UserContext:
        resolved_tenant_id = tenant_id or settings.default_tenant_id
        resolved_user_id = user_id or settings.default_user_id
        context = await self._users.get(resolved_tenant_id, resolved_user_id)
        if context is None:
            raise ValueError("User context not found")
        return context

    @staticmethod
    def _ensure_scope(context: UserContext, required_scope: str) -> None:
        if required_scope not in context.scopes:
            raise PermissionError(f"Missing scope: {required_scope}")
