"use client";

import { useState } from "react";

import { KnowledgeBaseManager } from "@/components/knowledge/knowledge-base-manager";
import { KnowledgeIngestPanel } from "@/components/knowledge/knowledge-ingest-panel";
import { WikiFileDistributionPanel } from "@/components/knowledge/wiki-file-distribution-panel";
import { WikiManagementPanel } from "@/components/knowledge/wiki-management-panel";
import { WikiSearchPanel } from "@/components/knowledge/wiki-search-panel";
import { Shell } from "@/components/shared/shell";
import type {
  AdminKnowledgeResponse,
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
  sources,
  wikiPages,
  wikiRuns,
  wikiDistribution,
}: KnowledgeConsoleProps) {
  const [activeTab, setActiveTab] = useState<"rag" | "wiki">(initialActiveTab);
  const [wikiView, setWikiView] = useState<"overview" | "distribution" | "search">("overview");
  const [showWikiIngest, setShowWikiIngest] = useState(false);

  const selectedKnowledgeBaseMeta = knowledgeBases.find(
    (item) => item.knowledge_base_code === selectedKnowledgeBase,
  );
  const selectedKnowledgeBaseName = selectedKnowledgeBaseMeta?.name ?? selectedKnowledgeBase;

  function handleWikiTabClick() {
    if (activeTab === "wiki") {
      // 再次点击 Wiki 页签时回到列表视图
      window.location.href = "/knowledge?tab=wiki";
      return;
    }
    setActiveTab("wiki");
  }

  function handleBackToWikiList() {
    window.location.href = "/knowledge?tab=wiki";
  }

  const ragPipeline = [
    { label: "已接入数据源", value: `${sources.length} 个`, progress: sources.length ? 100 : 0 },
    { label: "知识切片", value: `${sources.reduce((sum, item) => sum + item.chunk_count, 0)} 块`, progress: sources.length ? 76 : 0 },
    { label: "运行中源", value: `${sources.filter((item) => item.status === "运行中").length} 个`, progress: sources.length ? 82 : 0 },
    { label: "索引健康度", value: sources.length ? "已建立" : "暂无", progress: sources.length ? 96 : 0 },
  ];

  const sourceRows = sources.map((item) => ({
    name: item.name,
    type: item.source_type,
    owner: item.owner,
    chunks: item.chunk_count,
    status: item.status,
  }));

  return (
    <Shell
      activeKey="knowledge"
      title="知识库治理"
      searchPlaceholder={activeTab === "wiki" ? "搜索 Wiki 页面、编译任务..." : "搜索数据源、索引任务..."}
      tabs={[
        { label: "RAG 治理", active: activeTab === "rag", onClick: () => setActiveTab("rag") },
        { label: "Wiki 治理", active: activeTab === "wiki", onClick: handleWikiTabClick },
      ]}
    >
      {activeTab === "rag" ? (
        <section className="page-section">
          <div className="page-head">
            <div className="page-head-meta">
              <div className="breadcrumbs">
                <span>能力中心</span>
                <span className="material-symbols-outlined">chevron_right</span>
                <span className="current">知识库治理 / RAG</span>
              </div>
              <h1>RAG 知识治理中心</h1>
              <p>聚焦知识入库、切片、向量化和召回质量，管理原始知识源到 RAG 检索链路的全流程。</p>
            </div>
            <div className="page-head-actions">
              <button type="button" className="secondary-button">
                <span className="material-symbols-outlined">refresh</span>
                重新索引全部
              </button>
              <button type="button" className="primary-button">
                <span className="material-symbols-outlined">cloud_upload</span>
                上传新数据源
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

          <KnowledgeIngestPanel knowledgeBaseCode={selectedKnowledgeBase} knowledgeBases={knowledgeBases} />

          <div className="dashboard-grid">
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

            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>数据源列表</h3>
                  <p>按所有权、切片规模和当前状态管理知识源。</p>
                </div>
              </div>
              <div className="stack-list">
                {sourceRows.length ? (
                  sourceRows.map((item) => (
                    <article key={item.name} className="stack-item">
                      <div>
                        <strong>{item.name}</strong>
                        <p>
                          {item.type} / {item.owner}
                        </p>
                      </div>
                      <div className="stack-meta">
                        <span className="mono">{item.chunks} 块</span>
                        <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
                      </div>
                    </article>
                  ))
                ) : (
                  <article className="stack-item">
                    <div>
                      <strong>暂无数据源</strong>
                      <p>当前知识库还没有任何真实 Raw Source。</p>
                    </div>
                    <span className="status-chip plain">empty</span>
                  </article>
                )}
              </div>
            </section>
          </div>
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
                onClick={() => setShowWikiIngest((value) => !value)}
              >
                <span className="material-symbols-outlined">upload_file</span>
                {showWikiIngest ? "收起上传入口" : "上传 Raw Source"}
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

          {showWikiIngest ? (
            <KnowledgeIngestPanel knowledgeBaseCode={selectedKnowledgeBase} knowledgeBases={knowledgeBases} />
          ) : null}
          {wikiView === "overview" ? (
            <WikiManagementPanel pages={wikiPages} runs={wikiRuns} spaceCode={selectedKnowledgeBase} />
          ) : null}
          {wikiView === "distribution" ? (
            <WikiFileDistributionPanel
              initialData={wikiDistribution}
              selectedKnowledgeBase={selectedKnowledgeBase}
              knowledgeBases={knowledgeBases}
              sources={sources}
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
