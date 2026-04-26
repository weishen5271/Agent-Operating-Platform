from __future__ import annotations

from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.base import CapabilityPlugin


class ProcurementDraftPlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="workflow.procurement.request.create",
        description="生成采购申请草稿，待用户确认后执行。",
        risk_level="high",
        side_effect_level="write",
        required_scope="workflow:draft",
        input_schema={"required": ["request_title", "amount"]},
        output_schema={"required": ["summary", "approval_hint"]},
    )
    config_schema = {
        "endpoint": {"type": "string", "required": True, "default": "https://workflow.example.local"},
        "auth_ref": {"type": "string", "required": True, "format": "secret-ref"},
        "timeout_ms": {"type": "integer", "default": 5000},
    }
    auth_ref = "secrets/workflow_sandbox_token"

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        request_title = str(payload["request_title"])
        amount = str(payload["amount"])
        owner = str(payload.get("owner", "运营采购组"))
        return {
            "summary": f"已生成《{request_title}》采购申请草稿，预算金额 {amount}，归属 {owner}。",
            "approval_hint": "该动作属于 high 风险写操作，需先确认草稿并进入审批链。",
        }
