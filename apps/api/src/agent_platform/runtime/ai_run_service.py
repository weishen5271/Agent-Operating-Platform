from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from agent_platform.domain.models import (
    AIRun,
    BusinessOutput,
    TraceRecord,
    TraceStep,
    UserContext,
    utc_timestamp_ms,
)
from agent_platform.infrastructure.repositories import (
    AIRunRepository,
    BusinessOutputRepository,
    PluginConfigRepository,
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

    async def list_actions(
        self,
        *,
        tenant_id: str,
        user_id: str,
        package_id: str | None = None,
    ) -> dict[str, object]:
        await self._require_context(tenant_id, user_id)
        return {"items": [asdict(item) for item in self._actions.list_actions(package_id)]}

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
                load_tenant_config=self._load_tenant_config(context.tenant_id),
                add_step=add_step,
            )
            result = await executor.execute(skill, run.inputs)
            trace.answer = str(result.outputs.get("summary") or "")
            trace.sources = list(result.sources)
            saved_trace = await self._traces.save(trace)

            output = BusinessOutput(
                output_id=f"out-{uuid4().hex[:12]}",
                tenant_id=context.tenant_id,
                package_id=package_id,
                type="recommendation",
                title=f"{action.label} - {object_id}",
                status="draft",
                payload=self._structured_payload(result.outputs),
                citations=[item.id for item in result.sources],
                trace_id=saved_trace.trace_id,
                run_id=run.run_id,
                action_id=action_id,
                object_type=object_type,
                object_id=object_id,
                summary=str(result.outputs.get("summary") or ""),
                created_by=context.user_id,
            )
            saved_output = await self._business_outputs.create(output)

            run.status = "succeeded"
            run.trace_id = saved_trace.trace_id
            run.output_ids = [saved_output.output_id]
            run.updated_at = utc_timestamp_ms()
            run = await self._runs.update(run)
            return {"run": asdict(run), "output": asdict(saved_output), "trace_id": saved_trace.trace_id}
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

    def _load_tenant_config(self, tenant_id: str):
        async def load(capability_name: str) -> dict[str, object]:
            # Capability 到 plugin_name 的映射继续复用 registry，避免业务包硬编码租户配置。
            plugin_name = self._registry.get_plugin_name_for_capability(capability_name)
            config = await self._plugin_configs.get(tenant_id, plugin_name)
            return dict(config.config) if config else {}

        return load

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

        return {
            "facts": outputs.get("workorders", []),
            "citations": outputs.get("knowledge_matches", []),
            "reasoning_summary": outputs.get("summary", ""),
            "recommendations": outputs.get("recommendations", []),
            "action_plan": outputs.get("action_plan", []),
            "draft_action": outputs.get("draft_action"),
            "raw": outputs,
        }
