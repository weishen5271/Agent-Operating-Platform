from __future__ import annotations

from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.base import CapabilityPlugin


class WikiSearchPlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="wiki.search",
        description="检索治理后的 Wiki 页面与引用证据。",
        risk_level="low",
        side_effect_level="read",
        required_scope="knowledge:read",
        input_schema={"required": ["query"]},
        output_schema={"required": ["summary", "hits"]},
    )
    config_schema = {
        "space_code": {"type": "string", "default": "knowledge"},
        "top_k": {"type": "integer", "default": 5},
    }

    def invoke(self, payload: dict[str, str]) -> dict[str, object]:
        return {
            "summary": "Wiki 检索由 ChatService 统一接管，此占位实现不应直接执行。",
            "hits": [],
            "retrieval": {
                "backend": "wiki_unhandled",
                "query": payload.get("query", ""),
                "matched": False,
                "candidate_count": 0,
                "match_count": 0,
            },
        }
