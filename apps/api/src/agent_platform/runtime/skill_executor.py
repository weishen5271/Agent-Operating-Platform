from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent_platform.domain.models import SkillDefinition, SourceReference, TraceStep
from agent_platform.plugins.executors.dsl import BindingContext, render_mapping
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_registry import ToolRegistry


TraceStepCallback = Callable[[TraceStep], Awaitable[None]]
TenantConfigLoader = Callable[[str], Awaitable[dict[str, object]]]


@dataclass(slots=True)
class SkillExecutionResult:
    outputs: dict[str, object]
    step_results: dict[str, object] = field(default_factory=dict)
    sources: list[SourceReference] = field(default_factory=list)


class SkillExecutor:
    """Execute declarative skill.steps without changing legacy skill behavior."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        tools: ToolRegistry,
        load_tenant_config: TenantConfigLoader,
        add_step: TraceStepCallback | None = None,
    ) -> None:
        self._registry = registry
        self._tools = tools
        self._load_tenant_config = load_tenant_config
        self._add_step = add_step

    async def execute(self, skill: SkillDefinition, inputs: dict[str, object]) -> SkillExecutionResult:
        if not skill.steps:
            raise ValueError(f"Skill has no steps: {skill.name}")
        step_results: dict[str, object] = {}
        sources: list[SourceReference] = []

        for raw_step in skill.steps:
            step_id = str(raw_step.get("id") or "").strip()
            if not step_id:
                raise ValueError("skill.steps[] missing id")
            if step_id in step_results:
                raise ValueError(f"Duplicate skill step id: {step_id}")
            ctx = BindingContext(
                inputs={
                    **inputs,
                    "inputs": inputs,
                    "steps": step_results,
                    "prev_step": next(reversed(step_results.values()), {}),
                },
                config={},
            )
            step_input = render_mapping(raw_step.get("input") or {}, ctx)
            if not isinstance(step_input, dict):
                raise ValueError(f"Skill step input must render to object: {step_id}")

            capability_name = str(raw_step.get("capability") or "").strip()
            tool_name = str(raw_step.get("tool") or "").strip()
            if capability_name and tool_name:
                raise ValueError(f"Skill step cannot define both capability and tool: {step_id}")
            if capability_name:
                result = await self._invoke_capability(
                    step_id=step_id,
                    capability_name=capability_name,
                    payload=step_input,
                )
            elif tool_name:
                result = await self._invoke_tool(
                    step_id=step_id,
                    tool_name=tool_name,
                    payload=step_input,
                )
            else:
                raise ValueError(f"Skill step must define capability or tool: {step_id}")
            step_results[step_id] = result
            sources.extend(self._extract_sources(result))

        output_ctx = BindingContext(
            inputs={
                **inputs,
                "inputs": inputs,
                "steps": step_results,
                "prev_step": next(reversed(step_results.values()), {}),
            },
            config={},
        )
        outputs = render_mapping(skill.outputs_mapping or {}, output_ctx)
        if not isinstance(outputs, dict):
            outputs = {"result": outputs}
        if not outputs:
            outputs = {"steps": step_results}
        outputs.setdefault("skill", skill.name)
        outputs.setdefault("step_results", step_results)
        outputs.setdefault("sources", sources)
        return SkillExecutionResult(outputs=outputs, step_results=step_results, sources=sources)

    async def _invoke_capability(
        self,
        *,
        step_id: str,
        capability_name: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        tenant_config = await self._load_tenant_config(capability_name)
        result = self._registry.invoke(capability_name, payload, tenant_config=tenant_config)
        if self._add_step is not None:
            await self._add_step(
                TraceStep(
                    name=f"skill_step:{step_id}",
                    status="completed",
                    summary=f"Skill step {step_id} 调用 capability {capability_name} 完成。",
                    node_type="capability",
                    ref=capability_name,
                    ref_source=self._registry.get(capability_name).source,
                )
            )
        return result

    async def _invoke_tool(
        self,
        *,
        step_id: str,
        tool_name: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        result = self._tools.invoke(tool_name, payload)
        if self._add_step is not None:
            tool = self._tools.get(tool_name)
            await self._add_step(
                TraceStep(
                    name=f"skill_step:{step_id}",
                    status="completed",
                    summary=f"Skill step {step_id} 调用 tool {tool_name} 完成。",
                    node_type="tool",
                    ref=tool_name,
                    ref_source=tool.source if tool else "_platform",
                    ref_version=tool.version if tool else None,
                )
            )
        return result

    @staticmethod
    def _extract_sources(result: dict[str, object]) -> list[SourceReference]:
        raw_sources = result.get("sources")
        if not isinstance(raw_sources, list):
            return []
        return [item for item in raw_sources if isinstance(item, SourceReference)]
