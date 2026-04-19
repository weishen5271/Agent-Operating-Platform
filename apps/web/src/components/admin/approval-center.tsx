"use client";

import { useState, useTransition } from "react";

import { confirmDraftAction } from "@/lib/api-client";
import type { DraftActionResponse } from "@/lib/api-client/types";

type ApprovalCenterProps = {
  initialDrafts: DraftActionResponse[];
};

export function ApprovalCenter({ initialDrafts }: ApprovalCenterProps) {
  const [drafts, setDrafts] = useState(initialDrafts);
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleConfirm(draftId: string) {
    setFeedback(null);
    setActiveDraftId(draftId);
    startTransition(async () => {
      try {
        const result = await confirmDraftAction(draftId);
        setDrafts((prev) =>
          prev.map((item) => (item.draft_id === draftId ? result : item)),
        );
        setFeedback(`草稿 ${result.title} 已确认，可进入后续审批或执行链路。`);
      } catch {
        setFeedback("草稿确认失败，请确认后端 API 已启动。");
      } finally {
        setActiveDraftId(null);
      }
    });
  }

  return (
    <section className="page-section">
      <div className="page-head">
        <div className="page-head-meta">
          <div className="breadcrumbs">
            <span>治理与合规</span>
            <span className="material-symbols-outlined">chevron_right</span>
            <span className="current">审批确认</span>
          </div>
          <h1>审批确认中心</h1>
          <p>Agent 生成的高风险动作先进入草稿态，平台管理员确认后再进入审批或执行流程。</p>
        </div>
        <div className="page-head-actions">
          <button type="button" className="secondary-button">
            <span className="material-symbols-outlined">history</span>
            查看历史
          </button>
        </div>
      </div>

      <div className="panel-card">
        <div className="panel-header">
          <div>
            <h3>草稿确认列表</h3>
            <p>全部需要你确认的 Agent 草稿动作会集中在这里展示。</p>
          </div>
          <span className="status-chip info plain">{drafts.length} 条待跟进</span>
        </div>

        <div className="data-table">
          <div className="data-table-head approval-cols">
            <span>草稿标题</span>
            <span>能力</span>
            <span>风险等级</span>
            <span>状态</span>
            <span>操作</span>
          </div>
          {drafts.length === 0 ? (
            <div className="empty-state">当前无待确认草稿</div>
          ) : (
            drafts.map((item) => (
              <div key={item.draft_id} className="data-table-row approval-cols">
                <div>
                  <strong>{item.title}</strong>
                  <p className="row-meta">{item.summary}</p>
                </div>
                <span className="mono">{item.capability_name}</span>
                <span className={`risk-level ${item.risk_level.toLowerCase()}`}>{item.risk_level}</span>
                <span className={`status-chip ${item.status === "confirmed" ? "success" : "warning"}`}>
                  {item.status}
                </span>
                <div className="approval-action-cell">
                  <button
                    type="button"
                    className="primary-button"
                    disabled={isPending || item.status === "confirmed"}
                    onClick={() => handleConfirm(item.draft_id)}
                  >
                    {activeDraftId === item.draft_id
                      ? "确认中..."
                      : item.status === "confirmed"
                        ? "已确认"
                        : "确认执行"}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {feedback ? <p className="inline-feedback">{feedback}</p> : null}
      </div>
    </section>
  );
}
