# 多入口 AI 业务操作平台与外部数据分析方案

> 本文用于梳理平台从“对话驱动的业务包执行平台”升级为“多入口 AI 业务操作平台”的前后端改造方案。重点覆盖外部系统通过 HTTP / MQTT 接入数据、落入 ClickHouse 存储，再基于已存储数据进行 AI 智能分析的完整链路。

---

## 1. 背景与目标

当前平台已经具备对话入口、业务包、Skill / Capability / Tool、RAG / Wiki、Trace、BusinessOutput、DraftAction 等基础能力。

当前主要链路是：

```text
用户对话
  ↓
ChatService
  ↓
业务包路由 / 意图识别
  ↓
Skill / Capability / Tool / RAG / Wiki
  ↓
对话回答 / Trace / 草稿 / 业务成果
```

这条链路本质上是 Chat-first，即以自然语言对话作为统一入口。

后续目标是扩展为多入口 AI 业务操作平台：

- 保留对话入口。
- 增加 AI 工作台入口，支持结构化参数触发 AI 任务。
- 增加数据资产入口，支持外部数据先入库，再基于平台存储数据进行 AI 分析。
- 支持 HTTP / MQTT 接收外部系统数据。
- 使用 ClickHouse 存储外部业务明细和分析数据。
- 使用 PostgreSQL 继续承载平台事务主库。
- AI 分析基于 ClickHouse 聚合结果，而不是直接分析单条接入消息或全量明细。

---

## 2. 总体架构

### 2.1 外部数据分析链路

```text
外部系统
  ├─ HTTP 推送
  └─ MQTT 推送
        ↓
数据接入层 Ingestion Service
        ↓
数据标准化 / 校验 / 租户隔离 / 幂等处理
        ↓
ClickHouse 外部数据分析库
        ↓
Data Analysis Service 查询 / 聚合
        ↓
AI Task Runtime
        ↓
LLM 基于聚合结果生成分析
        ↓
PostgreSQL 保存任务、Trace、BusinessOutput、审批草稿
```

### 2.2 用户触发链路

```text
用户对话 / AI 工作台 / 数据资产页
        ↓
AI Task Runtime
        ↓
业务包 Skill / Capability / Tool / RAG / Wiki / Data Analysis
        ↓
PostgreSQL 保存 Trace / Output / Draft / Task
```

---

## 3. 数据库分工

### 3.1 PostgreSQL

PostgreSQL 继续作为平台事务主库，保存强一致、强权限、强状态流转的数据：

- 租户、用户、角色、权限。
- 业务包、插件配置、密钥配置。
- 对话、Trace、AI Task。
- BusinessOutput。
- 审批草稿 DraftAction。
- 知识库、Wiki、pgvector。
- 系统配置、审计、安全事件。

不建议把这些平台状态迁入 ClickHouse。

### 3.2 ClickHouse

ClickHouse 作为外部数据分析库，保存外部系统推送的明细数据和分析宽表：

- 设备报警。
- 传感器指标。
- 工单流水。
- 业务事件。
- 日志型数据。
- 指标快照。
- 标准化后的分析宽表。

ClickHouse 适合大批量写入、按时间范围查询、多维聚合、TopN、趋势统计和高压缩存储；不适合替代 PostgreSQL 承载用户权限、审批流、配置和频繁更新的事务状态。

---

## 4. 后端改造方案

### 4.1 新增 AI Task Runtime

新增通用 AI 任务层，让 Chat 不再是唯一入口。

建议新增模块：

```text
apps/api/src/agent_platform/runtime/ai_task_service.py
apps/api/src/agent_platform/runtime/data_analysis_service.py
apps/api/src/agent_platform/runtime/analysis_planner.py
```

建议新增接口：

```text
POST /api/v1/ai/tasks
GET  /api/v1/ai/tasks
GET  /api/v1/ai/tasks/{task_id}
GET  /api/v1/ai/tasks/{task_id}/trace
POST /api/v1/ai/data-analysis
```

AI Task 支持来源：

```text
chat           对话触发
workspace      AI 工作台触发
data_analysis  基于已入库外部数据触发
```

PostgreSQL 新增 `ai_task` 表：

```text
ai_task
- task_id
- tenant_id
- user_id
- package_id
- source
- scenario
- input
- status
- trace_id
- output_ids
- created_at
- updated_at
```

