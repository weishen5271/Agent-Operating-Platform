"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { getAdminPackages, getAdminReleases, importPackageBundle } from "@/lib/api-client";
import { Shell } from "@/components/shared/shell";
import { PackageImpactView } from "@/components/packages/package-impact-view";
import { PluginConfigForm } from "@/components/packages/plugin-config-form";
import { ReleaseTimeline } from "@/components/packages/release-timeline";
import { packageData } from "@/lib/workspace-fixtures";
import type { AdminPackagesResponse, AdminReleasesResponse, PackageDependency } from "@/lib/api-client/types";

type PackageRow = {
  package_id?: string;
  name: string;
  version: string;
  owner: string;
  plugins: number;
  status: string;
  dependencies?: PackageDependency[];
};

type TabKey = "packages" | "capabilities" | "tools" | "skills" | "knowledge" | "releases";

const TAB_DEFS: Array<{ key: TabKey; label: string }> = [
  { key: "packages", label: "业务包" },
  { key: "capabilities", label: "能力" },
  { key: "tools", label: "Tool" },
  { key: "skills", label: "Skill" },
  { key: "knowledge", label: "知识" },
  { key: "releases", label: "发布编排" },
];

function resolveTab(value: string | string[] | undefined): TabKey {
  const candidate = Array.isArray(value) ? value[0] : value;
  return TAB_DEFS.some((tab) => tab.key === candidate) ? (candidate as TabKey) : "packages";
}

