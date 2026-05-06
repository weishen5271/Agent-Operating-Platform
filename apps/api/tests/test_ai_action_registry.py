from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.runtime.ai_action_registry import AIActionRegistry
from agent_platform.runtime.package_loader import PackageLoader
from agent_platform.runtime.data_input import DataInput
from agent_platform.runtime.registry import CapabilityRegistry


def test_mfg_maintenance_action_is_declared() -> None:
    """示例业务包必须暴露设备故障分析 action，供 AI 工作台动态渲染入口。"""

    repo_root = Path(__file__).resolve().parents[3]
    loader = PackageLoader(
        catalog_dir=repo_root / "packages" / "catalog",
        installed_dir=repo_root / "example" / "bundles",
    )
    registry = AIActionRegistry(loader=loader)

    action = registry.get("industry.mfg_maintenance", "equipment_fault_analysis")

    assert action is not None
    assert action.object_types == ["equipment"]
    assert action.skill == "fault_triage"
    assert action.required_inputs == ["equipment_id"]
    assert action.data_input_modes == ["platform_pull"]


def test_default_registry_loads_installed_mfg_action() -> None:
    """运行时默认安装目录必须包含 AI Action，否则 AI 工作台不会渲染执行表单。"""

    registry = AIActionRegistry()

    action = registry.get("industry.mfg_maintenance", "equipment_fault_analysis")

    assert action is not None
    assert action.object_types == ["equipment"]


def test_default_registry_loads_equipment_lookup_declaration() -> None:
    """业务对象必须声明 lookup capability，供 AI 工作台执行前校验对象 ID。"""

    registry = AIActionRegistry()

    business_object = registry.get_business_object("industry.mfg_maintenance", "equipment")

    assert business_object is not None
    assert business_object["id_field"] == "equipment_id"
    assert business_object["lookup_capability"] == "equipment.lookup"


def test_default_capability_registry_loads_scada_as_http_executor() -> None:
    """SCADA 报警查询应通过 HTTP executor 接入，不能继续停留在 stub。"""

    registry = CapabilityRegistry()
    capability = registry.get("scada.alarm_query")
    plugin_name = registry.get_plugin_name_for_capability("scada.alarm_query")
    plugin = registry.get_plugin(plugin_name)

    assert capability.side_effect_level == "read"
    assert plugin.__class__.__name__ == "HttpExecutor"
    assert plugin_name == "scada.alarm_query"


def test_data_input_rejects_undeclared_mode() -> None:
    """host_context 只有在 action 声明支持时才可进入运行链路。"""

    with pytest.raises(ValueError, match="not allowed"):
        DataInput(mode="host_context").validate(["platform_pull"])
