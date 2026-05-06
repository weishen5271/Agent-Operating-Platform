"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { OutputList } from "@/components/outputs/output-list";
import { Shell } from "@/components/shared/shell";
import { listBusinessOutputs } from "@/lib/api-client";
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

export default function OutputsPage() {
  const searchParams = useSearchParams();
  const [items, setItems] = useState<BusinessOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const filters = useMemo(
    () => ({
      type: searchParams.get("type") ?? undefined,
      status: searchParams.get("status") ?? undefined,
      package: searchParams.get("package") ?? undefined,
    }),
    [searchParams],
  );

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    listBusinessOutputs(filters)
      .then((data) => {
        if (!alive) return;
        setItems(data.items);
      })
      .catch((exc) => {
        if (!alive) return;
        setItems([]);
        setError(exc instanceof Error ? exc.message : "业务成果加载失败");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [filters]);

  const counts = {
    total: items.length,
    draft: items.filter((item) => item.status === "draft").length,
    reviewing: items.filter((item) => item.status === "reviewing").length,
    exported: items.filter((item) => item.status === "exported").length,
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
            <p>管理 AI 动作和对话产出的报告、决策建议与行动计划，并联动 Trace 证据链。</p>
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
              <p>按类型 / 状态筛选，AI 工作台执行成功后会自动生成成果。</p>
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
          {loading ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">progress_activity</span>
              <p>正在加载业务成果...</p>
            </div>
          ) : error ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">error</span>
              <p>{error}</p>
            </div>
          ) : (
            <OutputList items={items} typeLabels={TYPE_LABELS} statusLabels={STATUS_LABELS} />
          )}
        </section>
      </section>
    </Shell>
  );
}
