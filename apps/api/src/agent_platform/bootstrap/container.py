from agent_platform.infrastructure.db import db_runtime
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.infrastructure.repositories import (
    PostgresConversationRepository,
    PostgresDraftRepository,
    PostgresKnowledgeRepository,
    PostgresKnowledgeBaseRepository,
    PostgresLLMConfigRepository,
    PostgresSecurityRepository,
    PostgresTenantRepository,
    PostgresTraceRepository,
    PostgresUserRepository,
    seed_postgres_defaults,
)
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.repository import PostgresWikiRepository


llm_config_repository = PostgresLLMConfigRepository(db_runtime)
llm_client = OpenAICompatibleLLMClient()
capability_registry = CapabilityRegistry()
security_repository = PostgresSecurityRepository(db_runtime)
conversation_repository = PostgresConversationRepository(db_runtime)
trace_repository = PostgresTraceRepository(db_runtime)
tenant_repository = PostgresTenantRepository(db_runtime)
user_repository = PostgresUserRepository(db_runtime)
draft_repository = PostgresDraftRepository(db_runtime)
knowledge_repository = PostgresKnowledgeRepository(db_runtime)
knowledge_base_repository = PostgresKnowledgeBaseRepository(db_runtime)
wiki_repository = PostgresWikiRepository(db_runtime)
wiki_service = WikiService(repository=wiki_repository, users=user_repository, knowledge_bases=knowledge_base_repository)

chat_service = ChatService(
    registry=capability_registry,
    conversations=conversation_repository,
    traces=trace_repository,
    tenants=tenant_repository,
    users=user_repository,
    drafts=draft_repository,
    security_events=security_repository,
    knowledge_sources=knowledge_repository,
    knowledge_bases=knowledge_base_repository,
    wiki_service=wiki_service,
    llm_config=llm_config_repository,
    llm_client=llm_client,
)


async def initialize_runtime_state() -> None:
    await seed_postgres_defaults(db_runtime)
