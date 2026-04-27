from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from agent_platform.domain.models import SkillDefinition, ToolDefinition
from agent_platform.runtime.package_loader import PackageLoader


class ToolRegistry:
    """平台原子工具注册中心。

    工具是无业务规则、无外部副作用的原子能力，例如 http_fetch、json_path、time_now。
    租户可以通过 tool_overrides 调整 quota / timeout / enabled，但默认值由代码声明。
    当前为骨架实现，仅承载契约展示，后续 Stage 3 接入真实调用与配额执行。
    """

    def __init__(self) -> None:
        defaults = [
            ToolDefinition(
                name="http_fetch",
                description="发起受限 HTTP GET，带超时、白名单与响应大小上限。",
                version="1.0.0",
                source="_platform",
                timeout_ms=5000,
                quota_per_minute=60,
            ),
            ToolDefinition(
                name="json_path",
                description="对 JSON 输入执行 JSONPath 查询。",
                version="1.0.0",
                source="_platform",
                timeout_ms=200,
                quota_per_minute=600,
            ),
            ToolDefinition(
                name="time_now",
                description="返回服务端当前时间，可指定时区。",
                version="1.0.0",
                source="_platform",
                timeout_ms=50,
                quota_per_minute=600,
            ),
        ]
        self._tools: dict[str, ToolDefinition] = {tool.name: tool for tool in defaults}

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Tool not found: {name}")
        if not tool.enabled:
            raise ValueError(f"Tool disabled: {name}")
        if name == "time_now":
            return self._invoke_time_now(payload)
        if name == "json_path":
            return self._invoke_json_path(payload)
        if name == "http_fetch":
            return self._invoke_http_fetch(payload, timeout_ms=tool.timeout_ms)
        raise ValueError(f"Tool has no executor: {name}")

    @staticmethod
    def _invoke_time_now(payload: dict[str, Any]) -> dict[str, Any]:
        requested = payload.get("timezones")
        if isinstance(requested, list) and requested:
            timezones = [str(item) for item in requested if str(item).strip()]
        else:
            timezones = [str(payload.get("timezone") or "Asia/Shanghai")]
        items = [ToolRegistry._time_for_timezone(timezone_name) for timezone_name in timezones]
        primary = items[0]
        return {
            **primary,
            "items": items,
        }

    @staticmethod
    def _time_for_timezone(timezone_name: str) -> dict[str, str]:
        try:
            if timezone_name.startswith("UTC") and len(timezone_name) > 3:
                offset_hours = int(timezone_name[3:])
                tzinfo = timezone(timedelta(hours=offset_hours), name=timezone_name)
            else:
                tzinfo = ZoneInfo(timezone_name)
        except Exception as exc:
            raise ValueError(f"Unsupported timezone: {timezone_name}") from exc
        now = datetime.now(tzinfo)
        return {
            "timezone": timezone_name,
            "iso": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
        }

    @staticmethod
    def _invoke_json_path(payload: dict[str, Any]) -> dict[str, Any]:
        document = payload.get("document")
        if isinstance(document, str):
            document = json.loads(document)
        path = str(payload.get("path") or "$")
        matches = ToolRegistry._json_path_query(document, path)
        return {
            "path": path,
            "matches": matches,
            "match_count": len(matches),
        }

    @staticmethod
    def _json_path_query(document: Any, path: str) -> list[Any]:
        if path == "$":
            return [document]
        if not path.startswith("$."):
            raise ValueError("JSONPath only supports '$' or '$.<field>[index]' syntax")
        tokens = re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path[1:])
        current = [document]
        for field, index in tokens:
            next_values: list[Any] = []
            for value in current:
                if field:
                    if isinstance(value, dict) and field in value:
                        next_values.append(value[field])
                    continue
                if index:
                    offset = int(index)
                    if isinstance(value, list) and 0 <= offset < len(value):
                        next_values.append(value[offset])
            current = next_values
        return current

    @staticmethod
    def _invoke_http_fetch(payload: dict[str, Any], *, timeout_ms: int) -> dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("url is required")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only absolute http(s) URLs are supported")
        request = Request(url, headers={"User-Agent": "Agent-Operating-Platform/0.1"})
        try:
            with urlopen(request, timeout=max(timeout_ms / 1000, 0.1)) as response:
                content_type = response.headers.get("content-type", "")
                body = response.read(8192)
                text = body.decode("utf-8", errors="replace")
                return {
                    "url": url,
                    "status": response.status,
                    "content_type": content_type,
                    "text": text,
                    "truncated": len(body) >= 8192,
                }
        except URLError as exc:
            raise ValueError(f"HTTP fetch failed: {exc}") from exc


class SkillRegistry:
    """技能注册中心。

    技能是多步编排的能力，可以组合 Capability + Tool + 检索。
    技能的来源有三种：_platform（平台内置）、_common（通用业务包）、package（行业包私有）。
    当前为骨架实现，承载契约展示与依赖图，编排执行后续 Stage 接入。
    """

    def __init__(self, loader: PackageLoader | None = None) -> None:
        self._loader = loader or PackageLoader.default()
        self._skills = self._load_skills()

    def list_skills(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def refresh(self) -> None:
        """Re-scan packages from disk. Call after a bundle is installed/uninstalled."""
        self._skills = self._load_skills()

    def _load_skills(self) -> dict[str, SkillDefinition]:
        skills: dict[str, SkillDefinition] = {}
        for package in self._loader.list_packages():
            package_id = str(package.get("package_id", ""))
            source_kind = str(package.get("source_kind") or "catalog")
            for raw_skill in package.get("skills", []):
                skill = self._normalize_skill(
                    raw_skill,
                    fallback_package_id=package_id,
                    bundle_default=source_kind == "bundle",
                )
                # Bundle-private skills are namespaced by package_id to avoid
                # cross-package collisions; catalog/platform skills keep their
                # global name.
                key = f"{skill.package_id}::{skill.name}" if skill.source == "package" and skill.package_id else skill.name
                if key in skills:
                    raise ValueError(f"Duplicate skill definition: {key}")
                skills[key] = skill
        return skills

    @staticmethod
    def _normalize_skill(
        raw: dict[str, Any],
        *,
        fallback_package_id: str,
        bundle_default: bool = False,
    ) -> SkillDefinition:
        required = ["name", "description", "version"]
        missing = [field for field in required if not str(raw.get(field, "")).strip()]
        if missing:
            raise ValueError(f"Skill definition missing fields: {', '.join(missing)}")
        # Bundle skills omit ``source`` — default it to "package" so the skill
        # is registered as private to the owning bundle.
        source = str(raw.get("source") or ("package" if bundle_default else ""))
        if not source:
            raise ValueError("Skill definition missing fields: source")
        package_id = raw.get("package_id")
        if source in {"_common", "package"} and not package_id:
            package_id = fallback_package_id
        return SkillDefinition(
            name=str(raw["name"]),
            description=str(raw["description"]),
            version=str(raw["version"]),
            source=source,
            package_id=str(package_id) if package_id else None,
            depends_on_capabilities=[
                str(item)
                for item in raw.get("depends_on_capabilities", [])
                if str(item).strip()
            ],
            depends_on_tools=[
                str(item)
                for item in raw.get("depends_on_tools", [])
                if str(item).strip()
            ],
            enabled=bool(raw.get("enabled", True)),
        )
