# LLM-Wiki 文件分布状态可视化方案

**版本**: v1.0  
**日期**: 2026-04-24  
**状态**: 方案草案  
**适用范围**: `llm-wiki` 治理后台中的“文件分布状态”可视化能力  
**关联文档**:

- `docs/LLM-Wiki独立模块化改造技术方案.md`
- `docs/知识库治理前端交互逻辑方案.md`
- Karpathy: [The ideal LLM knowledge source](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

---

## 1. 背景

当前项目已经具备 `LLM-Wiki` 的基础能力：

- 后端已有 `wiki_page / page_revision / citation / link / compile_run` 等结构。
- 前端已有 `Wiki 管理面板`、`Wiki 页面列表`、`Wiki 检索与问答入口`。
- 页面可以看到“编译过多少页、有哪些页、最近有哪些编译任务”。

但还缺少一个关键治理视角：

- **无法在界面上看到“所有文件当前如何分布、是否被编译、落到了哪些 Wiki 页面、覆盖是否均衡、哪些文件孤立或过热”。**

这会导致几个问题：

- 用户只能看“结果页”，不能看“原始文件 -> Wiki 沉淀”的全貌。
- 无法快速发现哪些文件还没有进入 Wiki。
- 无法判断某些页面是否过度依赖少量文件，或某些文件完全没有被消费。
- 当知识源规模上来后，编译质量和治理覆盖度难以做可视化巡检。

Karpathy 文档的核心启发并不是“再做一个搜索框”，而是要把知识源做成：

- 可持久化沉淀的知识对象。
- 可追踪来源和演化关系的知识网络。
- 可被人类直观浏览和审查的知识空间。

因此，这里的“文件分布状态”不应只做成一个普通列表，而应做成 **Wiki 治理视角下的分布地图**。

---

## 2. 目标

本方案目标是让用户在 `Wiki 治理中心` 中直接看到：

- 所有知识文件的总体分布。
- 文件按目录 / 类型 / 负责人 / 状态的分布。
- 每个文件是否已进入 Wiki 编译。
- 每个文件影响了哪些 Wiki 页面。
- 每个 Wiki 页面依赖了哪些文件。
- 哪些文件未覆盖、低覆盖、过度集中、重复集中。

最终界面要回答 4 个问题：

1. 现在系统里一共有多少文件，它们分布在哪里。
2. 哪些文件已经被 Wiki 消费，哪些还没进入治理视图。
3. 哪些 Wiki 页面覆盖面健康，哪些页面依赖过于集中。
4. 本次编译后，文件分布状态相比上一次发生了什么变化。

---

## 3. 非目标

本期不建议直接做以下内容：

- 不做完整自由拖拽图谱画布。
- 不做多用户在线协同编辑器。
- 不做复杂三维拓扑或大规模前端实时渲染引擎。
- 不把现有 RAG 页面和 Wiki 页面完全合并。
- 不直接改动现有 `knowledge_document / knowledge_chunk` 的语义。

---

## 4. 对当前仓库的判断

结合现有代码，当前系统适合采用“增量扩展”方案，而不是重做：

- 前端入口已存在：`apps/web/src/components/knowledge/knowledge-console.tsx`
- Wiki 管理面板已存在：`apps/web/src/components/knowledge/wiki-management-panel.tsx`
- Wiki 查询接口已存在：`apps/api/src/agent_platform/api/routes/admin.py`
- Wiki 持久化模型已存在：`apps/api/src/agent_platform/wiki/models.py`
- Wiki 表结构已存在：`migrations/versions/20260423_0003_add_knowledge_wiki_tables.py`

当前缺口也很明确：

- 现有 `AdminKnowledgeResponse` 只有源级别信息，没有文件层级结构信息。
- 现有 Wiki API 只有页面、编译记录、搜索接口，没有“文件分布”接口。
- 现有前端没有目录树、聚合分布图、覆盖矩阵、影响关系视图。
- 现有 Wiki 编译结果虽然保存了 `citation.source_id / chunk_id`，但没有形成适合前端直接消费的“分布快照”。

所以最佳路径不是推翻现有 Wiki，而是新增一层：

```text
knowledge source / chunk / wiki citation
    -> 文件分布聚合
    -> 分布快照
    -> 前端分布视图
```

---

## 5. 总体方案

建议在 `Wiki 治理中心` 中新增一个独立子视图：

```text
知识库治理
  └─ Wiki 治理
      ├─ 概览
      ├─ 页面列表
      ├─ 编译记录
      ├─ 检索验证
      └─ 文件分布
```

其中“文件分布”页由 4 个区域组成。

### 5.1 顶部概览卡

展示全局统计：

- 文件总数
- 已进入 Wiki 文件数
- 未覆盖文件数
- 平均每个文件影响页面数
- 平均每个页面依赖文件数
- 最近一次编译后变化量

### 5.2 左侧文件树 / 分组分布

支持按以下维度切换：

- 目录
- 文件类型
- 负责人
- 状态

表现形式建议：

- 默认用树状列表展示层级分布。
- 同时配合“占比条”显示该节点文件数和引用数。
- 节点旁显示覆盖状态颜色。

状态建议：

- `未入库`
- `已入库未编译`
- `已编译未命中页面`
- `已进入页面`
- `高影响`

### 5.3 中央分布主视图

这里不要直接上复杂图谱，首期推荐两种可切换视图。

第一种是“Treemap 文件分布图”：

- 每个矩形代表一个文件。
- 面积表示 chunk 数或字节规模。
- 颜色表示覆盖状态或最近编译状态。
- 点击矩形后，右侧详情联动。

第二种是“目录热力矩阵”：

- 行表示目录 / 分组。
- 列表示状态维度。
- 单元格表示文件数、命中页面数或 citation 数。
- 适合管理者快速巡检。

### 5.4 右侧详情抽屉

点击文件后展示：

- 基础信息：名称、类型、负责人、状态、更新时间。
- 编译信息：最近编译时间、最近 compile_run、chunk 数。
- Wiki 影响：命中了哪些页面、贡献了多少 citation。
- 覆盖诊断：是否孤立、是否过热、是否重复集中。
- 追踪入口：跳转到相关页面详情 / 编译记录 / 检索验证。

---

## 6. 核心交互设计

### 6.1 用户进入 Wiki 页签后的默认路径

建议默认停留在“概览”而不是“文件分布”，避免首次进入信息过载。

在 `Wiki 管理面板` 顶部增加一个操作入口：

- `查看文件分布`

点击后进入文件分布视图。

### 6.2 文件分布页推荐交互

页面结构建议：

```text
顶部筛选栏
  -> 空间 space_code
  -> 编译批次 compile_run
  -> 文件类型
  -> 覆盖状态
  -> 负责人

概览卡片

左：文件树 / 分组
中：Treemap 或 热力矩阵
右：文件详情

底部：异常文件列表
  -> 未覆盖
  -> 零命中
  -> 单页过热
  -> 近期变化大
```

### 6.3 关键筛选能力

必须支持：

- 仅看最近一次编译。
- 仅看未覆盖文件。
- 仅看某一类文件，例如 `Markdown / PDF / API / Excel`。
- 仅看某个负责人或业务域。
- 仅看影响超过阈值的高影响文件。

### 6.4 关键诊断标签

建议给文件打出机器可判定标签：

- `uncompiled`：已入库但未进入当前 Wiki 编译。
- `orphan`：已编译但没有沉淀到任何页面。
- `healthy`：覆盖正常，分布均衡。
- `hotspot`：对多个页面贡献很高。
- `over_concentrated`：页面过度依赖少数文件。
- `stale`：文件已更新但 Wiki 未重新编译。

---

## 7. 数据模型设计

本方案不建议改已有 Wiki 主表语义，建议通过**新增表**实现。

### 7.1 新增表 1：文件分布快照表

建议新增：

```text
knowledge_wiki_file_distribution_snapshot
```

用途：

- 保存某次编译后每个文件的聚合状态。
- 用于前端快速展示，不必每次实时 join 全量 citation。
- 支持按编译批次回看历史分布。

建议字段：

- `snapshot_id`
- `tenant_id`
- `compile_run_id`
- `space_code`
- `source_id`
- `source_name`
- `source_type`
- `owner`
- `group_path`
- `chunk_count`
- `page_count`
- `citation_count`
- `coverage_status`
- `distribution_score`
- `hotspot_score`
- `stale_flag`
- `metadata_json`
- `created_at`

说明：

- `group_path` 用于承接目录树或逻辑分组路径。
- `distribution_score` 表示覆盖均衡程度。
- `hotspot_score` 表示该文件对页面网络的集中影响程度。

### 7.2 新增表 2：文件到页面映射表

建议新增：

```text
knowledge_wiki_file_page_map
```

用途：

- 保存文件与 Wiki 页面的聚合映射关系。
- 右侧详情抽屉和页面跳转可直接读取。

建议字段：

- `map_id`
- `tenant_id`
- `compile_run_id`
- `source_id`
- `page_id`
- `citation_count`
- `support_sections`
- `contribution_score`
- `created_at`

### 7.3 为什么不直接实时查 citation

因为如果完全依赖：

- `knowledge_wiki_citation`
- `knowledge_wiki_page`
- `knowledge_document`

去实时聚合前端视图，会带来几个问题：

- 前端查询复杂，响应会越来越慢。
- 历史编译批次难以回放。
- 难以提供“变化量”和“诊断标签”。

因此更适合在编译完成时同步产出一份分布快照。

---

## 8. 后端接口方案

建议新增 3 组接口，仍挂在现有 `/admin/wiki/*` 下。

### 8.1 文件分布概览接口

```text
GET /admin/wiki/file-distribution/overview
```

返回：

- 文件总数
- 已编译文件数
- 未覆盖文件数
- 热点文件数
- 平均页面覆盖数
- 最近一次编译时间

### 8.2 文件分布列表接口

```text
GET /admin/wiki/file-distribution
```

查询参数建议：

- `space_code`
- `compile_run_id`
- `group_by=directory|type|owner|status`
- `coverage_status`
- `source_type`
- `owner`
- `keyword`
- `sort_by`

返回结构建议：

- 聚合分组数据
- 文件节点数据
- 总体统计

### 8.3 文件详情接口

```text
GET /admin/wiki/file-distribution/{source_id}
```

返回：

- 文件基础信息
- 最近快照信息
- 关联页面列表
- 关联 compile_run
- 覆盖诊断标签

---

## 9. 编译链路改造建议

当前已有 `compile_sources()`，建议在**编译成功后**追加一个分布聚合步骤，而不是在前端实时拼装。

推荐链路：

```text
source / chunk
 -> Wiki page compile
 -> citation write
 -> file-page aggregation
 -> distribution snapshot write
 -> compile run complete
```

### 9.1 聚合来源

聚合逻辑主要基于：

- `knowledge_document`
- `knowledge_chunk`
- `knowledge_wiki_citation`
- `knowledge_wiki_page`
- `knowledge_wiki_compile_run`

### 9.2 聚合输出

输出两类结果：

- 文件级快照
- 文件到页面的映射

### 9.3 分布状态判定规则

建议先用规则法，不依赖模型：

- `已入库未编译`: 文件存在，但不在 `input_source_ids`
- `已编译未命中页面`: 在编译范围内，但 `page_count = 0`
- `已进入页面`: `page_count > 0`
- `高影响`: `page_count` 或 `citation_count` 高于分位阈值
- `过度集中`: 单一页面引用占比超过阈值，例如 70%
- `过期`: 文件更新时间晚于最近成功编译时间

---

## 10. 前端实现建议

### 10.1 推荐组件拆分

建议新增以下组件：

```text
apps/web/src/components/knowledge/
  wiki-file-distribution-panel.tsx
  wiki-file-distribution-treemap.tsx
  wiki-file-distribution-matrix.tsx
  wiki-file-distribution-tree.tsx
  wiki-file-distribution-detail.tsx
```

### 10.2 与现有页面的集成方式

不建议新开一级导航，直接集成到现有 `Wiki 治理` 区域。

推荐两种落法：

方案 A：

- 在 `WikiManagementPanel` 下方新增一个新板块“文件分布状态”。

方案 B：

- 在 `Wiki 治理中心` 内再做二级 tabs：
  - `概览`
  - `文件分布`
  - `检索验证`

本项目更建议 **方案 B**，原因是：

- 现有 `WikiManagementPanel` 已经比较长。
- 文件分布会是一个信息密度很高的独立视图。
- 后续如果再加“页面依赖网络”，二级 tabs 更容易扩展。

### 10.3 首期视觉形态建议

首期优先级建议如下：

1. 概览卡片
2. 左侧文件树
3. 中间 Treemap
4. 右侧详情抽屉
5. 底部异常列表

先不要在首期直接做复杂力导向图，原因是：

- 当前数据规模和交互需求还不足以证明图谱优于 Treemap。
- 力导向图首期易出现“炫但不好用”的问题。
- 管理后台更需要稳定巡检，而不是探索式可视化优先。

---

## 11. 指标设计

为了让“分布状态”不是纯展示，建议定义以下指标。

### 11.1 文件覆盖率

```text
进入至少一个 Wiki 页面的文件数 / 已编译文件数
```

### 11.2 页面依赖分散度

```text
某页面引用的不同 source_id 数量
```

### 11.3 文件热点度

```text
某文件关联的页面数 * 权重 + citation 数 * 权重
```

### 11.4 分布均衡度

可以先用简化版：

- 页面覆盖过于集中时给低分。
- 文件只命中一个页面且占比极高时给低分。
- 文件命中多个页面且引用分布较均匀时给高分。

### 11.5 孤立文件率

```text
已编译但未命中页面的文件数 / 已编译文件数
```

---

## 12. 分阶段落地建议

### 阶段 1：最小可用版本

目标：

- 让页面先能看到“所有文件的分布状态”。

范围：

- 新增文件分布概览接口。
- 新增文件分布列表接口。
- 新增前端二级 tab“文件分布”。
- 实现文件树 + 概览卡 + 异常文件列表。

这一阶段不做：

- Treemap
- 历史回放
- 复杂评分

### 阶段 2：可视化增强

范围：

- Treemap 分布图
- 文件详情抽屉
- 文件到页面关系面板
- compile_run 维度切换

### 阶段 3：治理闭环

范围：

- 分布变化趋势
- 过期文件提醒
- 热点 / 孤立自动诊断
- 从异常文件一键发起重编译或进入检索验证

---

## 13. 推荐实施顺序

建议按下面顺序推进：

1. 先补后端聚合结构和接口。
2. 再补前端二级 tabs 和基础列表视图。
3. 验证现有数据是否足够支撑“文件分布”语义。
4. 再决定是否引入 Treemap。

原因：

- 如果文件分组路径、文件类型、更新时间这些源信息不完整，前端做再漂亮也会失真。
- “所有文件分布状态”首先是数据建模问题，其次才是图形问题。

---

## 14. 风险与取舍

### 14.1 当前数据源未必真有“目录路径”

这是本方案最大的现实风险。

当前 `AdminKnowledgeResponse` 中能看到的是：

- `source_id`
- `name`
- `source_type`
- `owner`
- `chunk_count`
- `status`

如果源数据目前没有真实文件路径，那么“目录分布”只能先用**逻辑分组**代替，例如：

- `space_code/source_type/owner`
- 或在 `metadata_json` 中补 `group_path`

所以本方案默认假设：

- **首期的“文件分布”允许先采用逻辑分组路径，不强依赖操作系统文件目录。**

### 14.2 不建议首期直接做实时图谱

原因：

- 交互成本高。
- 数据噪声大。
- 难以解释。

### 14.3 不建议把该能力塞进现有 RAG 页签

因为这个视图本质上是 Wiki 治理视角，不是原始 RAG 入库视角。

---

## 15. 最终建议

结合当前项目现状，建议采用以下最终方案：

- 保持 `LLM-Wiki` 现有架构不变。
- 在 `Wiki 治理中心` 内新增二级视图 `文件分布`。
- 后端新增“文件分布快照 + 文件到页面映射”两类聚合结构。
- 编译完成后同步生成分布快照，而不是前端实时拼数据。
- 前端首期先落“概览卡 + 文件树 + 异常文件列表”，第二期再上 Treemap。

如果用一句话总结：

**不是简单把所有文件列出来，而是把“文件如何进入 Wiki、如何分布到页面、哪里覆盖不足、哪里依赖过热”做成一个可治理的可视化视图。**

---

## 16. 对当前仓库的直接改造点

如果后续进入实现，建议优先改这些位置：

- `apps/api/src/agent_platform/api/routes/admin.py`
  - 新增文件分布相关接口。
- `apps/api/src/agent_platform/wiki/`
  - 新增分布聚合与查询逻辑。
- `migrations/versions/`
  - 通过新增迁移补充分布快照与映射表。
- `apps/web/src/lib/api-client/types.ts`
  - 增加文件分布响应类型。
- `apps/web/src/lib/api-client/index.ts`
  - 增加文件分布接口调用。
- `apps/web/src/components/knowledge/knowledge-console.tsx`
  - 为 Wiki 页签增加二级视图。
- `apps/web/src/components/knowledge/`
  - 增加文件分布面板与可视化组件。

---

## 17. 结论

这件事值得做，而且适合放在当前 `llm-wiki` 的下一步里做。

因为它补的不是“又一个页面”，而是 `LLM-Wiki` 从“能编译、能搜索”走向“可治理、可巡检、可解释”的关键一层。

从当前仓库现状看，最稳的做法是：

- 不改老的 RAG 逻辑。
- 不硬塞进现有搜索接口。
- 通过新增聚合结构和新视图完成能力闭环。

这条路线和现有项目结构是一致的，风险也最小。
