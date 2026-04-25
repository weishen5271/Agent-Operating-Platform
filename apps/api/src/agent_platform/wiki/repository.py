from __future__ import annotations

from dataclasses import asdict
from collections import Counter, defaultdict
import re
from uuid import uuid4

from sqlalchemy import delete, desc, select

from agent_platform.domain.models import utc_now
from agent_platform.infrastructure.db import DatabaseRuntime
from agent_platform.infrastructure.db_models import (
    KnowledgeWikiCitationRecord,
    KnowledgeWikiCompileRunRecord,
    KnowledgeWikiPageRecord,
    KnowledgeWikiPageRevisionRecord,
    KnowledgeWikiSourceChunkRecord,
    KnowledgeWikiSourceRecord,
)
from agent_platform.retrieval.text import chunk_text, content_hash, embed_text, tokenize
from agent_platform.wiki.models import (
    WikiCitation,
    WikiCompileRun,
    WikiFileDistributionDetail,
    WikiFileDistributionGroup,
    WikiFileDistributionItem,
    WikiFileDistributionOverview,
    WikiFilePageImpact,
    WikiPage,
    WikiPageRevision,
    WikiSearchHit,
    WikiSearchResult,
)


def _page_from_record(record: KnowledgeWikiPageRecord) -> WikiPage:
    return WikiPage(
        page_id=record.page_id,
        tenant_id=record.tenant_id,
        space_code=record.space_code,
        page_type=record.page_type,
        title=record.title,
        slug=record.slug,
        summary=record.summary,
        content_markdown=record.content_markdown,
        metadata_json=dict(record.metadata_json),
        status=record.status,
        confidence=record.confidence,
        freshness_score=record.freshness_score,
        source_count=record.source_count,
        citation_count=record.citation_count,
        revision_no=record.revision_no,
        created_by=record.created_by,
        updated_by=record.updated_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _revision_from_record(record: KnowledgeWikiPageRevisionRecord) -> WikiPageRevision:
    return WikiPageRevision(
        revision_id=record.revision_id,
        page_id=record.page_id,
        tenant_id=record.tenant_id,
        revision_no=record.revision_no,
        compile_run_id=record.compile_run_id,
        change_type=record.change_type,
        content_markdown=record.content_markdown,
        summary=record.summary,
        change_summary=record.change_summary,
        quality_score=record.quality_score,
        metadata_json=dict(record.metadata_json),
        created_at=record.created_at,
        created_by=record.created_by,
    )


def _citation_from_record(record: KnowledgeWikiCitationRecord) -> WikiCitation:
    return WikiCitation(
        citation_id=record.citation_id,
        tenant_id=record.tenant_id,
        page_id=record.page_id,
        revision_id=record.revision_id,
        section_key=record.section_key,
        claim_text=record.claim_text,
        source_id=record.source_id,
        chunk_id=record.chunk_id,
        evidence_snippet=record.evidence_snippet,
        support_type=record.support_type,
        created_at=record.created_at,
    )


def _compile_run_from_record(record: KnowledgeWikiCompileRunRecord) -> WikiCompileRun:
    return WikiCompileRun(
        compile_run_id=record.compile_run_id,
        tenant_id=record.tenant_id,
        trigger_type=record.trigger_type,
        status=record.status,
        scope_type=record.scope_type,
        scope_value=record.scope_value,
        input_source_ids=list(record.input_source_ids),
        input_chunk_ids=list(record.input_chunk_ids),
        affected_page_ids=list(record.affected_page_ids),
        summary=record.summary,
        error_message=record.error_message,
        token_usage=record.token_usage,
        started_at=record.started_at,
        finished_at=record.finished_at,
        created_by=record.created_by,
        created_at=record.created_at,
    )


class PostgresWikiRepository:
    def __init__(
        self,
        runtime: DatabaseRuntime,
        *,
        llm_config=None,
        embedding_client=None,
    ) -> None:
        self._runtime = runtime
        self._llm_config = llm_config
        self._embedding_client = embedding_client

    async def _embed_texts(
        self, *, tenant_id: str | None, texts: list[str]
    ) -> tuple[list[list[float]], str | None]:
        if not texts:
            return [], None
        if self._llm_config is None or self._embedding_client is None:
            return [[] for _ in texts], None
        try:
            config, api_key = await self._llm_config.get_embedding_credentials(tenant_id=tenant_id)
        except Exception:
            return [[] for _ in texts], None
        if not config.embedding_enabled or not api_key:
            return [[] for _ in texts], None
        try:
            vectors = self._embedding_client.embed(config=config, api_key=api_key, texts=texts)
        except Exception:
            return [[] for _ in texts], None
        return vectors, config.embedding_model

    async def list_pages(
        self,
        *,
        tenant_id: str,
        status: str | None = None,
        page_type: str | None = None,
        space_code: str | None = None,
        limit: int = 50,
    ) -> list[WikiPage]:
        async with self._runtime.session() as session:
            stmt = (
                select(KnowledgeWikiPageRecord)
                .where(KnowledgeWikiPageRecord.tenant_id == tenant_id)
                .order_by(desc(KnowledgeWikiPageRecord.updated_at))
                .limit(limit)
            )
            if status:
                stmt = stmt.where(KnowledgeWikiPageRecord.status == status)
            if page_type:
                stmt = stmt.where(KnowledgeWikiPageRecord.page_type == page_type)
            if space_code:
                stmt = stmt.where(KnowledgeWikiPageRecord.space_code == space_code)
            result = await session.execute(stmt)
            return [_page_from_record(item) for item in result.scalars().all()]

    async def get_page(self, *, tenant_id: str, page_id: str) -> WikiPage | None:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiPageRecord)
                .where(KnowledgeWikiPageRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiPageRecord.page_id == page_id)
            )
            record = result.scalar_one_or_none()
            return _page_from_record(record) if record else None

    async def list_page_revisions(self, *, tenant_id: str, page_id: str) -> list[WikiPageRevision]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiPageRevisionRecord)
                .where(KnowledgeWikiPageRevisionRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiPageRevisionRecord.page_id == page_id)
                .order_by(desc(KnowledgeWikiPageRevisionRecord.revision_no))
            )
            return [_revision_from_record(item) for item in result.scalars().all()]

    async def list_page_citations(self, *, tenant_id: str, page_id: str) -> list[WikiCitation]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiCitationRecord)
                .where(KnowledgeWikiCitationRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiCitationRecord.page_id == page_id)
                .order_by(desc(KnowledgeWikiCitationRecord.created_at))
            )
            return [_citation_from_record(item) for item in result.scalars().all()]

    async def list_compile_runs(self, *, tenant_id: str, limit: int = 20) -> list[WikiCompileRun]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiCompileRunRecord)
                .where(KnowledgeWikiCompileRunRecord.tenant_id == tenant_id)
                .order_by(desc(KnowledgeWikiCompileRunRecord.created_at))
                .limit(limit)
            )
            return [_compile_run_from_record(item) for item in result.scalars().all()]

    async def get_compile_run(self, *, tenant_id: str, compile_run_id: str) -> WikiCompileRun | None:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiCompileRunRecord)
                .where(KnowledgeWikiCompileRunRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiCompileRunRecord.compile_run_id == compile_run_id)
            )
            record = result.scalar_one_or_none()
            return _compile_run_from_record(record) if record else None

    async def search_pages(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int = 5,
        space_code: str | None = None,
    ) -> WikiSearchResult:
        terms = tokenize(query)
        normalized_query = query.strip().lower()
        async with self._runtime.session() as session:
            page_stmt = (
                select(KnowledgeWikiPageRecord)
                .where(KnowledgeWikiPageRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiPageRecord.status == "published")
            )
            revision_stmt = (
                select(KnowledgeWikiPageRevisionRecord)
                .where(KnowledgeWikiPageRevisionRecord.tenant_id == tenant_id)
                .order_by(desc(KnowledgeWikiPageRevisionRecord.revision_no))
            )
            citation_stmt = (
                select(KnowledgeWikiCitationRecord)
                .where(KnowledgeWikiCitationRecord.tenant_id == tenant_id)
            )
            if space_code:
                page_stmt = page_stmt.where(KnowledgeWikiPageRecord.space_code == space_code)
            page_result = await session.execute(page_stmt.order_by(desc(KnowledgeWikiPageRecord.updated_at)))
            revision_result = await session.execute(revision_stmt)
            citation_result = await session.execute(citation_stmt.order_by(desc(KnowledgeWikiCitationRecord.created_at)))

        pages = list(page_result.scalars().all())
        revisions = list(revision_result.scalars().all())
        citations = list(citation_result.scalars().all())
        latest_revision_by_page: dict[str, KnowledgeWikiPageRevisionRecord] = {}
        for revision in revisions:
            latest_revision_by_page.setdefault(revision.page_id, revision)
        citations_by_page: dict[str, list[KnowledgeWikiCitationRecord]] = {}
        for citation in citations:
            citations_by_page.setdefault(citation.page_id, []).append(citation)

        hits: list[WikiSearchHit] = []
        for page in pages:
            citations_for_page = citations_by_page.get(page.page_id, [])
            page_score = self._score_page(page=page, terms=terms, normalized_query=normalized_query)
            best_citation = self._best_citation(
                citations=citations_for_page,
                terms=terms,
                normalized_query=normalized_query,
            )
            citation_score = best_citation[1] if best_citation else 0.0
            score = page_score + citation_score
            if score <= 0:
                continue

            revision = latest_revision_by_page.get(page.page_id)
            citation = best_citation[0] if best_citation else None
            snippet = self._build_snippet(
                content="\n".join(
                    part
                    for part in (
                        page.summary,
                        page.content_markdown,
                        citation.claim_text if citation else "",
                        citation.evidence_snippet if citation else "",
                    )
                    if part
                ),
                normalized_query=normalized_query,
                terms=terms,
            )
            claim_text = citation.claim_text if citation else page.summary
            evidence = citation.evidence_snippet if citation else snippet
            hits.append(
                WikiSearchHit(
                    page_id=page.page_id,
                    revision_id=revision.revision_id if revision else None,
                    revision_no=page.revision_no,
                    title=page.title,
                    summary=page.summary,
                    snippet=snippet,
                    citation_id=citation.citation_id if citation else None,
                    claim_text=claim_text,
                    evidence_snippet=evidence,
                    source_id=citation.source_id if citation else None,
                    chunk_id=citation.chunk_id if citation else None,
                    score=round(score, 4),
                    locator=(
                        f"wiki:{page.slug}#citation:{citation.citation_id}"
                        if citation
                        else f"wiki:{page.slug}"
                    ),
                )
            )

        hits.sort(key=lambda item: item.score, reverse=True)
        return WikiSearchResult(
            hits=hits[:top_k],
            backend="wiki_page_citation_hybrid",
            query=query,
            candidate_count=len(pages),
            match_count=min(len(hits), top_k),
        )

    async def create_compile_run(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        scope_type: str,
        scope_value: str,
        input_source_ids: list[str],
        input_chunk_ids: list[str],
        created_by: str,
    ) -> WikiCompileRun:
        compile_run = WikiCompileRun(
            compile_run_id=f"wcr-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            status="running",
            scope_type=scope_type,
            scope_value=scope_value,
            input_source_ids=input_source_ids,
            input_chunk_ids=input_chunk_ids,
            started_at=utc_now(),
            created_by=created_by,
        )
        async with self._runtime.session() as session:
            session.add(KnowledgeWikiCompileRunRecord(**asdict(compile_run)))
            await session.commit()
        return compile_run

    async def complete_compile_run(
        self,
        *,
        tenant_id: str,
        compile_run_id: str,
        affected_page_ids: list[str],
        summary: str,
        token_usage: int = 0,
    ) -> WikiCompileRun:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiCompileRunRecord)
                .where(KnowledgeWikiCompileRunRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiCompileRunRecord.compile_run_id == compile_run_id)
            )
            record = result.scalar_one()
            record.status = "completed"
            record.affected_page_ids = affected_page_ids
            record.summary = summary
            record.token_usage = token_usage
            record.finished_at = utc_now()
            await session.commit()
            await session.refresh(record)
            return _compile_run_from_record(record)

    async def fail_compile_run(self, *, tenant_id: str, compile_run_id: str, error_message: str) -> WikiCompileRun:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiCompileRunRecord)
                .where(KnowledgeWikiCompileRunRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiCompileRunRecord.compile_run_id == compile_run_id)
            )
            record = result.scalar_one()
            record.status = "failed"
            record.error_message = error_message
            record.finished_at = utc_now()
            await session.commit()
            await session.refresh(record)
            return _compile_run_from_record(record)

    async def list_sources(self, *, tenant_id: str, source_id: str | None = None) -> list[KnowledgeWikiSourceRecord]:
        async with self._runtime.session() as session:
            stmt = (
                select(KnowledgeWikiSourceRecord)
                .where(KnowledgeWikiSourceRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiSourceRecord.status == "运行中")
                .order_by(KnowledgeWikiSourceRecord.source_id)
            )
            if source_id:
                stmt = stmt.where(KnowledgeWikiSourceRecord.source_id == source_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def ingest_text(
        self,
        *,
        tenant_id: str,
        name: str,
        content: str,
        source_type: str,
        owner: str,
        knowledge_base_code: str,
    ) -> KnowledgeWikiSourceRecord:
        chunked = chunk_text(content)
        if not chunked:
            raise ValueError("Wiki source content is empty after parsing")

        normalized = [
            piece if isinstance(piece, dict) else {"content": piece, "parents": [], "locator": ""}
            for piece in chunked
        ]
        contents = [item["content"] for item in normalized]
        vectors, embedding_model = await self._embed_texts(tenant_id=tenant_id, texts=contents)

        source_id = f"wks-{uuid4().hex[:12]}"
        async with self._runtime.session() as session:
            document = KnowledgeWikiSourceRecord(
                source_id=source_id,
                tenant_id=tenant_id,
                knowledge_base_code=knowledge_base_code,
                name=name,
                source_type=source_type,
                owner=owner,
                chunk_count=len(contents),
                status="运行中",
            )
            session.add(document)
            for index, item in enumerate(normalized):
                vec = vectors[index] if index < len(vectors) else []
                session.add(
                    KnowledgeWikiSourceChunkRecord(
                        chunk_id=f"wkc-{uuid4().hex[:12]}",
                        source_id=source_id,
                        tenant_id=tenant_id,
                        chunk_index=index,
                        title=name,
                        content=item["content"],
                        content_hash=content_hash(item["content"]),
                        embedding=vec or [],
                        metadata_json={
                            "version": "v1",
                            "classification": "internal",
                            "locator": item.get("locator") or f"chunk:{index + 1}",
                            "parents": item.get("parents") or [],
                        },
                        token_count=len(tokenize(item["content"])),
                        status="published",
                        embedding_status="ready" if vec else "pending",
                        embedding_model=embedding_model or "",
                    )
                )
            await session.commit()
            await session.refresh(document)
            return document

    async def get_file_distribution_overview(self, *, tenant_id: str, space_code: str | None = None) -> WikiFileDistributionOverview:
        sources, pages, citations, runs = await self._load_distribution_records(tenant_id=tenant_id, space_code=space_code)
        latest_run = self._latest_completed_run(runs)
        compiled_source_ids = self._compiled_source_ids(runs, citations)
        citations_by_source = self._citations_by_source(citations)
        source_ids_by_page = self._source_ids_by_page(citations)
        items = [
            self._build_distribution_item(
                source=source,
                citation_records=citations_by_source.get(source.source_id, []),
                compiled_source_ids=compiled_source_ids,
                latest_run=latest_run,
            )
            for source in sources
        ]
        compiled_count = sum(1 for item in items if item.compiled)
        uncovered_count = sum(1 for item in items if item.coverage_status in {"已入库未编译", "已编译未命中页面"})
        high_impact_count = sum(1 for item in items if item.coverage_status == "高影响")
        avg_pages_per_source = (
            round(sum(item.page_count for item in items) / len(items), 2) if items else 0.0
        )
        avg_sources_per_page = (
            round(sum(len(source_ids_by_page.get(page.page_id, set())) for page in pages) / len(pages), 2)
            if pages
            else 0.0
        )
        return WikiFileDistributionOverview(
            total_sources=len(sources),
            compiled_sources=compiled_count,
            uncovered_sources=uncovered_count,
            high_impact_sources=high_impact_count,
            total_pages=len(pages),
            total_citations=len(citations),
            avg_pages_per_source=avg_pages_per_source,
            avg_sources_per_page=avg_sources_per_page,
            latest_compile_run_id=latest_run.compile_run_id if latest_run else None,
            latest_compile_finished_at=latest_run.finished_at if latest_run else None,
        )

    async def list_file_distribution(
        self,
        *,
        tenant_id: str,
        space_code: str | None = None,
        group_by: str = "source_type",
        coverage_status: str | None = None,
        source_type: str | None = None,
        owner: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[WikiFileDistributionGroup], list[WikiFileDistributionItem]]:
        sources, _, citations, runs = await self._load_distribution_records(tenant_id=tenant_id, space_code=space_code)
        latest_run = self._latest_completed_run(runs)
        compiled_source_ids = self._compiled_source_ids(runs, citations)
        citations_by_source = self._citations_by_source(citations)

        items = [
            self._build_distribution_item(
                source=source,
                citation_records=citations_by_source.get(source.source_id, []),
                compiled_source_ids=compiled_source_ids,
                latest_run=latest_run,
            )
            for source in sources
        ]
        filtered_items = [
            item
            for item in items
            if (not coverage_status or item.coverage_status == coverage_status)
            and (not source_type or item.source_type == source_type)
            and (not owner or item.owner == owner)
            and (not keyword or keyword.lower() in f"{item.source_name} {item.group_path}".lower())
        ]
        filtered_items.sort(key=lambda item: (item.hotspot_score, item.citation_count, item.chunk_count), reverse=True)

        groups_by_key: dict[str, list[WikiFileDistributionItem]] = defaultdict(list)
        for item in filtered_items:
            group_key = self._distribution_group_key(item=item, group_by=group_by)
            groups_by_key[group_key].append(item)

        groups: list[WikiFileDistributionGroup] = []
        for group_key, members in groups_by_key.items():
            status_counter = Counter(item.coverage_status for item in members)
            groups.append(
                WikiFileDistributionGroup(
                    group_key=group_key,
                    group_label=group_key,
                    source_count=len(members),
                    compiled_count=sum(1 for item in members if item.compiled),
                    uncovered_count=sum(
                        1
                        for item in members
                        if item.coverage_status in {"已入库未编译", "已编译未命中页面"}
                    ),
                    citation_count=sum(item.citation_count for item in members),
                    page_count=sum(item.page_count for item in members),
                    dominant_status=status_counter.most_common(1)[0][0] if status_counter else "未知",
                )
            )
        groups.sort(key=lambda item: (item.source_count, item.citation_count), reverse=True)
        return groups, filtered_items

    async def get_file_distribution_detail(
        self,
        *,
        tenant_id: str,
        source_id: str,
        space_code: str | None = None,
    ) -> WikiFileDistributionDetail | None:
        sources, pages, citations, runs = await self._load_distribution_records(tenant_id=tenant_id, space_code=space_code)
        source = next((item for item in sources if item.source_id == source_id), None)
        if source is None:
            return None
        latest_run = self._latest_completed_run(runs)
        compiled_source_ids = self._compiled_source_ids(runs, citations)
        citations_by_source = self._citations_by_source(citations)
        page_by_id = {page.page_id: page for page in pages}
        source_citations = citations_by_source.get(source_id, [])
        item = self._build_distribution_item(
            source=source,
            citation_records=source_citations,
            compiled_source_ids=compiled_source_ids,
            latest_run=latest_run,
        )
        page_counter: Counter[str] = Counter(citation.page_id for citation in source_citations)
        related_pages = [
            WikiFilePageImpact(
                page_id=page_id,
                title=page_by_id[page_id].title,
                slug=page_by_id[page_id].slug,
                citation_count=count,
                contribution_score=round(count / max(item.citation_count, 1), 2),
            )
            for page_id, count in page_counter.most_common()
            if page_id in page_by_id
        ]
        diagnostic_tags = self._diagnostic_tags(item=item, page_counter=page_counter)
        return WikiFileDistributionDetail(
            item=item,
            related_pages=related_pages,
            diagnostic_tags=diagnostic_tags,
        )

    async def list_source_chunks(self, *, tenant_id: str, source_id: str) -> list[KnowledgeWikiSourceChunkRecord]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiSourceChunkRecord)
                .where(KnowledgeWikiSourceChunkRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiSourceChunkRecord.source_id == source_id)
                .where(KnowledgeWikiSourceChunkRecord.status == "published")
                .order_by(KnowledgeWikiSourceChunkRecord.chunk_index)
            )
            return list(result.scalars().all())

    async def save_page_bundle(
        self,
        *,
        tenant_id: str,
        slug: str,
        space_code: str,
        page_type: str,
        title: str,
        summary: str,
        content_markdown: str,
        metadata_json: dict,
        confidence: str,
        freshness_score: float,
        created_by: str,
        compile_run_id: str,
        change_summary: str,
        quality_score: float,
        citations: list[dict[str, str]],
    ) -> tuple[WikiPage, WikiPageRevision, list[WikiCitation]]:
        async with self._runtime.session() as session:
            result = await session.execute(
                select(KnowledgeWikiPageRecord)
                .where(KnowledgeWikiPageRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiPageRecord.slug == slug)
            )
            record = result.scalar_one_or_none()
            now = utc_now()
            is_new = record is None
            if record is None:
                record = KnowledgeWikiPageRecord(
                    page_id=f"wp-{uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    space_code=space_code,
                    page_type=page_type,
                    title=title,
                    slug=slug,
                    created_by=created_by,
                    updated_by=created_by,
                )
                session.add(record)
                await session.flush()

            revision_no = record.revision_no + 1
            record.space_code = space_code
            record.page_type = page_type
            record.title = title
            record.summary = summary
            record.content_markdown = content_markdown
            record.metadata_json = metadata_json
            record.status = "published"
            record.confidence = confidence
            record.freshness_score = freshness_score
            record.source_count = len(set(metadata_json.get("source_ids", [])))
            record.citation_count = len(citations)
            record.revision_no = revision_no
            record.updated_by = created_by
            record.updated_at = now

            revision_record = KnowledgeWikiPageRevisionRecord(
                revision_id=f"wpr-{uuid4().hex[:12]}",
                page_id=record.page_id,
                tenant_id=tenant_id,
                revision_no=revision_no,
                compile_run_id=compile_run_id,
                change_type="create" if is_new else "update",
                content_markdown=content_markdown,
                summary=summary,
                change_summary=change_summary,
                quality_score=quality_score,
                metadata_json=metadata_json,
                created_at=now,
                created_by=created_by,
            )
            session.add(revision_record)

            await session.execute(
                delete(KnowledgeWikiCitationRecord)
                .where(KnowledgeWikiCitationRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiCitationRecord.page_id == record.page_id)
            )
            citation_records: list[KnowledgeWikiCitationRecord] = []
            for citation in citations:
                citation_record = KnowledgeWikiCitationRecord(
                    citation_id=f"wct-{uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    page_id=record.page_id,
                    revision_id=revision_record.revision_id,
                    section_key=citation["section_key"],
                    claim_text=citation["claim_text"],
                    source_id=citation["source_id"],
                    chunk_id=citation["chunk_id"],
                    evidence_snippet=citation["evidence_snippet"],
                    support_type=citation.get("support_type", "direct"),
                )
                citation_records.append(citation_record)
            session.add_all(citation_records)
            await session.commit()
            await session.refresh(record)
            await session.refresh(revision_record)

            return (
                _page_from_record(record),
                _revision_from_record(revision_record),
                [_citation_from_record(item) for item in citation_records],
            )

    @staticmethod
    def _score_page(
        *,
        page: KnowledgeWikiPageRecord,
        terms: list[str],
        normalized_query: str,
    ) -> float:
        score = 0.0
        title = page.title.lower()
        summary = page.summary.lower()
        content = page.content_markdown.lower()
        if normalized_query:
            if normalized_query in title:
                score += 15.0
            if normalized_query in summary:
                score += 10.0
            if normalized_query in content:
                score += 8.0
        for term in terms:
            if term in title:
                score += 4.0
            if term in summary:
                score += 3.0
            if term in content:
                score += min(content.count(term), 4)
        return score

    @staticmethod
    def _best_citation(
        *,
        citations: list[KnowledgeWikiCitationRecord],
        terms: list[str],
        normalized_query: str,
    ) -> tuple[KnowledgeWikiCitationRecord, float] | None:
        scored: list[tuple[KnowledgeWikiCitationRecord, float]] = []
        for citation in citations:
            score = 0.0
            claim = citation.claim_text.lower()
            evidence = citation.evidence_snippet.lower()
            if normalized_query:
                if normalized_query in claim:
                    score += 10.0
                if normalized_query in evidence:
                    score += 6.0
            for term in terms:
                if term in claim:
                    score += 3.0
                if term in evidence:
                    score += min(evidence.count(term), 3)
            if score > 0:
                scored.append((citation, score))
        if not scored:
            return None
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[0]

    @staticmethod
    def _build_snippet(content: str, *, normalized_query: str, terms: list[str]) -> str:
        normalized = re.sub(r"\s+", " ", content).strip()
        if not normalized:
            return ""
        index = normalized.lower().find(normalized_query) if normalized_query else -1
        if index == -1:
            for term in terms:
                index = normalized.lower().find(term)
                if index != -1:
                    break
        if index == -1:
            return normalized[:180]
        start = max(index - 60, 0)
        end = min(index + 160, len(normalized))
        return normalized[start:end]

    async def _load_distribution_records(
        self,
        *,
        tenant_id: str,
        space_code: str | None = None,
    ) -> tuple[
        list[KnowledgeWikiSourceRecord],
        list[KnowledgeWikiPageRecord],
        list[KnowledgeWikiCitationRecord],
        list[KnowledgeWikiCompileRunRecord],
    ]:
        async with self._runtime.session() as session:
            source_stmt = (
                select(KnowledgeWikiSourceRecord)
                .where(KnowledgeWikiSourceRecord.tenant_id == tenant_id)
                .order_by(
                    KnowledgeWikiSourceRecord.source_type,
                    KnowledgeWikiSourceRecord.owner,
                    KnowledgeWikiSourceRecord.name,
                )
            )
            if space_code:
                source_stmt = source_stmt.where(KnowledgeWikiSourceRecord.knowledge_base_code == space_code)
            source_result = await session.execute(source_stmt)
            page_stmt = (
                select(KnowledgeWikiPageRecord)
                .where(KnowledgeWikiPageRecord.tenant_id == tenant_id)
                .where(KnowledgeWikiPageRecord.status == "published")
            )
            if space_code:
                page_stmt = page_stmt.where(KnowledgeWikiPageRecord.space_code == space_code)
            page_result = await session.execute(page_stmt)
            citation_result = await session.execute(
                select(KnowledgeWikiCitationRecord)
                .where(KnowledgeWikiCitationRecord.tenant_id == tenant_id)
            )
            run_result = await session.execute(
                select(KnowledgeWikiCompileRunRecord)
                .where(KnowledgeWikiCompileRunRecord.tenant_id == tenant_id)
                .order_by(desc(KnowledgeWikiCompileRunRecord.created_at))
            )
        sources = list(source_result.scalars().all())
        pages = list(page_result.scalars().all())
        source_ids = {item.source_id for item in sources}
        page_ids = {item.page_id for item in pages}
        citations = [
            item
            for item in citation_result.scalars().all()
            if item.source_id in source_ids and item.page_id in page_ids
        ]
        return (
            sources,
            pages,
            citations,
            list(run_result.scalars().all()),
        )

    @staticmethod
    def _latest_completed_run(runs: list[KnowledgeWikiCompileRunRecord]) -> KnowledgeWikiCompileRunRecord | None:
        return next((run for run in runs if run.status == "completed"), None)

    @staticmethod
    def _citations_by_source(
        citations: list[KnowledgeWikiCitationRecord],
    ) -> dict[str, list[KnowledgeWikiCitationRecord]]:
        grouped: dict[str, list[KnowledgeWikiCitationRecord]] = defaultdict(list)
        for citation in citations:
            grouped[citation.source_id].append(citation)
        return grouped

    @staticmethod
    def _source_ids_by_page(
        citations: list[KnowledgeWikiCitationRecord],
    ) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = defaultdict(set)
        for citation in citations:
            grouped[citation.page_id].add(citation.source_id)
        return grouped

    @staticmethod
    def _compiled_source_ids(
        runs: list[KnowledgeWikiCompileRunRecord],
        citations: list[KnowledgeWikiCitationRecord],
    ) -> set[str]:
        compiled: set[str] = {citation.source_id for citation in citations}
        for run in runs:
            if run.status == "completed":
                compiled.update(run.input_source_ids)
        return compiled

    @staticmethod
    def _build_distribution_item(
        *,
        source: KnowledgeWikiSourceRecord,
        citation_records: list[KnowledgeWikiCitationRecord],
        compiled_source_ids: set[str],
        latest_run: KnowledgeWikiCompileRunRecord | None,
    ) -> WikiFileDistributionItem:
        page_ids = {citation.page_id for citation in citation_records}
        citation_count = len(citation_records)
        page_count = len(page_ids)
        compiled = source.source_id in compiled_source_ids
        hotspot_score = round((page_count * 2) + (citation_count * 0.8), 2)
        distribution_score = round(min(100.0, (page_count * 20) + (citation_count * 6)), 2)
        if not compiled:
            coverage_status = "已入库未编译"
        elif citation_count == 0:
            coverage_status = "已编译未命中页面"
        elif page_count >= 3 or citation_count >= 5:
            coverage_status = "高影响"
        else:
            coverage_status = "已进入页面"
        return WikiFileDistributionItem(
            source_id=source.source_id,
            tenant_id=source.tenant_id,
            source_name=source.name,
            source_type=source.source_type,
            owner=source.owner,
            group_path=f"{source.source_type}/{source.owner}",
            chunk_count=source.chunk_count,
            status=source.status,
            coverage_status=coverage_status,
            compiled=compiled,
            page_count=page_count,
            citation_count=citation_count,
            distribution_score=distribution_score,
            hotspot_score=hotspot_score,
            latest_compile_run_id=latest_run.compile_run_id if latest_run else None,
            latest_compile_finished_at=latest_run.finished_at if latest_run else None,
        )

    @staticmethod
    def _distribution_group_key(*, item: WikiFileDistributionItem, group_by: str) -> str:
        if group_by == "owner":
            return item.owner
        if group_by == "status":
            return item.coverage_status
        if group_by == "group_path":
            return item.group_path
        return item.source_type

    @staticmethod
    def _diagnostic_tags(*, item: WikiFileDistributionItem, page_counter: Counter[str]) -> list[str]:
        tags: list[str] = []
        if not item.compiled:
            tags.append("uncompiled")
        if item.compiled and item.citation_count == 0:
            tags.append("orphan")
        if item.coverage_status == "高影响":
            tags.append("hotspot")
        if item.page_count > 0 and page_counter:
            top_page_share = page_counter.most_common(1)[0][1] / max(item.citation_count, 1)
            if top_page_share >= 0.7:
                tags.append("over_concentrated")
            else:
                tags.append("healthy")
        return tags
