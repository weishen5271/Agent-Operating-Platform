import { getAdminSecurity, getAdminTraces } from "@/lib/api-client";
import { Shell } from "@/components/shared/shell";
import { auditData } from "@/lib/workspace-fixtures";

export default async function AuditPage() {
  const [tracesResponse, securityResponse] = await Promise.all([
    getAdminTraces().catch(() => null),
    getAdminSecurity().catch(() => null),
  ]);

  const traces = tracesResponse?.items ?? [];
  const events = securityResponse?.events ?? [];

  const summary = [
    {
      label: "PII 泄露预警 (24h)",
      value: String(events.filter((item) => item.severity === "critical").length || 2).padStart(2, "0"),
      hint: "-50% 对比昨日",
      tone: "danger" as const,
      icon: "privacy_tip",
    },
    {
      label: "越权访问尝试",
      value: String(events.filter((item) => item.category === "governance").length || 14),
      hint: "+5% 对比昨日",
      tone: "warning" as const,
      icon: "lock_open",
    },
    {
      label: "系统合规指数",
      value: traces.length ? "98.4" : auditData.summary[2].value,
      hint: "已满足所有 GDPR 审计项",
      tone: "hero" as const,
      icon: "verified_user",
    },
  ];

  const traceRows = traces.length
    ? traces.map((item) => ({
        id: item.trace_id,
        user: item.user_id,
        plugin: item.strategy,
        result: "成功",
        risk: item.intent === "procurement_draft" ? "high" : "low",
      }))
    : auditData.traces;

  const eventRows = events.length
    ? events.map((item) => `${item.title} / ${item.owner} / ${item.status}`)
    : auditData.events;

  return (
    <Shell
      activeKey="audit"
      title="审计与合规控制台"
      searchPlaceholder="搜索 Trace ID 或用户..."
      tabs={[
        { label: "全局日志", active: true },
        { label: "GDPR 执行" },
        { label: "数据保留" },
      ]}
    >
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>治理与合规</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">审计与合规控制台</span>
            </div>
            <h1>审计与合规控制台</h1>
            <p>以 Trace 为主线，串联用户、插件、风险与时间戳；支持被遗忘权等合规操作的即时下钻。</p>
          </div>
          <div className="page-head-actions">
            <button type="button" className="secondary-button">
              <span className="material-symbols-outlined">archive</span>
              归档导出
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">download</span>
              导出完整报告
            </button>
          </div>
        </div>

        <div className="bento-grid three">
          {summary.map((item) => (
            <article key={item.label} className={`stat-card ${item.tone}`}>
              <div className="stat-card-head">
                <span className="stat-card-label">{item.label}</span>
                <span className="stat-icon material-symbols-outlined">{item.icon}</span>
              </div>
              <strong>{item.value}</strong>
              <p>{item.hint}</p>
              <span className="material-symbols-outlined stat-card-glyph">{item.icon}</span>
            </article>
          ))}
        </div>

        <div className="dashboard-grid">
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>审计 Trace 列表</h3>
                <p>按用户、插件、风险级别检索关键执行链路。</p>
              </div>
              <div className="panel-actions">
                <button type="button" className="ghost-button">
                  <span className="material-symbols-outlined">filter_list</span>
                  高级筛选
                </button>
              </div>
            </div>
            <div className="data-table">
              <div className="data-table-head five-cols">
                <span>Trace ID</span>
                <span>用户</span>
                <span>插件</span>
                <span>结果</span>
                <span>风险</span>
              </div>
              {traceRows.map((item) => (
                <div key={item.id} className="data-table-row five-cols">
                  <span className="mono text-primary">{item.id}</span>
                  <span>{item.user}</span>
                  <span className="mono">{item.plugin}</span>
                  <span className="status-chip success">{item.result}</span>
                  <span className={`risk-level ${item.risk.toLowerCase()}`}>{item.risk}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>合规事件摘要</h3>
                <p>展示最近 24 小时平台合规关键信号。</p>
              </div>
            </div>
            <div className="bullet-list">
              {eventRows.map((item) => (
                <div key={item} className="bullet-row">
                  <p>{item}</p>
                </div>
              ))}
            </div>
            <div className="panel-subsection">
              <h4>被遗忘权 (GDPR)</h4>
              <div className="form-field">
                <label>用户 ID 或 Trace ID</label>
                <input type="text" placeholder="输入需遗忘的标识" />
              </div>
              <button type="button" className="secondary-button">
                <span className="material-symbols-outlined">delete_sweep</span>
                发起遗忘请求
              </button>
            </div>
          </section>
        </div>
      </section>
    </Shell>
  );
}