export default function PackagesPage() {
  const searchParams = useSearchParams();
  const activeTab = resolveTab(searchParams.get("tab") ?? undefined);
  const [adminPackages, setAdminPackages] = useState<AdminPackagesResponse | null>(null);
  const [adminReleases, setAdminReleases] = useState<AdminReleasesResponse | null>(null);
  const [loadError, setLoadError] = useState("");
  const [importMessage, setImportMessage] = useState("");
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [reloadCounter, setReloadCounter] = useState(0);

  useEffect(() => {
    let alive = true;

    async function loadPackageRuntime() {
      setLoadError("");
      try {
        const [packagesResponse, releasesResponse] = await Promise.all([
          getAdminPackages(),
          getAdminReleases().catch(() => null),
        ]);
        if (!alive) return;
        setAdminPackages(packagesResponse);
        setAdminReleases(releasesResponse);
      } catch (exc) {
        if (!alive) return;
        setAdminPackages(null);
        setAdminReleases(null);
        setLoadError(exc instanceof Error ? exc.message : "业务包配置加载失败");
      }
    }

    void loadPackageRuntime();
    return () => {
      alive = false;
    };
  }, [reloadCounter]);

  async function handleBundleSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setImportMessage("仅支持 .zip 业务包");
      return;
    }
    setImporting(true);
    setImportMessage("");
    try {
      const overwrite = window.confirm(
        `即将导入业务包 ${file.name}。\n\n如果该业务包 ID 已存在，是否覆盖现有版本？\n确定 = 覆盖，取消 = 仅在不存在时安装`,
      );
      const result = await importPackageBundle(file, { overwrite });
      setImportMessage(
        `已导入 ${result.name} (${result.version}) · skills ${result.skills} / tools ${result.tools} / plugins ${result.plugins}`,
      );
      setReloadCounter((value) => value + 1);
    } catch (exc) {
      setImportMessage(exc instanceof Error ? exc.message : "导入失败");
    } finally {
      setImporting(false);
    }
  }

  const packages: PackageRow[] = adminPackages?.packages.length
    ? adminPackages.packages.map((item, index) => ({
        package_id: item.package_id,
        name: item.name,
        version: item.version ?? "v1.2.0",
        owner: item.owner,
        status: item.status,
        plugins: Math.max((adminPackages.capabilities?.length ?? 3) - index * 2, 3),
        dependencies: item.dependencies,
      }))
    : packageData.packages.map((item) => ({ ...item }));
  const capabilities = adminPackages?.capabilities ?? packageData.plugins.map((item) => ({
    name: item.name,
    risk_level: item.effect,
    side_effect_level: item.effect,
    required_scope: item.packageName,
  }));
  const skills = adminPackages?.skills ?? [];
  const tools = adminPackages?.tools ?? [];

  const grayCount = packages.filter((item) => item.status === "灰度中").length || Number(packageData.hero.gray);

  function statusTone(status: string): string {
    if (status.includes("运行")) return "success";
    if (status.includes("灰度")) return "warning";
    if (status.includes("待")) return "info";
    return "";
  }

  const tabs = TAB_DEFS.map((tab) => ({
    label: tab.label,
    href: `/packages?tab=${tab.key}`,
    active: tab.key === activeTab,
  }));

  return (
    <Shell
      activeKey="packages"
      title="业务包管理"
      searchPlaceholder="全局搜索业务包或插件..."
      tabs={tabs}
    >
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>能力中心</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">业务包管理</span>
            </div>
            <h1>业务包管理</h1>
            <p>统一维护业务包生命周期，结合灰度与插件健康度推进稳妥发布。</p>
          </div>
          <div className="page-head-actions">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,application/zip"
              style={{ display: "none" }}
              onChange={handleBundleSelected}
            />
            <button
              type="button"
              className="secondary-button"
              disabled={importing}
              onClick={() => fileInputRef.current?.click()}
            >
              <span className="material-symbols-outlined">upload</span>
              {importing ? "导入中..." : "导入业务包"}
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">add</span>
              部署新业务包
            </button>
          </div>
        </div>

        {loadError ? <p className="inline-error">{loadError}</p> : null}
        {importMessage ? <p className="inline-error">{importMessage}</p> : null}

        <div className="bento-grid three">
          <article className="stat-card hero">
            <div className="stat-card-head">
              <span className="stat-card-label">活跃业务包总数</span>
              <span className="stat-icon material-symbols-outlined">inventory_2</span>
            </div>
            <strong>{packages.length || packageData.hero.total}</strong>
            <p>覆盖 HR / 财务 / 法务 / 工业 四大域</p>
            <span className="stat-trend">
              <span className="material-symbols-outlined">trending_up</span>
              +12% 较上月
            </span>
            <span className="material-symbols-outlined stat-card-glyph">deployed_code</span>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">灰度中配置</span>
              <span className="stat-icon material-symbols-outlined">experiment</span>
            </div>
            <strong>{grayCount}</strong>
            <p>涉及 6 个业务域</p>
            <span className="stat-trend">
              <span className="material-symbols-outlined">trending_flat</span>
              稳步推进
            </span>
            <span className="material-symbols-outlined stat-card-glyph">experiment</span>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">插件平均响应</span>
              <span className="stat-icon material-symbols-outlined">speed</span>
            </div>
            <strong>{packageData.hero.latency}</strong>
            <p>维持在平台 SLO 范围内</p>
            <span className="stat-trend">
              <span className="material-symbols-outlined">trending_down</span>
              -4ms 较上周
            </span>
            <span className="material-symbols-outlined stat-card-glyph">speed</span>
          </article>
        </div>

        {activeTab === "packages" ? (
          <div className="dashboard-grid">
            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>业务包列表</h3>
                  <p>查看版本、负责人、插件数量与当前发布状态。</p>
                </div>
                <div className="panel-actions">
                  <button type="button" className="ghost-button">
                    <span className="material-symbols-outlined">filter_list</span>
                    筛选
                  </button>
                  <button type="button" className="ghost-button">
                    <span className="material-symbols-outlined">sort</span>
                    排序
                  </button>
                </div>
              </div>
              <div className="data-table">
                <div className="data-table-head five-cols">
                  <span>业务包</span>
                  <span>版本</span>
                  <span>负责人</span>
                  <span>插件数</span>
                  <span>状态</span>
                </div>
                {packages.map((item) => (
                  <Link
                    key={item.name}
                    href={`/packages/${encodeURIComponent(item.package_id ?? item.name)}` as never}
                    className="data-table-row five-cols"
                  >
                    <div className="tenant-cell">
                      <span className="tenant-avatar">{item.name.charAt(0)}</span>
                      <div>
                        <strong>{item.name}</strong>
                        <p className="row-meta">ns / {item.package_id ?? item.name.toLowerCase().replace(/\s+/g, "-")}</p>
                      </div>
                    </div>
                    <span className="mono">{item.version}</span>
                    <span>{item.owner}</span>
                    <span className="mono">{item.plugins}</span>
                    <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
                  </Link>
                ))}
              </div>
            </section>

            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>依赖速览</h3>
                  <p>展示业务包绑定的 Skill / 通用包 / 插件版本范围。</p>
                </div>
              </div>
              <div className="stack-list">
                {packages.flatMap((pkg) =>
                  (pkg.dependencies ?? []).map((dep, index) => (
                    <article key={`${pkg.name}-${dep.name}-${index}`} className="stack-item">
                      <div>
                        <strong>{dep.name}</strong>
                        <p>
                          {pkg.name} · {dep.kind} · 范围 {dep.version_range}
                        </p>
                      </div>
                      <span className={`status-chip ${dep.compatible ? "success" : "warning"}`}>
                        {dep.current_version}
                      </span>
                    </article>
                  )),
                )}
                {packages.every((pkg) => !pkg.dependencies?.length) ? (
                  <article className="stack-item">
                    <div>
                      <strong>暂无依赖信息</strong>
                      <p>等待 PackageLoader 接入后展示真实依赖。</p>
                    </div>
                    <span className="status-chip plain">empty</span>
                  </article>
                ) : null}
              </div>
            </section>
          </div>
        ) : null}

        {activeTab === "capabilities" ? (
          <div className="dashboard-grid">
            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>能力契约 (Capability)</h3>
                  <p>插件返回的能力契约：副作用等级、风险等级与所需权限。</p>
                </div>
              </div>
              <div className="data-table">
                <div className="data-table-head five-cols">
                  <span>能力</span>
                  <span>副作用</span>
                  <span>风险</span>
                  <span>所需权限</span>
                  <span>来源</span>
                </div>
                {capabilities.map((item) => {
                  const source = "source" in item ? (item as { source?: string }).source : undefined;
                  const packageId =
                    "package_id" in item
                      ? (item as { package_id?: string | null }).package_id
                      : undefined;
                  const sourceLabel =
                    source === "package" && packageId
                      ? `bundle · ${packageId}`
                      : source ?? "_platform";
                  return (
                    <div key={item.name} className="data-table-row five-cols">
                      <strong>{item.name}</strong>
                      <span className="status-chip plain">{item.side_effect_level}</span>
                      <span className="mono">{item.risk_level}</span>
                      <span>{item.required_scope}</span>
                      <span className="status-chip plain">{sourceLabel}</span>
                    </div>
                  );
                })}
              </div>
            </section>
            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>插件配置</h3>
                  <p>按 config_schema 渲染配置表单，密钥字段仅允许选择引用。</p>
                </div>
              </div>
              <PluginConfigForm pluginName={capabilities[0]?.name ?? "knowledge.search"} />
            </section>
          </div>
        ) : null}

        {activeTab === "tools" ? (
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>Tool 平台原子工具</h3>
                <p>无业务规则的原子能力，由平台代码声明默认配额与超时。</p>
              </div>
            </div>
            {tools.length === 0 ? (
              <div className="trace-empty-state">
                <span className="material-symbols-outlined">build</span>
                <p>暂无 Tool。</p>
              </div>
            ) : (
              <div className="data-table">
                <div className="data-table-head five-cols">
                  <span>名称</span>
                  <span>来源</span>
                  <span>版本</span>
                  <span>超时 (ms)</span>
                  <span>配额 / 分钟</span>
                </div>
                {tools.map((tool) => (
                  <div key={tool.name} className="data-table-row five-cols">
                    <div>
                      <strong>{tool.name}</strong>
                      <p className="row-meta">{tool.description}</p>
                    </div>
                    <span className="status-chip plain">{tool.source}</span>
                    <span className="mono">{tool.version}</span>
                    <span className="mono">{tool.timeout_ms}</span>
                    <span className="mono">{tool.quota_per_minute}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        ) : null}

        {activeTab === "skills" ? (
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>Skill 多步编排技能</h3>
                <p>组合 Capability + Tool + 知识检索的编排能力。</p>
              </div>
            </div>
            {skills.length === 0 ? (
              <div className="trace-empty-state">
                <span className="material-symbols-outlined">auto_awesome</span>
                <p>暂无 Skill。</p>
              </div>
            ) : (
              <div className="stack-list">
                {skills.map((skill) => (
                  <article key={skill.name} className="stack-item">
                    <div>
                      <strong>
                        {skill.name}
                        <span className="mono" style={{ marginLeft: 8, opacity: 0.7 }}>
                          {skill.version}
                        </span>
                      </strong>
                      <p>{skill.description}</p>
                      <p className="row-meta">
                        依赖能力：{skill.depends_on_capabilities.join(", ") || "—"} · 依赖工具：
                        {skill.depends_on_tools.join(", ") || "—"}
                      </p>
                    </div>
                    <span className="status-chip plain">{skill.source}</span>
                  </article>
                ))}
              </div>
            )}
          </section>
        ) : null}

        {activeTab === "knowledge" ? (
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>知识绑定</h3>
                <p>展示业务包绑定的知识源与扩展属性，详情请前往「知识库治理」。</p>
              </div>
            </div>
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">menu_book</span>
              <p>知识绑定可视化将在 Stage 3（业务包配置可视化）落地。</p>
            </div>
          </section>
        ) : null}

        {activeTab === "releases" ? (
          <div className="dashboard-grid">
            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h3>发布编排</h3>
                  <p>业务包灰度状态与回滚入口。</p>
                </div>
              </div>
              <div className="stack-list">
                {packages.map((pkg) => (
                  <article key={`release-${pkg.name}`} className="stack-item">
                    <div>
                      <strong>{pkg.name}</strong>
                      <p>当前版本 {pkg.version} · 负责人 {pkg.owner}</p>
                    </div>
                    <span className={`status-chip ${statusTone(pkg.status)}`}>{pkg.status}</span>
                  </article>
                ))}
              </div>
            </section>
            <PackageImpactView key={adminPackages ? "package-impact-loaded" : "package-impact-empty"} packages={adminPackages?.packages ?? []} />
            <ReleaseTimeline key={adminReleases ? "release-loaded" : "release-empty"} initialReleases={adminReleases?.releases ?? []} />
          </div>
        ) : null}

        <div className="info-card-grid">
          <div className="info-card">
            <div className="info-card-icon">
              <span className="material-symbols-outlined">hub</span>
            </div>
            <div>
              <h4>业务包契约治理</h4>
              <p>所有业务包通过统一的能力契约发布，平台自动校验参数、幂等语义与副作用等级。</p>
              <a className="info-card-link" href="#">
                阅读契约规范
                <span className="material-symbols-outlined">open_in_new</span>
              </a>
            </div>
          </div>
          <div className="info-card">
            <div className="info-card-icon">
              <span className="material-symbols-outlined">shield</span>
            </div>
            <div>
              <h4>灰度与回滚</h4>
              <p>支持按租户、按能力灰度，同时保留 30 天内的快速回滚路径，减少上线风险。</p>
              <a className="info-card-link" href="#">
                查看发布策略
                <span className="material-symbols-outlined">arrow_forward</span>
              </a>
            </div>
          </div>
        </div>
      </section>
    </Shell>
  );
}
