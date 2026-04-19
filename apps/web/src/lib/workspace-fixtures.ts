export const overviewData = {
  metrics: [
    { label: "昨日请求总量", value: "1,284,902", hint: "12.5% 较前日", tone: "primary", icon: "analytics" },
    { label: "请求成功率", value: "99.98%", hint: "系统运行极稳", tone: "success", icon: "verified" },
    { label: "今日告警统计", value: "12", hint: "3 条严重待处理", tone: "danger", icon: "warning" },
    { label: "租户活跃数", value: "48", hint: "新增 2 个试点租户", tone: "secondary", icon: "corporate_fare" },
  ],
  packageHealth: [
    { name: "HR 业务包", status: "运行中", calls: "42.1k", owner: "人力共享中心" },
    { name: "财务业务包", status: "灰度中", calls: "18.9k", owner: "财务运营组" },
    { name: "法务业务包", status: "运行中", calls: "9.4k", owner: "法务合规部" },
    { name: "工业业务包", status: "待发布", calls: "2.1k", owner: "工业智能组" },
  ],
  incidents: [
    { id: "INC-240418-01", title: "财务报销插件重试率升高", severity: "P1", owner: "运行平台组" },
    { id: "INC-240418-02", title: "北京租户搜索延迟抖动", severity: "P2", owner: "检索服务组" },
    { id: "INC-240418-03", title: "安全策略误拦截待复核", severity: "P2", owner: "安全治理组" },
  ],
  recentSessions: [
    { title: "北京销售增长点分析", source: "统一对话", time: "14:20" },
    { title: "采购审批草稿生成", source: "审批联动", time: "13:42" },
    { title: "员工年假余额查询", source: "HR 业务包", time: "11:08" },
  ],
  hotCapabilities: [
    "知识检索问答",
    "费用报销草稿生成",
    "组织权限核验",
    "审计 Trace 检索",
  ],
};

export const systemData = {
  summary: [
    { label: "租户总数", value: "86", hint: "生产 48 / 沙箱 38" },
    { label: "活跃用户", value: "13,422", hint: "昨日新增 217" },
    { label: "角色模板", value: "24", hint: "覆盖 7 类业务角色" },
    { label: "预算池", value: "¥ 1.92M", hint: "本月已用 61%" },
  ],
  tenants: [
    { name: "默认企业", level: "生产", users: 3421, budget: "¥ 420k", status: "运行中" },
    { name: "华东试点租户", level: "试点", users: 892, budget: "¥ 95k", status: "灰度中" },
    { name: "工业沙箱租户", level: "沙箱", users: 114, budget: "¥ 18k", status: "运行中" },
    { name: "法务专属租户", level: "生产", users: 428, budget: "¥ 66k", status: "运行中" },
  ],
  roles: [
    { name: "平台管理员", scopes: "全部治理能力", count: 12 },
    { name: "业务包管理员", scopes: "业务包、插件、知识源", count: 48 },
    { name: "审计人员", scopes: "Trace / 审计只读", count: 16 },
    { name: "普通业务用户", scopes: "对话与审批发起", count: 13280 },
  ],
};

export const chatData = {
  threads: [
    "北京销售增长点分析",
    "采购审批草稿生成",
    "北京地区报销政策问答",
    "财务插件报错定位",
  ],
  messages: [
    {
      role: "user",
      content: "帮我查询一下上个月北京地区的销售总额，并分析主要的增长点在哪里。",
      time: "14:20:05",
    },
    {
      role: "assistant",
      content:
        "为您查询到上个月（2026 年 3 月）北京地区总销售额为 ¥1,245,600，同比提升 12.4%。主要增长点来自新能源汽车配件（+45%）与智能家居终端（+22%）。如需，我可以继续生成详细增长报告与引用依据。",
      time: "14:20:08 / 耗时 3.2s",
    },
  ],
  trace: [
    { step: "intent", summary: "识别为销售分析类任务", status: "completed" },
    { step: "planner", summary: "生成 direct_answer + data_plugin 检索计划", status: "completed" },
    { step: "plugin", summary: "调用 sales.analytics.region_growth", status: "completed" },
    { step: "response", summary: "组装分析结论与下一步建议", status: "completed" },
  ],
  references: [
    { title: "北京地区销售日报", type: "knowledge", snippet: "2026-03 月累计销售额 124.56 万元，同比提升 12.4%" },
    { title: "sales.analytics.region_growth", type: "plugin", snippet: "返回区域维度销售额与主要品类变化" },
  ],
};

