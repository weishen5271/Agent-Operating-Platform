from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import re
from uuid import uuid4

from agent_platform.domain.models import (
    AIRun,
    BusinessOutput,
    DraftAction,
    OutputGuardRule,
    SecurityEvent,
    TraceRecord,
    TraceStep,
    UserContext,
    utc_timestamp_ms,
)
from agent_platform.infrastructure.repositories import (
    AIRunRepository,
    BusinessOutputRepository,
    DraftRepository,
    OutputGuardRuleRepository,
    PluginConfigRepository,
    SecurityRepository,
    TenantRepository,
    TraceRepository,
    UserRepository,
)
from agent_platform.runtime.ai_action_registry import AIActionRegistry
from agent_platform.runtime.data_input import DataInput
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_executor import SkillExecutor
from agent_platform.runtime.skill_registry import SkillRegistry, ToolRegistry


class AIRunService:
    """结构化 AI Action 执行入口，复用现有 Skill / Capability / Trace / Output 能力。"""

    def __init__(
        self,
        *,
        actions: AIActionRegistry,
        runs: AIRunRepository,
        registry: CapabilityRegistry,
        skills: SkillRegistry,
        tools: ToolRegistry,
        traces: TraceRepository,
        tenants: TenantRepository,
        users: UserRepository,
        plugin_configs: PluginConfigRepository,
        business_outputs: BusinessOutputRepository,
        output_guard_rules: OutputGuardRuleRepository | None = None,
        drafts: DraftRepository | None = None,
        security_events: SecurityRepository | None = None,
    ) -> None:
        self._actions = actions
        self._runs = runs
        self._registry = registry
        self._skills = skills
        self._tools = tools
        self._traces = traces
        self._tenants = tenants
        self._users = users
        self._plugin_configs = plugin_configs
        self._business_outputs = business_outputs
        self._output_guard_rules = output_guard_rules
        self._drafts = drafts
        self._security_events = security_events

    async def list_actions(
        self,
        *,
        tenant_id: str,
        user_id: str,
        package_id: str | None = None,
    ) -> dict[str, object]:
        await self._require_context(tenant_id, user_id)
        return {"items": [asdict(item) for item in self._actions.list_actions(package_id)]}

    async def list_business_objects(
        self,
        *,
        tenant_id: str,
        user_id: str,
        package_id: str | None = None,
    ) -> dict[str, object]:
        await self._require_context(tenant_id, user_id)
        return {"items": self._actions.list_business_objects(package_id)}

    async def lookup_business_object(
        self,
        *,
        tenant_id: str,
        user_id: str,
        package_id: str,
        object_type: str,
        object_id: str,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id, user_id)
        declaration = self._actions.get_business_object(package_id, object_type)
        if declaration is None:
            raise ValueError("Business object is not declared by package")
        lookup_capability = str(declaration.get("lookup_capability") or "").strip()
        if not lookup_capability:
            raise ValueError("Business object lookup capability is not configured")
        capability = self._registry.get(lookup_capability)
        if capability.side_effect_level != "read":
            raise ValueError("Business object lookup capability must be read-only")
        self._ensure_scope(context=context, required_scope=capability.required_scope)
        id_field = str(declaration.get("id_field") or "object_id").strip() or "object_id"
        payload = {id_field: object_id.strip(), "query": object_id.strip()}
        config = await self._load_tenant_config(context.tenant_id)(lookup_capability)
        result = self._registry.invoke(lookup_capability, payload, tenant_config=config)
        return {
            "package_id": package_id,
            "object_type": object_type,
            "object_id": object_id,
            "lookup_capability": lookup_capability,
            "result": _jsonable(result),
        }

    async def list_runs(
        self,
        *,
        tenant_id: str,
        user_id: str,
        limit: int = 20,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id, user_id)
        runs = await self._runs.list_recent(context.tenant_id, limit=limit)
        return {"items": [asdict(item) for item in runs]}

    async def get_run(self, *, tenant_id: str, user_id: str, run_id: str) -> dict[str, object]:
        context = await self._require_context(tenant_id, user_id)
        run = await self._runs.get(context.tenant_id, run_id)
        if run is None:
            raise ValueError("AI run not found")
        return asdict(run)

    async def get_run_trace(self, *, tenant_id: str, user_id: str, run_id: str) -> dict[str, object]:
        context = await self._require_context(tenant_id, user_id)
        run = await self._runs.get(context.tenant_id, run_id)
        if run is None or not run.trace_id:
            raise ValueError("AI run trace not found")
        trace = await self._traces.get(run.trace_id)
        if trace is None or trace.tenant_id != context.tenant_id:
            raise ValueError("AI run trace not found")
        return asdict(trace)

    async def run_action(
        self,
        *,
        tenant_id: str,
        user_id: str,
        package_id: str,
        action_id: str,
        source: str,
        object_type: str,
        object_id: str,
        inputs: dict[str, object],
        data_input: DataInput,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id, user_id)
        action = self._actions.get(package_id, action_id)
        if action is None:
            raise ValueError("AI action not found")
        if object_type not in action.object_types:
            raise ValueError("Object type is not supported by action")
        data_input.validate(action.data_input_modes)

        run_inputs = self._build_skill_inputs(object_type=object_type, object_id=object_id, inputs=inputs)
        self._validate_required_inputs(action.required_inputs, run_inputs)
        now_ms = utc_timestamp_ms()
        run = AIRun(
            run_id=f"run-{uuid4().hex[:12]}",
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            package_id=package_id,
            action_id=action_id,
            source=source,
            object_type=object_type,
            object_id=object_id,
            inputs=run_inputs,
            data_input_mode=data_input.mode,
            status="running",
            created_at=now_ms,
            updated_at=now_ms,
        )
        run = await self._runs.create(run)

        trace = TraceRecord(
            trace_id=f"trace-{uuid4().hex[:12]}",
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            intent=action_id,
            strategy="ai_action",
            message=f"{action.label}: {object_type}/{object_id}",
        )

        async def add_step(step: TraceStep) -> None:
            """SkillExecutor 回调写入 Trace step，保持 Action 执行链路可审计。"""

            trace.steps.append(step)

        try:
            skill = self._skills.get(f"{package_id}::{action.skill}") or self._skills.get(action.skill)
            if skill is None:
                raise ValueError(f"Skill not found: {action.skill}")

            executor = SkillExecutor(
                registry=self._registry,
                tools=self._tools,
                load_tenant_config=self._load_tenant_config(context.tenant_id, context=context),
                add_step=add_step,
            )
            result = await executor.execute(skill, run.inputs)
            payload = self._structured_payload(result.outputs)
            guard_result = await self._apply_output_guard(context.tenant_id, payload)
            payload = guard_result["payload"]
            if guard_result["matched"]:
                trace.steps.append(
                    TraceStep(
                        name="output_guard",
                        status="completed",
                        summary=guard_result["summary"],
                        node_type="guard",
                    )
                )
            trace.answer = str(payload.get("reasoning_summary") or result.outputs.get("summary") or "")
            trace.sources = list(result.sources)
            saved_trace = await self._traces.save(trace)

            output = BusinessOutput(
                output_id=f"out-{uuid4().hex[:12]}",
                tenant_id=context.tenant_id,
                package_id=package_id,
                type="recommendation",
                title=f"{action.label} - {object_id}",
                status="draft",
                payload=payload,
                citations=[item.id for item in result.sources],
                trace_id=saved_trace.trace_id,
                run_id=run.run_id,
                action_id=action_id,
                object_type=object_type,
                object_id=object_id,
                summary=str(payload.get("reasoning_summary") or ""),
                created_by=context.user_id,
            )
            saved_output = await self._business_outputs.create(output)

            run.status = "succeeded"
            run.trace_id = saved_trace.trace_id
            run.output_ids = [saved_output.output_id]
            if self._requires_draft(action):
                draft = await self._create_action_draft(
                    context=context,
                    action=action,
                    run=run,
                    output=saved_output,
                    data_input=data_input,
                )
                run.draft_id = draft.draft_id
            run.updated_at = utc_timestamp_ms()
            run = await self._runs.update(run)
            response = {"run": asdict(run), "output": asdict(saved_output), "trace_id": saved_trace.trace_id}
            if run.draft_id:
                response["draft_action"] = self._serialize_draft(draft)
            return response
        except Exception as exc:
            trace.steps.append(
                TraceStep(
                    name="ai_action_failed",
                    status="failed",
                    summary=str(exc),
                    node_type="runtime",
                )
            )
            saved_trace = await self._traces.save(trace)
            run.status = "failed"
            run.trace_id = saved_trace.trace_id
            run.error_message = str(exc)
            run.updated_at = utc_timestamp_ms()
            run = await self._runs.update(run)
            return {"run": asdict(run)}

    async def _require_context(self, tenant_id: str, user_id: str) -> UserContext:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None or not tenant.active:
            raise ValueError("Tenant not found or inactive")
        user = await self._users.get(tenant_id, user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    def _load_tenant_config(self, tenant_id: str, *, context: UserContext | None = None):
        async def load(capability_name: str) -> dict[str, object]:
            # Capability 到 plugin_name 的映射继续复用 registry，避免业务包硬编码租户配置。
            if context is not None:
                capability = self._registry.get(capability_name)
                self._ensure_scope(context=context, required_scope=capability.required_scope)
            plugin_name = self._registry.get_plugin_name_for_capability(capability_name)
            config = await self._plugin_configs.get(tenant_id, plugin_name)
            return dict(config.config) if config else {}

        return load

    @staticmethod
    def _ensure_scope(*, context: UserContext, required_scope: str) -> None:
        if required_scope and required_scope not in context.scopes:
            raise PermissionError(f"Missing scope: {required_scope}")

    @staticmethod
    def _requires_draft(action) -> bool:
        return bool(action.requires_confirmation) or action.risk_level in {"medium", "high", "critical"}

    async def _create_action_draft(
        self,
        *,
        context: UserContext,
        action,
        run: AIRun,
        output: BusinessOutput,
        data_input: DataInput,
    ) -> DraftAction:
        if self._drafts is None:
            raise RuntimeError("Draft repository is not configured")
        draft = DraftAction(
            draft_id=f"draft-{uuid4().hex[:12]}",
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            capability_name=f"ai_action:{action.package_id}:{action.id}",
            title=f"{action.label} 确认",
            risk_level=action.risk_level,
            status="awaiting_confirmation",
            payload={
                "run_id": run.run_id,
                "output_id": output.output_id,
                "package_id": action.package_id,
                "action_id": action.id,
                "object": {
                    "object_type": run.object_type,
                    "object_id": run.object_id,
                },
                "inputs": run.inputs,
                "data_input": {
                    "mode": data_input.mode,
                    "context": data_input.context,
                },
            },
            summary=output.summary or f"{action.label} 已生成待确认业务成果。",
            approval_hint="请复核 AI Run、Trace、外部事实和知识引用后再确认。",
        )
        return await self._drafts.save(draft)

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

    async def _apply_output_guard(self, tenant_id: str, payload: dict[str, object]) -> dict[str, object]:
        if self._output_guard_rules is None:
            return {"payload": payload, "warnings": [], "summary": "OutputGuard 未配置，跳过输出治理。", "matched": False}
        rules = await self._output_guard_rules.list_enabled()
        answer = self._guard_text(payload)
        if not answer or not rules:
            guarded = dict(payload)
            guarded["output_guard"] = {
                "warnings": [],
                "summary": "输出脱敏与内容审查完成，未命中红线规则。",
            }
            return {"payload": guarded, "warnings": [], "summary": guarded["output_guard"]["summary"], "matched": False}

        guarded_answer = answer
        warnings: list[str] = []
        matched_rules: list[OutputGuardRule] = []
        blocked = False
        for rule in rules:
            if not rule.enabled or not self._output_guard_matches(rule.pattern, guarded_answer):
                continue
            matched_rules.append(rule)
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
                guarded_answer = "该回答命中安全红线，已停止输出具体操作建议。请联系安全治理组或具备资质的现场负责人复核。"
                blocked = True
                warnings.append(f"OutputGuard 已拦截回答：{rule.rule_id}")
                break

        for rule in matched_rules:
            if self._security_events is not None:
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

        summary = (
            "输出脱敏与内容审查完成，未命中红线规则。"
            if not matched_rules
            else f"输出治理命中 {len(matched_rules)} 条红线规则：{', '.join(rule.rule_id for rule in matched_rules)}。"
        )
        guarded_payload = dict(payload)
        if matched_rules:
            guarded_payload["reasoning_summary"] = guarded_answer
            if blocked:
                guarded_payload["recommendations"] = []
                guarded_payload["action_plan"] = []
        guarded_payload["output_guard"] = {"warnings": warnings, "summary": summary}
        return {"payload": guarded_payload, "warnings": warnings, "summary": summary, "matched": bool(matched_rules)}

    @staticmethod
    def _guard_text(payload: dict[str, object]) -> str:
        return json.dumps(
            {
                "reasoning_summary": payload.get("reasoning_summary"),
                "recommendations": payload.get("recommendations"),
                "action_plan": payload.get("action_plan"),
            },
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _output_guard_matches(pattern: str, answer: str) -> bool:
        if not pattern:
            return False
        try:
            return re.search(pattern, answer, flags=re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            return pattern.lower() in answer.lower()

    @staticmethod
    def _mask_sensitive_output(answer: str) -> str:
        masked = re.sub(r"\b1[3-9]\d{3}(\d{4})\d{4}\b", r"1****\1****", answer)
        masked = re.sub(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[^'\"\s,;}]+", r"\1=***", masked)
        return masked

    @staticmethod
    def _summarize_guarded_answer(answer: str) -> str:
        text = re.sub(r"\s+", " ", answer).strip()
        return text[:240] + ("..." if len(text) > 240 else "")

    @staticmethod
    def _build_skill_inputs(
        *,
        object_type: str,
        object_id: str,
        inputs: dict[str, object],
    ) -> dict[str, object]:
        # Phase 1 只把对象 ID 映射到 action 输入，不保存外部对象快照。
        merged = dict(inputs)
        if object_type == "equipment":
            merged.setdefault("equipment_id", object_id)
        merged.setdefault("query", " ".join(str(item) for item in [object_id, merged.get("fault_code", "")] if item))
        return merged

    @staticmethod
    def _validate_required_inputs(required_inputs: list[str], inputs: dict[str, object]) -> None:
        missing = [item for item in required_inputs if inputs.get(item) in ("", None)]
        if missing:
            raise ValueError(f"Missing required action inputs: {', '.join(missing)}")

    @staticmethod
    def _structured_payload(outputs: dict[str, object]) -> dict[str, object]:
        """把 Skill 输出收敛成可治理结构，避免只保存一段自然语言。"""

        facts = [_jsonable(item) for item in _as_list(outputs.get("workorders"))]
        citations = [_jsonable(item) for item in _as_list(outputs.get("knowledge_matches"))]
        alarms = [_jsonable(item) for item in _as_list(outputs.get("alarms"))]
        warnings = AIRunService._collect_runtime_warnings(outputs)
        reasoning_summary = str(outputs.get("summary") or "")
        recommendations = _as_list(outputs.get("recommendations"))
        action_plan = _as_list(outputs.get("action_plan"))
        if not recommendations:
            recommendations = AIRunService._derive_recommendations(
                facts=facts,
                citations=citations,
                alarms=alarms,
                warnings=warnings,
            )
        if not action_plan:
            action_plan = AIRunService._derive_action_plan(
                facts=facts,
                citations=citations,
                alarms=alarms,
                warnings=warnings,
            )

        return {
            "facts": facts,
            "citations": citations,
            "reasoning_summary": reasoning_summary,
            "recommendations": recommendations,
            "action_plan": action_plan,
            "draft_action": outputs.get("draft_action"),
            "runtime_warnings": warnings,
            "alarms": alarms,
            "raw": _jsonable(outputs),
        }

    @staticmethod
    def _derive_recommendations(
        *,
        facts: list[object],
        citations: list[object],
        alarms: list[object],
        warnings: list[str],
    ) -> list[dict[str, object]]:
        recommendations: list[dict[str, object]] = []
        if facts:
            recommendations.append(
                {
                    "type": "fact_based",
                    "text": "优先复核历史工单中与当前设备和故障码匹配的处置记录。",
                    "evidence_count": len(facts),
                }
            )
        if citations:
            recommendations.append(
                {
                    "type": "knowledge_based",
                    "text": "结合知识库命中的 SOP、故障代码或维修记录确认处置步骤。",
                    "evidence_count": len(citations),
                }
            )
        if alarms:
            recommendations.append(
                {
                    "type": "alarm_based",
                    "text": "核对报警记录的时间、等级和复现频次，再决定是否升级现场排查。",
                    "evidence_count": len(alarms),
                }
            )
        if warnings:
            recommendations.append(
                {
                    "type": "runtime_warning",
                    "text": "存在 stub 或配置缺失等运行提示，结论需在真实外部系统返回后再确认。",
                    "warnings": warnings,
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "type": "insufficient_evidence",
                    "text": "当前未取得可用事实或知识引用，请补充对象 ID、故障码或外部系统配置后重试。",
                    "evidence_count": 0,
                }
            )
        return recommendations

    @staticmethod
    def _derive_action_plan(
        *,
        facts: list[object],
        citations: list[object],
        alarms: list[object],
        warnings: list[str],
    ) -> list[dict[str, object]]:
        plan: list[dict[str, object]] = [
            {
                "step": 1,
                "title": "核对输入与数据来源",
                "description": "确认业务对象 ID、故障码、外部系统配置和数据来源标识。",
            }
        ]
        if facts or alarms:
            plan.append(
                {
                    "step": len(plan) + 1,
                    "title": "复核外部系统事实",
                    "description": "基于历史工单和报警记录确认故障是否重复出现，以及最近一次处置结果。",
                }
            )
        if citations:
            plan.append(
                {
                    "step": len(plan) + 1,
                    "title": "对照知识库步骤",
                    "description": "按命中的 SOP 或故障代码说明执行人工复核，避免直接采纳未核实建议。",
                }
            )
        if warnings:
            plan.append(
                {
                    "step": len(plan) + 1,
                    "title": "消除运行提示",
                    "description": "优先补齐真实 executor 配置或替换 stub，再将分析结果用于现场处置。",
                }
            )
        plan.append(
            {
                "step": len(plan) + 1,
                "title": "沉淀处理结果",
                "description": "完成复核后将有效结论保存为业务成果，必要时发起审批草稿。",
            }
        )
        return plan

    @staticmethod
    def _collect_runtime_warnings(outputs: dict[str, object]) -> list[str]:
        warnings: list[str] = []
        step_results = outputs.get("step_results")
        if not isinstance(step_results, dict):
            return warnings
        for step_id, result in step_results.items():
            if not isinstance(result, dict):
                continue
            if result.get("stub"):
                capability = str(result.get("capability") or "").strip()
                warnings.append(f"{step_id}: {capability or 'capability'} 当前返回 stub 占位结果")
        return warnings


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
