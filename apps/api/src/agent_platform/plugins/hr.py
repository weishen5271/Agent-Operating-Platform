from __future__ import annotations

from agent_platform.domain.models import CapabilityDefinition, SourceReference
from agent_platform.plugins.base import CapabilityPlugin


class HRLeaveBalancePlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="hr.leave.balance.query",
        description="查询员工剩余年假天数。",
        risk_level="low",
        side_effect_level="read",
        required_scope="hr:read",
        input_schema={"required": ["employee_name"]},
        output_schema={"required": ["days_remaining", "summary"]},
    )

    def __init__(self) -> None:
        self._balances = {
            "张三": 7,
            "李四": 10,
            "王五": 4,
        }

    def invoke(self, payload: dict[str, str]) -> dict[str, object]:
        employee_name = payload["employee_name"]
        days_remaining = self._balances.get(employee_name, 5)
        return {
            "days_remaining": days_remaining,
            "summary": f"{employee_name} 当前剩余年假 {days_remaining} 天。",
            "sources": [
                SourceReference(
                    id="hr-policy-leave",
                    title="HR 系统假期台账",
                    snippet="示例数据源：当前环境使用内置演示台账。",
                    source_type="plugin",
                )
            ],
        }
