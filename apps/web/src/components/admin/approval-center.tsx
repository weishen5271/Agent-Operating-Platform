"use client";

import { useEffect, useState, useTransition } from "react";

import { confirmDraftAction, listDraftActions, rejectDraftAction } from "@/lib/api-client";
import type { DraftActionResponse } from "@/lib/api-client/types";

type ApprovalCenterProps = {
  initialDrafts?: DraftActionResponse[];
};

export function ApprovalCenter({ initialDrafts = [] }: ApprovalCenterProps) {
  const [drafts, setDrafts] = useState(initialDrafts);
  const [activeDraftId, setActiveDraftId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(!initialDrafts.length);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFeedback(null);
    listDraftActions()
      .then((response) => {
        if (!alive) return;
        setDrafts(response.drafts);
      })
      .catch((exc) => {
        if (!alive) return;
        setDrafts([]);
        setFeedback(exc instanceof Error ? exc.message : "审批草稿加载失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  function handleConfirm(draftId: string) {
    setFeedback(null);
    setActiveDraftId(draftId);
    startTransition(async () => {
      try {
        const result = await confirmDraftAction(draftId, comments[draftId] ?? "");
        setDrafts((prev) =>
          prev.map((item) => (item.draft_id === draftId ? result : item)),
        );
        setFeedback(`草稿 ${result.title} 已通过，关联业务成果已标记为已确认。`);
      } catch {
        setFeedback("草稿确认失败，请确认后端 API 已启动。");
      } finally {
        setActiveDraftId(null);
      }
    });
  }

  function handleReject(draftId: string) {
    setFeedback(null);
    setActiveDraftId(draftId);
    startTransition(async () => {
      try {
        const result = await rejectDraftAction(draftId, comments[draftId] ?? "");
        setDrafts((prev) =>
          prev.map((item) => (item.draft_id === draftId ? result : item)),
        );
        setFeedback(`草稿 ${result.title} 已驳回，关联业务成果已标记为已驳回。`);
      } catch {
        setFeedback("草稿驳回失败，请确认后端 API 已启动。");
      } finally {
        setActiveDraftId(null);
      }
    });
  }

  function statusLabel(status: string): string {
    if (status === "confirmed") return "已通过";
    if (status === "rejected") return "已驳回";
    return "待确认";
  }

  function statusTone(status: string): string {
    if (status === "confirmed") return "success";
    if (status === "rejected") return "danger";
    return "warning";
  }

  function riskLabel(risk: string): string {
    if (risk === "critical") return "关键风险";
    if (risk === "high") return "高风险";
    if (risk === "medium") return "中风险";
    if (risk === "low") return "低风险";
    return risk || "未分级";
  }

  function capabilityLabel(item: DraftActionResponse): string {
    const payload = item.payload ?? {};
    const actionId = typeof payload.action_id === "string" ? payload.action_id : "";
    const labels: Record<string, string> = {
      equipment_fault_review: "故障处置复核",
      equipment_fault_analysis: "故障分析",
    };
    if (actionId && labels[actionId]) return labels[actionId];
    if (item.capability_name.startsWith("ai_action:")) return "AI 业务动作";
    if (item.capability_name === "cmms.work_order.draft.create") return "CMMS 工单草稿";
    if (item.capability_name === "workflow.procurement.request.create") return "采购申请草稿";
    return item.title || "待确认动作";
  }

  function sourceLabel(item: DraftActionResponse): string {
    const payload = item.payload ?? {};
    const packageId = typeof payload.package_id === "string" ? payload.package_id : "";
    const actionId = typeof payload.action_id === "string" ? payload.action_id : "";
    if (packageId === "industry.mfg_maintenance" && actionId === "equipment_fault_review") {
      return "制造业设备运维助手 / 故障处置复核";
    }
    if (packageId && actionId) {
      return `${packageId} / ${capabilityLabel(item)}`;
    }
    if (item.capability_name === "workflow.procurement.request.create") return "工作流 / 采购申请草稿";
    if (item.capability_name === "cmms.work_order.draft.create") return "CMMS / 工单草稿";
    return capabilityLabel(item);
  }

  function objectLabel(item: DraftActionResponse): string {
    const object = item.payload.object;
    if (!object || typeof object !== "object" || Array.isArray(object)) return "未关联业务对象";
    const record = object as Record<string, unknown>;
    const type = typeof record.object_type === "string" ? record.object_type : "对象";
    const id = typeof record.object_id === "string" ? record.object_id : "-";
    return `${type} / ${id}`;
  }

  function runId(item: DraftActionResponse): string {
    const value = item.payload.run_id;
    return typeof value === "string" ? value : "";
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
          <span className="status-chip info plain">
            {drafts.filter((item) => item.status === "awaiting_confirmation").length} 条待确认
          </span>
        </div>

        {loading ? (
          <div className="empty-state">正在加载审批草稿...</div>
        ) : drafts.length === 0 ? (
          <div className="empty-state">当前无待确认草稿</div>
        ) : (
          <div className="approval-card-list">
            {drafts.map((item) => (
              <article key={item.draft_id} className="approval-card-item">
                <div className="approval-card-main">
                  <div className="approval-card-icon">
                    <span className="material-symbols-outlined">approval_delegation</span>
                  </div>
                  <div className="approval-card-copy">
                    <div className="approval-title-row">
                      <strong>{item.title}</strong>
                      <span className={`status-chip ${statusTone(item.status)}`}>
                        {statusLabel(item.status)}
                      </span>
                    </div>
                    <p>{item.summary}</p>
                    <div className="approval-meta-grid">
                      <span>
                        <b>能力</b>
                        {capabilityLabel(item)}
                      </span>
                      <span>
                        <b>业务对象</b>
                        {objectLabel(item)}
                      </span>
                      <span>
                        <b>风险</b>
                        <em className={`risk-level ${item.risk_level.toLowerCase()}`}>{riskLabel(item.risk_level)}</em>
                      </span>
                      <span>
                        <b>Run</b>
                        <code>{runId(item) || "-"}</code>
                      </span>
                    </div>
                    <p className="row-meta">来源 · {sourceLabel(item)}</p>
                    {item.decision_comment ? <p className="approval-decision-note">审批意见：{item.decision_comment}</p> : null}
                  </div>
                </div>
                <div className="approval-action-cell">
                  <div className="approval-decision-panel">
                    <div className="approval-decision-head">
                      <span className="material-symbols-outlined">rate_review</span>
                      <div>
                        <strong>审批意见</strong>
                        <p>{item.status === "awaiting_confirmation" ? "填写判断依据后处理草稿" : "该草稿已完成处理"}</p>
                      </div>
                    </div>
                    <textarea
                      value={comments[item.draft_id] ?? item.decision_comment ?? ""}
                      placeholder="例如：证据充分，同意进入后续处理。"
                      disabled={isPending || item.status !== "awaiting_confirmation"}
                      onChange={(event) =>
                        setComments((current) => ({
                          ...current,
                          [item.draft_id]: event.target.value,
                        }))
                      }
                    />
                    <div className="approval-button-row">
                      <button
                        type="button"
                        className="primary-button"
                        disabled={isPending || item.status !== "awaiting_confirmation"}
                        onClick={() => handleConfirm(item.draft_id)}
                      >
                        <span className="material-symbols-outlined">check_circle</span>
                        {activeDraftId === item.draft_id
                          ? "处理中..."
                          : item.status === "confirmed"
                            ? "已通过"
                            : "通过"}
                      </button>
                      <button
                        type="button"
                        className="secondary-button danger"
                        disabled={isPending || item.status !== "awaiting_confirmation"}
                        onClick={() => handleReject(item.draft_id)}
                      >
                        <span className="material-symbols-outlined">cancel</span>
                        {item.status === "rejected" ? "已驳回" : "驳回"}
                      </button>
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {feedback ? <p className="inline-feedback">{feedback}</p> : null}
      </div>
    </section>
  );
}
