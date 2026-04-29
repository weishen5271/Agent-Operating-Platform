# 多入口 AI 业务操作平台实施计划

> 本计划基于 [多入口AI业务操作平台与外部数据分析方案.md](../01-architecture/多入口AI业务操作平台与外部数据分析方案.md) 制定，结合 Claude 补充建议，落地为可执行的分阶段排期。
>
> 计划口径：1 人天 = 1 名后端或前端工程师 1 个工作日。所有时长为预估，实际以站会调整为准。

---

## 0. 计划总览

### 0.1 阶段划分

| 阶段 | 目标 | 预估工期 | 关键产出 |
|------|------|----------|----------|
| Sprint 0 | 基础设施与抽象前置 | 5 个工作日 | CK 部署、Runtime 接口、缓冲层、观测埋点骨架 |
| Sprint 1 | HTTP + MQTT 最小闭环入库 | 8 个工作日 | 设备报警从 HTTP / MQTT 入 CK，前端可查 |
| Sprint 2 | 基于存储数据的 AI 分析 | 8 个工作日 | 趋势分析报告完整闭环 |
| Sprint 3 | 业务包 datasets 声明 | 5 个工作日 | manifest 扩展 + 动态渲染 |
| Sprint 4 | 多入口融合与治理 | 6 个工作日 | Chat / 工作台 / 数据资产 统一进 Runtime |
| Sprint 5 | 生产化与合规 | 5 个工作日 | TTL、Row Policy、降级、压测、回归 |

合计约 **37 个工作日**（不含联调与 Bug 修复缓冲）。建议预留 **20% Buffer** 共 ≈ 45 工作日，按 2 后端 + 1 前端的小组配置约需 **3 ~ 3.5 周**全力投入。

### 0.2 角色分工

- **后端 A（资深）**：Runtime / Ingestion / ClickHouse / 安全。
- **后端 B**：Analysis Service / Manifest / AI Task / 观测。
- **前端**：数据接入页、数据资产页、AI 数据分析页、业务包管理页扩展。
- **DevOps（兼任）**：ClickHouse / Kafka 部署、监控接入。

### 0.3 关键依赖

- ClickHouse 24.x 集群（至少 1 主 1 副本，生产前升级到 ReplicatedMergeTree）。
- Kafka 或 Redis Stream（Sprint 0 需就绪）。
- MQTT Broker（建议 EMQX 或现有方案）。
- LLM 网关已就绪（沿用现有 ChatService 通道）。

---

## 1. Sprint 0：基础设施与抽象前置（5 工作日）

> 目的：把后续阶段返工成本最高的几件事先做掉，对应 Claude 建议优先级 11.1.1 / 11.1.5 / 11.2.3。

### 1.1 任务清单

| # | 任务 | 负责人 | 工期 | 产出 |
|---|------|--------|------|------|
| 0-1 | ClickHouse 部署（单实例 + 副本预留） | DevOps | 1 天 | 集群可用、用户分级、Row Policy 启用 |
| 0-2 | Kafka / Redis Stream 部署 + topic 规划 | DevOps | 0.5 天 | `ingest.raw.events` topic |
| 0-3 | AI Task Runtime 接口抽象 | 后端 A | 1.5 天 | `ai_task_runtime` 接口 + `TaskContext` |
| 0-4 | ChatService 接入 Runtime（保持行为不变） | 后端 A | 1 天 | Chat 改造为 Runtime 的 `source=chat` 调用 |
| 0-5 | 观测埋点骨架（OTel + metrics） | 后端 B | 1 天 | trace_id 贯穿、Prometheus 指标暴露 |
| 0-6 | `ai_task` 表 DDL + 状态机枚举 | 后端 B | 0.5 天 | PG 迁移脚本 |

### 1.2 验收标准

- ChatService 走新 Runtime 后，所有现有对话用例回归通过。
- `ai_task` 表落库，状态枚举为 `pending | queued | running | streaming | success | failed | cancelled | timeout`。
- 所有后续接口默认带 `trace_id`。
- ClickHouse 用普通业务账号登录时，未配 Row Policy 的表无访问权限。

