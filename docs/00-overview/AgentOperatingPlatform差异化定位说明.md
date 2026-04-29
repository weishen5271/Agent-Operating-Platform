# Agent Operating Platform 差异化定位说明

> 本文用于梳理当前项目与 Dify、Flowise、n8n 等类似平台的差异，明确当前项目的核心亮点、产品边界和后续演进方向。

---

## 1. 核心结论

当前项目不应被定位为“带 bundle 导出能力的 Dify”。

更准确的定位是：

> 面向企业业务能力交付的 Agent Operating Platform。

它的核心不是让用户画一个固定 AI workflow，而是把企业业务系统、知识、工具和决策动作沉淀成一组受治理的 capabilities，再由 Agent 在租户、权限、上下文和风险策略约束下动态选择、组合和调用。

一句话区分：

```text
Dify：Workflow-first，人先固定流程，LLM 在流程节点里工作。

当前项目：Capability-first / Agent-planned，平台沉淀受治理能力，Agent 动态规划调用。
```

---

## 2. 当前系统已经具备的基础能力

当前项目已经实现了业务包和 Agent 执行闭环的主要底座。

### 2.1 业务包 Bundle 生命周期

- 支持 zip bundle 上传、安装、覆盖和卸载。
- 支持 `manifest.json` 校验。
- 支持 installed bundle 优先于 catalog 示例包。
- 支持 bundle 内声明：
  - `plugins`
  - `skills`
  - `tools`
  - `prompts`
  - `knowledge_imports`
- 支持路径逃逸防护，禁止 bundle 上传 Python 代码。
- 支持前端包详情页查看 bundle 内容和执行卸载。

### 2.2 Capability / Skill / Plugin / Tool 治理

- CapabilityRegistry 已接入 bundle capability。
- SkillRegistry 已加载 bundle skill。
- ToolRegistry 支持平台 tool。
- 内置 capability 优先，bundle 不能 shadow 平台内置能力。
- `executor: "platform"` 支持引用平台预装能力并做版本范围校验。
- `executor: "http"` 支持声明式 HTTP binding。
- `executor: "mcp"` 支持 MCP `initialize -> initialized -> tools/call` 最小闭环。

### 2.3 租户配置与安全

- plugin_config 支持按租户配置。
- secrets 支持嵌套 schema、前端掩码保留、后端应用层加密。
- MCP server 配置从 bundle 分离，进入平台注册表。
- HTTP/MCP executor 已有出站 URL allowlist 和 SSRF 防护。
- HTTP executor 支持 retry、idempotency key、rate limit。

### 2.4 Agent 执行链路

- Chat 主链路已接入 SkillExecutor。
- Skill steps 支持：
  - capability step
  - tool step
  - `$inputs`
  - `$steps`
  - `$prev_step`
  - `outputs_mapping`
- Trace 已能记录 skill step 执行过程。
- DraftAction 已有基础模型，可承接高风险动作的“先草稿、后确认”模式。

### 2.5 知识治理

- bundle 可声明 `knowledge_imports`。
- 上传 bundle 时默认不自动写入知识库。
- 用户可在 UI 上显式触发知识导入。
- attributes 可写入 chunk metadata。
- 已有知识库治理、wiki 编译、文件分布等模块基础。

---

## 3. 与 Dify 类平台的关键差异

### 3.1 Dify 是 Workflow-first

Dify 的典型模式是：

```text
用户先固定流程
→ 节点中调用 LLM、知识库、工具或 API
→ 用户输入进入流程
→ 按预设路径执行
```

它适合：

- 固定问答流程。
- 固定表单处理。
- 固定知识库应用。
- 固定工具调用链。

LLM 参与生成、提取、判断，但流程骨架通常由人提前定义。

### 3.2 当前项目应是 Capability-first

当前项目更应该围绕 capability 构建：

```text
平台沉淀受治理能力
→ Agent 根据租户、意图、权限、上下文选择能力
→ 平台校验 scope / risk / side_effect / schema
→ 执行 capability / skill
→ 生成答案、草稿、业务输出或审计记录
```

