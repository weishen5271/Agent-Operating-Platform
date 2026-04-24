"use client";

import { useEffect, useMemo, useState, useTransition } from "react";

import { getAdminWikiFileDistribution, getAdminWikiFileDistributionDetail } from "@/lib/api-client";
import type {
  AdminKnowledgeResponse,
  AdminKnowledgeBasesResponse,
  AdminWikiCompileRunsResponse,
  AdminWikiFileDistributionDetailResponse,
  AdminWikiFileDistributionResponse,
  AdminWikiPagesResponse,
} from "@/lib/api-client/types";

type WikiFileDistributionPanelProps = {
  initialData: AdminWikiFileDistributionResponse | null;
  selectedKnowledgeBase: string;
  knowledgeBases: AdminKnowledgeBasesResponse["items"];
  sources: AdminKnowledgeResponse["sources"];
  wikiPages: AdminWikiPagesResponse["pages"];
  wikiRuns: AdminWikiCompileRunsResponse["items"];
};

type Filters = {
  coverageStatus: string;
  keyword: string;
};

const EMPTY_DATA: AdminWikiFileDistributionResponse = {
  overview: {
    total_sources: 0,
    compiled_sources: 0,
    uncovered_sources: 0,
    high_impact_sources: 0,
    total_pages: 0,
    total_citations: 0,
    avg_pages_per_source: 0,
    avg_sources_per_page: 0,
    latest_compile_run_id: null,
    latest_compile_finished_at: null,
  },
  groups: [],
  items: [],
};

function toneOfCoverage(status: string): string {
  if (status === "高影响") return "warning";
  if (status === "已进入页面") return "success";
  if (status === "已编译未命中页面") return "danger";
  return "";
}

