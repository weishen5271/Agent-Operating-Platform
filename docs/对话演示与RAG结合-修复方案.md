# 对话演示与 RAG 结合 - 修复方案

**版本**: v1.0
**日期**: 2026-04-25
**状态**: 草案
**关联代码**: `apps/api/src/agent_platform/runtime/chat_service.py`、`apps/api/src/agent_platform/retrieval/text.py`

---

## 一、背景与现象

在对话演示中输入诸如「帮我查询一下"可扩展Agent架构-技术开发文档"的内容，分析一下该如何设计」时，返回结果形如：

```
已从平台文档中整理出与你问题最相关的要点。
- 可扩展Agent架构-技术开发文档: # 可扩展Agent架构 - 技术开发文档 **版本**: v1.3 ...
- 可扩展Agent架构-通用能力模块化方案: # 可扩展Agent架构 - 通用能力模块化方案 ...
- 可扩展Agent平台-通用PRD-v1.0: # 可扩展 Agent 平台 - 通用 PRD ...
```

——召回的是文档**首段截断**，没有针对"如何设计"做任何分析或归纳，体验明显不健全。

---

## 二、现状诊断

### 2.1 已具备的能力

`ChatService.complete()` 已经实现了一条相对完整的 RAG 链路：

1. 意图分类 (`_classify_intent`, `chat_service.py:732`) → 路由到 `knowledge_query` / `wiki_query` / `general_chat`
2. 检索执行 (`_run_knowledge_search`, `chat_service.py:798`) → 调 `KnowledgeRepository.search()` 做关键词+向量混合检索（RRF 融合）
3. 答案合成 (`_compose_answer`, `chat_service.py:837`) → 拼装 bullet 列表
4. LLM 增强 (`_generate_rag_llm_answer`, `chat_service.py:948`) → 若租户开启 LLM，则把 sources 作为 context 调模型重写答案
5. Trace 记录、输出脱敏、会话持久化

### 2.2 病根定位

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| A | **假 embedding** —— 用 SHA256 哈希到 64 维伪向量 | `retrieval/text.py:41` `embed_text()` | 完全没有语义能力，"如何设计"这种意图无法召回正确 chunk |
| B | **Bullet 模板兜底** —— LLM 未启用或返回空时直接 `title: snippet` 拼接，并截断到 chunk 首段 | `chat_service.py:872` `_compose_answer` | 用户看到原始片段堆叠，没有分析 |
| C | **LLM Prompt 信息不足** —— 只把 `f"{title}: {snippet}"` 当 context_blocks | `chat_service.py:958` | 即便启用 LLM，也无来源编号、无章节路径，难以引用与组织答案 |
| D | **召回数量过少** —— `top_k=3` | `chat_service.py:801` | 上下文不够，开放问题难以充分回答 |
| E | **chunk 切分不带语义边界** —— 按 900 字硬切 | `retrieval/text.py:15` `chunk_text()` | 片段断在句中、丢失所属标题路径 |
| F | **缺少 query 改写与 rerank** | 无 | 一次召回准确度有限 |

---

## 三、修复方案

### 阶段 1：让"现有链路"立刻生效（P0，约 0.5 天）

**目标**：在不改 embedding 的前提下，先让用户看到 LLM 生成的结构化回答。

#### 1.1 暴露"LLM 未启用"诊断

`chat_service.py:219` 已写入 trace 一条 `model failed` 步骤，但前端调试面板需明显呈现。建议：

- 当 `llm_answer is None` 且 `sources` 非空时，在响应里追加 `warnings: ["LLM 未启用，已退化到拼装答案"]`
- 前端在对话气泡上方以警示色提示用户去"设置 → LLM 配置"启用模型

#### 1.2 强化 RAG Prompt

修改 `_generate_rag_llm_answer`（`chat_service.py:958`）：

```python
context_blocks = [
    f"[{i+1}] 文档《{s.title}》\n来源ID: {s.source_id or s.id}\n章节: {s.locator or '-'}\n正文:\n{s.snippet}"
    for i, s in enumerate(sources)
]
```

并在 `OpenAICompatibleLLMClient.complete` 的 system prompt 中增加：

> 你是企业知识助手。严格基于"参考资料"作答，资料未涵盖的内容请明确说明"资料未提及"。
> - 引用时使用 `[1][2]` 角标，与参考资料编号一一对应
> - 对开放性问题（如"如何设计 / 怎么实现"），按以下结构组织：
>   1. 背景与目标
>   2. 关键模块与职责
>   3. 设计要点（含取舍）
>   4. 风险与开放问题
> - 不要复述资料原文，要做归纳和提炼

#### 1.3 召回数量调整

`_run_knowledge_search` 中 `top_k=3` 调整为 `top_k=8`（`chat_service.py:801`）。

#### 1.4 验收

输入"帮我分析可扩展Agent架构如何设计"，预期：
- 返回 ≥200 字的结构化答案
- 文中含 `[1][2]` 角标
- sources 列表展示 5-8 条命中片段

---

### 阶段 2：召回质量根治（P1，约 1.5 天）

**目标**：相关文档真正排在前面，告别"伪向量"。

#### 2.1 引入真实 Embedding 模型

**选型对比**：

| 方案 | 维度 | 成本 | 部署 |
|---|---|---|---|
| BGE-m3（本地） | 1024 | 免费 | 需 GPU 或 CPU 推理服务 |
| OpenAI `text-embedding-3-small` | 1536 | 低 | API |
| 通义 `text-embedding-v3` | 1024 | 低 | API |