### 4.2 新增数据接入层

新增 ingestion 模块：

```text
apps/api/src/agent_platform/ingestion/
  service.py
  http_routes.py
  mqtt_consumer.py
  schema_registry.py
  clickhouse_repository.py
```

建议新增接口：

```text
POST /api/v1/data-ingest/events
POST /api/v1/data-ingest/events/batch
GET  /api/v1/data-assets/datasets
GET  /api/v1/data-assets/records
```

HTTP 和 MQTT 都只负责接收、校验、标准化、入库，不直接触发 AI 分析。

统一内部链路：

```text
HTTP Ingest Route ┐
                  ├─ IngestionService → ClickHouse
MQTT Consumer     ┘
```

### 4.3 接入数据结构

HTTP 接入请求示例：

```json
{
  "tenant_id": "sw",
  "package_id": "industry.mfg_maintenance",
  "dataset": "equipment_alarm",
  "source": "scada",
  "external_id": "alarm-001",
  "occurred_at": "2026-04-29T10:30:00+08:00",
  "payload": {
    "equipment_id": "CNC-01",
    "fault_code": "AX-203",
    "severity": "high",
    "alarm_time": "2026-04-29T10:30:00+08:00",
    "message": "伺服驱动过热"
  }
}
```

处理要求：

- `tenant_id` 必须可鉴权，不应只信任请求体。
- `package_id` 和 `dataset` 必须在业务包声明中存在。
- `external_id` 用于幂等。
- `occurred_at` 必须独立字段，不只放在 payload 中。
- 原始 payload 和标准化 payload 分开保存。

### 4.4 ClickHouse 表设计

保留一张原始通用表，用于所有外部接入数据留痕：

```sql
CREATE TABLE raw_external_event
(
    tenant_id String,
    package_id String,
    dataset LowCardinality(String),
    source LowCardinality(String),
    external_id String,
    occurred_at DateTime64(3, 'Asia/Shanghai'),
    ingested_at DateTime64(3, 'Asia/Shanghai') DEFAULT now64(3),
    payload String,
    normalized_payload String
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, package_id, dataset, occurred_at, external_id);
```

对核心高频数据集建立分析宽表，例如设备报警：

```sql
CREATE TABLE equipment_alarm
(
    tenant_id String,
    package_id String,
    equipment_id String,
    fault_code String,
    severity LowCardinality(String),
    message String,
    alarm_time DateTime64(3, 'Asia/Shanghai'),
    external_id String,
    payload String,
    ingested_at DateTime64(3, 'Asia/Shanghai') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(alarm_time)
ORDER BY (tenant_id, equipment_id, alarm_time, external_id);
```

设计原则：

- 通用表用于原始数据留痕和低频数据集。
- 宽表用于高频查询和核心分析场景。
- 分区字段优先使用业务发生时间。
- 排序键优先包含租户、核心过滤字段、时间字段、外部唯一标识。

### 4.5 基于存储数据的 AI 分析

AI 分析必须从 ClickHouse 中查询已存储数据，不直接基于刚收到的单条消息做分析。

请求示例：

```json
{
  "package_id": "industry.mfg_maintenance",
  "dataset": "equipment_alarm",
  "analysis_type": "trend_summary",
  "filters": {
    "equipment_id": "CNC-01",
    "start_time": "2026-04-01T00:00:00+08:00",
    "end_time": "2026-04-29T23:59:59+08:00"
  },
  "question": "分析这台设备本月报警趋势和主要风险"
}
```

后端执行流程：

```text
校验租户、权限、业务包、数据集
  ↓
读取业务包 dataset 声明
  ↓
根据 dataset、analysis_type、filters 选择查询模板
  ↓
ClickHouse 返回聚合数据和关键样本
  ↓
LLM 基于聚合结果生成分析结论
  ↓
保存 BusinessOutput
  ↓
记录 Trace
```

LLM 不直接访问 ClickHouse，也不接收全量明细。

程序侧应先完成确定性聚合：

- 总记录数。
- 时间趋势。
- TopN 设备、故障码、事件类型。
- 严重等级分布。
- 最近关键样本。
- 环比变化。
- 异常集中时段。

LLM 只负责基于聚合结果生成：

- 趋势解释。
- 可能原因。
- 风险判断。
- 处置建议。
- 报告摘要。
- 行动计划。

