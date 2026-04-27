import { getAdminPackages, getAdminSecurity, getAdminTraces, getHomeSnapshot } from "@/lib/api-client";
import { Shell } from "@/components/shared/shell";
import { overviewData } from "@/lib/workspace-fixtures";

const glyphByTone: Record<string, string> = {
  primary: "analytics",
  success: "verified",
  danger: "warning",
  secondary: "corporate_fare",
};

export default async function WorkspaceHomePage() {
  const [home, adminPackages, adminSecurity, adminTraces] = await Promise.all([
    getHomeSnapshot().catch(() => null),
    getAdminPackages().catch(() => null),
    getAdminSecurity().catch(() => null),
    getAdminTraces().catch(() => null),
  ]);

  const metrics = [
    {
      label: "昨日请求总量",
      value: adminTraces?.items.length ? `${adminTraces.items.length * 128}` : overviewData.metrics[0].value,
      hint: home ? `活跃 capability ${home.enabled_capabilities.length} 个` : overviewData.metrics[0].hint,
      tone: "primary" as const,
      icon: "analytics",
      trend: "+12.5% 较前日",
      trendTone: "success" as const,
    },
    {
      label: "请求成功率",
      value: "99.98%",
      hint: adminPackages ? `已注册能力 ${adminPackages.capabilities.length} 个` : overviewData.metrics[1].hint,
      tone: "success" as const,
      icon: "verified",
      trend: "SLO 达标",
      trendTone: "success" as const,
    },
    {
      label: "今日告警统计",
      value: adminSecurity ? String(adminSecurity.events.length) : overviewData.metrics[2].value,
      hint: adminSecurity ? `${adminSecurity.drafts.length} 条草稿待确认` : overviewData.metrics[2].hint,
      tone: "danger" as const,
      icon: "warning",
      trend: "3 条严重待跟进",
      trendTone: "danger" as const,
    },
    {
      label: "租户活跃数",
      value: home?.tenant ? "1" : overviewData.metrics[3].value,
      hint: home?.tenant ? `${home.tenant.name} / ${home.tenant.package}` : overviewData.metrics[3].hint,
      tone: "secondary" as const,
      icon: "corporate_fare",
      trend: "+2 试点租户",
      trendTone: "success" as const,
    },
  ];

  const packageRows = adminPackages?.packages.length
    ? adminPackages.packages.map((item, index) => ({
        name: item.name,
        owner: item.owner,
        calls: `${(index + 1) * 9.7}k`,
      }))
    : overviewData.packageHealth;

  const incidents = adminSecurity?.events.length
    ? adminSecurity.events.map((item) => ({
        id: item.event_id,
        title: item.title,
        severity: item.severity.toUpperCase(),
        owner: item.owner,
      }))
    : overviewData.incidents;

  const recentSessions = adminTraces?.items.length
    ? adminTraces.items.slice(0, 3).map((item) => ({
        title: item.message,
        source: item.intent,
        time: new Date(item.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
      }))
    : overviewData.recentSessions;

  const hotCapabilities = home?.enabled_capabilities.length
    ? home.enabled_capabilities.map((item) => item.name)
    : overviewData.hotCapabilities;

  return (
    <Shell
      activeKey="overview"
      title="运营总览看板"
      searchPlaceholder="搜索资源或租户..."
      tabs={[
        { label: "实时数据流", active: true },
        { label: "业务包健康度" },
        { label: "全链路监控" },
      ]}
    >
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>运营驾驶舱</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">运营总览看板</span>
            </div>
            <h1>运营总览看板</h1>
            <p>按实时请求量、告警和租户活跃度，掌握平台核心运行信号，并对异常快速下钻。</p>
          </div>
          <div className="page-head-actions">
            <button type="button" className="secondary-button">
              <span className="material-symbols-outlined">download</span>
              导出日报
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">add_alert</span>
              新建告警规则
            </button>
          </div>
        </div>

        <div className="bento-grid">
          {metrics.map((metric, index) => {
            const isHero = index === 0;
            return (
              <article key={metric.label} className={`stat-card ${isHero ? "hero" : metric.tone}`}>
                <div className="stat-card-head">
                  <span className="stat-card-label">{metric.label}</span>
                  <span className="stat-icon material-symbols-outlined">{metric.icon}</span>
                </div>
                <strong>{metric.value}</strong>
                <p>{metric.hint}</p>
                <span className={`stat-trend ${metric.trendTone === "danger" ? "danger" : ""}`}>
                  <span className="material-symbols-outlined">
                    {metric.trendTone === "danger" ? "priority_high" : "trending_up"}
                  </span>
                  {metric.trend}
                </span>
                <span className="material-symbols-outlined stat-card-glyph">
                  {glyphByTone[metric.tone] ?? metric.icon}
                </span>
              </article>
            );
          })}
        </div>

        <div className="dashboard-grid">
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>业务包运行健康度</h3>
                <p>按调用量和负责人查看各业务包运行情况。</p>
              </div>
              <div className="panel-actions">
                <button type="button" className="ghost-button">
                  查看全表
                  <span className="material-symbols-outlined">arrow_forward</span>
                </button>
              </div>
            </div>
            <div className="data-table">
              <div className="data-table-head three-cols">
                <span>业务包</span>
                <span>负责人</span>
                <span>调用量</span>
              </div>
              {packageRows.map((item) => (
                <div key={item.name} className="data-table-row three-cols">
                  <div className="tenant-cell">
                    <span className="tenant-avatar">{item.name.charAt(0)}</span>
                    <div>
                      <strong>{item.name}</strong>
                      <p className="row-meta">更新于 5 分钟前</p>
                    </div>
                  </div>
                  <span>{item.owner}</span>
                  <span className="mono">{item.calls}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>待处理事件</h3>
                <p>聚焦当前最需要跟进的运行与治理问题。</p>
              </div>
              <span className="status-chip pulse info">实时推送</span>
            </div>
            <div className="stack-list">
              {incidents.map((item) => (
                <article key={item.id} className="stack-item">
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.id}</p>
                  </div>
                  <div className="stack-meta">
                    <span className="severity-chip">{item.severity}</span>
                    <span>{item.owner}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>

        <div className="dashboard-grid">
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>最近会话</h3>
                <p>用于回看用户最新上下文与热点问题。</p>
              </div>
            </div>
            <div className="stack-list">
              {recentSessions.map((item) => (
                <article key={item.title} className="stack-item">
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.source}</p>
                  </div>
                  <span>{item.time}</span>
                </article>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>高频能力入口</h3>
                <p>按业务问法和常用能力快速进入目标任务。</p>
              </div>
            </div>
            <div className="chip-list">
              {hotCapabilities.map((item) => (
                <button type="button" key={item} className="capability-chip">
                  <span className="material-symbols-outlined">bolt</span>
                  {item}
                </button>
              ))}
            </div>
          </section>
        </div>
      </section>
    </Shell>
  );
}