建议**默认采用 OpenAI 兼容 API**（与现有 `OpenAICompatibleLLMClient` 一致），可无缝切换通义/Azure。

**实现要点**：

- 新增 `apps/api/src/agent_platform/infrastructure/embedding_client.py`
- 扩展 `LLMConfig` 增加 `embedding_provider` / `embedding_model` / `embedding_api_key`
- `retrieval/text.py:embed_text()` 改为异步：`async def embed_text(text: str) -> list[float]`，内部调用客户端
- 所有调用方（索引构建、检索时 query 向量化）改为 `await`

#### 2.2 数据迁移

- 新增 migration：`migrations/versions/2026xxxx_resize_embedding_dim.py`
  - 修改 `EMBEDDING_DIMENSIONS`
  - drop & recreate `embedding_vector` 列（pgvector 维度）
  - 重建 hnsw 索引
- 增加 `embedding_status` 字段（`pending` / `ready`），新维度上线后异步 backfill 历史 chunks，避免一次性重算阻塞发布

#### 2.3 chunk 按标题切分

重写 `chunk_text()`（`retrieval/text.py:15`）：

1. 优先按 markdown 标题（`#` / `##` / `###`）切
2. 单段超过 max_chars 再按句号切
3. 每个 chunk 保存 `metadata.parents = ["顶级标题", "二级标题", ...]`
4. 召回时把 `parents` 路径作为 snippet 前缀，让 LLM 知道"这段属于哪一节"

#### 2.4 Locator 字段填充

`SourceReference.locator` 当前 RAG 路径下未填充，建议从 chunk metadata 取 `parents` 拼成 `"技术开发文档 / 三、模块设计 / 3.2 检索"` 形式，前端引用更直观。

---

### 阶段 3：召回精排与查询增强（P2，约 1 天）

#### 3.1 Query 改写

在 `_run_knowledge_search` 调用前，用 LLM 将用户原始 query 改写为 2-3 个检索友好的变体：

```
原始: "可扩展Agent架构如何设计"
变体: ["可扩展 Agent 架构 设计原则", "Agent 平台 模块划分", "Agent 架构 扩展性 方案"]
```

每个变体独立召回 top_k，按文档去重合并。

#### 3.2 Rerank

召回阶段拉宽到 `top_k=20`，再用以下任一方式重排取 top 5：

- **方案 A（推荐）**：BGE-reranker-v2 本地服务
- **方案 B（轻量）**：调 LLM 一次，要求"对每条片段输出 1-5 的相关度分"

---

### 阶段 4：体验闭环与回归（P2，约 0.5 天）

#### 4.1 Trace 可视化

把以下信息写入 `TraceStep` 并在前端调试面板呈现：
- query 改写后的 N 个变体
- 每个变体的召回 candidates 与得分
- rerank 前后对比
- LLM prompt 长度、token 消耗

#### 4.2 空召回兜底

当 `match_count=0`：
- prompt 切到"开放回答 + 提示用户上传相关文档"
- 不再返回干巴巴的"未检索到"

#### 4.3 回归测试

`apps/api/tests/` 增加 `test_rag_quality.py`：

| 用例 | 断言 |
|---|---|
| "可扩展Agent架构如何设计" | sources 含 `可扩展Agent架构-技术开发文档`；answer 长度 >200；包含 `[` 角标 |
| "RAG 检索流程是什么" | sources 含 `技术文档知识库-混合检索优化方案` |
| "查询无关的乱码 xyzqaz" | answer 含"资料未提及"或开放回答提示 |

---

## 四、落地优先级

| 优先级 | 任务 | 收益 | 工作量 |
|---|---|---|---|
| **P0** | LLM 启用诊断、强化 prompt、top_k=8 | 用户立刻看到 LLM 生成的结构化回答 | 0.5 天 |
| **P1** | 真 embedding + 维度迁移 + backfill | 召回质量根本性提升 | 1 天 |
| **P1** | chunk 按标题切 + locator 路径 | LLM 理解片段位置，引用准确 | 0.5 天 |
| **P2** | Rerank + Query 改写 | 边际提升、成本可控 | 1 天 |
| **P2** | Trace 可视化 + 回归用例 | 长期可维护 | 0.5 天 |

**合计**: 约 3.5 人日

---

## 五、风险与依赖

1. **LLM API 配额**：阶段 2 之后每次对话会多调一次 embedding 与可能的一次 rerank/改写，需评估成本与限流
2. **数据迁移窗口**：embedding 维度变更需要重建索引，建议在低峰期执行 backfill；上线前保留旧字段做回滚
3. **租户配置缺失**：若租户未配置 LLM 或 embedding key，要在 UI 显式引导，而不是默默退化
4. **chunking 规则变化**：会导致历史 trace 中的 `chunk_id` 与新 chunk 不一致，旧 trace 的引用回链可能失效——需评估是否同步迁移历史记录

---

## 六、关联文档

- [可扩展Agent架构-技术开发文档](./可扩展Agent架构-技术开发文档.md)
- [技术文档知识库-混合检索优化方案](./技术文档知识库-混合检索优化方案.md)
- [知识库行业插件化索引与混合检索-功能技术方案](./知识库行业插件化索引与混合检索-功能技术方案.md)
