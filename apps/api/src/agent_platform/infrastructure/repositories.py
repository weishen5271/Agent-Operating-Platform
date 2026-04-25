from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import (
    Conversation,
    ConversationMessage,
    DraftAction,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeSource,
    KnowledgeSourceDetail,
    KnowledgeSearchResult,
    LLMRuntimeConfig,
    SecurityEvent,
    SourceReference,
    TenantProfile,
    TraceRecord,
    TraceStep,
    UserContext,
    utc_now,
)
from agent_platform.infrastructure.auth import get_password_hash
from agent_platform.infrastructure.db import DatabaseRuntime
from agent_platform.infrastructure.db_models import (
    ApprovalRequestRecord,
    ConversationMessageRecord,
    ConversationRecord,
    KnowledgeDocumentRecord,
    KnowledgeChunkRecord,
    KnowledgeBaseRecord,
    LLMRuntimeConfigRecord,
    RequestTraceRecord,
    SecurityEventRecord,
    TenantRecord,
    TraceStepRecord,
    UserAccountRecord,
)
from agent_platform.retrieval.text import chunk_text, content_hash, cosine_similarity, embed_text, tokenize


DEFAULT_TENANT_ID = "sw"
DEFAULT_TENANT_NAME = "SW 默认租户"
DEFAULT_TENANT_PACKAGE = "通用业务包"
DEFAULT_TENANT_ENVIRONMENT = "生产"
DEFAULT_TENANT_BUDGET = "¥ 0"
DEFAULT_ADMIN_USER_ID = "admin"
DEFAULT_ADMIN_EMAIL = "admin@sw.com"
DEFAULT_ADMIN_PASSWORD = "Aa111111"


class ConversationRepository(Protocol):
    async def list_recent(self, tenant_id: str, limit: int = 5) -> list[Conversation]: ...

    async def get(self, tenant_id: str, conversation_id: str) -> Conversation | None: ...

    async def append_message(
        self,
        tenant_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
    ) -> Conversation: ...


class TraceRepository(Protocol):
    async def save(self, trace: TraceRecord) -> TraceRecord: ...

    async def get(self, trace_id: str) -> TraceRecord | None: ...

    async def list_recent(self, tenant_id: str, limit: int = 20) -> list[TraceRecord]: ...


class KnowledgeRepository(Protocol):
    async def list_recent(self, tenant_id: str, knowledge_base_code: str | None = None) -> list[KnowledgeSource]: ...

    async def get_detail(self, tenant_id: str, source_id: str) -> KnowledgeSourceDetail | None: ...

    async def ingest_text(
        self,
        *,
        tenant_id: str,
        name: str,
        content: str,
        source_type: str,
        owner: str,
        knowledge_base_code: str,
    ) -> KnowledgeSource: ...


class KnowledgeBaseRepository(Protocol):
    async def list_by_tenant(self, tenant_id: str) -> list[KnowledgeBase]: ...

    async def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase: ...

    async def update(self, knowledge_base: KnowledgeBase) -> KnowledgeBase: ...

    async def delete(self, tenant_id: str, knowledge_base_code: str) -> bool: ...

    async def search(self, *, tenant_id: str, query: str, top_k: int = 3) -> KnowledgeSearchResult: ...


class TenantRepository(Protocol):
    async def get(self, tenant_id: str) -> TenantProfile | None: ...

    async def list_all(self) -> list[TenantProfile]: ...

    async def create(self, tenant: TenantProfile) -> TenantProfile: ...

    async def update(self, tenant: TenantProfile) -> TenantProfile: ...

    async def delete(self, tenant_id: str) -> bool: ...


class UserRepository(Protocol):
    async def get(self, tenant_id: str, user_id: str) -> UserContext | None: ...

    async def get_by_email(self, email: str) -> tuple[UserContext, str] | None: ...

    async def list_by_tenant(self, tenant_id: str) -> list[UserContext]: ...

    async def create(self, user: UserContext, password_hash: str) -> UserContext: ...

    async def update(self, user: UserContext) -> UserContext: ...

    async def delete(self, tenant_id: str, user_id: str) -> bool: ...


class DraftRepository(Protocol):
    async def save(self, draft: DraftAction) -> DraftAction: ...

    async def confirm(self, draft_id: str, tenant_id: str, confirmed_at: datetime) -> DraftAction | None: ...

    async def list_recent(self, tenant_id: str, limit: int = 10) -> list[DraftAction]: ...