Capability 是企业能力资产，而不是 workflow 的普通节点。

每个 capability 都应具备：

- 输入 schema。
- 输出 schema。
- 权限 scope。
- 风险等级。
- 副作用等级。
- 租户配置。
- executor。
- Trace 审计。
- 是否需要草稿或审批。

这使平台更像“企业业务能力操作系统”，而不是普通工作流编辑器。

---

## 4. Bundle 与图形化工作流的关系

### 4.1 图形化界面可以替代手写 Bundle

长期看，不应要求实施人员长期手写：

```json
{
  "steps": [
    {
      "id": "query_alarm",
      "capability": "scada.alarm.query",
      "input": {
        "equipment_id": "$inputs.equipment_id"
      }
    }
  ]
}
```

更好的体验是：

```text
拖拽节点
→ 配置 capability
→ 连线
→ 配置参数映射
→ 校验
→ 试运行
→ 发布
```

所以图形化界面应该替代“人工编辑 bundle JSON”的过程。

### 4.2 Bundle 不应被完全替代

Bundle 仍然应该保留为：

- 版本化交付物。
- 环境迁移载体。
- 审计归档对象。
- 回滚单位。
- 安全边界声明。
- 离线交付包。

如果只有数据库中的图形化配置，会带来问题：

- 难以做版本 diff。
- 难以离线交付。
- 难以跨环境迁移。
- 难以审计某次发布到底包含哪些能力。
- 难以回滚到某个明确版本。

因此更合理的关系是：

```text
Workflow Draft
→ 图形化编辑
→ 校验 / 试运行
→ 发布成 Bundle Release
→ 安装到租户
→ Agent 运行时调用
```

也就是：

```text
图形化是编辑入口。
Bundle 是发布产物。
Capability / Skill 是运行契约。
```

---

## 5. Agent 的入口不应只有用户提问

如果项目定位是 Agent Operating Platform，Chat 只是其中一种入口。

### 5.1 Chat 入口

```text
用户提问
→ Agent 判断意图
→ 选择 capability / skill
→ 返回答案或决策草稿
```

适合：

- 智能问答。
- 临时分析。
- 业务咨询。
- 操作建议。

### 5.2 Event 入口

```text
设备报警
工单状态变化
合同进入审核节点
库存低于阈值
客户投诉创建
审批超时
```

事件触发后，Agent 可以自动判断：

- 属于哪个租户。
- 属于哪个业务包。
- 应触发哪个 skill。
- 是否需要查询外部系统。
- 是否生成 DraftAction。

### 5.3 Schedule 入口

```text
每天生成风险巡检
每小时检查异常工单
每晚汇总新增知识
每周生成租户运营报告
```

适合：

- 巡检。
- 报表。
- 风险扫描。
- SLA 监控。

### 5.4 API / Webhook / UI Action 入口

外部系统或业务页面也可以触发 Agent：

```text
POST /agent/run
POST /events
页面按钮“智能诊断”
页面按钮“风险审核”
Webhook 回调
消息队列事件
审批回调
```

这让 Agent 嵌入真实业务流程，而不是只停留在聊天框。

### 5.5 统一 Trigger 模型

后续可以抽象统一入口：

```text
Agent Trigger
- chat trigger
- event trigger
- schedule trigger
- api trigger
- ui action trigger
- approval trigger
```

所有 trigger 进入同一条治理链路：

```text
Trigger
→ Agent Router
→ Planner
→ Governed Execution
→ Output / Draft / Audit
```

---

## 6. 当前项目真正的亮点

### 6.1 业务能力可打包

能力不是散落在应用配置里，而是可以被组织成业务包：

- 行业包。
- 通用包。
- 客户私有包。
- 平台能力包。

业务包可安装、升级、卸载、回滚和审计。

### 6.2 能力调用可治理

每个 capability 都有明确治理字段：

- scope。
- risk_level。
- side_effect_level。
- input_schema。
- output_schema。
- executor。
- tenant_config。

平台不是简单执行工具，而是在执行前做权限、风险、副作用和参数校验。

