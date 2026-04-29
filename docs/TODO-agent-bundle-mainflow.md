# Agent ↔ Bundle 主流程待办（现状校准版）

记录时间：2026-04-28
校准时间：2026-04-29
范围：保证 Agent 与业务 Bundle 联动主流程跑通；优先修主链路阻断点，不做架构层重构。

---

## 总体判断

当前文档识别的问题整体成立，但需要按现有实现修正两点：

- 当前代码主流程位于 `apps/api/src/agent_platform/runtime/`，不是 `application/`。
- 部分方案属于中期协议改造，例如多轮参数补全、按 bundle 限定知识检索范围、管理后台完整状态徽标；应与主流程 P0 修复拆开。

建议优先级：

1. 先修 **#6 Bundle knowledge 入库闭环**：这是“安装/激活后知识完全检索不到”的核心问题。
2. 再修 **#1 intents fallback**：避免 bundle 有 skill 但因顶层 `intents` 缺失而无法路由。
3. 再修 **#2 Skill 执行错误结构化**：避免执行异常只表现为前端请求失败。
4. 再修 **#3 缺参结构化提示**：先给前后端稳定协议；多轮挂起补参放第二阶段。
5. 最后收口 **#4/#5** 边界体验。
6. RAG 可用后补 **#7 RAG 最终回答等待时间优化**：避免“检索已完成但用户长时间等模型完整返回”的演示体验问题。

---

## 1. Bundle 顶层 intents 缺失导致路由不到 skill【高】

- **触发**：bundle manifest 缺 `intents` 字段，或字段为 `[]`，但 `provides.skills` 中的 skill 声明了 `intents`。
- **表现**：用户激活 bundle 后提问，Planner 的允许意图集合不包含该 bundle 意图，后续 `_select_skill_for_intent()` 也无法选中 skill，效果接近未安装。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/package_loader.py`：`_normalize_manifest()` 只保留 manifest 顶层 `intents`
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`_package_intent_names()` 只读取 package 顶层 `intents`
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`_candidate_skill_names_for_intent()` 先匹配 package 顶层 `intents`，再找 skill

### 建议方案

1. **加载期 fallback（P0）**  
   `PackageLoader._normalize_manifest()` 中，当顶层 `intents` 为空且 bundle 提供了 skills 时，从 `skills[*].intents` 汇总生成 fallback intent 列表。

   生成规则建议：
   - 每个 intent 转成 `{ "name": intent, "score": 0.8, "keywords": [] }`
   - 保持去重与原顺序
   - 仅在顶层 `intents` 为空时启用，不覆盖显式 manifest 配置

2. **运行期 WARN（P0）**  
   `_package_intent_names()` 发现某个激活 bundle 有 skills 但没有任何 intent 时打印 WARN，附 `package_id`。

3. **安装期校验（P1）**  
   不建议当前立即拒绝旧 bundle。可以在 manifest 版本升级后，再要求“声明 `provides.skills` 的 bundle 必须显式声明顶层 `intents`”。

### 验证建议

- 增加 loader 单测：manifest 顶层无 `intents`，skill 有 `intents`，加载后 package 顶层出现 fallback intents。
- 增加 chat 主链路单测：激活该 bundle 后，对应 intent 能选中私有 skill。

---

## 2. Skill 执行异常缺少业务化错误事件【高】

- **触发**：`SkillExecutor` 抛 `ValueError`，或 capability/tool 执行失败。
- **现状**：SSE route 已有顶层异常处理，会转成 `event: error`，不再是纯 500 中断；但错误缺少 `skill_id`、`step_id`、`code` 等业务上下文，前端通常只显示“请求失败，未收到 Agent 响应”。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/chat_service.py`：调用 `_run_declarative_skill()` 处没有按 skill 语义捕获异常
  - `apps/api/src/agent_platform/api/routes/chat.py`：`/chat/completions/stream` 顶层捕获异常并输出通用 `event: error`
  - `apps/web/src/components/chat/chat-workbench.tsx`：收到 stream error 后将空助手气泡替换为通用失败文案

### 建议方案

1. **定义 Skill 执行错误结构（P0）**  
   新增或复用 `SkillExecutionError`，至少包含：
   - `code`
   - `message`
   - `skill_id` / `skill_name`
   - `step_id`（能定位时填写）
   - `recoverable`

2. **执行点捕获并写 Trace（P0）**  
   在 `_run_declarative_skill()` 调用点或 `SkillExecutor.execute()` 内捕获可预期异常，写入失败 TraceStep，例如：
   - `name="skill_failed"`
   - `status="failed"`
   - `node_type="skill"`
   - `ref=selected_skill.name`