class SecurityRepository(Protocol):
    async def list_recent(self, tenant_id: str) -> list[SecurityEvent]: ...


class LLMConfigRepository(Protocol):
    async def get(self, tenant_id: str | None = None) -> tuple[LLMRuntimeConfig, str]: ...

    async def update(
        self,
        tenant_id: str | None,
        *,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float,
        system_prompt: str,
    ) -> tuple[LLMRuntimeConfig, str]: ...

    async def create_or_update_for_tenant(
        self,
        tenant_id: str | None,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float,
        system_prompt: str,
    ) -> tuple[LLMRuntimeConfig, str]: ...


def _conversation_from_record(record: ConversationRecord) -> Conversation:
    ordered_messages = sorted(record.messages, key=lambda item: item.created_at)
    return Conversation(
        conversation_id=record.conversation_id,
        title=record.title,
        tenant_id=record.tenant_id,
        messages=[ConversationMessage(role=item.role, content=item.content) for item in ordered_messages],
        updated_at=record.updated_at,
    )


def _trace_from_record(record: RequestTraceRecord) -> TraceRecord:
    ordered_steps = sorted(record.steps, key=lambda item: item.timestamp)
    return TraceRecord(
        trace_id=record.trace_id,
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        message=record.message,
        intent=record.intent,
        strategy=record.strategy,
        answer=record.answer,
        sources=[
            SourceReference(
                id=item["id"],
                title=item["title"],
                snippet=item["snippet"],
                source_type=item["source_type"],
            )
            for item in record.sources
        ],
        steps=[
            TraceStep(
                name=item.name,
                status=item.status,
                summary=item.summary,
                timestamp=item.timestamp,
            )
            for item in ordered_steps
        ],
        created_at=record.created_at,
    )


def _draft_from_record(record: ApprovalRequestRecord) -> DraftAction:
    return DraftAction(
        draft_id=record.draft_id,
        tenant_id=record.tenant_id,
        user_id=record.user_id,
        capability_name=record.capability_name,
        title=record.title,
        risk_level=record.risk_level,
        status=record.status,
        payload=record.payload,
        summary=record.summary,
        approval_hint=record.approval_hint,
        created_at=record.created_at,
        confirmed_at=record.confirmed_at,
    )


def _security_from_record(record: SecurityEventRecord) -> SecurityEvent:
    return SecurityEvent(
        event_id=record.event_id,
        tenant_id=record.tenant_id,
        category=record.category,
        severity=record.severity,
        title=record.title,
        status=record.status,
        owner=record.owner,
    )


def _knowledge_from_record(record: KnowledgeDocumentRecord) -> KnowledgeSource:
    return KnowledgeSource(
        source_id=record.source_id,
        tenant_id=record.tenant_id,
        knowledge_base_code=record.knowledge_base_code,
        name=record.name,
        source_type=record.source_type,
        owner=record.owner,
        chunk_count=record.chunk_count,
        status=record.status,
    )


def _knowledge_chunk_from_record(record: KnowledgeChunkRecord) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=record.chunk_id,
        source_id=record.source_id,
        tenant_id=record.tenant_id,
        chunk_index=record.chunk_index,
        title=record.title,
        content=record.content,
        content_hash=record.content_hash,
        metadata_json=dict(record.metadata_json),
        token_count=record.token_count,
        status=record.status,
        created_at=record.created_at,
    )


