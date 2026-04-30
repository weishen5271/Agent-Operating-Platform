# 外挂式 Agent 业务对象闭环方案

> 本文依据《Agent 平台总体战略规划》整理，用于指导当前阶段和后续阶段的产品、架构、前后端开发。平台主线不是自建数据接入、MQTT 采集或 ClickHouse 数据分析平台，而是作为外挂式 Agent 运行与治理层，围绕外部业务系统中的业务对象执行受控 AI 动作，并沉淀业务成果、草稿和审计链路。

---

## 1. 战略定位

平台定位：

> 外挂式 Agent 业务操作平台：连接企业已有业务系统、知识库和工具能力，在权限、租户、风险和审计约束下，围绕业务对象执行 AI 分析、建议生成、草稿创建和成果沉淀。

平台的核心价值不是“存业务数据”，而是“让已有业务系统获得可治理的 AI 能力”。

平台主责：

- 读取业务包声明的业务对象、AI 动作、Skill、Capability、Tool。
- 通过 HTTP / MCP / Platform executor 按需调用外部系统。
- 在一次 AI 动作中组合外部系统事实、知识库引用和模型分析。
- 保存 AI Run、Trace、BusinessOutput、DraftAction。
- 提供租户、权限、插件配置、LLM Runtime、OutputGuard 和审计治理。
- 支持独立工作台和嵌入式模块两种交付形态。

平台不主责：

- 接管外部系统主数据。
- 自建 MQTT / IoT 数据采集链路。
- 长期保存 SCADA、ERP、MES、CRM、CMMS 的完整业务明细。
- 替代数据中台、BI、流程编排平台或行业垂直 SaaS。

---

## 2. 产品闭环

当前 Chat-first 的能力需要升级为“业务对象 + AI 动作”闭环。

标准闭环：

```text
选择业务包
  ↓
选择业务对象类型
  ↓
输入或检索业务对象 ID
  ↓
选择 AI 动作
  ↓
平台按需调用外部系统和知识库
  ↓
区分事实、引用、推断、建议、草稿
  ↓
保存为 BusinessOutput / DraftAction
  ↓
Trace 审计全过程
```

关键原则：

- 用户不必先聊天，Chat 只是入口之一。
- 平台不需要先同步外部数据。
- 外部业务数据仍由原系统管理。
- 平台保存 AI 过程和结果，不保存外部业务主数据。
- 第一阶段至少接通一个真实外部只读能力，不能只停留在全 stub 演示。

---

## 3. 交付形态

平台支持两种交付形态，共享同一个 AI 执行引擎。

### 3.1 独立工作台

独立工作台是当前阶段主交付形态，适合演示、早期验证、轻量使用和平台运营。

主要页面：

- AI 工作台：选择业务包、对象、动作，执行并查看结果。
- 业务包详情：展示业务对象、AI 动作、依赖能力状态、配置完整性。
- 业务成果：展示 AI 生成的报告、建议、行动计划和草稿来源。
- Chat：自然语言探索入口，可触发结构化 AI Action。
- 审批中心：处理 DraftAction。

### 3.2 嵌入式模块

嵌入式模块是后续深度客户/OEM/白标交付形态。平台能力嵌入客户已有系统中，用户不需要切换工作环境。

集成模式分阶段支持：

```text
Phase 2: iframe 嵌入预留，提供 /embed/workbench
Phase 3: iframe 正式可用，支持 postMessage 上下文传递
Phase 3+: 后端 SDK / API 直接调用
Phase 4: Web Component / 白标 / OEM
```

嵌入模式下允许宿主系统在一次 AI Action 调用中传入业务上下文或对象快照，但这些数据只作为本次执行上下文和必要审计材料，不作为平台长期业务主数据保存。

---

## 4. 总体架构