3. **SSE 输出结构化 error（P0）**  
   stream 事件保持 `event: "error"`，但 payload 增加 `code / skill_id / step_id / recoverable`。前端据此渲染明确错误气泡。

4. **同步接口保持一致（P1）**  
   非流式 `/chat/completions` 也应返回同等错误语义，避免两个入口行为分裂。

### 验证建议

- 构造一个缺少 step id 或 step 同时声明 capability/tool 的 skill，断言 SSE 输出结构化 `error`，且 Trace 中有失败步骤。
- 前端单测或手工验证：错误显示为可读业务错误，而不是空白或通用请求失败。

---

## 3. Skill 必填入参缺失只返回文案，缺少结构化补参协议【高】

- **触发**：Planner/LLM 无法为 skill 填齐必填 `inputs`，`missing_inputs` 非空。
- **现状**：后端会返回提示文案、跳过外部 capability 调用，并写 skipped Trace；这能避免错误执行，但前端无法渲染表单或快速补参。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`_missing_skill_inputs()` 与 `_compose_missing_skill_inputs_answer()`
  - `apps/api/tests/test_chat_runtime_chain.py`：已有缺少 `equipment_id` 时暂停执行的测试

### 建议方案

1. **先返回结构化缺参元数据（P0）**  
   在 response meta 或 message 附加字段中返回：
   - `event` 或 `status`: `need_inputs`
   - `skill_id` / `skill_name`
   - `missing_inputs`
   - `input_schema`：字段名、类型、required、label/description、default/example（有则带）

2. **前端先做只读/轻交互展示（P0）**  
   优先把缺参渲染清楚，例如“需要补充：设备编号或设备名称”。若当前不做表单回填，也应避免用户只能猜该怎么问。

3. **多轮挂起补参放第二阶段（P1）**  
   `pending_skill_call`、`input_fill`、超时清理等会引入会话状态协议，改动面较大，不建议作为主流程 P0 的必要条件。

### 验证建议

- 保留现有“缺参不执行 skill steps”的断言。
- 新增断言：响应包含结构化 `need_inputs` 信息，字段 schema 可被前端消费。

---

## 4. 命中 bundle intent 但无可执行 skill 时误走 capability 分支【中】

- **触发**：intent 来自激活 bundle，但 `_select_skill_for_intent()` 返回 `None`，例如 skills 为空、被禁用或声明不匹配。
- **表现**：代码继续走传统 capability 规划，可能因 capability 不在候选集合中抛 `PermissionError`，前端显示成权限不足，误导用户。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`_select_skill_for_intent()` 返回 `None` 后继续执行 `_plan()` 与 capability 分支

### 建议方案

1. **仅对 bundle intent 做阻断（P1）**  
   判断当前 intent 是否来自激活 bundle 的顶层 `intents`。如果是，且没有选到可执行 skill，则不要继续走平台 capability fallback。

2. **返回明确业务文案（P1）**  
   示例：`业务包 {package_name} 声明了意图 {intent}，但暂未配置可执行技能，请联系管理员补全。`

3. **routing/trace 标记原因（P1）**  
   增加 `reason: "bundle_skill_missing"`，便于排查。

### 验证建议

- 构造有 intent 但无 skill 的 bundle，断言不会抛 PermissionError，响应中包含明确原因。
- 同时验证平台内置 capability intent 不受影响。

---

## 5. routing 前端消费缺少防御【中】

