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
        <p>当前还没有业务成果。在对话页选择"保存为成果"即可生成。</p>
      </div>
    );
  }

  return (
    <div className="data-table">
      <div className="data-table-head five-cols">
        <span>标题</span>
        <span>类型</span>
        <span>业务包</span>
        <span>状态</span>
        <span>更新时间</span>
      </div>
      {items.map((item) => (
        <Link
          key={item.output_id}
          href={`/outputs/${encodeURIComponent(item.output_id)}`}
          className="data-table-row five-cols table-row-button"
        >
          <div>
            <strong>{item.title}</strong>
            <p className="row-meta">{item.summary || item.output_id}</p>
            {item.run_id || item.action_id || item.object_id ? (
              <p className="row-meta">
                {item.action_id || "未关联动作"} · {item.object_type || "对象"} / {item.object_id || "-"} ·{" "}
                {item.run_id || "-"}
              </p>
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
        </Link>
      ))}
    </div>
  );
}
