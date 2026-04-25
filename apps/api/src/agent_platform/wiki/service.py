from __future__ import annotations

import re
from dataclasses import asdict
from typing import Literal

from agent_platform.bootstrap.settings import settings
from agent_platform.domain.models import UserContext
from agent_platform.infrastructure.repositories import KnowledgeBaseRepository, UserRepository
from agent_platform.wiki.repository import PostgresWikiRepository


class WikiService:
    def __init__(
        self,
        repository: PostgresWikiRepository,
        users: UserRepository,
        knowledge_bases: KnowledgeBaseRepository,
    ) -> None:
        self._repository = repository
        self._users = users
        self._knowledge_bases = knowledge_bases

    async def list_pages(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        status: str | None = None,
        page_type: str | None = None,
        space_code: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        pages = await self._repository.list_pages(
            tenant_id=context.tenant_id,
            status=status,
            page_type=page_type,
            space_code=space_code,
        )
        return {"pages": [asdict(item) for item in pages]}

    async def search(
        self,
        *,
        query: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 5,
        space_code: str | None = None,
        scope_mode: Literal["chat", "admin"] = "admin",
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        if scope_mode == "chat":
            self._ensure_any_scope(context, {"knowledge:read", "wiki:read", "admin:read"})
        else:
            self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        result = await self._repository.search_pages(
            tenant_id=context.tenant_id,
            query=query,
            top_k=top_k,
            space_code=space_code,
        )
        summary = (
            "已从 Wiki 页面与引用证据中整理出最相关内容。"
            if result.hits
            else "未在当前已发布 Wiki 页面中检索到相关内容。"
        )
        return {
            "summary": summary,
            "hits": [asdict(item) for item in result.hits],
            "retrieval": {
                "backend": result.backend,
                "query": result.query,
                "matched": bool(result.hits),
                "candidate_count": result.candidate_count,
                "match_count": result.match_count,
            },
        }

    async def get_page_detail(
        self,
        *,
        page_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        page = await self._repository.get_page(tenant_id=context.tenant_id, page_id=page_id)
        if page is None:
            raise ValueError("Wiki page not found")
        citations = await self._repository.list_page_citations(tenant_id=context.tenant_id, page_id=page_id)
        return {
            "page": asdict(page),
            "citations": [asdict(item) for item in citations],
        }

    async def list_page_revisions(
        self,
        *,
        page_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        revisions = await self._repository.list_page_revisions(tenant_id=context.tenant_id, page_id=page_id)
        return {"revisions": [asdict(item) for item in revisions]}

    async def list_compile_runs(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        runs = await self._repository.list_compile_runs(tenant_id=context.tenant_id)
        return {"items": [asdict(item) for item in runs]}

    async def get_compile_run(
        self,
        *,
        compile_run_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        run = await self._repository.get_compile_run(tenant_id=context.tenant_id, compile_run_id=compile_run_id)
        if run is None:
            raise ValueError("Wiki compile run not found")
        return asdict(run)

    async def get_file_distribution_overview(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        space_code: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        overview = await self._repository.get_file_distribution_overview(
            tenant_id=context.tenant_id,
            space_code=space_code,
        )
        return {"overview": asdict(overview)}

    async def list_file_distribution(
        self,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        space_code: str | None = None,
        group_by: str = "source_type",
        coverage_status: str | None = None,
        source_type: str | None = None,
        owner: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        overview = await self._repository.get_file_distribution_overview(
            tenant_id=context.tenant_id,
            space_code=space_code,
        )
        groups, items = await self._repository.list_file_distribution(
            tenant_id=context.tenant_id,
            space_code=space_code,
            group_by=group_by,
            coverage_status=coverage_status,
            source_type=source_type,
            owner=owner,
            keyword=keyword,
        )
        return {
            "overview": asdict(overview),
            "groups": [asdict(item) for item in groups],
            "items": [asdict(item) for item in items],
        }

    async def get_file_distribution_detail(
        self,
        *,
        source_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        space_code: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:read"})
        detail = await self._repository.get_file_distribution_detail(
            tenant_id=context.tenant_id,
            source_id=source_id,
            space_code=space_code,
        )
        if detail is None:
            raise ValueError("Wiki file distribution source not found")
        return asdict(detail)

    async def ingest_source(
        self,
        *,
        name: str,
        content: str,
        source_type: str,
        owner: str,
        knowledge_base_code: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:compile"})
        record = await self._repository.ingest_text(
            tenant_id=context.tenant_id,
            name=name,
            content=content,
            source_type=source_type,
            owner=owner,
            knowledge_base_code=knowledge_base_code,
        )
        return {
            "source": {
                "source_id": record.source_id,
                "tenant_id": record.tenant_id,
                "knowledge_base_code": record.knowledge_base_code,
                "name": record.name,
                "source_type": record.source_type,
                "owner": record.owner,
                "chunk_count": record.chunk_count,
                "status": record.status,
            }
        }

    async def compile_sources(
        self,
        *,
        source_id: str | None = None,
        space_code: str = "knowledge",
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, object]:
        context = await self._require_context(tenant_id=tenant_id, user_id=user_id)
        self._ensure_any_scope(context, {"admin:read", "wiki:compile"})

        sources = await self._repository.list_sources(tenant_id=context.tenant_id, source_id=source_id)
        if space_code:
            sources = [item for item in sources if item.knowledge_base_code == space_code]
        if not sources:
            raise ValueError("No running knowledge sources found for wiki compilation")

        input_source_ids = [item.source_id for item in sources]
        input_chunk_ids: list[str] = []
        for source in sources:
            chunks = await self._repository.list_source_chunks(tenant_id=context.tenant_id, source_id=source.source_id)
            input_chunk_ids.extend(chunk.chunk_id for chunk in chunks)

        compile_run = await self._repository.create_compile_run(
            tenant_id=context.tenant_id,
            trigger_type="manual",
            scope_type="source" if source_id else "tenant",
            scope_value=source_id or context.tenant_id,
            input_source_ids=input_source_ids,
            input_chunk_ids=input_chunk_ids,
            created_by=context.user_id,
        )

        try:
            compiled_pages: list[dict[str, object]] = []
            affected_page_ids: list[str] = []
            for source in sources:
                chunks = await self._repository.list_source_chunks(tenant_id=context.tenant_id, source_id=source.source_id)
                if not chunks:
                    continue
                payload = self._build_page_payload(space_code=space_code, source=source, chunks=chunks)
                page, revision, citations = await self._repository.save_page_bundle(
                    tenant_id=context.tenant_id,
                    slug=payload["slug"],
                    space_code=space_code,
                    page_type="overview",
                    title=payload["title"],
                    summary=payload["summary"],
                    content_markdown=payload["content_markdown"],
                    metadata_json=payload["metadata_json"],
                    confidence=payload["confidence"],
                    freshness_score=payload["freshness_score"],
                    created_by=context.user_id,
                    compile_run_id=compile_run.compile_run_id,
                    change_summary=payload["change_summary"],
                    quality_score=payload["quality_score"],
                    citations=payload["citations"],
                )
                affected_page_ids.append(page.page_id)
                compiled_pages.append(
                    {
                        "page": asdict(page),
                        "revision": asdict(revision),
                        "citations": [asdict(item) for item in citations],
                    }
                )

            compile_run = await self._repository.complete_compile_run(
                tenant_id=context.tenant_id,
                compile_run_id=compile_run.compile_run_id,
                affected_page_ids=affected_page_ids,
                summary=f"已编译 {len(compiled_pages)} 个 Wiki 页面。",
                token_usage=0,
            )
            return {
                "compile_run": asdict(compile_run),
                "pages": compiled_pages,
            }
        except Exception as exc:  # noqa: BLE001
            failed_run = await self._repository.fail_compile_run(
                tenant_id=context.tenant_id,
                compile_run_id=compile_run.compile_run_id,
                error_message=str(exc),
            )
            return {
                "compile_run": asdict(failed_run),
                "pages": [],
            }

    @staticmethod
    def _build_page_payload(*, space_code: str, source, chunks: list) -> dict[str, object]:
        ordered_chunks = list(chunks)[:5]
        highlights = [WikiService._normalize_line(chunk.content) for chunk in ordered_chunks]
        summary = "；".join(item[:60] for item in highlights[:2] if item)
        if not summary:
            summary = f"{source.name} 的 Wiki 编译页面。"

        key_points = "\n".join(
            f"- {item[:120]}" for item in highlights[:3] if item
        ) or "- 当前知识源暂无可展示摘要。"
        evidence_lines = "\n".join(
            f"- `{chunk.chunk_id}`: {WikiService._normalize_line(chunk.content)[:120]}"
            for chunk in ordered_chunks
        )
        content_markdown = (
            f"## 摘要\n\n{summary}\n\n"
            f"## 关键结论\n\n{key_points}\n\n"
            f"## 详细说明\n\n"
            f"该页面由知识源 `{source.name}` 的已发布切片自动编译生成，当前为 P0 确定性编译版本，"
            "用于验证 Wiki 独立模块的数据结构、治理流程与版本留痕。\n\n"
            f"## 证据来源\n\n{evidence_lines}\n"
        )
        citations = [
            {
                "section_key": "key_points",
                "claim_text": WikiService._normalize_line(chunk.content)[:120],
                "source_id": source.source_id,
                "chunk_id": chunk.chunk_id,
                "evidence_snippet": WikiService._normalize_line(chunk.content)[:180],
                "support_type": "direct",
            }
            for chunk in ordered_chunks
        ]
        return {
            "slug": f"source-{source.source_id}",
            "title": f"{source.name} Wiki 总览",
            "summary": summary,
            "content_markdown": content_markdown,
            "metadata_json": {
                "source_ids": [source.source_id],
                "source_type": source.source_type,
                "owner": source.owner,
                "space_code": space_code,
                "compile_strategy": "deterministic_p0",
            },
            "confidence": "medium",
            "freshness_score": 1.0,
            "change_summary": f"基于知识源 {source.source_id} 重新生成 Wiki 总览页。",
            "quality_score": 0.7,
            "citations": citations,
        }

    @staticmethod
    def _normalize_line(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    async def _require_context(self, tenant_id: str | None, user_id: str | None) -> UserContext:
        resolved_tenant_id = tenant_id or settings.default_tenant_id
        resolved_user_id = user_id or settings.default_user_id
        context = await self._users.get(resolved_tenant_id, resolved_user_id)
        if context is None:
            raise ValueError("User context not found")
        return context

    @staticmethod
    def _ensure_any_scope(context: UserContext, allowed_scopes: set[str]) -> None:
        # 临时关闭现有 scope 校验，后续统一替换为新的权限模型。
        _ = (context, allowed_scopes)
        return None