```text
交付层
  ├─ AI 工作台
  ├─ Chat
  ├─ /embed/workbench
  ├─ SDK / API
  └─ 业务成果 / 审批 / 审计页面
        ↓
AI Execution Engine
  ├─ AIRunService
  ├─ AIActionRegistry
  ├─ SkillExecutor
  ├─ CapabilityRegistry
  ├─ ToolRegistry
  ├─ RAG / Wiki
  ├─ LLM Runtime
  ├─ OutputGuard
  └─ Trace
        ↓
业务包运行时
  ├─ business_objects
  ├─ ai_actions
  ├─ skills
  ├─ plugins
  ├─ tools
  └─ prompts / knowledge_bindings
        ↓
外部业务系统
  ├─ CMMS
  ├─ SCADA
  ├─ ERP
  ├─ MES
  └─ CRM

PostgreSQL 保存平台治理数据：
  ai_run / trace / business_outputs / draft_actions /
  conversations / plugin_config / tenant / user / permission / knowledge
```

设计原则：

- 引擎层是核心资产，交付层只做薄封装。
- ChatService 应逐步复用 AI Execution Engine，而不是形成第二套执行逻辑。
- 业务包 manifest 是能力契约，前后端都围绕 manifest 动态工作。

---

## 5. 核心抽象

### 5.1 BusinessObject

业务对象是外部系统里的业务实体。平台只保存对象引用和执行上下文。

```json
{
  "object_type": "equipment",
  "object_id": "CNC-01",
  "display_name": "CNC-01 数控机床",
  "package_id": "industry.mfg_maintenance",
  "source_system": "cmms"
}
```

第一阶段支持手动输入对象 ID。后续如果业务包声明 `lookup_capability`，则支持从外部系统检索对象候选。

### 5.2 AIAction

AI 动作描述平台可以围绕某类业务对象执行什么操作。

```json
{
  "id": "equipment_fault_analysis",
  "label": "故障分析",
  "object_types": ["equipment"],
  "description": "查询报警、历史工单和知识库，生成故障原因分析与处置建议。",
  "skill": "fault_triage",
  "required_inputs": ["equipment_id"],
  "optional_inputs": ["fault_code", "time_range"],
  "outputs": ["recommendation", "action_plan"],
  "risk_level": "low",
  "requires_confirmation": false
}
```

AIAction 可以绑定：

- 一个 Skill。
- 一个 Capability。
- 多个 Capability / Tool 编排。
- 知识库/RAG/Wiki 检索。
- 需要确认的 DraftAction。

### 5.3 DataInput

为支持独立工作台和嵌入式模块，执行引擎需要抽象数据输入来源。

```text
platform_pull   平台通过 HTTP/MCP executor 主动查询外部系统
host_context    宿主系统在调用 AI Action 时传入本次上下文或快照
mixed           部分由宿主传入，部分由平台按需查询
```

约束：

- `host_context` 不是长期数据接入。
- 宿主传入的数据只用于本次 AI Run 和必要审计。
- 如需保存快照，只保存摘要、脱敏样本和外部引用 ID。

### 5.4 AIRun

AI Run 是一次非 Chat 或结构化 Chat 动作执行记录。

```text
ai_run
- run_id
- tenant_id
- user_id
- package_id
- action_id
- source: workspace | chat | embed | api
- object_type
- object_id
- inputs
- data_input_mode
- status
- trace_id
- output_ids
- draft_id
- error_message
- created_at
- updated_at
```

---

## 6. 后端设计

### 6.1 新增模块

```text
apps/api/src/agent_platform/runtime/ai_run_service.py
apps/api/src/agent_platform/runtime/ai_action_registry.py
apps/api/src/agent_platform/runtime/data_input.py
```

`AIRunService` 复用：

- `PackageLoader`
- `SkillRegistry`
- `CapabilityRegistry`
- `SkillExecutor`
- `TraceRepository`
- `BusinessOutputRepository`
- `DraftRepository`
- `OutputGuardRuleRepository`
- `PluginConfigRepository`
- `LLMConfigRepository`
- `OpenAICompatibleLLMClient`