### 4.6 查询安全

ClickHouse 查询不允许由用户自由拼 SQL。

建议采用白名单查询模板：

```text
dataset + analysis_type + filters
  ↓
后端选择固定 SQL 模板
  ↓
参数化绑定 tenant_id、时间范围、设备编号等条件
```

必须保证：

- 查询自动注入 `tenant_id`。
- 用户只能查询当前租户数据。
- dataset 必须在业务包声明中存在。
- analysis_type 必须在业务包声明中存在。
- 时间范围、limit、返回样本数必须有限制。

---

## 5. 业务包改造方案

业务包 `manifest.json` 增加 `datasets` 声明，用于描述外部数据集、存储位置和可用分析类型。

示例：

```json
{
  "datasets": [
    {
      "name": "equipment_alarm",
      "label": "设备报警数据",
      "source": "scada",
      "storage": "clickhouse",
      "table": "equipment_alarm",
      "time_field": "alarm_time",
      "unique_keys": ["external_id"],
      "schema": {
        "required": ["equipment_id", "alarm_time", "severity"],
        "properties": {
          "equipment_id": { "type": "string", "label": "设备编号" },
          "fault_code": { "type": "string", "label": "故障码" },
          "severity": { "type": "string", "label": "严重等级" },
          "alarm_time": { "type": "datetime", "label": "报警时间" },
          "message": { "type": "string", "label": "报警描述" }
        }
      },
      "analysis": [
        {
          "type": "trend_summary",
          "label": "趋势分析",
          "default_filters": ["equipment_id", "time_range"],
          "outputs": ["report", "recommendation"]
        },
        {
          "type": "risk_summary",
          "label": "风险分析",
          "default_filters": ["severity", "time_range"],
          "outputs": ["recommendation", "action_plan"]
        }
      ]
    }
  ]
}
```

业务包仍保留现有声明：

- `intents`
- `skills`
- `tools`
- `plugins`
- `prompts`
- `knowledge_bindings`

扩展后，业务包可以同时声明：

- 能调用哪些外部能力。
- 能接收哪些外部数据。
- 数据存到哪里。
- 支持哪些 AI 分析类型。
- 分析结果可以生成哪些业务成果。

---

## 6. 前端改造方案

### 6.1 数据接入页

新增页面：

```text
/(workspace)/data-ingest
```

功能：

- 查看 HTTP 接入地址。
- 查看 MQTT Topic 配置。
- 查看租户数据源状态。
- 查看最近入库量。
- 查看接收失败记录。
- 查看字段映射和标准化状态。

### 6.2 数据资产页

新增页面：

```text
/(workspace)/data-assets
```

功能：

- 选择业务包。
- 选择数据集。
- 按时间、设备、等级等字段筛选。
- 查看 ClickHouse 中已入库记录。
- 查看原始 payload。
- 查看标准化 payload。
- 查看数据量趋势。

### 6.3 AI 数据分析页

新增页面：

```text
/(workspace)/data-analysis
```

功能：

- 选择业务包。
- 选择数据集。
- 选择分析类型。
- 设置筛选条件。
- 预览参与分析的数据范围和统计概况。
- 点击生成 AI 分析。
- 展示报告、建议、行动计划。
- 关联 Trace。
- 保存到业务成果。

### 6.4 现有页面增强

对话页：

- 继续作为自然语言入口。
- 展示关联 AI Task。
- 展示生成的 BusinessOutput。
- 保留 Trace、路由解释、引用依据。

业务成果页：

- 展示 AI 数据分析生成的报告、建议、行动计划。
- 展示来源数据集、时间范围、筛选条件。
- 支持从成果反查 AI Task 和 Trace。

审计页：

- 支持按 AI Task、数据集、trace 查询。
- 区分 Chat 入口、工作台入口、数据资产入口。

业务包管理页：

- 展示 datasets。
- 展示 analysis 类型。
- 展示存储引擎、表名、时间字段、唯一键。
- 展示数据接入状态。
- 标注能力是真实 HTTP / MCP 接入，还是 stub。

---

## 7. 安全与治理要求

### 7.1 接入鉴权

- HTTP 数据接入必须鉴权，建议使用租户级 API Key 或请求签名。
- MQTT topic 必须绑定租户和数据源。
- 不能仅依赖请求体中的 `tenant_id` 判断租户。

