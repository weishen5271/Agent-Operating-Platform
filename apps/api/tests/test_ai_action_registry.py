from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.runtime.ai_action_registry import AIActionRegistry
from agent_platform.runtime.package_loader import PackageLoader
from agent_platform.runtime.data_input import DataInput


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


def test_data_input_rejects_undeclared_mode() -> None:
    """host_context 只有在 action 声明支持时才可进入运行链路。"""

    with pytest.raises(ValueError, match="not allowed"):
        DataInput(mode="host_context").validate(["platform_pull"])
