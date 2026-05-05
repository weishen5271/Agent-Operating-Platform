from agent_platform.infrastructure.db import db_runtime
from agent_platform.bootstrap.settings import settings
from agent_platform.infrastructure.embedding_client import LocalHuggingFaceEmbeddingClient
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.infrastructure.repositories import (
    PostgresAIRunRepository,
    PostgresBusinessOutputRepository,
    PostgresConversationRepository,
    PostgresDraftRepository,
    PostgresKnowledgeRepository,
    PostgresKnowledgeBaseRepository,
    PostgresLLMConfigRepository,
    PostgresMcpServerRepository,
    PostgresOutputGuardRuleRepository,
    PostgresPluginConfigRepository,
    PostgresReleasePlanRepository,
    PostgresSecurityRepository,
    PostgresTenantRepository,
    PostgresToolOverrideRepository,
    PostgresTraceRepository,
    PostgresUserRepository,
    seed_postgres_defaults,
)
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.ai_action_registry import AIActionRegistry
from agent_platform.runtime.ai_run_service import AIRunService
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_registry import SkillRegistry, ToolRegistry
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.repository import PostgresWikiRepository


# 全局运行时对象在这里集中装配，API 路由层只依赖 service，避免各路由重复创建仓储和客户端。
# 这些实例会在应用生命周期内复用，因此只放无请求态对象，请求上下文通过方法参数向下传递。
llm_config_repository = PostgresLLMConfigRepository(db_runtime)
llm_client = OpenAICompatibleLLMClient()
embedding_client = LocalHuggingFaceEmbeddingClient(
    model_name=settings.local_embedding_model,
    device=settings.local_embedding_device,
    cache_dir=settings.local_embedding_cache_dir,
)
capability_registry = CapabilityRegistry()
skill_registry = SkillRegistry()
tool_registry = ToolRegistry()
security_repository = PostgresSecurityRepository(db_runtime)
conversation_repository = PostgresConversationRepository(db_runtime)
trace_repository = PostgresTraceRepository(db_runtime)
tenant_repository = PostgresTenantRepository(db_runtime)
tool_override_repository = PostgresToolOverrideRepository(db_runtime)
output_guard_rule_repository = PostgresOutputGuardRuleRepository(db_runtime)
plugin_config_repository = PostgresPluginConfigRepository(db_runtime)
mcp_server_repository = PostgresMcpServerRepository(db_runtime)
release_plan_repository = PostgresReleasePlanRepository(db_runtime)
user_repository = PostgresUserRepository(db_runtime)
draft_repository = PostgresDraftRepository(db_runtime)
business_output_repository = PostgresBusinessOutputRepository(db_runtime)
ai_run_repository = PostgresAIRunRepository(db_runtime)
knowledge_repository = PostgresKnowledgeRepository(
    db_runtime,
    llm_config=llm_config_repository,
    embedding_client=embedding_client,
)
knowledge_base_repository = PostgresKnowledgeBaseRepository(
    db_runtime,
    llm_config=llm_config_repository,
    embedding_client=embedding_client,
)
wiki_repository = PostgresWikiRepository(
    db_runtime,
    llm_config=llm_config_repository,
    embedding_client=embedding_client,
)
wiki_service = WikiService(repository=wiki_repository, users=user_repository, knowledge_bases=knowledge_base_repository)

chat_service = ChatService(
    registry=capability_registry,
    skills=skill_registry,
    tools=tool_registry,
    conversations=conversation_repository,
    traces=trace_repository,
    tenants=tenant_repository,
    tool_overrides=tool_override_repository,
    output_guard_rules=output_guard_rule_repository,
    plugin_configs=plugin_config_repository,
    mcp_servers=mcp_server_repository,
    releases=release_plan_repository,
    users=user_repository,
    drafts=draft_repository,
    business_outputs=business_output_repository,
    security_events=security_repository,
    knowledge_sources=knowledge_repository,
    knowledge_bases=knowledge_base_repository,
    wiki_service=wiki_service,
    llm_config=llm_config_repository,
    llm_client=llm_client,
)

ai_action_registry = AIActionRegistry()
ai_run_service = AIRunService(
    actions=ai_action_registry,
    runs=ai_run_repository,
    registry=capability_registry,
    skills=skill_registry,
    tools=tool_registry,
    traces=trace_repository,
    tenants=tenant_repository,
    users=user_repository,
    plugin_configs=plugin_config_repository,
    business_outputs=business_output_repository,
)


async def initialize_runtime_state() -> None:
    # 启动时写入默认租户、管理员、基础配置等幂等数据，保证本地环境首次启动即可进入主流程。
    await seed_postgres_defaults(db_runtime)