### 7.2 数据边界

- 未在业务包声明的数据集默认拒绝，或进入隔离区等待管理员处理。
- payload 大小必须限制。
- 必须记录原始数据和标准化数据。
- external_id 需要做幂等处理。
- 原始数据、聚合事实、AI 推断结论必须分开存储和展示。

### 7.3 AI 分析边界

- AI 分析只读取当前租户数据。
- LLM 只接收聚合结果和少量关键样本。
- 输出进入现有 OutputGuard。
- 高风险动作继续走 Draft / Approval。
- 不允许模型输出直接改写原始数据。

### 7.4 SQL 安全

- 不允许前端传入原始 SQL。
- 不允许 LLM 生成 SQL 后直接执行。
- 所有查询必须走后端白名单模板。
- 时间范围、limit、样本数量必须有上限。

---

## 8. 实施阶段

### 第一阶段：ClickHouse 接入与 HTTP 入库

目标：外部数据可以进入平台存储，并能在前端查看。

后端：

- 增加 ClickHouse 配置和客户端。
- 新增 `raw_external_event` 表。
- 新增 `equipment_alarm` 宽表。
- 新增 HTTP ingest 接口。
- 新增数据资产查询接口。

前端：

- 新增数据接入页。
- 新增数据资产页。
- 支持查看入库记录和 payload。

### 第二阶段：基于存储数据的 AI 分析

目标：AI 从 ClickHouse 查询聚合结果，并生成分析成果。

后端：

- 新增 `DataAnalysisService`。
- 支持设备报警趋势分析。
- 从 ClickHouse 聚合趋势、TopN、严重等级、关键样本。
- LLM 基于聚合结果生成报告。
- 保存 BusinessOutput。
- 记录 Trace。

前端：

- 新增 AI 数据分析页。
- 支持选择数据集、分析类型、筛选条件。
- 展示分析结果和 Trace。

### 第三阶段：业务包数据集声明

目标：业务包声明自己支持哪些外部数据和分析能力。

后端：

- 扩展 manifest 解析。
- 校验 datasets。
- 后端根据 dataset 声明选择存储表和分析模板。

前端：

- 业务包详情展示 datasets 和 analysis。
- AI 数据分析页根据 manifest 动态渲染筛选项。

### 第四阶段：MQTT 接入

目标：MQTT 数据复用同一套入库链路。

后端：

- 新增 MQTT consumer。
- 支持 topic 到 tenant / package / dataset 的映射。
- 复用 IngestionService。
- 增加入库失败记录和监控。

前端：

- 数据接入页展示 MQTT 连接状态、topic、最近消息。

### 第五阶段：多入口融合

目标：Chat、AI 工作台、数据资产页统一进入 AI Task Runtime。

后端：

- ChatService 复用 AI Task Runtime 的公共执行逻辑。
- AI 工作台支持结构化任务。
- 数据分析任务统一进入 AI Task 表。

前端：

- Chat 展示关联 AI Task 和 Output。
- 数据资产页支持一键生成分析。
- Outputs 汇总所有报告、建议、行动计划。

---

## 9. 最小可落地版本

建议第一版只实现一个完整闭环，避免范围过大。

最小闭环：

1. 业务包声明 `equipment_alarm` 数据集。
2. HTTP 接口接收设备报警数据。
3. 数据写入 ClickHouse 的 `raw_external_event` 和 `equipment_alarm`。
4. 前端数据资产页能查看入库数据。
5. AI 数据分析页选择设备编号和时间范围。
6. 后端从 ClickHouse 聚合报警次数、故障码 TopN、严重等级分布、最近样本。
7. LLM 基于聚合结果生成分析报告。
8. 报告保存到 PostgreSQL 的 BusinessOutput。
9. Trace 记录完整分析过程。

该版本不需要先实现 MQTT，不需要覆盖所有数据集，也不需要做自由 SQL 分析。

---

## 10. 核心结论

本方案的关键不是“外部数据来了之后马上触发一次 AI”，而是：

> 外部数据通过 HTTP / MQTT 接入平台，先沉淀为平台可治理、可查询、可聚合的数据资产；AI 分析基于 ClickHouse 中已存储的数据进行统计、归因、解释和建议生成；分析过程、结果和审批仍由 PostgreSQL 中的平台治理体系承载。

