import { Shell } from "@/components/shared/shell";
import { systemData } from "@/lib/workspace-fixtures";
import { TenantManagement } from "@/components/admin/tenant-management";
import { McpServerManagement } from "@/components/admin/mcp-server-management";

const summaryIcons = ["apartment", "group", "badge", "payments"];

export default async function SystemPage() {
  return (
    <Shell
      activeKey="system"
      title="租户与权限管理"
      searchPlaceholder="搜索租户、用户、角色..."
      tabs={[
        { label: "租户与用户", active: true },
        { label: "资源监控" },
        { label: "权限配置" },
      ]}
    >
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>治理与合规</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">租户与权限管理</span>
            </div>
            <h1>租户与权限管理</h1>
            <p>以硬隔离方式管理多租户架构，分配模型配额、角色模板与用户生命周期。</p>
          </div>
          <div className="page-head-actions">
            <button type="button" className="secondary-button">
              <span className="material-symbols-outlined">download</span>
              导出报告
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">add</span>
              新增租户
            </button>
          </div>
        </div>

        <div className="bento-grid">
          {systemData.summary.map((item, index) => (
            <article
              key={item.label}
              className={`stat-card ${index === 0 ? "hero" : ""}`}
            >
              <div className="stat-card-head">
                <span className="stat-card-label">{item.label}</span>
                <span className="stat-icon material-symbols-outlined">
                  {summaryIcons[index] ?? "info"}
                </span>
              </div>
              <strong>{item.value}</strong>
              <p>{item.hint}</p>
              <span className="material-symbols-outlined stat-card-glyph">
                {summaryIcons[index] ?? "info"}
              </span>
            </article>
          ))}
        </div>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>角色模板</h3>
              <p>按职责范围预配置平台常见角色与权限边界。</p>
            </div>
          </div>
          <div className="stack-list">
            {systemData.roles.map((item) => (
              <article key={item.name} className="stack-item">
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.scopes}</p>
                </div>
                <div className="stack-meta">
                  <span className="role-badge">{item.count} 人</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <TenantManagement />

        <McpServerManagement />

        <div className="info-card-grid">
          <div className="info-card">
            <div className="info-card-icon">
              <span className="material-symbols-outlined">hub</span>
            </div>
            <div>
              <h4>租户隔离策略</h4>
              <p>当前系统采用硬隔离机制（Hard-Multi-Tenancy），各租户数据存储及算力分配互不干扰。跨租户共享需在联盟链模式下开启。</p>
              <a className="info-card-link" href="#">
                阅读技术白皮书
                <span className="material-symbols-outlined">open_in_new</span>
              </a>
            </div>
          </div>
          <div className="info-card">
            <div className="info-card-icon">
              <span className="material-symbols-outlined">key</span>
            </div>
            <div>
              <h4>全局用户安全审计</h4>
              <p>实时监控所有 API Key 调用及高频登录行为，异常行为拦截率 99.8%，建议关注 2 个潜在风险账户。</p>
              <a className="info-card-link" href="/audit">
                进入审计合规中心
                <span className="material-symbols-outlined">arrow_forward</span>
              </a>
            </div>
          </div>
        </div>
      </section>
    </Shell>
  );
}
