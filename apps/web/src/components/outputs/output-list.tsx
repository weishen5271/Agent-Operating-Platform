import Link from "next/link";

import type { BusinessOutput } from "@/lib/api-client/types";

function statusTone(status: string): string {
  switch (status) {
    case "approved":
      return "success";
    case "exported":
      return "info";
    case "reviewing":
      return "warning";
    case "rejected":
      return "danger";
    case "archived":
      return "plain";
    default:
      return "";
  }
}

export function OutputList({
  items,
  typeLabels,
  statusLabels,
}: {
  items: BusinessOutput[];
  typeLabels: Record<string, string>;
  statusLabels: Record<string, string>;
}) {
  if (!items.length) {
    return (
      <div className="trace-empty-state">
        <span className="material-symbols-outlined">inventory_2</span>
        <p>当前还没有业务成果。AI 工作台执行成功或对话保存后会在这里生成记录。</p>
      </div>
    );
  }

  return (
    <div className="data-table">
      <div className="data-table-head output-cols">
        <span>标题</span>
        <span>类型</span>
        <span>业务包</span>
        <span>状态</span>
        <span>更新时间</span>
        <span>入口</span>
      </div>
      {items.map((item) => (
        <div key={item.output_id} className="data-table-row output-cols">
          <div>
            <Link href={`/outputs/${encodeURIComponent(item.output_id)}`}>
              <strong>{item.title}</strong>
            </Link>
            <p className="row-meta">{item.summary || item.output_id}</p>
            {item.run_id || item.action_id || item.object_id ? (
              <p className="row-meta">
                {item.action_id || "未关联动作"} · {item.object_type || "对象"} / {item.object_id || "-"} ·{" "}
                {item.run_id || "-"}
              </p>
            ) : null}
            {item.linked_draft_group_id ? (
              <p className="row-meta">审批草稿 · {item.linked_draft_group_id}</p>
            ) : null}
          </div>
          <span className="status-chip plain">{typeLabels[item.type] ?? item.type}</span>
          <span className="mono">{item.package_id}</span>
          <span className={`status-chip ${statusTone(item.status)}`}>
            {statusLabels[item.status] ?? item.status}
          </span>
          <span className="mono">
            {item.updated_at ? new Date(item.updated_at).toLocaleString("zh-CN") : "-"}
          </span>
          <span className="row-actions output-row-actions">
            <Link
              href={item.trace_id ? `/audit?trace_id=${encodeURIComponent(item.trace_id)}` : `/outputs/${encodeURIComponent(item.output_id)}`}
              className={`secondary-button compact ${item.trace_id ? "" : "muted"}`}
            >
              <span className="material-symbols-outlined">account_tree</span>
              Trace
            </Link>
            <Link
              href={item.linked_draft_group_id ? "/approvals" : `/outputs/${encodeURIComponent(item.output_id)}`}
              className={`secondary-button compact ${item.linked_draft_group_id ? "" : "muted"}`}
            >
              <span className="material-symbols-outlined">approval</span>
              审批
            </Link>
          </span>
        </div>
      ))}
    </div>
  );
}
