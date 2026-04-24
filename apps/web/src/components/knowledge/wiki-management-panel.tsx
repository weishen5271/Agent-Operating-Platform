"use client";

import { useState, useTransition } from "react";

import { compileAdminWiki } from "@/lib/api-client";
import type {
  AdminWikiCompileRunsResponse,
  AdminWikiPagesResponse,
} from "@/lib/api-client/types";

type WikiManagementPanelProps = {
  pages: AdminWikiPagesResponse["pages"];
  runs: AdminWikiCompileRunsResponse["items"];
  spaceCode?: string;
};

type Status = {
  tone: "idle" | "success" | "error";
  message: string;
};

function formatTime(value?: string | null): string {
  if (!value) {
    return "未完成";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function toneOfRun(status: string): string {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  return "warning";
}

export function WikiManagementPanel({ pages, runs, spaceCode = "knowledge" }: WikiManagementPanelProps) {
  const [status, setStatus] = useState<Status>({ tone: "idle", message: "" });
  const [isPending, startTransition] = useTransition();

  function handleCompileAll() {
    setStatus({ tone: "idle", message: "" });
    startTransition(async () => {
      try {
        const response = await compileAdminWiki({ space_code: spaceCode });
        setStatus({
          tone: "success",
          message: `已触发 Wiki 编译，生成 ${response.pages.length} 个页面，编译任务 ${response.compile_run.compile_run_id} 已完成。`,
        });
        window.location.reload();
      } catch (error) {
        setStatus({
          tone: "error",
          message: error instanceof Error ? error.message : "Wiki 编译失败",
        });
      }
    });
  }

  return (
    <section className="management-sections">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>Wiki 管理面板</h3>
            <p>从已入库知识源手动编译 Wiki 页面，并查看页面版本和引用沉淀情况。</p>
          </div>
          <button type="button" className="primary-button" disabled={isPending} onClick={handleCompileAll}>
            <span className="material-symbols-outlined">{isPending ? "hourglass_top" : "auto_awesome"}</span>
            {isPending ? "编译中" : "编译全部知识源"}
          </button>
        </div>

        <div className="bento-grid three">
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">Wiki 页面</span>
              <span className="stat-icon material-symbols-outlined">article</span>
            </div>
            <strong>{pages.length}</strong>
            <p>当前已发布的治理页面总数</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">最近编译任务</span>
              <span className="stat-icon material-symbols-outlined">history</span>
            </div>
            <strong>{runs.length}</strong>
            <p>展示最近的 Wiki 编译记录</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">引用总量</span>
              <span className="stat-icon material-symbols-outlined">format_quote</span>
            </div>
            <strong>{pages.reduce((sum, item) => sum + item.citation_count, 0)}</strong>
            <p>页面累计沉淀的 citation 数量</p>
          </article>
        </div>

        {status.message ? <span className={`form-status ${status.tone}`}>{status.message}</span> : null}
      </section>

      <div className="dashboard-grid">
        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>编译记录</h3>
              <p>查看最近一次 Wiki 编译的范围、状态和结果摘要。</p>
            </div>
          </div>
          <div className="stack-list">
            {runs.length ? (
              runs.map((item) => (
                <article key={item.compile_run_id} className="stack-item">
                  <div>
                    <strong>{item.compile_run_id}</strong>
                    <p>{item.summary || `${item.scope_type} / ${item.scope_value}`}</p>
                    <p className="stack-subtle">
                      {formatTime(item.finished_at || item.created_at)} / 影响 {item.affected_page_ids.length} 页
                    </p>
                  </div>
                  <div className="stack-meta">
                    <span className="mono">{item.input_source_ids.length} 源</span>
                    <span className={`status-chip ${toneOfRun(item.status)}`}>{item.status}</span>
                  </div>
                </article>
              ))
            ) : (
              <article className="stack-item">
                <div>
                  <strong>暂无编译记录</strong>
                  <p>可以先执行一次 Wiki 编译，再查看页面和引用生成情况。</p>
                </div>
                <span className="status-chip plain">empty</span>
              </article>
            )}
          </div>
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>Wiki 页面列表</h3>
              <p>查看当前已发布的 Wiki 页面、版本号和引用覆盖度。</p>
            </div>
          </div>
          <div className="stack-list">
            {pages.length ? (
              pages.map((item) => (
                <article key={item.page_id} className="stack-item">
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.summary || `${item.page_type} / ${item.space_code}`}</p>
                    <p className="stack-subtle">
                      {item.slug} / rev {item.revision_no}
                    </p>
                  </div>
                  <div className="stack-meta">
                    <span className="mono">{item.citation_count} 引用</span>
                    <span className={`status-chip ${item.status === "published" ? "success" : ""}`}>{item.status}</span>
                  </div>
                </article>
              ))
            ) : (
              <article className="stack-item">
                <div>
                  <strong>暂无 Wiki 页面</strong>
                  <p>当前还没有已发布的 Wiki 页面，先触发编译后再回来查看。</p>
                </div>
                <span className="status-chip plain">empty</span>
              </article>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