export const packageData = {
  hero: {
    total: "1,284",
    gray: "18",
    latency: "42ms",
  },
  packages: [
    { name: "HR 业务包", version: "v1.2.0", owner: "人力共享中心", plugins: 12, status: "运行中" },
    { name: "财务业务包", version: "v0.9.8", owner: "财务运营组", plugins: 18, status: "灰度中" },
    { name: "法务业务包", version: "v1.0.6", owner: "法务合规部", plugins: 9, status: "运行中" },
    { name: "工业业务包", version: "v0.6.1", owner: "工业智能组", plugins: 15, status: "待发布" },
  ],
  plugins: [
    { name: "knowledge.search", packageName: "通用知识包", effect: "read", health: "99.99%" },
    { name: "hr.leave.balance.query", packageName: "HR 业务包", effect: "read", health: "99.96%" },
    { name: "finance.reimbursement.submit", packageName: "财务业务包", effect: "write", health: "98.21%" },
    { name: "org.auth.verify", packageName: "权限治理包", effect: "read", health: "99.88%" },
  ],
};

export const securityData = {
  stats: [
    { label: "当前活动规则总数", value: "1,248" },
    { label: "今日严重拦截", value: "32" },
    { label: "待处理高风险审批", value: "156" },
    { label: "越权访问告警", value: "14" },
  ],
  approvals: [
    { id: "APR-20260418-001", title: "报销提交草稿确认", risk: "high", applicant: "张三", status: "待审批" },
    { id: "APR-20260418-002", title: "组织权限开通申请", risk: "critical", applicant: "李四", status: "待二级审批" },
    { id: "APR-20260418-003", title: "合同摘要外发确认", risk: "high", applicant: "王五", status: "待你确认" },
  ],
  rules: [
    { name: "PII 外发检测", owner: "安全治理组", hit: 24, action: "block" },
    { name: "跨租户数据访问", owner: "权限治理组", hit: 8, action: "block" },
    { name: "高风险写操作", owner: "审批中心", hit: 156, action: "review" },
    { name: "Prompt Injection 检测", owner: "内容安全组", hit: 64, action: "review" },
  ],
};

export const auditData = {
  summary: [
    { label: "PII 泄露预警 (24h)", value: "02", hint: "-50% 对比昨日" },
    { label: "越权访问尝试", value: "14", hint: "+5% 对比昨日" },
    { label: "系统合规指数", value: "98.4", hint: "已满足所有 GDPR 审计项" },
  ],
  traces: [
    { id: "trc_9a13f1", user: "zhangsan", plugin: "finance.reimbursement.submit", result: "审批中", risk: "high" },
    { id: "trc_b341ad", user: "lisi", plugin: "knowledge.search", result: "成功", risk: "low" },
    { id: "trc_f1cc08", user: "wangwu", plugin: "org.auth.verify", result: "成功", risk: "medium" },
    { id: "trc_291bc0", user: "zhaoliu", plugin: "sales.analytics.region_growth", result: "成功", risk: "low" },
  ],
  events: [
    "审计留痕已覆盖意图识别、检索、插件调用、响应组装",
    "过去 24 小时无跨租户泄露事件",
    "3 条高风险审批与审计编号完成关联",
  ],
};

export const knowledgeData = {
  pipeline: [
    { label: "正在清洗", value: "1,248 条", progress: 74 },
    { label: "分块索引", value: "854 块", progress: 51 },
    { label: "向量化", value: "4,102 向量", progress: 83 },
    { label: "质量校验", value: "96.8%", progress: 96 },
  ],
  sources: [
    { name: "企业制度库", type: "PDF / Docx", chunks: 4812, owner: "知识平台组", status: "运行中" },
    { name: "财务流程文档", type: "Confluence", chunks: 1946, owner: "财务运营组", status: "运行中" },
    { name: "工业设备手册", type: "Markdown", chunks: 3021, owner: "工业智能组", status: "重建中" },
    { name: "法务合同模板", type: "SharePoint", chunks: 883, owner: "法务合规部", status: "运行中" },
  ],
};