def _knowledge_base_from_record(record: KnowledgeBaseRecord) -> KnowledgeBase:
    return KnowledgeBase(
        knowledge_base_id=record.knowledge_base_id,
        knowledge_base_code=record.knowledge_base_code,
        tenant_id=record.tenant_id,
        name=record.name,
        description=record.description,
        status=record.status,
        created_by=record.created_by,
        updated_by=record.updated_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _runtime_from_record(record: LLMRuntimeConfigRecord) -> tuple[LLMRuntimeConfig, str]:
    return (
        LLMRuntimeConfig(
            provider=record.provider,
            base_url=record.base_url,
            model=record.model,
            api_key_configured=bool(record.api_key),
            temperature=record.temperature,
            system_prompt=record.system_prompt,
            enabled=record.enabled,
        ),
        record.api_key,
    )


class PostgresConversationRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def list_recent(self, tenant_id: str, limit: int = 5) -> list[Conversation]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(ConversationRecord)
                .options(selectinload(ConversationRecord.messages))
                .where(ConversationRecord.tenant_id == tenant_id)
                .order_by(desc(ConversationRecord.updated_at))
                .limit(limit)
            )
            return [_conversation_from_record(item) for item in result.scalars().unique().all()]

    async def get(self, tenant_id: str, conversation_id: str) -> Conversation | None:
        async with self._runtime.session() as session:
            conversation = await session.get(
                ConversationRecord,
                conversation_id,
                options=[selectinload(ConversationRecord.messages)],
            )
            if conversation is None or conversation.tenant_id != tenant_id:
                return None
            return _conversation_from_record(conversation)

    async def append_message(
        self,
        tenant_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
    ) -> Conversation:
        resolved_conversation_id = conversation_id or str(uuid4())
        async with self._runtime.session() as session:
            conversation = await session.get(
                ConversationRecord,
                resolved_conversation_id,
                options=[selectinload(ConversationRecord.messages)],
            )
            now = utc_now()
            if conversation is None:
                conversation = ConversationRecord(
                    conversation_id=resolved_conversation_id,
                    tenant_id=tenant_id,
                    title=user_message[:24] or "新会话",
                    updated_at=now,
                )
                session.add(conversation)
                await session.flush()
            else:
                conversation.updated_at = now

            session.add_all(
                [
                    ConversationMessageRecord(
                        conversation_id=resolved_conversation_id,
                        role="user",
                        content=user_message,
                        created_at=now,
                    ),
                    ConversationMessageRecord(
                        conversation_id=resolved_conversation_id,
                        role="assistant",
                        content=assistant_message,
                        created_at=now,
                    ),
                ]
            )
            await session.commit()
            await session.refresh(conversation, attribute_names=["messages"])
            return _conversation_from_record(conversation)


class PostgresTraceRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def save(self, trace: TraceRecord) -> TraceRecord:
        async with self._runtime.session() as session:
            session.add(
                RequestTraceRecord(
                    trace_id=trace.trace_id,
                    tenant_id=trace.tenant_id,
                    user_id=trace.user_id,
                    intent=trace.intent,
                    strategy=trace.strategy,
                    message=trace.message,
                    answer=trace.answer,
                    sources=[asdict(item) for item in trace.sources],
                    created_at=trace.created_at,
                    steps=[
                        TraceStepRecord(
                            name=item.name,
                            status=item.status,
                            summary=item.summary,
                            timestamp=item.timestamp,
                        )
                        for item in trace.steps
                    ],
                )
            )
            await session.commit()
        return trace

    async def get(self, trace_id: str) -> TraceRecord | None:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(RequestTraceRecord)
                .options(selectinload(RequestTraceRecord.steps))
                .where(RequestTraceRecord.trace_id == trace_id)
            )
            record = result.scalar_one_or_none()
            return _trace_from_record(record) if record else None

    async def list_recent(self, tenant_id: str, limit: int = 20) -> list[TraceRecord]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(RequestTraceRecord)
                .options(selectinload(RequestTraceRecord.steps))
                .where(RequestTraceRecord.tenant_id == tenant_id)
                .order_by(desc(RequestTraceRecord.created_at))
                .limit(limit)
            )
            return [_trace_from_record(item) for item in result.scalars().unique().all()]


class PostgresTenantRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def get(self, tenant_id: str) -> TenantProfile | None:
        async with self._runtime.session() as session:
            result = await session.execute(select(TenantRecord).where(TenantRecord.tenant_id == tenant_id))
            record = result.scalar_one_or_none()
            if record is None:
                return None
            return TenantProfile(
                tenant_id=record.tenant_id,
                name=record.name,
                package=record.package,
                environment=record.environment,
                budget=record.budget,
                active=record.active,
            )

    async def list_all(self) -> list[TenantProfile]:
        async with self._runtime.session() as session:
            result = await session.execute(select(TenantRecord).order_by(TenantRecord.tenant_id))
            return [
                TenantProfile(
                    tenant_id=item.tenant_id,
                    name=item.name,
                    package=item.package,
                    environment=item.environment,
                    budget=item.budget,
                    active=item.active,
                )
                for item in result.scalars().all()
            ]

    async def create(self, tenant: TenantProfile) -> TenantProfile:
        async with self._runtime.session() as session:
            record = TenantRecord(
                tenant_record_id=f"tn-{uuid4().hex[:12]}",
                tenant_id=tenant.tenant_id,
                name=tenant.name,
                package=tenant.package,
                environment=tenant.environment,
                budget=tenant.budget,
                active=tenant.active,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("租户名称或租户 ID 已存在，请更换后重试") from exc
            return tenant

    async def update(self, tenant: TenantProfile) -> TenantProfile:
        async with self._runtime.session() as session:
            result = await session.execute(select(TenantRecord).where(TenantRecord.tenant_id == tenant.tenant_id))
            record = result.scalar_one_or_none()
            if record is None:
                raise ValueError(f"Tenant {tenant.tenant_id} not found")
            record.name = tenant.name
            record.package = tenant.package
            record.environment = tenant.environment
            record.budget = tenant.budget
            record.active = tenant.active
            await session.commit()
            await session.refresh(record)
            return TenantProfile(
                tenant_id=record.tenant_id,
                name=record.name,
                package=record.package,
                environment=record.environment,
                budget=record.budget,
                active=record.active,
            )

    async def delete(self, tenant_id: str) -> bool:
        async with self._runtime.session() as session:
            result = await session.execute(select(TenantRecord).where(TenantRecord.tenant_id == tenant_id))
            record = result.scalar_one_or_none()
            if record is None:
                return False
            await session.delete(record)
            await session.commit()
            return True


class PostgresUserRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def get(self, tenant_id: str, user_id: str) -> UserContext | None:
        async with self._runtime.session() as session:
            result = await session.execute(select(UserAccountRecord).where(UserAccountRecord.user_id == user_id))
            record = result.scalar_one_or_none()
            if record is None or record.tenant_id != tenant_id:
                return None
            return UserContext(
                user_id=record.user_id,
                tenant_id=record.tenant_id,
                role=record.role,
                scopes=list(record.scopes),
                email=record.email,
            )

    async def get_by_email(self, email: str) -> tuple[UserContext, str] | None:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(UserAccountRecord).where(UserAccountRecord.email == email)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return None
            return (
                UserContext(
                    user_id=record.user_id,
                    tenant_id=record.tenant_id,
                    role=record.role,
                    scopes=list(record.scopes),
                    email=record.email,
                ),
                record.password_hash,
            )

    async def list_by_tenant(self, tenant_id: str) -> list[UserContext]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(UserAccountRecord).where(UserAccountRecord.tenant_id == tenant_id)
            )
            return [
                UserContext(
                    user_id=item.user_id,
                    tenant_id=item.tenant_id,
                    role=item.role,
                    scopes=list(item.scopes),
                    email=item.email,
                )
                for item in result.scalars().all()
            ]

    async def create(self, user: UserContext, password_hash: str) -> UserContext:
        async with self._runtime.session() as session:
            record = UserAccountRecord(
                user_account_id=f"usr-{uuid4().hex[:12]}",
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                email=user.email,
                password_hash=password_hash,
                role=user.role,
                scopes=user.scopes,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("用户邮箱或用户 ID 已存在，请更换后重试") from exc
            return user

    async def update(self, user: UserContext) -> UserContext:
        async with self._runtime.session() as session:
            result = await session.execute(select(UserAccountRecord).where(UserAccountRecord.user_id == user.user_id))
            record = result.scalar_one_or_none()
            if record is None or record.tenant_id != user.tenant_id:
                raise ValueError(f"User {user.user_id} not found")
            record.role = user.role
            record.scopes = user.scopes
            await session.commit()
            await session.refresh(record)
            return UserContext(
                user_id=record.user_id,
                tenant_id=record.tenant_id,
                role=record.role,
                scopes=list(record.scopes),
                email=record.email,
            )

    async def delete(self, tenant_id: str, user_id: str) -> bool:
        async with self._runtime.session() as session:
            result = await session.execute(select(UserAccountRecord).where(UserAccountRecord.user_id == user_id))
            record = result.scalar_one_or_none()
            if record is None or record.tenant_id != tenant_id:
                return False
            await session.delete(record)
            await session.commit()
            return True


class PostgresDraftRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def save(self, draft: DraftAction) -> DraftAction:
        async with self._runtime.session() as session:
            session.add(
                ApprovalRequestRecord(
                    draft_id=draft.draft_id,
                    tenant_id=draft.tenant_id,
                    user_id=draft.user_id,
                    capability_name=draft.capability_name,
                    title=draft.title,
                    risk_level=draft.risk_level,
                    status=draft.status,
                    payload=draft.payload,
                    summary=draft.summary,
                    approval_hint=draft.approval_hint,
                    created_at=draft.created_at,
                    confirmed_at=draft.confirmed_at,
                )
            )
            await session.commit()
        return draft

    async def confirm(self, draft_id: str, tenant_id: str, confirmed_at: datetime) -> DraftAction | None:
        async with self._runtime.session() as session:
            record = await session.get(ApprovalRequestRecord, draft_id)
            if record is None or record.tenant_id != tenant_id:
                return None
            record.status = "confirmed"
            record.confirmed_at = confirmed_at
            await session.commit()
            await session.refresh(record)
            return _draft_from_record(record)

    async def list_recent(self, tenant_id: str, limit: int = 10) -> list[DraftAction]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(ApprovalRequestRecord)
                .where(ApprovalRequestRecord.tenant_id == tenant_id)
                .order_by(desc(ApprovalRequestRecord.created_at))
                .limit(limit)
            )
            return [_draft_from_record(item) for item in result.scalars().all()]


class PostgresSecurityRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def list_recent(self, tenant_id: str) -> list[SecurityEvent]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(SecurityEventRecord)
                .where(SecurityEventRecord.tenant_id == tenant_id)
                .order_by(desc(SecurityEventRecord.created_at))
            )
            return [_security_from_record(item) for item in result.scalars().all()]


class PostgresKnowledgeRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def list_recent(self, tenant_id: str, knowledge_base_code: str | None = None) -> list[KnowledgeSource]:
        async with self._runtime.session() as session:
            stmt = (
                select(KnowledgeDocumentRecord)
                .where(KnowledgeDocumentRecord.tenant_id == tenant_id)
                .order_by(KnowledgeDocumentRecord.source_id)
            )
            if knowledge_base_code:
                stmt = stmt.where(KnowledgeDocumentRecord.knowledge_base_code == knowledge_base_code)
            result = await session.execute(stmt)
            return [_knowledge_from_record(item) for item in result.scalars().all()]

    async def get_detail(self, tenant_id: str, source_id: str) -> KnowledgeSourceDetail | None:
        async with self._runtime.session() as session:
            document_result = await session.execute(
                select(KnowledgeDocumentRecord)
                .where(KnowledgeDocumentRecord.tenant_id == tenant_id)
                .where(KnowledgeDocumentRecord.source_id == source_id)
            )
            document = document_result.scalar_one_or_none()
            if document is None:
                return None

            chunks_result = await session.execute(
                select(KnowledgeChunkRecord)
                .where(KnowledgeChunkRecord.tenant_id == tenant_id)
                .where(KnowledgeChunkRecord.source_id == source_id)
                .order_by(KnowledgeChunkRecord.chunk_index)
            )
            chunks = [_knowledge_chunk_from_record(item) for item in chunks_result.scalars().all()]
            return KnowledgeSourceDetail(
                source=_knowledge_from_record(document),
                chunks=chunks,
                content="\n\n".join(chunk.content for chunk in chunks),
            )

    async def ingest_text(
        self,
        *,
        tenant_id: str,
        name: str,
        content: str,
        source_type: str,
        owner: str,
        knowledge_base_code: str,
    ) -> KnowledgeSource:
        chunks = chunk_text(content)
        if not chunks:
            raise ValueError("Knowledge content is empty after parsing")

        source_id = f"ks-{uuid4().hex[:12]}"
        async with self._runtime.session() as session:
            document = KnowledgeDocumentRecord(
                source_id=source_id,
                tenant_id=tenant_id,
                knowledge_base_code=knowledge_base_code,
                name=name,
                source_type=source_type,
                owner=owner,
                chunk_count=len(chunks),
                status="运行中",
            )
            session.add(document)
            for index, chunk in enumerate(chunks):
                session.add(
                    KnowledgeChunkRecord(
                        chunk_id=f"kc-{uuid4().hex[:12]}",
                        source_id=source_id,
                        tenant_id=tenant_id,
                        chunk_index=index,
                        title=name,
                        content=chunk,
                        content_hash=content_hash(chunk),
                        embedding=embed_text(chunk),
                        metadata_json={
                            "version": "v1",
                            "classification": "internal",
                            "locator": f"chunk:{index + 1}",
                        },
                        token_count=len(tokenize(chunk)),
                        status="published",
                    )
                )
            await session.commit()
            await session.refresh(document)
            return _knowledge_from_record(document)


class PostgresKnowledgeBaseRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def list_by_tenant(self, tenant_id: str) -> list[KnowledgeBase]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeBaseRecord)
                .where(KnowledgeBaseRecord.tenant_id == tenant_id)
                .order_by(KnowledgeBaseRecord.created_at)
            )
            return [_knowledge_base_from_record(item) for item in result.scalars().all()]

    async def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        async with self._runtime.session() as session:
            session.add(KnowledgeBaseRecord(**asdict(knowledge_base)))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("知识库编码已存在，请更换后重试") from exc
            result = await session.execute(
                select(KnowledgeBaseRecord).where(
                    KnowledgeBaseRecord.knowledge_base_code == knowledge_base.knowledge_base_code
                )
            )
            return _knowledge_base_from_record(result.scalar_one())

    async def update(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeBaseRecord)
                .where(KnowledgeBaseRecord.tenant_id == knowledge_base.tenant_id)
                .where(KnowledgeBaseRecord.knowledge_base_code == knowledge_base.knowledge_base_code)
            )
            record = result.scalar_one()
            record.name = knowledge_base.name
            record.description = knowledge_base.description
            record.status = knowledge_base.status
            record.updated_by = knowledge_base.updated_by
            await session.commit()
            await session.refresh(record)
            return _knowledge_base_from_record(record)

    async def delete(self, tenant_id: str, knowledge_base_code: str) -> bool:
        async with self._runtime.session() as session:
            source_result = await session.execute(
                select(KnowledgeDocumentRecord.source_id)
                .where(KnowledgeDocumentRecord.tenant_id == tenant_id)
                .where(KnowledgeDocumentRecord.knowledge_base_code == knowledge_base_code)
            )
            if source_result.scalars().first() is not None:
                raise ValueError("Knowledge base still has sources")
            result = await session.execute(
                select(KnowledgeBaseRecord)
                .where(KnowledgeBaseRecord.tenant_id == tenant_id)
                .where(KnowledgeBaseRecord.knowledge_base_code == knowledge_base_code)
            )
            record = result.scalar_one_or_none()
            if record is None:
                return False
            await session.delete(record)
            await session.commit()
            return True

    async def search(self, *, tenant_id: str, query: str, top_k: int = 3) -> KnowledgeSearchResult:
        terms = tokenize(query)
        query_vector = embed_text(query)
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeChunkRecord, KnowledgeDocumentRecord)
                .join(KnowledgeDocumentRecord, KnowledgeDocumentRecord.source_id == KnowledgeChunkRecord.source_id)
                .where(KnowledgeChunkRecord.tenant_id == tenant_id)
                .where(KnowledgeChunkRecord.status == "published")
                .where(KnowledgeDocumentRecord.status == "运行中")
            )
            rows = result.all()

        keyword_ranked: list[tuple[str, float]] = []
        vector_ranked: list[tuple[str, float]] = []
        chunk_map: dict[str, tuple[KnowledgeChunkRecord, KnowledgeDocumentRecord]] = {}
        for chunk, document in rows:
            chunk_map[chunk.chunk_id] = (chunk, document)
            keyword_score = self._keyword_score(chunk=chunk, document=document, terms=terms, query=query)
            if keyword_score > 0:
                keyword_ranked.append((chunk.chunk_id, keyword_score))
            vector_score = cosine_similarity(query_vector, chunk.embedding)
            if vector_score > 0:
                vector_ranked.append((chunk.chunk_id, vector_score))

        keyword_ranked.sort(key=lambda item: item[1], reverse=True)
        vector_ranked.sort(key=lambda item: item[1], reverse=True)
        fused_scores = self._rrf(keyword_ranked, vector_ranked)
        ordered_ids = sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)[:top_k]
        matches = [
            self._source_reference(chunk_map[chunk_id][0], chunk_map[chunk_id][1], query=query, terms=terms)
            for chunk_id in ordered_ids
        ]
        return KnowledgeSearchResult(
            matches=matches,
            backend="postgres_json_hybrid",
            query=query,
            candidate_count=len(rows),
            match_count=len(matches),
            keyword_match_count=len(keyword_ranked),
            vector_match_count=len(vector_ranked),
        )

    @staticmethod
    def _keyword_score(
        *,
        chunk: KnowledgeChunkRecord,
        document: KnowledgeDocumentRecord,
        terms: list[str],
        query: str,
    ) -> float:
        title = document.name.lower()
        content = chunk.content.lower()
        normalized_query = query.lower()
        score = 0.0
        if normalized_query and normalized_query in title:
            score += 12.0
        if normalized_query and normalized_query in content:
            score += 8.0
        for term in terms:
            if term in title:
                score += 4.0
            if term in content:
                score += min(content.count(term), 5)
        return score

    @staticmethod
    def _rrf(*ranked_lists: list[tuple[str, float]], k: int = 60) -> dict[str, float]:
        scores: dict[str, float] = {}
        for ranked in ranked_lists:
            for rank, (chunk_id, _score) in enumerate(ranked, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)
        return scores

    @staticmethod
    def _source_reference(
        chunk: KnowledgeChunkRecord,
        document: KnowledgeDocumentRecord,
        *,
        query: str,
        terms: list[str],
    ) -> SourceReference:
        snippet = PostgresKnowledgeRepository._build_snippet(chunk.content, query=query, terms=terms)
        return SourceReference(
            id=chunk.chunk_id,
            title=document.name,
            snippet=snippet,
            source_type="knowledge",
        )

    @staticmethod
    def _build_snippet(content: str, *, query: str, terms: list[str]) -> str:
        lowered = content.lower()
        index = lowered.find(query.lower()) if query else -1
        if index == -1:
            index = next((lowered.find(term) for term in terms if lowered.find(term) != -1), -1)
        if index == -1:
            return content[:180].replace("\n", " ")
        start = max(index - 60, 0)
        end = min(index + 160, len(content))
        return content[start:end].replace("\n", " ")


