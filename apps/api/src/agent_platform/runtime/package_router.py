from __future__ import annotations

from typing import Any

from agent_platform.domain.models import TenantProfile
from agent_platform.runtime.package_loader import PackageLoader


class PackageRouter:
    """根据租户绑定、通用业务包和意图规则，为一次请求选择最相关的业务包。"""

    def __init__(self, loader: PackageLoader) -> None:
        self._loader = loader

    @classmethod
    def default(cls) -> "PackageRouter":
        return cls(PackageLoader.default())

    def route(self, tenant: TenantProfile | None, intent: str, message: str = "") -> dict[str, object]:
        active_ids = self._active_package_ids(tenant)
        packages = [item for item in self._loader.list_packages() if str(item.get("package_id")) in active_ids]
        if not packages and tenant and tenant.package:
            # loader 未读到清单时仍保留租户绑定信息，避免路由结果完全丢失业务包上下文。
            packages = [{"package_id": tenant.package, "intents": []}]

        scored: list[tuple[str, float, list[str]]] = []
        for package in packages:
            package_id = str(package.get("package_id", ""))
            # 主业务包天然比通用包更贴近当前租户场景；关键词只作为意图命中的微调信号。
            base_score = 0.75 if tenant and package_id == tenant.package else 0.62
            score = base_score
            signals = [f"package={package_id}"]
            for rule in package.get("intents", []):
                if not isinstance(rule, dict) or rule.get("name") != intent:
                    continue
                rule_score = float(rule.get("score", 0.8))
                keywords = [str(item) for item in rule.get("keywords", [])]
                keyword_hits = [item for item in keywords if item and item.lower() in message.lower()]
                keyword_bonus = min(0.12, len(keyword_hits) * 0.04)
                score = max(score, rule_score + keyword_bonus)
                signals.append(f"intent={intent}")
                if keyword_hits:
                    signals.append(f"keywords={','.join(keyword_hits[:3])}")
            scored.append((package_id, min(score, 0.99), signals))

        if not scored:
            return {
                "matched_package_id": "default",
                "confidence": 0.5,
                "candidates": [],
                "signals": [f"intent={intent}", "package=default"],
            }
        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        matched_package_id, confidence, signals = ranked[0]
        return {
            "matched_package_id": matched_package_id,
            "confidence": confidence,
            "candidates": [
                {"package_id": package_id, "confidence": score}
                for package_id, score, _ in ranked[1:3]
            ],
            "signals": [f"intent={intent}", *signals, f"candidates={len(ranked)}"],
        }

    @staticmethod
    def _active_package_ids(tenant: TenantProfile | None) -> set[str]:
        if tenant is None:
            return set()
        package_ids = {tenant.package}
        package_ids.update(tenant.enabled_common_packages)
        return {item for item in package_ids if item}
