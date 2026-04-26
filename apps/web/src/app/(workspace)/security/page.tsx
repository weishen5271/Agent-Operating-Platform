import { getAdminSecurity } from "@/lib/api-client";
import { OutputGuardRuleEditor } from "@/components/admin/output-guard-rule-editor";
import { ToolOverrideMatrix } from "@/components/admin/tool-override-matrix";
import { Shell } from "@/components/shared/shell";
import { securityData } from "@/lib/workspace-fixtures";

export default async function SecurityPage() {
  const adminSecurity = await getAdminSecurity().catch(() => null);
  const events = adminSecurity?.events ?? [];
  const drafts = adminSecurity?.drafts ?? [];
  const toolOverrides = adminSecurity?.tool_overrides ?? [];
  const redlines = adminSecurity?.redlines ?? [];

  const stats = [
    {
      label: "当前活动规则总数",
      value: String(Math.max(events.length * 12, Number(securityData.stats[0].value.replace(/,/g, "")))),
      tone: "hero" as const,
      icon: "policy",
      hint: "覆盖 7 大类策略",
      trend: "+8% 较上周",
    },
    {
      label: "今日严重拦截",
      value: String(events.filter((item) => item.severity === "critical").length || Number(securityData.stats[1].value)),
      tone: "danger" as const,
      icon: "gpp_bad",
      hint: "高风险写操作已阻断",
      trend: "-12% 较昨日",
      trendTone: "success" as const,
    },
    {
      label: "待处理高风险审批",
      value: String(drafts.length || Number(securityData.stats[2].value)),
      tone: "warning" as const,
      icon: "assignment_late",
      hint: "需要你确认的草稿单",
      trend: "SLA 120 分钟",
    },
    {
      label: "越权访问告警",
      value: String(events.filter((item) => item.category === "governance").length || Number(securityData.stats[3].value)),
      tone: "secondary" as const,
      icon: "lock_open",
      hint: "主要来自跨租户访问",
      trend: "持续跟进",
    },
  ];

  const approvalRows = drafts.length
    ? drafts.map((item) => ({
        id: item.draft_id,
        title: item.title,
        applicant: "admin",
        risk: item.risk_level,
        status: item.status,
      }))
    : securityData.approvals;

  const ruleRows = events.length
    ? events.map((item) => ({
        name: item.title,
        owner: item.owner,
        action: item.status,
        hit: 1,
      }))
    : securityData.rules;

  function statusTone(status: string): string {
    const normalized = status.toLowerCase();
    if (normalized.includes("通过") || normalized.includes("confirmed")) return "success";
    if (normalized.includes("拒绝") || normalized.includes("blocked")) return "danger";
    if (normalized.includes("待")) return "warning";
    return "";
  }

  return (
    <Shell
      activeKey="security"
      title="安全治理与审批中心"
      searchPlaceholder="搜索审批单..."
      tabs={[
        { label: "审批概览", active: true },
        { label: "规则配置" },
        { label: "拦截日志" },
      ]}
    >
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>治理与合规</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">安全治理与审批中心</span>
            </div>
            <h1>安全治理与审批中心</h1>
            <p>以策略为中心聚合高风险动作，支持草稿确认与审批链联动，保持平台安全边界。</p>
          </div>
          <div className="page-head-actions">
            <button type="button" className="secondary-button">
              <span className="material-symbols-outlined">description</span>
              生成合规简报
            </button>
            <button type="button" className="primary-button">
              <span className="material-symbols-outlined">add_moderator</span>
              新增规则
            </button>
          </div>
        </div>

        <div className="bento-grid">
          {stats.map((item) => (
            <article key={item.label} className={`stat-card ${item.tone}`}>
              <div className="stat-card-head">
                <span className="stat-card-label">{item.label}</span>
                <span className="stat-icon material-symbols-outlined">{item.icon}</span>
              </div>
              <strong>{item.value}</strong>
              <p>{item.hint}</p>
              <span className={`stat-trend ${item.trendTone === "success" ? "" : "danger"}`}>
                <span className="material-symbols-outlined">trending_up</span>
                {item.trend}
              </span>
              <span className="material-symbols-outlined stat-card-glyph">{item.icon}</span>
            </article>
          ))}
        </div>

        <div className="dashboard-grid">
          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>审批策略</h3>
                <p>高风险写操作与跨权限动作统一在此受控处理。</p>
              </div>
              <span className="status-chip pulse info">实时同步</span>
            </div>
            <div className="data-table">
              <div className="data-table-head four-cols">
                <span>审批单</span>
                <span>申请人</span>
                <span>风险等级</span>
                <span>状态</span>
              </div>
              {approvalRows.map((item) => (
                <div key={item.id} className="data-table-row four-cols">
                  <div>
                    <strong>{item.title}</strong>
                    <p className="row-meta">{item.id}</p>
                  </div>
                  <span>{item.applicant}</span>
                  <span className={`risk-level ${item.risk.toLowerCase()}`}>{item.risk}</span>
                  <span className={`status-chip ${statusTone(item.status)}`}>{item.status}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>Tool 启用矩阵</h3>
                <p>按租户查看 Tool 默认配额、超时与启用状态。</p>
              </div>
            </div>
            <ToolOverrideMatrix initialRows={toolOverrides} />
          </section>
        </div>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>OutputGuard 红线</h3>
              <p>展示业务包声明的输出安全红线与近期触发计数。</p>
            </div>
          </div>
          <div className="dashboard-grid">
            <OutputGuardRuleEditor initialRows={redlines} />
            <div className="stack-list">
              {ruleRows.map((item) => (
                <article key={item.name} className="stack-item">
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.owner}</p>
                  </div>
                  <div className="stack-meta">
                    <span className="status-chip warning plain">{item.action}</span>
                    <span className="mono">{item.hit} 次</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </section>
    </Shell>
  );
}