class PostgresLLMConfigRepository:
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def get(self, tenant_id: str | None = None) -> tuple[LLMRuntimeConfig, str]:
        async with self._runtime.session() as session:
            if tenant_id:
                result = await session.execute(
                    select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.tenant_id == tenant_id)
                )
                record = result.scalar_one_or_none()
                if record is None:
                    result = await session.execute(
                        select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.config_key == "default")
                    )
                    record = result.scalar_one_or_none()
            else:
                result = await session.execute(
                    select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.config_key == "default")
                )
                record = result.scalar_one_or_none()
            if record is None:
                raise RuntimeError("LLM runtime config is not initialized")
            return _runtime_from_record(record)

    async def update(
        self,
        tenant_id: str | None,
        *,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float,
        system_prompt: str,
    ) -> tuple[LLMRuntimeConfig, str]:
        async with self._runtime.session() as session:
            if tenant_id:
                result = await session.execute(
                    select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.tenant_id == tenant_id)
                )
                record = result.scalar_one_or_none()
                if record is None:
                    result = await session.execute(
                        select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.config_key == "default")
                    )
                    record = result.scalar_one_or_none()
            else:
                result = await session.execute(
                    select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.config_key == "default")
                )
                record = result.scalar_one_or_none()
            if record is None:
                raise RuntimeError("LLM runtime config is not initialized")
            record.base_url = base_url
            record.model = model
            if api_key:
                record.api_key = api_key
            record.temperature = temperature
            record.system_prompt = system_prompt
            record.enabled = bool(base_url and model and record.api_key)
            await session.commit()
            await session.refresh(record)
            return _runtime_from_record(record)

    async def create_or_update_for_tenant(
        self,
        tenant_id: str | None,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float,
        system_prompt: str,
    ) -> tuple[LLMRuntimeConfig, str]:
        async with self._runtime.session() as session:
            if tenant_id:
                result = await session.execute(
                    select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.tenant_id == tenant_id)
                )
            else:
                result = await session.execute(
                    select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.config_key == "default")
                )
            record = result.scalar_one_or_none()
            if record is None:
                effective_api_key = api_key
                if tenant_id and not effective_api_key:
                    result = await session.execute(
                        select(LLMRuntimeConfigRecord).where(LLMRuntimeConfigRecord.config_key == "default")
                    )
                    default_record = result.scalar_one_or_none()
                    effective_api_key = default_record.api_key if default_record else ""
                config_key = f"tenant-{tenant_id}" if tenant_id else "default"
                record = LLMRuntimeConfigRecord(
                    config_key=config_key,
                    tenant_id=tenant_id,
                    provider=provider,
                    base_url=base_url,
                    model=model,
                    api_key=effective_api_key,
                    temperature=temperature,
                    system_prompt=system_prompt,
                    enabled=bool(base_url and model and effective_api_key),
                )
                session.add(record)
            else:
                record.provider = provider
                record.base_url = base_url
                record.model = model
                if api_key:
                    record.api_key = api_key
                record.temperature = temperature
                record.system_prompt = system_prompt
                record.enabled = bool(base_url and model and record.api_key)
            await session.commit()
            await session.refresh(record)
            return _runtime_from_record(record)