### 6.3 Agent 决策可审计

Agent 不只是回答问题，还要能解释：

- 为什么选择这个 skill。
- 为什么调用这个 capability。
- 参数从哪里来。
- 哪些步骤成功或失败。
- 是否触发了审批或草稿。

Trace 是项目差异化的一部分。

### 6.4 外部系统接入可控

HTTP/MCP executor 都是声明式接入：

- 不上传业务 Python 代码。
- endpoint 与 secrets 在租户配置中管理。
- secrets 加密。
- 出站 allowlist。
- SSRF 防护。
- retry / idempotency / rate limit。

这比普通 workflow 的“随便配 API 节点”更适合企业环境。

### 6.5 高风险动作可转草稿

对于有副作用的 capability：

```text
side_effect_level = write / irreversible
```

平台应优先生成 DraftAction，由人确认后再执行。

这让 Agent 更适合进入真实业务场景。

### 6.6 知识来源可追溯

知识不是简单 dataset，而是可以和业务包、source_type、attributes、chunk metadata、wiki 编译、文件分布治理结合。

后续可以继续增强：

- 知识来源追溯。
- bundle 导入关系。
- 重复导入检测。
- 知识版本治理。
- 引用审计。

---

## 7. 产品边界建议

### 7.1 不要把“流程画布”作为唯一主心智

如果项目下一步直接做一个大而全流程画布，很容易被 Dify / Flowise 的心智覆盖。

更好的主心智是：

```text
企业业务能力治理 + Agent 动态决策执行
```

图形化界面可以做，但应该服务于：

- capability catalog。
- skill policy。
- 参数映射。
- 风险策略。
- tenant binding。
- 发布审计。

而不是把项目变成普通 AI workflow builder。

### 7.2 三层产品模型

建议将项目拆成三层：

#### Capability Layer

平台能做什么。

例如：

- 查知识。
- 查工单。
- 查报警。
- 创建草稿。
- 发起审批。
- 查库存。

#### Skill / Policy Layer

某类业务问题通常怎么处理。

例如：

- 故障诊断先查报警、SOP、历史工单。
- 法务审核先查合同条款、红线规则、历史案例。
- 财务报销先查制度、票据、审批规则。

#### Agent Planning Layer

LLM 根据当前租户、用户问题、上下文和策略决定：

- 选哪个 skill。
- 调哪些 capability。
- 参数是否完整。
- 是否需要补问。
- 是否需要审批。
- 最终输出什么业务结果。

---

## 8. 推荐演进方向

### 8.1 先强化 Capability Catalog

把 capability 做成一等公民：

- 能力列表。
- 输入输出 schema。
- 风险等级。
- 副作用等级。
- executor 类型。
- 租户启用状态。
- 最近调用记录。
- 失败率和延迟。

### 8.2 再做 Skill Policy 可视化

不要一开始做完整 Dify 式画布。

先做：

- 只读 skill steps 流程图。
- 参数映射查看。
- Trace 回放。
- step 级失败定位。

之后再逐步做编辑能力。

### 8.3 增加 Agent Trigger 模型

把 Chat 之外的入口纳入平台：

- event。
- schedule。
- api。
- ui action。
- webhook。
- approval callback。

### 8.4 强化 Governed Execution

继续增强：

- input_schema 校验。
- scope 校验。
- side_effect 策略。
- DraftAction。
- Approval。
- Trace。
- 审计日志。
- 幂等。
- 限流。

### 8.5 Bundle 作为发布态

保留 bundle，但把它从“用户手写上传”升级为：

```text
配置草稿
→ 校验
→ 试运行
→ 发布
→ 生成 bundle release
→ 租户安装
```

---

## 9. 一句话定位

当前项目的差异化不在于“也能画流程”，而在于：

> 把企业业务系统能力、知识能力和决策动作封装成可治理、可审计、可发布、可租户化的 Capability / Business Package，再由 Agent 在规则约束下动态规划和执行。

这才是它区别于 Dify-like 工作流平台的核心。
