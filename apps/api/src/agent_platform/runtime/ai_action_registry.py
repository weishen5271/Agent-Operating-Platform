from __future__ import annotations

from agent_platform.domain.models import AIActionDefinition
from agent_platform.runtime.package_loader import PackageLoader


class AIActionRegistry:
    """从业务包 manifest 中读取结构化 AI Action 声明。"""

    def __init__(self, loader: PackageLoader | None = None) -> None:
        self._loader = loader or PackageLoader.default()

    def list_actions(self, package_id: str | None = None) -> list[AIActionDefinition]:
        actions: list[AIActionDefinition] = []
        for package in self._loader.list_packages():
            current_package_id = str(package.get("package_id") or "")
            if package_id and current_package_id != package_id:
                continue
            for raw in package.get("ai_actions", []):
                if isinstance(raw, dict):
                    actions.append(self._normalize(raw, current_package_id))
        return actions

    def get(self, package_id: str, action_id: str) -> AIActionDefinition | None:
        for action in self.list_actions(package_id):
            if action.id == action_id:
                return action
        return None

    @staticmethod
    def _normalize(raw: dict[str, object], package_id: str) -> AIActionDefinition:
        """把 manifest 原始字典收敛成后端内部稳定契约。"""

        return AIActionDefinition(
            id=str(raw.get("id") or "").strip(),
            label=str(raw.get("label") or raw.get("id") or "").strip(),
            package_id=package_id,
            object_types=[str(item) for item in raw.get("object_types", []) if str(item).strip()],
            skill=str(raw.get("skill") or "").strip(),
            description=str(raw.get("description") or ""),
            required_inputs=[str(item) for item in raw.get("required_inputs", []) if str(item).strip()],
            optional_inputs=[str(item) for item in raw.get("optional_inputs", []) if str(item).strip()],
            outputs=[str(item) for item in raw.get("outputs", []) if str(item).strip()],
            risk_level=str(raw.get("risk_level") or "low"),
            requires_confirmation=bool(raw.get("requires_confirmation", False)),
            data_input_modes=[
                str(item) for item in raw.get("data_input_modes", []) if str(item).strip()
            ]
            or ["platform_pull"],
        )
