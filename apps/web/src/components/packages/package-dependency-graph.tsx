import type { PackageDependency, PackagePluginSummary } from "@/lib/api-client/types";

type DependencyGroup = {
  key: PackageDependency["kind"] | "plugin";
  title: string;
  icon: string;
  description: string;
};

const GROUPS: DependencyGroup[] = [
  {
    key: "platform_skill",
    title: "平台 Skill",
    icon: "auto_awesome",
    description: "平台内置或公共编排技能，业务包通过版本范围引用。",
  },
  {
    key: "common_package",
    title: "通用包",
    icon: "deployed_code",
    description: "多个行业包可复用的基础能力包。",
  },
  {
    key: "plugin",
    title: "插件",
    icon: "extension",
    description: "业务包声明的外部系统能力接入点。",
  },
  {
    key: "platform_tool",
    title: "平台 Tool",
    icon: "build",
    description: "平台提供的原子工具能力。",
  },
];

function DependencyItem({ item }: { item: PackageDependency }) {
  return (
    <article className="stack-item">
      <div>
        <strong>{item.name}</strong>
        <p>
          版本范围 {item.version_range || "未声明"} · 当前 {item.current_version || "未解析"}
        </p>
      </div>
      <span className={`status-chip ${item.compatible ? "success" : "warning"}`}>
        {item.compatible ? "compatible" : "review"}
      </span>
    </article>
  );
}

function PluginItem({ plugin }: { plugin: PackagePluginSummary }) {
  return (
    <article className="stack-item">
      <div>
        <strong>{plugin.name}</strong>
        <p>
          {plugin.executor ?? "stub"} · {plugin.version ?? "未声明版本"} · {plugin.capabilities?.length ?? 0} capabilities
        </p>
        {plugin.description ? <p className="row-meta">{plugin.description}</p> : null}
      </div>
    </article>
  );
}

export function PackageDependencyGraph({
  dependencies,
  plugins = [],
}: {
  dependencies: PackageDependency[];
  plugins?: PackagePluginSummary[];
}) {
  if (dependencies.length === 0 && plugins.length === 0) {
    return (
      <div className="trace-empty-state">
        <span className="material-symbols-outlined">account_tree</span>
        <p>暂无依赖或插件声明。</p>
      </div>
    );
  }

  return (
    <div className="dependency-group-grid">
      {GROUPS.map((group) => {
        const groupDependencies = dependencies.filter((item) => item.kind === group.key);
        const hasItems = group.key === "plugin" ? plugins.length > 0 || groupDependencies.length > 0 : groupDependencies.length > 0;
        return (
          <section key={group.key} className="dependency-group">
            <div className="section-mini-head">
              <h4>
                <span className="material-symbols-outlined">{group.icon}</span>
                {group.title}
              </h4>
              <span className="status-chip plain">
                {group.key === "plugin" ? plugins.length + groupDependencies.length : groupDependencies.length}
              </span>
            </div>
            <p className="row-meta">{group.description}</p>
            <div className="stack-list compact-list">
              {group.key === "plugin" ? plugins.map((plugin) => <PluginItem key={plugin.name} plugin={plugin} />) : null}
              {groupDependencies.map((item) => (
                <DependencyItem key={`${item.kind}-${item.name}`} item={item} />
              ))}
              {!hasItems ? (
                <article className="stack-item empty">
                  <div>
                    <strong>暂无</strong>
                    <p>当前业务包未声明此类依赖。</p>
                  </div>
                </article>
              ) : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}