### 1.3 风险

- **Runtime 抽象走偏**：建议先写 1~2 个调用方再固化接口；不要一次性设计完美抽象。
- **ChatService 回归覆盖不足**：先补现有对话的 E2E 测试，再做改造。

---

## 2. Sprint 1：HTTP + MQTT 最小闭环入库（8 工作日）

> 目的：完成方案第一阶段 + 第四阶段的 PoC 合并落地，对应 Claude 建议 11.1.1 / 11.1.2 / 11.1.3 / 11.1.4 / 11.2.7。

### 2.1 任务清单

| # | 任务 | 负责人 | 工期 |
|---|------|--------|------|
| 1-1 | `raw_external_event` 表 DDL（UTC 时间 + bloom filter） | 后端 A | 0.5 天 |
| 1-2 | `equipment_alarm` 宽表 DDL + TTL 占位 | 后端 A | 0.5 天 |
| 1-3 | IngestionService（含 schema 校验、tenant 鉴权、幂等语义） | 后端 A | 2 天 |
| 1-4 | Kafka producer + 批量 flush（≥1000 行 或 ≥1 秒） | 后端 A | 1 天 |
| 1-5 | Kafka consumer → ClickHouse 批量写入 | 后端 A | 1 天 |
| 1-6 | HTTP `/api/v1/data-ingest/events` + `/batch` | 后端 B | 1 天 |
| 1-7 | MQTT consumer（PoC，单 topic，QoS 1） | 后端 B | 1 天 |
| 1-8 | 数据资产查询接口（keyset pagination） | 后端 B | 0.5 天 |
| 1-9 | 前端：数据接入页（HTTP 地址、MQTT topic、入库量） | 前端 | 1.5 天 |
| 1-10 | 前端：数据资产页（筛选、明细、原始/标准化 payload 切换） | 前端 | 2 天 |
| 1-11 | 死信队列 + 入库失败回放接口 | 后端 A | 1 天 |

### 2.2 接口契约

```
POST /api/v1/data-ingest/events         # 单条
POST /api/v1/data-ingest/events/batch   # 批量，最多 500 条
GET  /api/v1/data-assets/datasets        # 列出当前租户可见数据集
GET  /api/v1/data-assets/records         # keyset 分页查询明细
```

鉴权：HTTP 走租户级 API Key（Header `X-Tenant-Key`），MQTT 走 username/password + topic ACL。

### 2.3 验收标准

- 1000 QPS 持续 5 分钟入库，CK Part 数稳定在合理区间（< 300 / 表）。
- 重复推送同一 `external_id` 行为符合既定语义（默认：后写覆盖，文档显式声明）。
- CK 服务下线 30 秒，恢复后数据无丢失（Kafka 缓冲 + consumer 重连）。
- 前端数据资产页翻页无超时，明细查询 P95 < 1s。

### 2.4 风险

- **MQTT broker 与现有运维边界**：先用项目内嵌 broker 跑通 PoC，避免阻塞。
- **Kafka 部署延迟**：可临时用 Redis Stream 顶替，接口保持一致。

---

## 3. Sprint 2：基于存储数据的 AI 分析（8 工作日）

> 目的：完成趋势分析端到端，对应方案第二阶段 + Claude 建议 11.2.1 / 11.2.2 / 11.3.1 / 11.3.2。

### 3.1 任务清单

| # | 任务 | 负责人 | 工期 |
|---|------|--------|------|
| 2-1 | DataAnalysisService 框架 + 白名单模板注册 | 后端 A | 1 天 |
| 2-2 | `trend_summary` SQL 模板（趋势、TopN、严重度、关键样本） | 后端 A | 1.5 天 |
| 2-3 | 聚合结果缓存层（Redis，key=hash(dataset+filters+type)） | 后端 A | 0.5 天 |
| 2-4 | 关键样本分层采样（按严重度 + 时间分桶 TopK，总量 ≤ 50） | 后端 B | 0.5 天 |
| 2-5 | LLM Prompt 模板 + 槽位渲染（数字不由 LLM 生成） | 后端 B | 1.5 天 |
| 2-6 | BusinessOutput 扩展字段：`dataset_ref`、`filter_snapshot`、`sql_hash` | 后端 B | 0.5 天 |
| 2-7 | `POST /api/v1/ai/data-analysis` + Trace 串联 | 后端 B | 1 天 |
| 2-8 | AI Task 超时 / 取消机制 | 后端 A | 0.5 天 |
| 2-9 | 前端：AI 数据分析页 | 前端 | 2.5 天 |
| 2-10 | 前端：业务成果页展示 dataset 来源、时间范围、反查 Trace | 前端 | 1 天 |

