import Link from "next/link";
import { notFound } from "next/navigation";

import { ChartCanvas } from "@/components/outputs/chart-canvas";
import { DecisionCard } from "@/components/outputs/decision-card";
import { ReportWorkspace } from "@/components/outputs/report-workspace";
import { Shell } from "@/components/shared/shell";
import { getBusinessOutput } from "@/lib/api-client";

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

export default async function OutputDetailPage({
  params,
}: {
  params: Promise<{ outputId: string }>;
}) {
  const { outputId } = await params;
  const output = await getBusinessOutput(decodeURIComponent(outputId)).catch(() => null);
  if (!output) {
    notFound();
  }

  return (
    <Shell activeKey="outputs" title="业务成果详情" searchPlaceholder="搜索业务成果...">
      <section className="page-section">
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
              <p>对话产出关联的证据与引用源。</p>
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

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>关联信息</h3>
              <p>对话、追踪与草稿包的反向链接，便于回溯。</p>
            </div>
          </div>
          <dl className="data-source-grid">
            <div>
              <dt>对话 ID</dt>
              <dd className="mono">{output.conversation_id || "-"}</dd>
            </div>
            <div>
              <dt>Trace ID</dt>
              <dd className="mono">{output.trace_id || "-"}</dd>
            </div>
            <div>
              <dt>草稿包</dt>
              <dd className="mono">{output.linked_draft_group_id || "-"}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd className="mono">
                {output.updated_at ? new Date(output.updated_at).toLocaleString("zh-CN") : "-"}
              </dd>
            </div>
          </dl>
        </section>
      </section>
    </Shell>
  );
}
