import { getAdminPackages } from "@/lib/api-client";
import { Shell } from "@/components/shared/shell";
import { packageData } from "@/lib/workspace-fixtures";

export default async function PackagesPage() {
  const adminPackages = await getAdminPackages().catch(() => null);
  const packages = adminPackages?.packages.length
    ? adminPackages.packages.map((item, index) => ({
        ...item,
        version: "v1.2.0",
        plugins: Math.max(adminPackages.capabilities.length - index * 2, 3),
      }))
    : packageData.packages;
  const capabilities = adminPackages?.capabilities ?? packageData.plugins.map((item) => ({
    name: item.name,
    risk_level: item.effect,
    side_effect_level: item.effect,
    required_scope: item.packageName,
  }));

  const grayCount = packages.filter((item) => item.status === "灰度中").length || Number(packageData.hero.gray);

  function statusTone(status: string): string {
    if (status.includes("运行")) return "success";
    if (status.includes("灰度")) return "warning";
    if (status.includes("待")) return "info";
    return "";
  }

  return (
    <Shell
      activeKey="packages"
      title="业务包管理"
      searchPlaceholder="全局搜索业务包或插件..."
      tabs={[
        { label: "业务包", active: true },
        { label: "能力契约" },
        { label: "发布编排" },
      ]}
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
            <button type="button" className="secondary-button">
              <span className="material-symbols-outlined">upload</span>
              导入契约
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">add</span>
              部署新业务包
            </button>
          </div>
        </div>

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
                <div key={item.name} className="data-table-row five-cols">
                  <div className="tenant-cell">
                    <span className="tenant-avatar">{item.name.charAt(0)}</span>
                    <div>
                      <strong>{item.name}</strong>
                      <p className="row-meta">ns / {item.name.toLowerCase().replace(/\s+/g, "-")}</p>
                    </div>
                  </div>
                  <span className="mono">{item.version}</span>
                  <span>{item.owner}</span>
                  <span className="mono">{item.plugins}</span>
                  <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>插件健康度</h3>
                <p>按能力契约查看插件可用性与副作用等级。</p>
              </div>
            </div>
            <div className="stack-list">
              {capabilities.map((item) => (
                <article key={item.name} className="stack-item">
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.required_scope}</p>
                  </div>
                  <div className="stack-meta">
                    <span className="status-chip success">{item.side_effect_level}</span>
                    <span className="mono">{item.risk_level}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>

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