function formatTime(value?: string | null): string {
  if (!value) return "暂无";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function normalizeFileName(name: string): string {
  const trimmed = name.trim() || "untitled";
  return trimmed.endsWith(".md") || trimmed.endsWith(".txt") || trimmed.endsWith(".json") || trimmed.endsWith(".csv")
    ? trimmed
    : `${trimmed}.md`;
}

export function WikiFileDistributionPanel({
  initialData,
  selectedKnowledgeBase,
  knowledgeBases,
  sources,
  wikiPages,
  wikiRuns,
}: WikiFileDistributionPanelProps) {
  const [filters, setFilters] = useState<Filters>({
    coverageStatus: "",
    keyword: "",
  });
  const [data, setData] = useState<AdminWikiFileDistributionResponse>(initialData ?? EMPTY_DATA);
  const [detail, setDetail] = useState<AdminWikiFileDistributionDetailResponse | null>(null);
  const [status, setStatus] = useState("");
  const [isPending, startTransition] = useTransition();
  const [isDetailPending, startDetailTransition] = useTransition();
  const currentKnowledgeBase = knowledgeBases.find((item) => item.knowledge_base_code === selectedKnowledgeBase) ?? null;

  useEffect(() => {
    startTransition(async () => {
      try {
        const response = await getAdminWikiFileDistribution({
          spaceCode: selectedKnowledgeBase,
          coverageStatus: filters.coverageStatus || undefined,
          keyword: filters.keyword || undefined,
        });
        setData(response);
        setStatus(
          response.items.length
            ? `已加载 ${response.items.length} 个原始文件节点，并映射到 Wiki 文件空间。`
            : "当前没有符合筛选条件的文件节点。",
        );
        if (response.items.length) {
          const preferredSourceId =
            detail && response.items.some((item) => item.source_id === detail.item.source_id)
              ? detail.item.source_id
              : response.items[0].source_id;
          const detailResponse = await getAdminWikiFileDistributionDetail(preferredSourceId, selectedKnowledgeBase);
          setDetail(detailResponse);
        } else {
          setDetail(null);
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "加载文件空间失败");
        setData(EMPTY_DATA);
        setDetail(null);
      }
    });
  }, [filters.coverageStatus, filters.keyword, selectedKnowledgeBase]);

  const rawSourceFiles = useMemo(
    () =>
      sources
        .filter((source) => source.knowledge_base_code === selectedKnowledgeBase)
        .map((source) => {
        const matched = data.items.find((item) => item.source_id === source.source_id);
        return {
          sourceId: source.source_id,
          path: `raw/${source.source_type.toLowerCase()}/${normalizeFileName(source.name)}`,
          title: source.name,
          owner: source.owner,
          chunkCount: source.chunk_count,
          coverageStatus: matched?.coverage_status ?? "已入库未编译",
          pageCount: matched?.page_count ?? 0,
          citationCount: matched?.citation_count ?? 0,
        };
        }),
    [data.items, selectedKnowledgeBase, sources],
  );

  const wikiMarkdownFiles = useMemo(
    () =>
      wikiPages.map((page) => ({
        pageId: page.page_id,
        path: `wiki/pages/${page.slug}.md`,
        title: page.title,
        citationCount: page.citation_count,
        sourceCount: page.source_count,
        revisionNo: page.revision_no,
      })),
    [wikiPages],
  );

  const knowledgeBaseSourceIds = useMemo(
    () => new Set(rawSourceFiles.map((item) => item.sourceId)),
    [rawSourceFiles],
  );

  const visibleWikiRuns = useMemo(
    () =>
      wikiRuns.filter((run) => run.input_source_ids.some((sourceId) => knowledgeBaseSourceIds.has(sourceId))),
    [knowledgeBaseSourceIds, wikiRuns],
  );

  function handleSelectSource(sourceId: string) {
    startDetailTransition(async () => {
      try {
        const response = await getAdminWikiFileDistributionDetail(sourceId, selectedKnowledgeBase);
        setDetail(response);
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "加载文件详情失败");
      }
    });
  }

  return (
    <section className="management-sections">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>LLM Wiki 文件空间</h3>
            <p>按文章中的文件系统思路展示 Raw Sources、Wiki Markdown、Index / Log 的分布关系，而不是只看表级统计。</p>
          </div>
        </div>

        <div className="distribution-filter-bar">
          <label>
            <span>当前知识库</span>
            <select
              value={selectedKnowledgeBase}
              onChange={(event) => {
                const url = new URL(window.location.href);
                url.searchParams.set("tab", "wiki");
                url.searchParams.set("knowledgeBase", event.target.value);
                window.location.href = url.toString();
              }}
            >
              {knowledgeBases.map((item) => (
                <option key={item.knowledge_base_code} value={item.knowledge_base_code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>覆盖状态</span>
            <select
              value={filters.coverageStatus}
              onChange={(event) => setFilters((prev) => ({ ...prev, coverageStatus: event.target.value }))}
            >
              <option value="">全部</option>
              <option value="已入库未编译">已入库未编译</option>
              <option value="已编译未命中页面">已编译未命中页面</option>
              <option value="已进入页面">已进入页面</option>
              <option value="高影响">高影响</option>
            </select>
          </label>
          <label className="wide">
            <span>关键字</span>
            <input
              value={filters.keyword}
              placeholder="搜索 raw 文件名或 wiki 页面"
              onChange={(event) => setFilters((prev) => ({ ...prev, keyword: event.target.value }))}
            />
          </label>
        </div>

        <div className="bento-grid three">
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">当前知识库</span>
              <span className="stat-icon material-symbols-outlined">database</span>
            </div>
            <strong>{currentKnowledgeBase?.name ?? selectedKnowledgeBase}</strong>
            <p>{currentKnowledgeBase?.description || "当前知识库暂无描述"}</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">Raw Sources</span>
              <span className="stat-icon material-symbols-outlined">description</span>
            </div>
            <strong>{rawSourceFiles.length}</strong>
            <p>原始知识文件集合，作为 immutable source layer</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">Wiki Pages</span>
              <span className="stat-icon material-symbols-outlined">article</span>
            </div>
            <strong>{wikiMarkdownFiles.length}</strong>
            <p>由原始文件沉淀出的真实 Wiki 页面</p>
          </article>
        </div>

        {status ? <span className={`form-status ${status.includes("失败") ? "error" : "success"}`}>{status}</span> : null}
      </section>

      <div className="wiki-fs-layout">
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>Raw Sources</h3>
              <p>上传进来的原始文件，作为 LLM Wiki 的原始知识源。</p>
            </div>
          </div>
          <div className="stack-list">
            {rawSourceFiles.length ? (
              rawSourceFiles.map((file) => (
                <button
                  key={file.sourceId}
                  type="button"
                  className={`stack-item stack-button ${detail?.item.source_id === file.sourceId ? "active" : ""}`}
                  onClick={() => handleSelectSource(file.sourceId)}
                >
                  <div>
                    <strong>{file.path}</strong>
                    <p>
                      {file.title} / {file.owner}
                    </p>
                    <p className="stack-subtle">
                      {file.chunkCount} 块 / {file.pageCount} 页 / {file.citationCount} 引用
                    </p>
                  </div>
                  <div className="stack-meta">
                    <span className={`status-chip ${toneOfCoverage(file.coverageStatus)}`}>{file.coverageStatus}</span>
                  </div>
                </button>
              ))
            ) : (
              <article className="stack-item">
                <div>
                  <strong>暂无 Raw 文件</strong>
                  <p>先通过上传入口导入至少一个文本文件。</p>
                </div>
                <span className="status-chip plain">empty</span>
              </article>
            )}
          </div>
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>Wiki Markdown Files</h3>
              <p>由 Raw Sources 编译得到的 wiki 页面文件空间。</p>
            </div>
          </div>
          <div className="stack-list">
            {wikiMarkdownFiles.length ? (
              wikiMarkdownFiles.map((file) => (
                <article key={file.pageId} className="stack-item">
                  <div>
                    <strong>{file.path}</strong>
                    <p>{file.title}</p>
                    <p className="stack-subtle">
                      rev {file.revisionNo} / {file.sourceCount} 源 / {file.citationCount} 引用
                    </p>
                  </div>
                  <div className="stack-meta">
                    <span className="status-chip success">published</span>
                  </div>
                </article>
              ))
            ) : (
              <article className="stack-item">
                <div>
                  <strong>暂无 Wiki 文件</strong>
                  <p>当前还没有编译出的 wiki markdown 页面。</p>
                </div>
                <span className="status-chip plain">empty</span>
              </article>
            )}
          </div>
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>编译记录</h3>
              <p>仅展示当前知识库下已经真实产生的 Wiki 编译运行记录。</p>
            </div>
          </div>
          <div className="stack-list">
            {visibleWikiRuns.length ? (
              visibleWikiRuns.map((run) => (
                <article key={run.compile_run_id} className="stack-item">
                  <div>
                    <strong>{run.compile_run_id}</strong>
                    <p>{run.summary || `${run.scope_type} / ${run.scope_value}`}</p>
                    <p className="stack-subtle">{formatTime(run.finished_at || run.created_at)}</p>
                  </div>
                  <div className="stack-meta">
                    <span className="mono">{run.affected_page_ids.length} 页</span>
                    <span className="status-chip plain">{run.status}</span>
                  </div>
                </article>
              ))
            ) : (
              <article className="stack-item">
                <div>
                  <strong>暂无编译记录</strong>
                  <p>当前知识库还没有真实的 Wiki 编译数据。</p>
                </div>
                <span className="status-chip plain">empty</span>
              </article>
            )}
          </div>
        </section>
      </div>

      <div className="distribution-layout single">
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>Source to Wiki 映射</h3>
              <p>查看某个 Raw Source 在 Wiki 文件空间里触发了哪些页面更新。</p>
            </div>
          </div>
          {detail ? (
            <div className="distribution-detail">
              <article className="detail-summary-card">
                <strong>{`raw/${detail.item.source_type.toLowerCase()}/${normalizeFileName(detail.item.source_name)}`}</strong>
                <p>
                  {detail.item.source_type} / {detail.item.owner}
                </p>
                <p className="stack-subtle">
                  状态 {detail.item.coverage_status} / 最近编译 {formatTime(detail.item.latest_compile_finished_at)}
                </p>
                <div className="detail-chip-row">
                  {detail.diagnostic_tags.length ? (
                    detail.diagnostic_tags.map((tag) => (
                      <span key={tag} className="status-chip plain">
                        {tag}
                      </span>
                    ))
                  ) : (
                    <span className="status-chip plain">no-tags</span>
                  )}
                </div>
              </article>

              <div className="wiki-flow-grid">
                <article className="wiki-flow-card">
                  <span className="wiki-flow-label">Raw</span>
                  <strong>{detail.item.chunk_count} 个 chunk</strong>
                  <p>{detail.item.citation_count} 次引用进入 wiki layer</p>
                </article>
                <article className="wiki-flow-card accent">
                  <span className="wiki-flow-label">Wiki</span>
                  <strong>{detail.item.page_count} 个页面</strong>
                  <p>通过页面文件把原始内容重新组织为长期知识</p>
                </article>
              </div>

              <div className="stack-list">
                {detail.related_pages.length ? (
                  detail.related_pages.map((page) => (
                    <article key={page.page_id} className="stack-item">
                      <div>
                        <strong>{`wiki/pages/${page.slug}.md`}</strong>
                        <p>{page.title}</p>
                      </div>
                      <div className="stack-meta">
                        <span className="mono">{page.citation_count} 引用</span>
                        <span className="status-chip plain">{Math.round(page.contribution_score * 100)}%</span>
                      </div>
                    </article>
                  ))
                ) : (
                  <article className="stack-item">
                    <div>
                      <strong>{isDetailPending ? "加载中" : "暂无映射"}</strong>
                      <p>该 Raw Source 目前还没有生成任何 Wiki 页面映射。</p>
                    </div>
                    <span className="status-chip plain">empty</span>
                  </article>
                )}
              </div>
            </div>
          ) : (
            <div className="empty-distribution">从左侧选择一个 Raw Source 查看它在 Wiki 文件空间里的投影。</div>
          )}
        </section>
      </div>
    </section>
  );
}