async def seed_postgres_defaults(runtime: DatabaseRuntime) -> None:
    async with runtime.session() as session:
        tenant_result = await session.execute(select(TenantRecord).where(TenantRecord.tenant_id == DEFAULT_TENANT_ID))
        if tenant_result.scalar_one_or_none() is None:
            session.add(
                TenantRecord(
                    tenant_record_id="tn-default-sw",
                    tenant_id=DEFAULT_TENANT_ID,
                    name=DEFAULT_TENANT_NAME,
                    package=DEFAULT_TENANT_PACKAGE,
                    environment=DEFAULT_TENANT_ENVIRONMENT,
                    budget=DEFAULT_TENANT_BUDGET,
                    active=True,
                )
            )

        user_result = await session.execute(select(UserAccountRecord).where(UserAccountRecord.user_id == DEFAULT_ADMIN_USER_ID))
        default_admin = user_result.scalar_one_or_none()
        if default_admin is None:
            session.add(
                UserAccountRecord(
                    user_account_id="usr-default-admin",
                    user_id=DEFAULT_ADMIN_USER_ID,
                    tenant_id=DEFAULT_TENANT_ID,
                    email=DEFAULT_ADMIN_EMAIL,
                    password_hash=get_password_hash(DEFAULT_ADMIN_PASSWORD),
                    role="platform_admin",
                    scopes=[
                        "chat:read",
                        "knowledge:read",
                        "hr:read",
                        "workflow:draft",
                        "draft:confirm",
                        "admin:read",
                        "tenant:manage",
                    ],
                )
            )
        elif "tenant:manage" not in default_admin.scopes:
            default_admin.scopes = [*default_admin.scopes, "tenant:manage"]

        existing_event_ids = set((await session.execute(select(SecurityEventRecord.event_id))).scalars().all())
        if "sec-001" not in existing_event_ids:
            session.add(
                SecurityEventRecord(
                    event_id="sec-001",
                    tenant_id=DEFAULT_TENANT_ID,
                    category="approval",
                    severity="high",
                    title="报销提交草稿确认",
                    status="待审批",
                    owner="安全治理组",
                )
            )
        if "sec-002" not in existing_event_ids:
            session.add(
                SecurityEventRecord(
                    event_id="sec-002",
                    tenant_id=DEFAULT_TENANT_ID,
                    category="governance",
                    severity="critical",
                    title="跨租户访问已拦截",
                    status="已阻断",
                    owner="权限治理组",
                )
            )

        source_records = (await session.execute(select(KnowledgeDocumentRecord))).scalars().all()
        for record in source_records:
            if not getattr(record, "knowledge_base_code", None):
                record.knowledge_base_code = "knowledge"

        if await session.get(LLMRuntimeConfigRecord, "default") is None:
            session.add(
                LLMRuntimeConfigRecord(
                    config_key="default",
                    provider="openai-compatible",
                    base_url=settings.llm_base_url or "",
                    model=settings.llm_model or "",
                    api_key=settings.llm_api_key or "",
                    temperature=settings.llm_temperature,
                    system_prompt=settings.llm_system_prompt,
                    enabled=bool(settings.llm_base_url and settings.llm_model and settings.llm_api_key),
                )
            )

        await session.commit()