### 6.2 API

```text
GET  /api/v1/ai/actions
POST /api/v1/ai/actions/{action_id}/run
GET  /api/v1/ai/runs
GET  /api/v1/ai/runs/{run_id}
GET  /api/v1/ai/runs/{run_id}/trace
GET  /api/v1/ai/object-lookup
```

执行请求：

```json
{
  "package_id": "industry.mfg_maintenance",
  "source": "workspace",
  "object": {
    "object_type": "equipment",
    "object_id": "CNC-01"
  },
  "inputs": {
    "fault_code": "AX-203",
    "time_range": "last_7_days"
  },
  "data_input": {
    "mode": "platform_pull",
    "context": {}
  },
  "output_types": ["recommendation", "action_plan"]
}
```

### 6.3 输出结构

AI 输出必须区分事实、引用、推断、建议和草稿。

```json
{
  "facts": [],
  "citations": [],
  "reasoning_summary": "",
  "recommendations": [],
  "action_plan": [],
  "draft_action": null
}
```

`BusinessOutput.payload` 应保留结构化字段，避免只保存一段不可治理的自然语言。

### 6.4 可选分析快照

为审计和复盘，可以保存轻量快照：

```text
analysis_snapshot
- snapshot_id
- run_id
- tenant_id
- package_id
- source_system
- query_summary
- result_digest
- sampled_rows
- created_at
```

约束：

- 只保存摘要和少量样本。
- 不作为业务系统主数据。
- 不用于替代外部系统查询。
- 涉及敏感字段时必须脱敏或不保存。

---

## 7. 业务包 manifest 扩展

业务包新增：

```json
{
  "business_objects": [
    {
      "type": "equipment",
      "label": "设备",
      "id_field": "equipment_id",
      "lookup_capability": "cmms.equipment.lookup"
    }
  ],
  "ai_actions": [
    {
      "id": "equipment_fault_analysis",
      "label": "故障分析",
      "object_types": ["equipment"],
      "skill": "fault_triage",
      "required_inputs": ["equipment_id"],
      "optional_inputs": ["fault_code", "time_range"],
      "outputs": ["recommendation", "action_plan"],
      "risk_level": "low",
      "data_input_modes": ["platform_pull", "host_context", "mixed"]
    }
  ]
}
```

设计原则：

- Manifest 只描述业务语义，不写 UI 布局。
- 前端根据 manifest 动态渲染对象类型、动作和输入项。
- 后端严格校验 action 依赖的 Skill / Capability 是否存在。
- 依赖能力状态必须返回给前端：`http`、`mcp`、`platform`、`stub`、`missing_config`。
- 使用 stub 的结果必须显眼标注。

---

## 8. 前端设计

### 8.1 AI 工作台

路径：

```text
/(workspace)/ai-workbench
```

布局：

```text
左侧：业务包与业务对象
中间：对象上下文与 AI 动作
右侧：执行结果与 Trace
```

核心能力：

- 选择业务包。
- 选择业务对象类型。
- 输入或检索业务对象 ID。
- 展示可用 AI 动作。
- 填写动作参数。
- 执行动作。
- 展示事实、引用、推断、建议、草稿。
- 展示 Trace、已用 Skill / Capability / Tool。
- 保存或查看 BusinessOutput。

### 8.2 业务包详情页

新增展示：

- 业务对象。
- AI 动作。
- 依赖能力状态。
- 风险等级。
- 输出类型。
- 是否需要审批。
- 支持的数据输入模式。
- 插件配置完整性。

### 8.3 业务成果页

增强展示：

- 来源 run。
- 来源 action。
- 业务对象类型和对象 ID。
- 事实/引用/建议分层。
- Trace 入口。
- 关联 DraftAction。

### 8.4 嵌入预留

第一阶段只要求核心组件独立，不立即发布 Web Component。

组件设计要求：

