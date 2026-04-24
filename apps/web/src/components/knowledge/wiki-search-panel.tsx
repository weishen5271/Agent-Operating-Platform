"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { searchAdminWiki } from "@/lib/api-client";
import type { AdminWikiSearchResponse } from "@/lib/api-client/types";

type Status = {
  tone: "idle" | "success" | "error";
  message: string;
};

export function WikiSearchPanel() {
  const [query, setQuery] = useState("请检索与采购审批相关的治理页面和引用证据");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<Status>({ tone: "idle", message: "" });
  const [result, setResult] = useState<AdminWikiSearchResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setStatus({ tone: "error", message: "请输入要检索的 Wiki 问题或关键词。" });
      return;
    }
    setSubmitting(true);
    setStatus({ tone: "idle", message: "" });
    try {
      const response = await searchAdminWiki({ query: trimmed, topK: 3 });
      setResult(response);
      setStatus({
        tone: "success",
        message: `已完成 Wiki 检索，命中 ${response.retrieval.match_count}/${response.retrieval.candidate_count} 个候选页面。`,
      });
    } catch (error) {
      setResult(null);
      setStatus({
        tone: "error",
        message: error instanceof Error ? error.message : "Wiki 检索失败",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>Wiki 检索与问答入口</h3>
          <p>验证治理后的 Wiki 页面、引用证据和基于 Wiki 的问答链路是否可用。</p>
        </div>
        <Link href="/chat" className="secondary-button">
          <span className="material-symbols-outlined">forum</span>
          去对话页测试
        </Link>
      </div>

      <div className="wiki-entry-grid">
        <article className="wiki-entry-card">
          <span className="wiki-entry-label">链路 A</span>
          <strong>Wiki 检索</strong>
          <p>从已编译 Wiki 页面和 citation 中召回结果，验证页面级治理视图是否可检索。</p>
        </article>
        <article className="wiki-entry-card accent">
          <span className="wiki-entry-label">链路 B</span>
          <strong>Wiki Based QA</strong>
          <p>在对话页切换到 Wiki 模式，让 LLM 基于 Wiki 页面与引用证据生成最终回答。</p>
        </article>
      </div>

      <form className="wiki-search-form" onSubmit={handleSubmit}>
        <label className="full">
          <span>Wiki 检索问题</span>
          <textarea
            value={query}
            rows={4}
            placeholder="例如：采购审批链路的治理要求是什么？"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="knowledge-ingest-footer">
          {status.message ? <span className={`form-status ${status.tone}`}>{status.message}</span> : <span />}
          <button type="submit" className="primary-button" disabled={submitting}>
            <span className="material-symbols-outlined">{submitting ? "hourglass_top" : "travel_explore"}</span>
            {submitting ? "检索中" : "执行 Wiki 检索"}
          </button>
        </div>
      </form>

      {result ? (
        <div className="stack-list">
          {result.hits.length ? (
            result.hits.map((item) => (
              <article key={`${item.page_id}-${item.citation_id ?? "page"}`} className="stack-item">
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.claim_text || item.snippet}</p>
                  <p className="stack-subtle">
                    {item.locator} / rev {item.revision_no}
                  </p>
                </div>
                <div className="stack-meta">
                  <span className="mono">{item.score.toFixed(2)}</span>
                  <span className="status-chip plain">wiki</span>
                </div>
              </article>
            ))
          ) : (
            <article className="stack-item">
              <div>
                <strong>未命中 Wiki 页面</strong>
                <p>{result.summary}</p>
              </div>
              <span className="status-chip plain">empty</span>
            </article>
          )}
        </div>
      ) : null}
    </section>
  );
}
