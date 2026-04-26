import type { PackageDependency } from "@/lib/api-client/types";

const KIND_LABEL: Record<PackageDependency["kind"], string> = {
  platform_skill: "平台 Skill",
  common_package: "通用包",
  plugin: "插件",
  platform_tool: "平台 Tool",
};

export function PackageDependencyGraph({ dependencies }: { dependencies: PackageDependency[] }) {
  if (dependencies.length === 0) {
    return (
      <div className="trace-empty-state">
        <span className="material-symbols-outlined">account_tree</span>
        <p>暂无依赖信息。</p>
      </div>
    );
  }

  return (
    <div className="data-table">
      <div className="data-table-head five-cols">
        <span>依赖类型</span>
        <span>名称</span>
        <span>版本范围</span>
        <span>当前版本</span>
        <span>状态</span>
      </div>
      {dependencies.map((item) => (
        <div key={`${item.kind}-${item.name}`} className="data-table-row five-cols">
          <span className="status-chip plain">{KIND_LABEL[item.kind] ?? item.kind}</span>
          <strong>{item.name}</strong>
          <span className="mono">{item.version_range}</span>
          <span className="mono">{item.current_version}</span>
          <span className={`status-chip ${item.compatible ? "success" : "warning"}`}>
            {item.compatible ? "compatible" : "review"}
          </span>
        </div>
      ))}
    </div>
  );
}
