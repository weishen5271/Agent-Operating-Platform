"""Generic, declarative capability executors driven by bundle bindings."""

from agent_platform.plugins.executors.http import HttpExecutor
from agent_platform.plugins.executors.mcp import McpExecutor
from agent_platform.plugins.executors.platform import PlatformProxyPlugin

__all__ = ["HttpExecutor", "McpExecutor", "PlatformProxyPlugin"]