### 3.2 LLM 输入约束

- 聚合结果作为 JSON 注入。
- 关键样本 ≤ 50 条 + 字段裁剪。
- 报告中所有数字走槽位填充，禁止 LLM 自由生成数字。
- prompt 中明确"若需要数字，必须引用提供的字段名"。

### 3.3 验收标准

- 同一 `(dataset, filters, analysis_type)` 5 分钟内重复请求命中缓存，不重复调用 LLM。
- 报告中数字与 SQL 聚合结果一一对应（人工抽查 10 份）。
- 任务超时（默认 60s）能正确切到 `timeout` 状态并释放资源。
- BusinessOutput 可反查到原始 SQL hash 与查询参数。

### 3.4 风险

- **LLM 改数字**：必须在评审环节人工抽查；如有偏差立即收紧槽位约束。
- **聚合 SQL 慢**：上线前对每个模板做 EXPLAIN，必要时预建物化视图。

---

## 4. Sprint 3：业务包 datasets 声明（5 工作日）

> 目的：完成方案第三阶段 + Claude 建议 11.2.6。

### 4.1 任务清单

| # | 任务 | 负责人 | 工期 |
|---|------|--------|------|
| 3-1 | manifest schema 扩展：`datasets` / `schema_version` / `field_mapping` | 后端 B | 1 天 |
| 3-2 | `schema_registry` 实现：字段映射、版本兼容、JSON Schema 校验 | 后端 A | 1.5 天 |
| 3-3 | manifest 加载校验：dataset 必须有对应 CK 表 | 后端 A | 0.5 天 |
| 3-4 | IngestionService 接入 schema_registry | 后端 A | 0.5 天 |
| 3-5 | 前端：业务包详情展示 datasets / analysis / 接入状态 | 前端 | 1 天 |
| 3-6 | 前端：AI 数据分析页根据 manifest 动态渲染筛选项 | 前端 | 0.5 天 |

### 4.2 验收标准

- 业务包未声明的 dataset 推送数据时，进入隔离区并产生告警。
- `equipment_alarm` 数据集在 manifest 升级 schema_version 后，旧数据仍可查询。
- AI 数据分析页筛选项完全由 manifest 驱动，无硬编码。

---

## 5. Sprint 4：多入口融合与治理（6 工作日）

> 目的：完成方案第五阶段 + Claude 建议 11.2.4 / 11.2.2。

### 5.1 任务清单

| # | 任务 | 负责人 | 工期 |
|---|------|--------|------|
| 4-1 | AI 工作台入口接入 Runtime（`source=workspace`） | 后端 A | 1 天 |
| 4-2 | 数据资产页"一键生成分析"接入 Runtime（`source=data_analysis`） | 后端 B | 0.5 天 |
| 4-3 | AI Task 列表 + 详情接口 | 后端 B | 1 天 |
| 4-4 | 审计页扩展：按 source / dataset / trace 筛选 | 后端 B | 1 天 |
| 4-5 | 观测指标完善：LLM token 用量、单 task 成本、模板命中率 | 后端 A | 1 天 |
| 4-6 | 前端：Chat 关联 AI Task 与 Output 展示 | 前端 | 1 天 |
| 4-7 | 前端：Outputs 汇总页 | 前端 | 0.5 天 |

### 5.2 验收标准

