# 外挂式 Agent 业务对象闭环实施计划

> 本计划依据《Agent 平台总体战略规划》和 [外挂式 Agent 业务对象闭环方案](../01-architecture/多入口AI业务操作平台与外部数据分析方案.md) 制定。计划目标是支撑当前阶段开发，并为后续嵌入式交付、业务包生态和规模化实施预留架构边界。当前阶段不接入 MQTT，不新增 ClickHouse，不把平台升级为数据中台。

---

## 1. 阶段总览

| 阶段 | 目标 | 预估工期 | 关键产出 |
|------|------|----------|----------|
| Sprint 0 | 契约与边界确认 | 3 个工作日 | AIRun / AIAction / BusinessObject / DataInput 契约 |
| Sprint 1 | 后端 AI Run 最小闭环 | 6 个工作日 | AIRunService、API、Trace、BusinessOutput |
| Sprint 2 | 前端 AI 工作台 | 6 个工作日 | 对象输入式工作台、动作执行、分层结果展示 |
| Sprint 3 | Manifest 扩展与依赖诊断 | 5 个工作日 | business_objects / ai_actions 校验与动态渲染 |
| Sprint 4 | 真实外部能力与审批闭环 | 6 个工作日 | CMMS 真实只读接入、DraftAction 关联 |
| Sprint 5 | Chat 融合与嵌入预留 | 5 个工作日 | Chat 关联 AI Run、/embed 预留、API Key 骨架 |

合计约 **31 个工作日**。建议预留 20% buffer，整体约 **37 个工作日**。

---

## 2. 当前阶段范围

### 2.1 必做

- AI 工作台。
- 设备故障分析 action。
- 历史工单总结 action。
- `ai_run` 表。
- `AIRunService`。
- BusinessOutput 保存。
- Trace 展示。
- stub / missing_config 明确提示。
- 至少一个真实外部只读能力，优先 `cmms.work_order.history`。

### 2.2 不做

- MQTT 接入。
- ClickHouse。
- 外部业务明细长期存储。
- 自由 SQL 分析。
- 自动同步外部对象主数据。
- Web Component 正式发布。
- OAuth 完整实现。

### 2.3 预留

- DataInput 抽象：`platform_pull`、`host_context`、`mixed`。
- `/embed/workbench` 页面边界。
- API Key 调用形态。
- 组件独立化，避免绑定全局路由。

---

## 3. Sprint 0：契约与边界确认

目标：先把模型边界定清楚，避免再次滑向数据平台或 Chat-only。

任务：

- 梳理 `ChatService` 中可复用的执行逻辑。
- 确认 `ai_run` 表字段。
- 确认 `BusinessObject`、`AIAction`、`DataInput` 请求/响应结构。
- 确认输出分层结构：事实、引用、推断、建议、草稿。
- 确认第一版只支持对象 ID 手动输入。
- 确认第一版动作：
  - `equipment_fault_analysis`
  - `work_order_history_summary`
- 确认真实外部只读能力接入目标：`cmms.work_order.history`。

验收：

- API 契约草案完成。
- 数据库迁移草案完成。
- Manifest 扩展草案完成。
- 明确第一版不引入 MQTT、ClickHouse、外部数据长期存储。

---

## 4. Sprint 1：后端 AI Run 最小闭环

目标：后端可以通过结构化请求执行一次 AI 动作，并保存结果、Trace、业务成果。

任务：

- 新增 `ai_run` 表迁移。
- 新增 `AIRunService`。
- 新增 `AIActionRegistry`。
- 新增 `DataInput` 结构，第一版支持 `platform_pull`。
- 新增接口：
  - `GET /api/v1/ai/actions`
  - `POST /api/v1/ai/actions/{action_id}/run`
  - `GET /api/v1/ai/runs/{run_id}`
  - `GET /api/v1/ai/runs/{run_id}/trace`
- 复用 `SkillExecutor` 执行 `fault_triage`。
- 复用 `TraceRepository` 记录步骤。
- 复用 `BusinessOutputRepository` 保存 `recommendation` / `action_plan`。
- 输出 payload 区分 facts、citations、reasoning_summary、recommendations、action_plan。
- 缺少必填参数时返回缺参结果，不调用外部能力。
- Capability 为 stub 时在结果和 Trace 中标注。

验收：

- 通过 API 输入 `equipment_id`、`fault_code` 可执行设备故障分析。
- 执行后生成 `ai_run`、Trace、BusinessOutput。
- 输出结构化，不只是纯文本。
- 缺参、missing_config、stub 均有明确提示。

---

## 5. Sprint 2：前端 AI 工作台

目标：用户可以不通过聊天，直接围绕业务对象执行 AI 动作。

任务：

- 新增页面：

```text
/(workspace)/ai-workbench
```

- 支持：
  - 选择业务包。
  - 选择对象类型。
  - 输入对象 ID。
  - 展示可用 AI 动作。
  - 填写动作参数。
  - 执行动作。
  - 展示事实、引用、推断、建议、行动计划。
  - 展示 Trace。
  - 展示已用 Skill / Capability / Tool。
  - 展示生成的 BusinessOutput。

组件要求：

- 对象输入组件不依赖页面路由。
- 动作选择组件不硬编码制造业业务。
- 结果展示组件支持后续嵌入复用。
- stub 标识必须显眼。

验收：

