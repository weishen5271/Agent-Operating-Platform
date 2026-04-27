from __future__ import annotations

import re
from typing import Any

_REF_PATTERN = re.compile(r"\$(prev_step|response|inputs|input|config|secret|steps)(?:\.([A-Za-z0-9_.\-]+))?")


class BindingContext:
    __slots__ = ("inputs", "config", "response")

    def __init__(self, *, inputs: dict[str, Any], config: dict[str, Any]) -> None:
        self.inputs = inputs
        self.config = config
        self.response: dict[str, Any] | None = None

    def require_config(self, key: str, *, error_factory: Any = ValueError) -> str:
        value = self.config.get(key)
        if not value:
            raise error_factory(
                "MISSING_CONFIG",
                None,
                f"plugin_config.{key} 未配置；请先在「业务包管理 → 能力 → 插件配置」填入。",
            )
        return str(value)

    def resolve(self, scope: str, dotted_path: str | None) -> Any:
        if scope == "secret":
            secrets = self.config.get("secrets") or {}
            if not isinstance(secrets, dict):
                return None
            return secrets.get(dotted_path or "")
        source: Any
        if scope in {"input", "inputs"}:
            source = self.inputs
        elif scope == "steps":
            source = self.inputs.get("steps", {})
        elif scope == "prev_step":
            source = self.inputs.get("prev_step", {})
        elif scope == "config":
            source = self.config
        elif scope == "response":
            source = self.response or {}
        else:
            return None
        if not dotted_path:
            return source
        return walk_path(source, dotted_path)


def render_mapping(value: Any, ctx: BindingContext) -> Any:
    if isinstance(value, dict):
        return {key: render_mapping(item, ctx) for key, item in value.items()}
    if isinstance(value, list):
        return [render_mapping(item, ctx) for item in value]
    if isinstance(value, str):
        return render_template(value, ctx)
    return value


def render_template(template: str, ctx: BindingContext) -> Any:
    match = _REF_PATTERN.fullmatch(template.strip())
    if match:
        return ctx.resolve(match.group(1), match.group(2))

    def replace(match: re.Match[str]) -> str:
        value = ctx.resolve(match.group(1), match.group(2))
        return "" if value is None else str(value)

    return _REF_PATTERN.sub(replace, template)


def walk_path(source: Any, dotted_path: str) -> Any:
    cursor: Any = source
    for segment in dotted_path.split("."):
        if cursor is None:
            return None
        if isinstance(cursor, dict):
            cursor = cursor.get(segment)
            continue
        if isinstance(cursor, list) and segment.isdigit():
            index = int(segment)
            cursor = cursor[index] if 0 <= index < len(cursor) else None
            continue
        return None
    return cursor
