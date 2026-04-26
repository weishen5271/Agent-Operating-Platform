"use client";

import { useEffect, useState } from "react";

import { KnowledgeBaseManager } from "@/components/knowledge/knowledge-base-manager";
import { KnowledgeIngestPanel } from "@/components/knowledge/knowledge-ingest-panel";
import { KnowledgeSourceAttributes } from "@/components/knowledge/knowledge-source-detail";
import { WikiFileDistributionPanel } from "@/components/knowledge/wiki-file-distribution-panel";
import { WikiManagementPanel } from "@/components/knowledge/wiki-management-panel";
import { WikiSearchPanel } from "@/components/knowledge/wiki-search-panel";
import { Modal } from "@/components/shared/modal";
import { Shell } from "@/components/shared/shell";
import { getAdminKnowledgeSourceDetail } from "@/lib/api-client";
import type {
  AdminKnowledgeResponse,
  AdminKnowledgeSourceDetailResponse,
  AdminKnowledgeBasesResponse,
  AdminWikiCompileRunsResponse,
  AdminWikiFileDistributionResponse,
  AdminWikiPagesResponse,
} from "@/lib/api-client/types";

type KnowledgeConsoleProps = {
  initialActiveTab: "rag" | "wiki";
  knowledgeBases: AdminKnowledgeBasesResponse["items"];
  selectedKnowledgeBase: string;
  isWikiDetailView: boolean;
  isRagDetailView: boolean;
  sources: AdminKnowledgeResponse["sources"];
  wikiPages: AdminWikiPagesResponse["pages"];
  wikiRuns: AdminWikiCompileRunsResponse["items"];
  wikiDistribution: AdminWikiFileDistributionResponse | null;
};

function statusTone(status: string): string {
  if (status.includes("运行") || status.includes("published")) return "success";
  if (status.includes("重建") || status.includes("灰度") || status.includes("running")) return "warning";
  if (status.includes("failed")) return "danger";
  return "";
}