最终平台形成三类 AI 入口：

```text
1. Chat 入口
用户自然语言触发业务包能力、RAG、工具调用。

2. 工作台入口
用户选择业务包、场景、参数，直接执行 AI 任务。

3. 数据资产入口
外部数据先入 ClickHouse，用户再基于已存储数据发起 AI 分析。
```

这会把平台从“对话演示 + 业务包调用”推进到“企业外部数据接入、存储、分析、治理、成果沉淀”的 AI 业务操作平台。

---

## 11. Claude 补充建议

> 本章节由 Claude 评审上述方案后补充，按"必须修正 / 强烈建议补充 / 锦上添花"三档列出潜在问题与改进点，建议在落地前纳入排期。

### 11.1 必须修正（不解决会踩生产坑）

#### 11.1.1 ClickHouse 写入模型不能直连 HTTP/MQTT

方案中 `HTTP / MQTT → IngestionService → ClickHouse` 是同步写入。ClickHouse 最忌讳高频小批量写入，会导致 Part 数量爆炸、Merge 压力剧增。

必须在中间加缓冲层：

- 推荐 Kafka / Redis Stream / 本地 buffer + 批量刷盘。
- 建议批量条件：≥1000 行 或 ≥1 秒触发一次 flush。
- 死信队列、重试、入库失败回放策略要在第一阶段就具备，不能等到 MQTT 阶段再补。

#### 11.1.2 ReplacingMergeTree 的"幂等"语义有歧义

`ReplacingMergeTree(ingested_at)` 的语义是"保留 ingested_at 最大的那条"，属于**后写覆盖**，而非**首次写入即保留**。这与方案中"external_id 用于幂等"的直觉不一致——同一 external_id 第二次推送会覆盖第一次的标准化结果。

需要明确：

- 是后写覆盖（当前模型），还是首写胜出（需要不更新 ingested_at 或使用业务版本号）。
- 查询是否需要 `FINAL` 或 `argMax`，否则在 merge 之前查询会看到重复行。
- 文档应显式说明该语义，避免业务侧误用。

#### 11.1.3 时区硬编码 `Asia/Shanghai`

多租户或跨地区场景一旦上线即出问题。建议：

- ClickHouse 内部统一存 UTC：`DateTime64(3, 'UTC')`。
- 展示层按租户或用户偏好转换。
- 接入层接收的时间字段必须显式带时区，禁止 naive datetime。

#### 11.1.4 排序键中包含高基数列 `external_id`

`ORDER BY (tenant_id, package_id, dataset, occurred_at, external_id)` 把 external_id 这种高基数列放在排序键末尾，会降低压缩率、增大 Part 体积。

建议：

- 排序键只保留低基数过滤字段和时间字段。
- external_id 走二级跳数索引：`INDEX idx_ext external_id TYPE bloom_filter GRANULARITY 4`。

#### 11.1.5 SQL 安全章节缺少强制租户隔离

"白名单模板 + 参数绑定"是对的，但没说**租户隔离怎么强制**。仅靠后端拼 WHERE，漏一个分支就是越权。

建议：

- 使用 ClickHouse Row Policy 做硬隔离：`CREATE ROW POLICY tenant_isolation ON equipment_alarm USING tenant_id = currentUser()`。
- 给业务用户独立的 CK 账号，账号绑定租户。
- 后端 WHERE 拼接 + Row Policy 双层防护。

### 11.2 强烈建议补充

#### 11.2.1 AI 数值幻觉防护

"LLM 基于聚合结果生成"是正确方向，但没说怎么防止 LLM 改数字。建议：

- 聚合结果以结构化 JSON 注入 prompt，报告中所有数字必须用模板/槽位渲染，不让 LLM 自由生成数字。
- 每个结论挂"数据来源 SQL hash + 查询参数 + 时间戳"，可反查复现。
- BusinessOutput 中保存原始聚合数据快照，便于审计。

#### 11.2.2 AI Task 状态机和生命周期

`status` 字段未枚举，建议明确为：

```text
pending | queued | running | streaming | success | failed | cancelled | timeout
```

并补充：

- 超时取消机制：长 LLM 调用必须有 deadline。
- 重试策略：区分确定性失败（参数错误，不重试）与临时失败（LLM 502，可重试）。
- 取消语义：前端关闭页面是否需要终止后端 LLM 调用与 CK 查询。