- **触发**：routing schema 变化、字段缺失、后端异常降级，或未来返回 unknown routing。
- **现状**：后端当前通常返回非空 routing 对象；`PackageRouter.route()` 在无匹配时也会返回 default 对象。但前端直接读取 `routing.confidence`、`routing.signals.length`、`routing.candidates.length`，对字段缺失不够稳。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/package_router.py`
  - `apps/web/src/components/chat/chat-workbench.tsx`
  - `apps/web/src/lib/api-client/types.ts`

### 建议方案

1. **后端保持非空对象（P1）**  
   `_build_routing_decision()` 继续保证返回对象；异常时返回：

   ```json
   {
     "matched_package_id": "unknown",
     "confidence": 0,
     "candidates": [],
     "signals": ["reason=..."]
   }
   ```

2. **前端字段默认值（P1）**  
   渲染时对 `confidence / signals / candidates` 做默认值处理，避免 schema 局部缺失导致组件崩溃。

### 验证建议

- 前端用缺失 `signals/candidates` 的 routing fixture 验证页面不崩。
- 后端构造 loader 读取不到包的场景，断言 routing 仍是合法对象。

---

## 6. Bundle knowledge 文件不会自动入库导致 RAG 检索为空【高】

- **触发**：安装或激活 bundle 后，直接在 chat 中询问 bundle 内 `knowledge/*.md|.txt` 内容。
- **表现**：`_run_knowledge_search()` 只能检索已入库知识切片；bundle 文件虽在磁盘上，但未进入 `knowledge_sources`，因此命中 0 条。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/package_loader.py`：`_discover_knowledge_imports()` 自动发现知识文件，但默认 `auto_import: False`
  - `apps/api/src/agent_platform/runtime/package_installer.py`：安装阶段只校验知识文件，不导入知识库
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`import_package_knowledge()` 是独立 admin 接口
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`_run_knowledge_search()` 依赖知识库已有切片
  - `apps/api/src/agent_platform/infrastructure/repositories.py`：`ingest_text()` 当前每次导入都会新增 source/chunks，缺少 bundle 文档级幂等

### 关键决策

不建议直接在底层 `PackageInstaller.install_zip()` 内静默导入知识库，因为 installer 只处理文件落盘，缺少租户、用户、权限、知识库命名等业务上下文。

推荐边界：

- **安装**：完成文件校验和注册表刷新。
- **激活或显式导入**：在有租户上下文的服务层执行知识导入。
- **导入结果**：返回导入/跳过数量，前端可展示状态。

### 建议方案

1. **自动发现知识默认可导入（P0）**  
   `_discover_knowledge_imports()` 默认：
   - `auto_import: True`
   - `knowledge_base_code: f"pkg-{package_id}"` 或经过合法化后的包专属 code

   注意：`package_id` 可能包含 `.`、`/` 等字符，需要确认当前 `KnowledgeBaseRecord.knowledge_base_code` 允许字符范围；如需收敛，应统一转换规则，例如 `pkg-industry-mfg-maintenance`。

2. **显式 manifest 配置优先（P0）**  
   `knowledge_imports[*].knowledge_base_code` 若显式声明，则保持现有值，不被默认规则覆盖。

3. **服务层 ensure knowledge base（P0）**  
   `import_package_knowledge()` 在 `ingest_text()` 前确保目标知识库存在：
   - 已存在则跳过创建
   - 不存在则用 bundle `name/description` 创建
   - 创建动作必须在当前 tenant/user 权限上下文内执行

4. **激活业务包后触发导入（P0/P1）**  
   推荐优先接入 `update_tenant_packages()`：当租户主业务包或通用包新增 bundle 时，对该 bundle 执行 `import_package_knowledge(auto_only=True)`。

   是否在 `install_package_bundle()` 后也立即导入，需要先确认产品语义：
   - 如果“导入包”默认仅进入包库，不代表租户启用，则不应自动入库。
   - 如果“导入包”即当前租户安装启用，则可以在服务层安装成功后导入。

5. **导入幂等（P0）**  
   `knowledge_sources.ingest_text()` 或 `import_package_knowledge()` 增加 bundle 文档级幂等，建议按：
   - `tenant_id`
   - `owner = bundle:{package_id}`
   - `name`
   - `knowledge_base_code`

   已存在同名文档时应更新或跳过，不能重复生成切片。具体选择更新还是跳过，需要结合知识库现有“重新导入”的产品语义决定。

6. **卸载清理（P1）**  
   卸载 bundle 时可清理 `owner = bundle:{package_id}` 的文档；知识库实体默认保留，避免误删用户后续手动追加内容。

7. **knowledge_bindings 生效（P2）**  
   当前 `knowledge_bindings` 更像元数据说明，尚未参与检索。按 binding 分发 KB、按当前 bundle 限定检索范围属于中期增强，不阻塞主流程。

### 验证 SQL

```sql
SELECT name, owner, knowledge_base_code
FROM knowledge_sources
WHERE tenant_id = '<tenant>'
  AND owner LIKE 'bundle:%';
```

若 bundle 已激活且包含知识文件，但返回 0 行，即说明知识未入库。

### 验证建议

- Loader 单测：未声明 `knowledge_imports` 时自动发现 `knowledge/*.md|.txt`，且 `auto_import=True`、默认 KB 为包专属 code。
- Service 单测：激活/导入 bundle 后，调用 `ingest_text()`，并创建或复用目标知识库。
- 幂等单测：重复导入同一 bundle 知识，不产生重复 source/chunks。
- Chat 主链路验证：导入后询问 bundle 知识内容，`_run_knowledge_search()` 能命中 bundle 文档。

---

## 7. RAG 最终回答等待时间过长【高】

- **触发**：用户在对话演示中进行知识库问答，检索已命中，但最终回答需要等待 LLM 完整生成。
- **表现**：前端虽然调用 `/chat/completions/stream`，但当前主链路不是直接转发 LLM token；后端等 LLM 完整返回后，再执行输出审查，最后把最终答案切片成 `message_delta` 发给前端。RAG prompt 较长、模型为推理模型时，首字等待时间明显变长，甚至触发 read timeout。
- **当前位置**：
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`stream_complete()` 负责 SSE 事件输出
  - `apps/api/src/agent_platform/runtime/chat_service.py`：`_complete_core()` 在 `knowledge_query` / `wiki_query` 调用 LLM 时传入 `on_delta=None`
  - `apps/api/src/agent_platform/runtime/chat_service.py`：最终 `answer = _review_output(answer)` 与 `_apply_output_guard(...)` 后，才通过 `_emit_text_deltas()` 模拟流式输出
  - `apps/api/src/agent_platform/infrastructure/llm_client.py`：`complete()` 为非流式完整响应，`stream_complete()` 才是真模型流式

### 关键取舍

真流式输出与严格输出审查存在天然冲突：

- 若要严格审查完整答案，必须等 LLM 全量返回后再发给前端，首字延迟会高。
- 若要低首字延迟，必须把 LLM token 直接流给前端，但已发送 token 无法被最终审查撤回。

因此不能简单把所有路径改成真流式，需要明确策略边界。

### 建议方案

1. **RAG prompt 压缩（P0）**  
   先降低生成耗时，改动风险最低：
   - 限制 RAG top_k，例如默认 3。
   - 限制单个 chunk 正文字数，例如 800-1200 字。
   - 限制总上下文长度，例如 3000-6000 字。
   - 去掉与回答无关的 metadata，只保留标题、来源、章节、正文。

2. **RAG 真流式输出（P0/P1）**  
   对 `kb_grounded_qa` / `wiki_grounded_qa`，在流式接口中将 `stream_answer` 传入 `_generate_rag_llm_answer()` / `_generate_wiki_llm_answer()`，让它走 `_stream_llm_answer()`。

   配套策略：
   - 流前执行输入审查、检索内容审查、权限审查。
   - 流中直接发送 LLM token，降低首字延迟。
   - 流后对完整答案做最终审查，审查结果用于落库、warning、trace；若命中高风险，追加提示或标记回答不应复用。

3. **检索拼装先返回，LLM 精炼后替换（P1）**  
   体验优先场景可以采用双阶段：
   - 检索完成后立即返回拼装回答和来源。
   - 后台继续生成 LLM 精炼回答。
   - 前端收到精炼版后替换或追加“模型整理版”。

4. **模型分层（P1）**  
   不建议所有 RAG 最终回答都使用推理模型：
   - 规划、复杂分析可用推理模型。
   - RAG 最终回答可用更快的 chat 模型。
   - 后续可为 `kb_grounded_qa` 单独配置 `answer_model`。

5. **超时分级（P1）**  
   不建议所有 RAG 都等待同一个大 timeout：
   - 简单知识问答：30-45 秒。
   - 普通 RAG：60-90 秒。
   - 明确要求方案设计/复杂分析：120-180 秒。
   - 超时后保留检索拼装回答，并给出明确 warning。

### 验证建议

- 流式接口验证：RAG 命中后，在 LLM 完整结束前，前端能收到真实 `message_delta`。
- 审查验证：真流式结束后，完整答案仍进入 `_review_output()` 与 `_apply_output_guard()`，并写入 Trace。
- 性能验证：记录 RAG 的检索耗时、首字耗时、完整回答耗时、输出审查耗时，便于对比优化前后。
- 超时验证：模拟 LLM 慢响应，确认超时后仍返回检索拼装回答，Trace 中保留明确失败原因。

---

## 当前不建议立即做的内容

- 不建议在没有租户上下文的 `PackageInstaller` 内直接写知识库。
- 不建议第一阶段实现完整 `pending_skill_call + input_fill` 多轮补参协议。
- 不建议第一阶段按 `knowledge_bindings` 重构检索范围；先保证 bundle 知识能入库并被搜到。
- 不建议为了兼容旧 bundle 立即把空 `intents` 变成安装失败；先用加载 fallback 和 WARN 平滑过渡。
- 不建议在未明确审查策略前，把所有回答路径无差别改成真流式输出。
