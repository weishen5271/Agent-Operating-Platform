from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agent_platform.domain.models import utc_now


@dataclass(slots=True)
class WikiPage:
    page_id: str
    tenant_id: str
    space_code: str
    page_type: str
    title: str
    slug: str
    summary: str
    content_markdown: str
    metadata_json: dict
    status: str
    confidence: str
    freshness_score: float
    source_count: int
    citation_count: int
    revision_no: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class WikiPageRevision:
    revision_id: str
    page_id: str
    tenant_id: str
    revision_no: int
    compile_run_id: str | None
    change_type: str
    content_markdown: str
    summary: str
    change_summary: str
    quality_score: float
    metadata_json: dict
    created_at: datetime
    created_by: str


@dataclass(slots=True)
class WikiCitation:
    citation_id: str
    tenant_id: str
    page_id: str
    revision_id: str
    section_key: str
    claim_text: str
    source_id: str
    chunk_id: str
    evidence_snippet: str
    support_type: str
    created_at: datetime


@dataclass(slots=True)
class WikiCompileRun:
    compile_run_id: str
    tenant_id: str
    trigger_type: str
    status: str
    scope_type: str
    scope_value: str
    input_source_ids: list[str] = field(default_factory=list)
    input_chunk_ids: list[str] = field(default_factory=list)
    affected_page_ids: list[str] = field(default_factory=list)
    summary: str = ""
    error_message: str = ""
    token_usage: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_by: str = "system"
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class WikiSearchHit:
    page_id: str
    revision_id: str | None
    revision_no: int
    title: str
    summary: str
    snippet: str
    citation_id: str | None
    claim_text: str
    evidence_snippet: str
    source_id: str | None
    chunk_id: str | None
    score: float
    locator: str


@dataclass(slots=True)
class WikiSearchResult:
    hits: list[WikiSearchHit]
    backend: str
    query: str
    candidate_count: int
    match_count: int


@dataclass(slots=True)
class WikiFileDistributionOverview:
    total_sources: int
    compiled_sources: int
    uncovered_sources: int
    high_impact_sources: int
    total_pages: int
    total_citations: int
    avg_pages_per_source: float
    avg_sources_per_page: float
    latest_compile_run_id: str | None
    latest_compile_finished_at: datetime | None


@dataclass(slots=True)
class WikiFileDistributionGroup:
    group_key: str
    group_label: str
    source_count: int
    compiled_count: int
    uncovered_count: int
    citation_count: int
    page_count: int
    dominant_status: str


@dataclass(slots=True)
class WikiFileDistributionItem:
    source_id: str
    tenant_id: str
    source_name: str
    source_type: str
    owner: str
    group_path: str
    chunk_count: int
    status: str
    coverage_status: str
    compiled: bool
    page_count: int
    citation_count: int
    distribution_score: float
    hotspot_score: float
    latest_compile_run_id: str | None
    latest_compile_finished_at: datetime | None


@dataclass(slots=True)
class WikiFilePageImpact:
    page_id: str
    title: str
    slug: str
    citation_count: int
    contribution_score: float


@dataclass(slots=True)
class WikiFileDistributionDetail:
    item: WikiFileDistributionItem
    related_pages: list[WikiFilePageImpact]
    diagnostic_tags: list[str]