- 对象输入、动作选择、结果展示、Trace 查看不依赖全局路由。
- 组件通过 props 接收上下文。
- 组件通过事件上报执行结果。

后续可封装为：

- `/embed/workbench`
- iframe + postMessage
- SDK / API
- Web Component

---

## 9. 租户与数据边界

租户定义：

> 租户是 Agent 运行与治理边界，不是业务数据归属边界。

租户隔离：

- 用户、角色、权限。
- 业务包启用范围。
- 插件配置和 secrets。
- LLM Runtime。
- 知识库和 Wiki。
- Trace、BusinessOutput、DraftAction。
- OutputGuard 和审批策略。

租户不表示：

- 一套外部业务主数据仓库。
- 一份设备/工单/订单/客户主数据副本。
- 一套 IoT 数据流。

---

## 10. 安全与治理

- AI Action 执行前校验租户、用户、required_scope。
- HTTP / MCP executor 继续执行 allowlist、SSRF 防护、timeout、retry、rate limit。
- 插件密钥继续走租户级 plugin_config。
- 不允许业务包上传 Python 执行代码。
- 高风险动作必须进入 DraftAction。
- AI 输出进入 OutputGuard。
- UI 必须区分外部系统事实、知识库引用、AI 推断、建议动作和待确认草稿。
- 使用 stub 或 host_context 的地方必须明确标注来源。

---

## 11. 分阶段演进

### Phase 1：独立工作台最小闭环

目标：证明“业务对象 + AI 动作 + 成果沉淀”的价值。

- 新增 AIRunService。
- 新增 AI 工作台。
- 支持设备故障分析。
- 至少接通一个真实外部只读能力，建议优先 CMMS 工单历史查询。
- 允许 SCADA 暂为 stub，但必须标注。
- 保存 recommendation / action_plan。
- Trace 可审计。

### Phase 2：声明完善与审批闭环

目标：业务包自描述完整，高风险动作可确认。

- Manifest 增加 business_objects / ai_actions。
- 业务包详情页展示动作和依赖状态。
- 支持 lookup_capability。
- DraftAction 关联 AI Run。
- 输出事实/引用/建议分层。

### Phase 3：Chat 融合与嵌入就绪

目标：自然语言入口和结构化动作入口共享同一引擎，开始支持嵌入。

- Chat Planner 可选择 AI Action。
- Chat 结果关联 run / output / draft。
- 提供 `/embed/workbench`。
- 定义 postMessage 协议。
- API 支持会话态和 API Key 两种认证。

### Phase 4：生态与规模化

目标：多行业业务包和合作伙伴扩展。

- SDK / API 示例。
- 业务包开发模板。
- 更多行业业务包。
- 白标/OEM。
- Webhook 异步回调。
- 可选 Web Component。

---

## 12. 最小可落地版本

第一版建议聚焦：

> 设备故障分析。

输入：

```text
业务包：industry.mfg_maintenance
对象类型：equipment
对象 ID：CNC-01
故障码：AX-203
```

执行链路：

```text
AIRunService
  ↓
fault_triage skill
  ↓
cmms.work_order.history（真实 HTTP 优先）
  ↓
scada.alarm_query（可暂为 stub）
  ↓
knowledge.search
  ↓
LLM 生成建议
  ↓
BusinessOutput: recommendation + action_plan
  ↓
Trace
```

验收重点：

- 用户不需要聊天。
- 至少一个外部系统真实接通。
- stub 明确标注。
- 平台不保存外部业务明细。
- 输出可保存、可追踪、可审计。

---

## 13. 核心结论

当前平台最有价值的方向是：

```text
业务对象
  ↓
AI 动作
  ↓
外部系统按需查询 / 宿主上下文输入
  ↓
知识增强分析
  ↓
业务成果 / 审批草稿
  ↓
Trace 审计
```

它不是数据中台，也不是通用 AI App 搭建器，而是面向企业已有系统的外挂式 Agent 运行与治理平台。
