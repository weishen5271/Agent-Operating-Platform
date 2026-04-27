from __future__ import annotations

import asyncio
from typing import Any

from agent_platform.domain.models import CapabilityDefinition, SkillDefinition
from agent_platform.plugins.stub import StubPackagePlugin
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_executor import SkillExecutor
from agent_platform.runtime.skill_registry import ToolRegistry


class EmptyLoader:
    def list_packages(self) -> list[dict[str, Any]]:
        return []


def build_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry(loader=EmptyLoader())  # type: ignore[arg-type]
    capability = CapabilityDefinition(
        name="pkg.echo.lookup",
        description="Protocol-level skill executor test capability",
        risk_level="low",
        side_effect_level="read",
        required_scope="test:read",
        input_schema={"required": ["query"]},
        output_schema={"required": ["items"]},
        source="package",
        package_id="pkg.test_skill",
    )
    registry._package_plugins = {
        capability.name: StubPackagePlugin(
            capability,
            package_id="pkg.test_skill",
            plugin_name="pkg.echo",
        )
    }
    return registry


def test_skill_executor_runs_capability_and_tool_steps_with_output_mapping() -> None:
    registry = build_registry()
    tools = ToolRegistry()
    loaded_configs: list[str] = []
    trace_steps: list[str] = []

    async def load_tenant_config(capability_name: str) -> dict[str, object]:
        loaded_configs.append(capability_name)
        return {}

    async def add_step(step) -> None:
        trace_steps.append(step.name)

    skill = SkillDefinition(
        name="echo_skill",
        description="Test-only declarative skill",
        version="1.0.0",
        source="package",
        package_id="pkg.test_skill",
        steps=[
            {
                "id": "lookup",
                "capability": "pkg.echo.lookup",
                "input": {"query": "$inputs.query"},
            },
            {
                "id": "extract",
                "tool": "json_path",
                "input": {
                    "document": "$steps.lookup",
                    "path": "$inputs.path",
                },
            },
        ],
        outputs_mapping={
            "summary": "matched $steps.extract.match_count item(s)",
            "matches": "$steps.extract.matches",
            "lookup_echo": "$steps.lookup.echo_input.query",
        },
    )
    executor = SkillExecutor(
        registry=registry,
        tools=tools,
        load_tenant_config=load_tenant_config,
        add_step=add_step,
    )

    result = asyncio.run(executor.execute(skill, {"query": "alpha", "path": "$.items"}))

    assert result.outputs["summary"] == "matched 1 item(s)"
    assert result.outputs["matches"] == [[]]
    assert result.outputs["lookup_echo"] == "alpha"
    assert loaded_configs == ["pkg.echo.lookup"]
    assert trace_steps == ["skill_step:lookup", "skill_step:extract"]
    assert set(result.step_results) == {"lookup", "extract"}


def test_skill_executor_supports_prev_step_reference() -> None:
    registry = build_registry()
    tools = ToolRegistry()

    async def load_tenant_config(capability_name: str) -> dict[str, object]:
        return {}

    skill = SkillDefinition(
        name="prev_step_skill",
        description="Test-only prev_step skill",
        version="1.0.0",
        source="package",
        package_id="pkg.test_skill",
        steps=[
            {
                "id": "lookup",
                "capability": "pkg.echo.lookup",
                "input": {"query": "$inputs.query"},
            },
            {
                "id": "extract",
                "tool": "json_path",
                "input": {
                    "document": "$prev_step.echo_input",
                    "path": "$.query",
                },
            },
        ],
        outputs_mapping={"query": "$steps.extract.matches.0"},
    )
    executor = SkillExecutor(
        registry=registry,
        tools=tools,
        load_tenant_config=load_tenant_config,
    )

    result = asyncio.run(executor.execute(skill, {"query": "alpha"}))

    assert result.outputs["query"] == "alpha"
