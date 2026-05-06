"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ChartCanvas } from "@/components/outputs/chart-canvas";
import { DecisionCard } from "@/components/outputs/decision-card";
import { ReportWorkspace } from "@/components/outputs/report-workspace";
import { Shell } from "@/components/shared/shell";
import { getBusinessOutput } from "@/lib/api-client";
import type { BusinessOutput } from "@/lib/api-client/types";

const TYPE_LABELS: Record<string, string> = {
  report: "分析报告",
  chart: "数据图表",
  recommendation: "决策建议",
  action_plan: "行动计划",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  reviewing: "审阅中",
  approved: "已确认",
  exported: "已导出",
  archived: "已归档",
};

function statusTone(status: string): string {
  switch (status) {
    case "approved":
      return "success";
    case "exported":
      return "info";
    case "reviewing":
      return "warning";
    case "archived":
      return "plain";
    default:
      return "";
  }
}

function shortId(value: string | null): string {
  if (!value) return "-";
  if (value.length <= 18) return value;
  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

export default function OutputDetailPage() {
  const params = useParams<{ outputId: string }>();
  const outputId = decodeURIComponent(params.outputId);
  const [output, setOutput] = useState<BusinessOutput | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    getBusinessOutput(outputId)
      .then((data) => {
        if (!alive) return;
        setOutput(data);
      })
      .catch((exc) => {
        if (!alive) return;
        setOutput(null);
        setError(exc instanceof Error ? exc.message : "业务成果加载失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [outputId]);

  return (
    <Shell activeKey="outputs" title="业务成果详情" searchPlaceholder="搜索业务成果...">
      <section className="page-section">
        {loading ? (
          <div className="trace-empty-state">
            <span className="material-symbols-outlined">progress_activity</span>
            <p>正在加载业务成果...</p>
          </div>
        ) : error || !output ? (
          <div className="trace-empty-state">
            <span className="material-symbols-outlined">error</span>
            <p>{error || "业务成果不存在"}</p>
            <Link href="/outputs" className="secondary-button">
              返回列表
            </Link>
          </div>
        ) : (
          <>
            <div className="page-head">
              <div className="page-head-meta">
                <div className="breadcrumbs">
                  <span>能力中心</span>
                  <span className="material-symbols-outlined">chevron_right</span>
                  <Link href="/outputs" className="current">
                    业务成果
                  </Link>
                  <span className="material-symbols-outlined">chevron_right</span>
                  <span className="current">{output.title}</span>
                </div>
                <h1>{output.title}</h1>
                <p>
                  {TYPE_LABELS[output.type] ?? output.type} · 业务包 {output.package_id} · 创建人{" "}
                  {output.created_by || "未知"}
                </p>
              </div>
              <div className="page-head-actions">
                <Link href="/outputs" className="secondary-button">
                  <span className="material-symbols-outlined">arrow_back</span>
                  返回列表
                </Link>
                <span className={`status-chip ${statusTone(output.status)}`}>
                  {STATUS_LABELS[output.status] ?? output.status}
                </span>
              </div>
            </div>

            {output.type === "report" ? (
              <ReportWorkspace output={output} />
            ) : output.type === "chart" ? (
              <ChartCanvas output={output} />
            ) : (
              <DecisionCard output={output} />
            )}

            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>引用证据</h3>
                  <p>对话或 AI 动作产出关联的证据与引用源。</p>
                </div>
                <span className="status-chip plain">{output.citations.length}</span>
              </div>
              {output.citations.length ? (
                <ul className="stack-list">
                  {output.citations.map((cite, idx) => (
                    <li key={idx} className="stack-item">
                      <div>
                        <span className="mono">{cite}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="row-meta">尚未关联任何证据。</p>
              )}
            </section>

            <section className="panel-card output-lineage-panel">
              <div className="panel-header">
                <div>
                  <h3>来源链路</h3>
                  <p>从业务对象到 AI Run、Trace 和成果沉淀的关联信息。</p>
                </div>
                <span className="status-chip plain">{output.run_id ? "AI Run" : "手动成果"}</span>
              </div>

              <div className="lineage-summary">
                <article>
                  <span className="material-symbols-outlined">precision_manufacturing</span>
                  <div>
                    <small>业务对象</small>
                    <strong>{output.object_id || "-"}</strong>
                    <p>{output.object_type || "未关联对象类型"}</p>
                  </div>
                </article>
                <article>
                  <span className="material-symbols-outlined">play_circle</span>
                  <div>
                    <small>AI 动作</small>
                    <strong>{output.action_id || "-"}</strong>
                    <p>{output.run_id ? shortId(output.run_id) : "未关联 Run"}</p>
                  </div>
                </article>
                <article>
                  <span className="material-symbols-outlined">account_tree</span>
                  <div>
                    <small>审计 Trace</small>
                    <strong>{shortId(output.trace_id)}</strong>
                    <p>{output.citations.length} 条引用证据</p>
                  </div>
                </article>
              </div>

              <dl className="lineage-detail-grid">
                <div>
                  <dt>Run ID</dt>
                  <dd className="mono" title={output.run_id || ""}>{output.run_id || "-"}</dd>
                </div>
                <div>
                  <dt>Action ID</dt>
                  <dd className="mono">{output.action_id || "-"}</dd>
                </div>
                <div>
                  <dt>Trace ID</dt>
                  <dd className="mono" title={output.trace_id || ""}>{output.trace_id || "-"}</dd>
                </div>
                <div>
                  <dt>业务包</dt>
                  <dd className="mono">{output.package_id}</dd>
                </div>
                <div>
                  <dt>对话 ID</dt>
                  <dd className="mono">{output.conversation_id || "-"}</dd>
                </div>
                <div>
                  <dt>草稿包</dt>
                  <dd className="mono">{output.linked_draft_group_id || "-"}</dd>
                </div>
                <div>
                  <dt>更新时间</dt>
                  <dd>{output.updated_at ? new Date(output.updated_at).toLocaleString("zh-CN") : "-"}</dd>
                </div>
              </dl>
            </section>
          </>
        )}
      </section>
    </Shell>
  );
}