export function KnowledgeConsole({
  initialActiveTab,
  knowledgeBases,
  selectedKnowledgeBase,
  isWikiDetailView,
  isRagDetailView,
  sources,
  wikiPages,
  wikiRuns,
  wikiDistribution,
}: KnowledgeConsoleProps) {
  const [activeTab, setActiveTab] = useState<"rag" | "wiki">(initialActiveTab);
  const [wikiView, setWikiView] = useState<"overview" | "distribution" | "search">("overview");
  const [showWikiIngestModal, setShowWikiIngestModal] = useState(false);
  const [showRagIngestModal, setShowRagIngestModal] = useState(false);
  const [showRagContent, setShowRagContent] = useState(false);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(sources[0]?.source_id ?? null);
  const [sourceDetail, setSourceDetail] = useState<AdminKnowledgeSourceDetailResponse | null>(null);
  const [sourceDetailLoading, setSourceDetailLoading] = useState(false);
  const [sourceDetailError, setSourceDetailError] = useState("");

  const selectedKnowledgeBaseMeta = knowledgeBases.find(
    (item) => item.knowledge_base_code === selectedKnowledgeBase,
  );
  const selectedKnowledgeBaseName = selectedKnowledgeBaseMeta?.name ?? selectedKnowledgeBase;

  useEffect(() => {
    setSelectedSourceId((current) => {
      if (!sources.length) {
        return null;
      }
      if (current && sources.some((item) => item.source_id === current)) {
        return current;
      }
      return sources[0]?.source_id ?? null;
    });
  }, [sources]);

  useEffect(() => {
    if (activeTab !== "rag" || !selectedSourceId) {
      setSourceDetail(null);
      setSourceDetailError("");
      return;
    }

    let cancelled = false;
    setSourceDetailLoading(true);
    setSourceDetailError("");
    void getAdminKnowledgeSourceDetail(selectedSourceId)
      .then((response) => {
        if (!cancelled) {
          setSourceDetail(response);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setSourceDetail(null);
          setSourceDetailError(error instanceof Error ? error.message : "加载原始文件内容失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSourceDetailLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, selectedSourceId]);

  function handleWikiTabClick() {
    window.location.href = "/knowledge?tab=wiki";
  }

  function handleRagTabClick() {
    window.location.href = "/knowledge?tab=rag";
  }

  function handleBackToWikiList() {
    window.location.href = "/knowledge?tab=wiki";
  }

  function handleBackToRagList() {
    window.location.href = "/knowledge?tab=rag";
  }

  const ragPipeline = [
    { label: "已接入数据源", value: `${sources.length} 个`, progress: sources.length ? 100 : 0 },
    { label: "知识切片", value: `${sources.reduce((sum, item) => sum + item.chunk_count, 0)} 块`, progress: sources.length ? 76 : 0 },
    { label: "运行中源", value: `${sources.filter((item) => item.status === "运行中").length} 个`, progress: sources.length ? 82 : 0 },
    { label: "索引健康度", value: sources.length ? "已建立" : "暂无", progress: sources.length ? 96 : 0 },
  ];

  return (
    <Shell
      activeKey="knowledge"
      title="知识库治理"
      searchPlaceholder={activeTab === "wiki" ? "搜索 Wiki 页面、编译任务..." : "搜索数据源、索引任务..."}
      tabs={[
        { label: "RAG 治理", active: activeTab === "rag", onClick: handleRagTabClick },
        { label: "Wiki 治理", active: activeTab === "wiki", onClick: handleWikiTabClick },
      ]}
    >
      {activeTab === "rag" && !isRagDetailView ? (
        <section className="page-section">
          <div className="page-head">
            <div className="page-head-meta">
              <div className="breadcrumbs">
                <span>能力中心</span>
                <span className="material-symbols-outlined">chevron_right</span>
                <span className="current">知识库治理 / RAG</span>
              </div>
              <h1>RAG 知识治理中心</h1>
              <p>选择一个知识库进入详情，查看数据源、切片与索引情况。</p>
            </div>
          </div>

          <KnowledgeBaseManager knowledgeBases={knowledgeBases} selectedKnowledgeBase="" tab="rag" />
        </section>
      ) : activeTab === "rag" && isRagDetailView ? (
        <section className="page-section">
          <div className="page-head">
            <div className="page-head-meta">
              <div className="breadcrumbs">
                <button
                  type="button"
                  onClick={handleBackToRagList}
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    color: "inherit",
                  }}
                >
                  RAG 治理
                </button>
                <span className="material-symbols-outlined">chevron_right</span>
                <span className="current">{selectedKnowledgeBaseName}</span>
              </div>
              <h1>{selectedKnowledgeBaseName} · RAG 治理</h1>
              <p>聚焦该知识库的数据入库、切片、向量化与召回质量。</p>
            </div>
            <div className="page-head-actions">
              <button type="button" className="secondary-button" onClick={handleBackToRagList}>
                <span className="material-symbols-outlined">arrow_back</span>
                返回列表
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => setShowRagIngestModal(true)}
              >
                <span className="material-symbols-outlined">cloud_upload</span>
                知识入库
              </button>
            </div>
          </div>

          <div className="bento-grid three">
            <article className="stat-card hero">
              <div className="stat-card-head">
                <span className="stat-card-label">检索质量指数</span>
                <span className="stat-icon material-symbols-outlined">troubleshoot</span>
              </div>
              <strong>{sources.length ? "已接入" : "--"}</strong>
              <p>{sources.length ? "当前页面仅展示真实入库与索引数据，不再展示演示质量分。" : "暂无真实知识源数据"}</p>
              <span className="stat-trend">{sources.length ? "请通过真实评测链路补充质量指标" : "等待真实数据"}</span>
              <span className="material-symbols-outlined stat-card-glyph">troubleshoot</span>
            </article>
            <article className="stat-card">
              <div className="stat-card-head">
                <span className="stat-card-label">总切片规模</span>
                <span className="stat-icon material-symbols-outlined">grid_view</span>
              </div>
              <strong>{sources.reduce((sum, item) => sum + item.chunk_count, 0).toLocaleString("zh-CN")}</strong>
              <p>覆盖已入库的 RAG 知识切片规模</p>
              <span className="stat-trend">{sources.length ? "基于真实已入库数据统计" : "当前暂无真实知识源"}</span>
              <span className="material-symbols-outlined stat-card-glyph">grid_view</span>
            </article>
            <article className="stat-card">
              <div className="stat-card-head">
                <span className="stat-card-label">平均新鲜度</span>
                <span className="stat-icon material-symbols-outlined">schedule</span>
              </div>
              <strong>{sources.length ? "实时" : "--"}</strong>
              <p>距离最近一次向量重建</p>
              <span className="stat-trend">{sources.length ? "基于当前数据实时展示" : "暂无重建记录"}</span>
              <span className="material-symbols-outlined stat-card-glyph">schedule</span>
            </article>
          </div>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>处理流水线状态</h3>
                <p>统一查看文档清洗、切片、向量化和质量校验进度。</p>
              </div>
            </div>
            <div className="pipeline-grid">
              {ragPipeline.map((item) => (
                <article key={item.label} className="pipeline-card">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <div className="progress-rail">
                    <div className="progress-fill" style={{ width: `${item.progress}%` }} />
                  </div>
                </article>
              ))}
            </div>
          </section>

          <div className="dashboard-grid">
            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>知识库文件列表</h3>
                  <p>点击文件项可在右侧查看对应的元数据信息。</p>
                </div>
              </div>
              <div className="stack-list">
                {sources.length ? (
                  sources.map((item) => (
                    <article
                      key={item.source_id}
                      className={`stack-item stack-button ${selectedSourceId === item.source_id ? "active" : ""}`}
                      onClick={() => setSelectedSourceId(item.source_id)}
                    >
                      <div>
                        <strong>{item.name}</strong>
                        <p>
                          {item.source_type} / {item.owner}
                        </p>
                        <p className="stack-subtle mono">{item.source_id}</p>
                      </div>
                      <div className="stack-meta">
                        <span className="mono">{item.chunk_count} 块</span>
                        <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
                      </div>
                    </article>
                  ))
                ) : (
                  <article className="stack-item">
                    <div>
                      <strong>暂无数据源</strong>
                      <p>点击右上角“知识入库”上传第一个 Raw Source。</p>
                    </div>
                    <span className="status-chip plain">empty</span>
                  </article>
                )}
              </div>
            </section>

            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>文件元数据</h3>
                  <p>展示当前选中文件的入库元数据与切片信息。</p>
                </div>
              </div>
              {!sources.length || !selectedSourceId ? (
                <div className="empty-state">
                  <strong>暂未选中文件</strong>
                  <p>从左侧列表选中一个文件，即可查看其元数据。</p>
                </div>
              ) : sourceDetailLoading ? (
                <div className="empty-state">
                  <strong>加载中</strong>
                  <p>正在读取所选文件的元数据。</p>
                </div>
              ) : sourceDetailError ? (
                <div className="empty-state">
                  <strong>加载失败</strong>
                  <p>{sourceDetailError}</p>
                </div>
              ) : sourceDetail ? (
                <div className="knowledge-source-detail">
                  <dl className="metadata-grid">
                    <div>
                      <dt>文件名称</dt>
                      <dd>{sourceDetail.source.name}</dd>
                    </div>
                    <div>
                      <dt>Source ID</dt>
                      <dd className="mono">{sourceDetail.source.source_id}</dd>
                    </div>
                    <div>
                      <dt>所属知识库</dt>
                      <dd className="mono">{sourceDetail.source.knowledge_base_code}</dd>
                    </div>
                    <div>
                      <dt>源类型</dt>
                      <dd>{sourceDetail.source.source_type}</dd>
                    </div>
                    <div>
                      <dt>负责人</dt>
                      <dd>{sourceDetail.source.owner}</dd>
                    </div>
                    <div>
                      <dt>切片数量</dt>
                      <dd className="mono">{sourceDetail.source.chunk_count}</dd>
                    </div>
                    <div>
                      <dt>Token 总量</dt>
                      <dd className="mono">
                        {sourceDetail.chunks.reduce((sum, chunk) => sum + chunk.token_count, 0)}
                      </dd>
                    </div>
                    <div>
                      <dt>状态</dt>
                      <dd>
                        <span className={`status-chip ${statusTone(sourceDetail.source.status)}`}>
                          {sourceDetail.source.status}
                        </span>
                      </dd>
                    </div>
                  </dl>

                  <KnowledgeSourceAttributes sourceId={sourceDetail.source.source_id} />

                  <div style={{ marginTop: "1rem" }}>
                    <h4 style={{ margin: "0 0 0.5rem" }}>切片元数据</h4>
                    <div className="stack-list">
                      {sourceDetail.chunks.length ? (
                        sourceDetail.chunks.map((chunk) => (
                          <article key={chunk.chunk_id} className="stack-item">
                            <div>
                              <strong>
                                #{chunk.chunk_index} · {chunk.title || "未命名切片"}
                              </strong>
                              <p className="stack-subtle mono">{chunk.chunk_id}</p>
                              <p className="stack-subtle mono">hash: {chunk.content_hash}</p>
                            </div>
                            <div className="stack-meta">
                              <span className="mono">{chunk.token_count} tokens</span>
                              <span className={`status-chip ${statusTone(chunk.status)}`}>
                                {chunk.status}
                              </span>
                            </div>
                          </article>
                        ))
                      ) : (
                        <article className="stack-item">
                          <div>
                            <strong>暂无切片</strong>
                            <p>该文件尚未生成切片。</p>
                          </div>
                          <span className="status-chip plain">empty</span>
                        </article>
                      )}
                    </div>
                  </div>

                  <div style={{ marginTop: "1rem" }}>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setShowRagContent((value) => !value)}
                    >
                      <span className="material-symbols-outlined">
                        {showRagContent ? "expand_less" : "expand_more"}
                      </span>
                      {showRagContent ? "收起文件正文" : "查看文件正文"}
                    </button>
                    {showRagContent ? (
                      <textarea
                        readOnly
                        value={sourceDetail.content}
                        rows={16}
                        className="mono"
                        style={{ marginTop: "0.5rem", display: "block", width: "100%" }}
                      />
                    ) : null}
                  </div>
                </div>
              ) : null}
            </section>
          </div>

          <Modal
            isOpen={showRagIngestModal}
            onClose={() => setShowRagIngestModal(false)}
            title="知识入库"
          >
            <KnowledgeIngestPanel
              knowledgeBaseCode={selectedKnowledgeBase}
              knowledgeBases={knowledgeBases}
            />
          </Modal>
        </section>
      ) : !isWikiDetailView ? (
        <section className="page-section">
          <div className="page-head">
            <div className="page-head-meta">
              <div className="breadcrumbs">
                <span>能力中心</span>
                <span className="material-symbols-outlined">chevron_right</span>
                <span className="current">知识库治理 / Wiki</span>
              </div>
              <h1>Wiki 治理中心</h1>
              <p>选择一个知识库进入详情，查看概览、文件分布或执行检索验证。</p>
            </div>
          </div>

          <KnowledgeBaseManager knowledgeBases={knowledgeBases} selectedKnowledgeBase="" />
        </section>
      ) : (
        <section className="page-section">
          <div className="page-head">
            <div className="page-head-meta">
              <div className="breadcrumbs">
                <button
                  type="button"
                  onClick={handleBackToWikiList}
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    color: "inherit",
                  }}
                >
                  Wiki 治理
                </button>
                <span className="material-symbols-outlined">chevron_right</span>
                <span className="current">{selectedKnowledgeBaseName}</span>
              </div>
              <h1>{selectedKnowledgeBaseName}</h1>
              <p>查看该知识库的概览、文件分布，并可对 Wiki 内容执行检索验证。</p>
            </div>
            <div className="page-head-actions">
              <button type="button" className="secondary-button" onClick={handleBackToWikiList}>
                <span className="material-symbols-outlined">arrow_back</span>
                返回列表
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => setShowWikiIngestModal(true)}
              >
                <span className="material-symbols-outlined">cloud_upload</span>
                知识入库
              </button>
            </div>
          </div>

          <nav className="console-tabs" aria-label="Wiki 详情页签" style={{ marginBottom: "1rem" }}>
            <button
              type="button"
              className={`console-tab ${wikiView === "overview" ? "active" : ""}`}
              onClick={() => setWikiView("overview")}
            >
              概览
            </button>
            <button
              type="button"
              className={`console-tab ${wikiView === "distribution" ? "active" : ""}`}
              onClick={() => setWikiView("distribution")}
            >
              文件分布
            </button>
            <button
              type="button"
              className={`console-tab ${wikiView === "search" ? "active" : ""}`}
              onClick={() => setWikiView("search")}
            >
              检索验证
            </button>
          </nav>

          <Modal
            isOpen={showWikiIngestModal}
            onClose={() => setShowWikiIngestModal(false)}
            title="知识入库"
          >
            <KnowledgeIngestPanel
              knowledgeBaseCode={selectedKnowledgeBase}
              knowledgeBases={knowledgeBases}
              target="wiki"
            />
          </Modal>
          {wikiView === "overview" ? (
            <WikiManagementPanel pages={wikiPages} runs={wikiRuns} spaceCode={selectedKnowledgeBase} />
          ) : null}
          {wikiView === "distribution" ? (
            <WikiFileDistributionPanel
              initialData={wikiDistribution}
              selectedKnowledgeBase={selectedKnowledgeBase}
              knowledgeBases={knowledgeBases}
              wikiPages={wikiPages}
              wikiRuns={wikiRuns}
            />
          ) : null}
          {wikiView === "search" ? <WikiSearchPanel /> : null}
        </section>
      )}
    </Shell>
  );
}