- 三类入口产生的 AI Task 在同一张表中，可统一审计。
- 单租户 24 小时 token 用量、成本可在监控面板查看。
- Chat 中触发的分析与数据资产页触发的分析，BusinessOutput 结构一致。

---

## 6. Sprint 5：生产化与合规（5 工作日）

> 目的：上线前必做项，对应 Claude 建议 11.2.5 / 11.3.4 / 11.3.5。

### 6.1 任务清单

| # | 任务 | 负责人 | 工期 |
|---|------|--------|------|
| 5-1 | ClickHouse 切换 ReplicatedMergeTree + 副本验证 | DevOps + 后端 A | 1 天 |
| 5-2 | TTL 策略落地（90 天热 / 360 天冷 / 软删除） | 后端 A | 0.5 天 |
| 5-3 | Row Policy 全表覆盖 + 越权用例测试 | 后端 A | 0.5 天 |
| 5-4 | 降级路径：CK 故障落本地 buffer，LLM 故障保留聚合结果 | 后端 A | 1 天 |
| 5-5 | Ingestion 压测（峰值 5000 QPS，持续 30 分钟） | 后端 B | 0.5 天 |
| 5-6 | 分析模板回归测试集（每个 analysis_type 至少 3 套样例） | 后端 B | 1 天 |
| 5-7 | 告警阈值配置：入库失败率 / 积压 / LLM 超时率 | DevOps | 0.5 天 |
| 5-8 | 文档：运维手册、故障处置手册、API 文档 | 全员 | 0.5 天 |

### 6.2 验收标准

- 越权测试：A 租户 token 访问 B 租户 dataset 必须 403。
- 压测期间无数据丢失，CK Part 数稳定。
- 分析模板回归用例 100% 通过（数字必须稳定，文本可漂移）。
- 故障演练：手动 kill CK / LLM，业务可降级，告警 1 分钟内触发。

---

## 7. 关键里程碑

| 时间点 | 里程碑 | 演示场景 |
|--------|--------|----------|
| Sprint 0 末 | 基础设施就绪 | Chat 走新 Runtime 无回归 |
| Sprint 1 末 | 数据可入可查 | HTTP / MQTT 推送报警，前端能看到 |
| Sprint 2 末 | AI 分析闭环 | 选 CNC-01 + 本月，生成趋势报告 |
| Sprint 3 末 | manifest 驱动 | 新业务包通过声明即可接入 |
| Sprint 4 末 | 三入口统一 | Chat / 工作台 / 数据资产 同一审计视图 |
| Sprint 5 末 | 可上线 | 压测 + 越权 + 降级演练通过 |

---

## 8. 跨阶段事项

### 8.1 持续进行

- 每个 PR 强制 code-review + 单元测试。
- 每个 Sprint 末跑一次完整 E2E。
- 观测指标随功能同步落地，不延后。

### 8.2 需提前对齐

- ClickHouse 容量规划（按预估每日入库量 × 365 × 压缩比估算）。
- LLM 成本预算（按单 task token 用量 × 日活估算）。
- 数据保留期与合规要求（与法务对齐 90 / 360 天是否合适）。

### 8.3 暂不纳入本计划

- 自由 SQL 分析（风险高，二期评估）。
- 跨租户聚合（运维场景，权限模型需单独设计）。
- 实时数据流到前端（WebSocket / SSE，二期）。
- 数据集间联合分析（需要先沉淀 join key 规范）。

---

## 9. 优先级与裁剪

如果总工期需要压缩到 **2 周**内出 Demo，建议保留：

- Sprint 0 全部（不可裁）。
- Sprint 1 中的 HTTP 入库 + 数据资产页（去掉 MQTT、去掉死信回放）。
- Sprint 2 中的 trend_summary 单一模板 + AI 数据分析页（去掉缓存、去掉超时机制）。

裁剪后需明确告知客户：**MQTT、生产化、合规、降级在 Demo 阶段未做**，避免误期望。

---

## 10. 计划修订记录

| 日期 | 版本 | 修订人 | 说明 |
|------|------|--------|------|
| 2026-04-29 | v0.1 | Claude | 初版，基于方案文档 v1 + 补充建议生成 |