- 用户能完成“设备故障分析”主路径。
- 页面不展示虚构对象列表，不伪造设备主数据。
- 页面能区分事实、引用、推断、建议。
- 页面能跳转 Trace 和 BusinessOutput。

---

## 6. Sprint 3：Manifest 扩展与依赖诊断

目标：AI 工作台能力由业务包声明驱动，而不是前后端硬编码。

后端任务：

- 扩展业务包 manifest 解析：
  - `business_objects`
  - `ai_actions`
  - `data_input_modes`
- 补充 JSON Schema 校验。
- 扩展业务包详情接口，返回业务对象和动作声明。
- 校验 action 依赖的 skill / capability 是否存在。
- 返回依赖能力状态：
  - `http`
  - `mcp`
  - `platform`
  - `stub`
  - `missing_config`

前端任务：

- 业务包详情页展示业务对象、AI 动作、依赖状态。
- AI 工作台根据 manifest 动态渲染对象类型、动作和输入项。

验收：

- 修改业务包 manifest 后，前端动作列表随之变化。
- 依赖能力缺失或配置不完整时，页面能提示。
- 不需要改前端代码即可新增简单 AI 动作。

---

## 7. Sprint 4：真实外部能力与审批闭环

目标：避免全 stub 演示，打通一个真实只读外部能力，并支持中高风险动作草稿。

后端任务：

- 配置并验证 `cmms.work_order.history` 真实 HTTP executor。
- AI Action 支持 `requires_confirmation`。
- 中高风险动作生成 DraftAction。
- DraftAction 关联 `ai_run`。
- 支持 `lookup_capability`。
- 新增对象检索接口：

```text
GET /api/v1/ai/object-lookup?package_id=...&object_type=...&keyword=...
```

前端任务：

- AI 工作台对象 ID 输入框支持搜索候选。
- 搜索结果来自外部系统。
- 中高风险动作展示草稿和审批入口。

验收：

- 至少一个外部系统能力真实接通。
- 能从外部系统按需检索对象候选。
- 平台不长期保存对象主数据。
- 工单草稿类动作不会直接写外部系统。
- 草稿可跳转审批页。

---

## 8. Sprint 5：Chat 融合与嵌入预留

目标：Chat 保留为自然语言入口，同时为嵌入式交付留出接口和组件边界。

后端任务：

- Chat Planner 可选择 AI Action。
- Chat 执行 AI Action 后关联 `ai_run`。
- Chat 响应返回 `run_id`、`output_ids`、`draft_id`。
- API 支持会话态和 API Key 骨架。
- 预留 `/embed/workbench` 路由和上下文参数解析。

前端任务：

- Chat 页面展示关联 AI Run。
- Chat 页面支持跳转业务成果和审批草稿。
- Outputs 页面展示来源 action、object、run。
- 核心组件 props 化，为 iframe/embed 复用准备。

验收：

- Chat 和 AI 工作台执行同一动作时，结果链路一致。
- 现有 Chat / RAG / Wiki / Tool 用例回归通过。
- `/embed/workbench` 能加载精简版工作台壳。
- Outputs 能反查 Trace 和 AI Run。

---

## 9. 后续阶段规划

### Phase 3：嵌入式交付可用

- `/embed/workbench` 正式可用。
- postMessage 协议完成。
- 支持宿主传入 `host_context`。
- SDK / API 文档完善。
- API Key 权限和审计完善。

### Phase 4：生态与规模化

- Web Component 可选发布。
- Python / TypeScript SDK。
- Webhook 异步回调。
- 白标/OEM。
- 业务包模板库。
- 多行业业务包。

---

## 10. 验收主路径

```text
进入 AI 工作台
  ↓
选择制造业设备运维业务包
  ↓
选择对象类型：设备
  ↓
输入对象 ID：CNC-01
  ↓
选择动作：故障分析
  ↓
输入故障码：AX-203
  ↓
执行
  ↓
查看事实、引用、推断、建议和行动计划
  ↓
查看 Trace
  ↓
在业务成果页查看保存结果
```

边界路径：

- 未输入设备 ID，系统提示缺少必填参数。
- CMMS 插件未配置，系统提示插件配置缺失。
- SCADA 能力为 stub，系统提示当前为占位 executor。
- 高风险动作生成草稿，不直接写外部系统。
- 宿主传入上下文时，页面标注数据来源为 host_context。

---

## 11. 成功指标

当前阶段指标：

- 至少 1 个真实外部只读能力接通。
- 设备故障分析闭环可在工作台完成。
- 每次执行均生成 Trace。
- 每次成功执行均生成 BusinessOutput。
- stub 调用 100% 可见。
- 输出中事实、引用、推断、建议可区分。

客户验证指标：

- 单次故障分析耗时下降。
- 用户保存或采纳建议的比例。
- 用户是否愿意每天使用工作台。
- 外部系统跨系统查询次数是否减少。
- 草稿是否进入审批。

---

## 12. 核心交付价值

本计划交付后，平台价值从“问答演示”转为：

```text
用户围绕业务对象工作
  ↓
平台按业务包提供 AI 动作
  ↓
Agent 按需调用外部系统和知识库
  ↓
生成可保存、可审批、可追踪的业务成果
  ↓
未来可嵌入客户已有系统
```

这条路径既支撑当前阶段开发，也为未来嵌入式交付、业务包生态和商业化扩展保留了清晰边界。
