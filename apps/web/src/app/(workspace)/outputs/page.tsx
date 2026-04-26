import Link from "next/link";

import { OutputList } from "@/components/outputs/output-list";
import { Shell } from "@/components/shared/shell";
import { listBusinessOutputs } from "@/lib/api-client";

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

export default async function OutputsPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string; status?: string; package?: string }>;
}) {
  const params = await searchParams;
  const data = await listBusinessOutputs({
    type: params.type,
    status: params.status,
    package: params.package,
  }).catch(() => ({ items: [] as Awaited<ReturnType<typeof listBusinessOutputs>>["items"] }));

  const counts = {
    total: data.items.length,
    draft: data.items.filter((item) => item.status === "draft").length,
    reviewing: data.items.filter((item) => item.status === "reviewing").length,
    exported: data.items.filter((item) => item.status === "exported").length,
  };

  return (
    <Shell activeKey="outputs" title="业务成果工作台" searchPlaceholder="搜索业务成果...">
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>能力中心</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">业务成果</span>
            </div>
            <h1>业务成果工作台</h1>
            <p>管理对话产出的报告、图表、决策建议与行动计划，并联动审批与证据链。</p>
          </div>
        </div>

        <div className="bento-grid four">
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">成果总数</span>
              <span className="stat-icon material-symbols-outlined">stacks</span>
            </div>
            <strong>{counts.total}</strong>
            <p>覆盖报告 / 图表 / 决策 / 行动计划。</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">草稿</span>
              <span className="stat-icon material-symbols-outlined">edit_note</span>
            </div>
            <strong>{counts.draft}</strong>
            <p>等待编辑或提交审阅。</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">审阅中</span>
              <span className="stat-icon material-symbols-outlined">rate_review</span>
            </div>
            <strong>{counts.reviewing}</strong>
            <p>审批链处理中的成果。</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">已导出</span>
              <span className="stat-icon material-symbols-outlined">cloud_download</span>
            </div>
            <strong>{counts.exported}</strong>
            <p>已生成对外交付件。</p>
          </article>
        </div>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>成果列表</h3>
              <p>按类型 / 状态筛选，或从对话页"保存为成果"创建。</p>
            </div>
            <div className="panel-actions">
              <Link href="/outputs?type=report" className="secondary-button compact">
                仅看报告
              </Link>
              <Link href="/outputs?type=chart" className="secondary-button compact">
                仅看图表
              </Link>
              <Link href="/outputs?type=recommendation" className="secondary-button compact">
                仅看决策
              </Link>
              <Link href="/outputs" className="secondary-button compact">
                清除筛选
              </Link>
            </div>
          </div>
          <OutputList
            items={data.items}
            typeLabels={TYPE_LABELS}
            statusLabels={STATUS_LABELS}
          />
        </section>
      </section>
    </Shell>
  );
}