#### 11.2.3 AI Task Runtime 的接入次序

方案把"ChatService 复用 AI Task Runtime"放到第五阶段，但第一阶段已经新建 Runtime。这意味着前四阶段会出现 ChatService 一条链、AI Task 一条链，两套并行。

建议：

- 第一阶段就把 Runtime 抽成接口/编排层。
- Chat 改成 Runtime 的一种 source。
- 否则第五阶段会出现大规模重构。

#### 11.2.4 观测性完全缺失

方案中未提任何指标，至少应补：

- 入库侧：QPS、积压队列长度、CK 写入耗时、Part 数、入库失败率、字段校验失败率。
- AI 侧：LLM 调用时长、token 用量、单 task 成本、模板命中率。
- 链路侧：OpenTelemetry trace 串联，trace_id 从 HTTP/MQTT 入口贯穿到 LLM 调用。
- 数据接入页应展示这些指标并支持告警阈值配置。

#### 11.2.5 数据生命周期与合规

ClickHouse 未设计 TTL 和冷热分层。建议：

- 表加 TTL 策略：`TTL alarm_time + INTERVAL 90 DAY TO VOLUME 'cold'`。
- GDPR / 等保的"被遗忘权"在 CK 上 mutation 成本高，应使用软删除 + TTL，而非 `ALTER TABLE DELETE`。
- 跨租户聚合（平台运维）的边界要在 RBAC 中显式声明。

#### 11.2.6 业务包 manifest 仍缺关键字段

datasets 声明建议补充：

- `schema_version`：外部系统升级字段后的兼容策略。
- `field_mapping`：外部 payload 字段 → 宽表字段的映射规则归属。`schema_registry.py` 提了模块名但未明确职责，建议明确它负责字段映射、版本兼容、JSON Schema 校验。
- 数据集间的关联关系：例如 alarm + workorder 联合分析需要 join key 声明。

#### 11.2.7 MQTT 阶段排序过晚

工业制造场景 80% 数据走 MQTT。第四阶段才上 MQTT，意味着前三阶段闭环都跑在"假装 HTTP 推过来"上，与实际客户场景脱节。

建议：

- 第一阶段最小闭环至少包含一个 MQTT 验证 demo（哪怕只支持单 topic），确保链路真能跑工业数据。
- 否则容易出现"客户对接时才发现 MQTT 链路有缺陷"的返工。

### 11.3 锦上添花

#### 11.3.1 聚合结果缓存层

同一 `(dataset, filters, analysis_type)` 短时间内重复触发，应缓存聚合结果，甚至缓存 LLM 报告，避免重复烧 token。

#### 11.3.2 关键样本采样策略

"最近关键样本"未限定上限。当严重报警上万条时如何选取？建议：

- 分层采样：按严重度 / 时间分桶，每桶 TopK。
- 总样本上限（如 50 条），避免 prompt 过长。

#### 11.3.3 前端数据资产页性能

ClickHouse 不擅长 OLTP 风格的 offset 翻页。建议：

- 使用 keyset pagination：`WHERE occurred_at < :cursor ORDER BY occurred_at DESC LIMIT 50`。
- 大表查询走预计算物化视图。

#### 11.3.4 降级路径

- ClickHouse 故障：ingestion 应落本地 buffer 或 Kafka，恢复后回放，而非直接 5xx。
- LLM 故障：分析任务应保留聚合结果展示给用户，标注"AI 解读暂不可用"，而非整个任务失败。

#### 11.3.5 测试与回归

- Ingestion 层压测：高并发、大 payload、断线重连场景。
- CK 查询模板覆盖测试：每个 analysis_type 至少一条样例数据 + 期望聚合结果。
- 分析模板回归测试：相同输入数据应得到稳定的聚合数字（LLM 文本不强一致，但数字必须一致）。

### 11.4 优先级建议

如果资源有限只能挑三件最重要的事先做：

1. **11.1.1 写入缓冲**：不做就直接卡在生产环境上线时。
2. **11.1.5 Row Policy 强隔离**：不做就是越权风险。
3. **11.2.3 Runtime 接口前置**：不做第五阶段就要重写。

这三项不前置，后期返工成本最大。
