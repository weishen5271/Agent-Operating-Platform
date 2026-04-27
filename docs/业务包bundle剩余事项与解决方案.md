# 业务包 Bundle 剩余事项与解决方案

> 本文用于记录“业务包 bundle 上传、配置、结合 Agent 做数据接入、智能问答与决策”当前尚未完成到生产验收级别的内容。
>
> 约束：不伪造业务数据、不伪造接口返回、不写入长期占位数据。凡涉及真实业务系统、真实 MCP Server、真实凭据或真实业务知识，必须由用户明确提供测试环境、endpoint、账号权限和验收样例。

---

## 1. 当前结论

当前平台已经打通基础闭环：

- bundle 可上传、安装、覆盖、卸载。
- bundle 可声明 plugins、skills、tools、prompts、knowledge_imports。
- HTTP executor、MCP executor、platform executor 已接入 CapabilityRegistry。
- plugin_config、MCP server 注册表、secrets 加密、前端配置 UI 已具备。
- Skill steps 已接入 chat 主链路，可做多步编排。
- 知识可由 bundle 声明，并由用户显式触发导入。

但以下能力仍处于“基础实现已具备，生产级闭环未完成”状态：

- 真实业务系统端到端联调。
- 完整 API 级 E2E 测试。
- Planner / Agent 决策能力增强。
- 知识导入后的版本、重复导入和卸载治理。
- MCP executor 的更多 transport、连接池、健康检查和写操作治理。
- 多进程部署下的幂等与限流持久化。
- CI 覆盖率门槛和环境权限问题收敛。

---

## 2. 剩余事项总览

| 优先级 | 剩余事项 | 当前状态 | 核心风险 | 建议处理顺序 |
| --- | --- | --- | --- | --- |
| P0 | 真实业务系统端到端联调 | 协议级测试已通过，真实服务未验收 | executor 与真实返回结构不匹配 | 第 1 |
| P0 | API 级 E2E 测试 | runtime / executor 测试已覆盖，完整 API 链路缺失 | 改动后主流程回归不充分 | 第 2 |
| P1 | Planner 参数提取与工具选择增强 | 目前偏规则和保守解析 | 复杂问题无法稳定转成结构化调用 | 第 3 |
| P1 | 知识导入治理 | 已支持显式导入，缺版本/去重/卸载关系 | 重复导入、知识与 bundle 生命周期混乱 | 第 4 |
| P1 | MCP executor 生产增强 | streamable-http/http 最小闭环已完成 | 长连接、健康检查、写操作幂等不足 | 第 5 |
| P2 | 幂等/限流多实例化 | 当前为进程内缓存/滑窗 | 多副本部署下保护失效 | 第 6 |
| P2 | CI 与覆盖率门槛 | 局部套件可跑，全量受环境影响 | 质量门禁不稳定 | 第 7 |
| P3 | agent-cli pack/release 工具链 | 暂未实现 | 离线分发和版本发布体验不足 | 第 8 |

---

## 3. P0：真实业务系统端到端联调

### 未完成内容

当前 HTTP executor 和 MCP executor 已通过协议级测试，但尚未接入用户提供的真实业务系统完成以下链路：

1. 上传真实业务包 bundle。
2. 配置真实 plugin_config / MCP server。
3. Agent 提问。
4. Planner 选择 skill / capability。
5. executor 调真实业务系统。
6. 返回结果进入回答、Trace 和决策草稿。

### 解决方案

1. 用户提供明确的联调环境信息：
   - HTTP endpoint 或 MCP server endpoint。
   - 允许访问的网络范围或 allowlist 配置。
   - 测试账号、token 或 secret 引用。
   - 可执行的只读 tool / capability。
   - 至少 3 条真实验收问题和期望结果边界。

2. 平台侧新增联调 checklist：
   - 校验 endpoint 不命中 SSRF 阻断。
   - 校验 plugin_config secrets 不明文落库。
   - 校验 capability 的 `input_schema` 与真实接口参数一致。
   - 校验 `response_map` 能解析真实返回。
   - 校验 Trace 中能看到 package、skill、capability、executor、状态码或 MCP tool 信息。

3. 先从只读能力开始：
   - HTTP：查询类接口。
   - MCP：只读 tool，例如 search、get、list。
   - 写操作必须等幂等键、审计和审批策略确认后再开放。

### 验收标准

- 使用用户提供的真实测试环境跑通至少 1 个 HTTP capability。
- 使用用户提供的真实测试环境跑通至少 1 个 MCP tool。
- Trace 中能定位业务包、skill step、capability、executor、外部调用结果。
- 不产生测试环境之外的业务写入。

---

## 4. P0：完整 API 级 E2E 测试

### 未完成内容

已有测试覆盖：

- bundle installer / loader。
- CapabilityRegistry / SkillRegistry。
- HTTP executor。
- MCP executor。
- SkillExecutor。
- Chat runtime chain。

缺少完整 API 级链路：

```text
POST /admin/packages/import
→ PUT /admin/plugins/{plugin}/config
→ POST /chat/complete
→ 校验 answer / trace / capability result
```

### 解决方案

1. 新增 `apps/api/tests/test_bundle_chat_e2e.py`。
2. 使用测试内临时 bundle fixture，测试结束删除。
3. 使用测试内 stub executor 或本地 fake client，不连接真实业务系统。
4. 不写入长期目录、长期数据库记录或真实业务知识。
5. 覆盖成功路径和失败路径：
   - 成功：上传 bundle 后 chat 命中 skill steps，并返回映射结果。
   - 失败：插件配置缺失时返回明确错误。
   - 失败：能力被内置能力 shadow 时不允许覆盖平台能力。

### 验收标准

- `pytest apps/api/tests/test_bundle_chat_e2e.py -q` 通过。
- 测试夹具仅存在于临时目录。
- 不依赖网络、不依赖真实 token。
- 能在 CI 环境稳定运行。

---

## 5. P1：Planner 参数提取与工具选择增强

### 未完成内容

当前 Agent 决策链路已经能基于 intent、package、skill、capability 执行最小闭环，但复杂业务问题仍存在限制：

- 参数提取偏规则，复杂自然语言不稳定。
- skill 选择和 capability 选择缺少置信度解释。
- 缺少结构化 arguments 校验和二次补问。
- 失败后缺少自动修正策略。

### 解决方案

1. 引入结构化 Planner 输出：

   ```jsonc
   {
     "intent": "fault_diagnosis",
     "skill": "fault_triage",
     "arguments": {
       "equipment_id": "...",
       "fault_code": "..."
     },
     "missing_fields": [],
     "confidence": 0.86,
     "reason": "..."
   }
   ```

2. 使用 skill `inputs` 做参数校验：
   - required 字段缺失时不执行 executor。
   - 返回补问，而不是猜测业务参数。

3. 增加 Planner 失败路径：
   - 找不到 skill：返回可解释原因。
   - 参数不足：要求用户补充。
   - 多个候选 skill：展示候选和置信度。

4. 将 Planner 输出写入 Trace：
   - intent。
   - selected_skill。
   - arguments。
   - missing_fields。
   - confidence。

### 验收标准

- 对 5 条用户提供的真实业务问题，Planner 能稳定输出结构化 arguments。
- 参数缺失时不调用外部系统。
- Trace 能解释为什么选择该 skill。

---

## 6. P1：知识导入治理

### 未完成内容

当前已支持：

- bundle 声明 `knowledge_imports[]`。
- UI 显式导入。
- attributes 写入 chunk metadata。
- bundle 卸载不会删除知识库数据。

仍缺：

- 重复导入检测。
- 知识来源与 bundle/package/version 的关系。
- bundle 升级后知识如何更新。
- bundle 卸载后是否提示保留或清理知识。
- 导入记录审计。

### 解决方案

1. 增加知识导入 source metadata：
   - `package_id`
   - `package_version`
   - `bundle_file`
   - `content_hash`
   - `imported_at`
   - `imported_by`

2. 导入前做重复检测：
   - 同 tenant、knowledge_base_code、package_id、bundle_file、content_hash 已存在时提示跳过。
   - content_hash 变化时创建新 source 或新 version，具体策略由知识库版本模型决定。

3. UI 增加导入预检：
   - 待导入。
   - 已存在。
   - 内容变更。
   - 文件缺失。

4. 卸载 bundle 时不自动删除知识，但提示：
   - 该 bundle 曾导入哪些知识。
   - 是否需要跳转知识库治理页面手动处理。

### 验收标准

- 同一 bundle 重复点击导入不会产生重复知识源。
- bundle 升级后能识别哪些知识文件内容发生变化。
- 知识详情能追溯来源 bundle。

---

## 7. P1：MCP Executor 生产增强

### 未完成内容

当前 MCP executor 支持：

- `streamable-http` / `http`
- `initialize`
- `notifications/initialized`
- `tools/call`
- SSE response 解析
- SSRF / allowlist 校验

仍缺：

- stdio transport。
- 独立 SSE transport。
- 连接池与 session 复用。
- MCP server 健康检查。
- tools/list 能力发现。
- 写操作幂等、审批和审计。

### 解决方案

1. transport 分层：
   - `McpHttpTransport`
   - `McpSseTransport`
   - `McpStdioTransport`

2. 增加 server health check：
   - 管理页展示状态。
   - 定期或手动触发 `initialize` / `tools/list`。
   - 记录最近错误。

3. 增加 tools discovery：
   - `GET /admin/mcp-servers/{name}/tools`
   - 返回工具名、inputSchema、description。
   - bundle 配置时可选择 tool，而不是手写。

4. 写操作治理：
   - capability `side_effect_level=write/irreversible` 时强制走 draft。
   - 支持 binding 级 `idempotency_key`。
   - Trace 记录 MCP method、tool、server、request_id。

### 验收标准

- 已注册 MCP server 能在 UI 上查看健康状态。
- 能列出 MCP tools。
- 写操作不会自动执行，必须进入草稿或审批链路。

---

## 8. P2：幂等与限流多实例化

### 未完成内容

当前 HTTP executor 的幂等缓存和 rate limit 是进程内实现：

- 单进程有效。
- 多进程、多副本部署时不共享。

### 解决方案

1. 抽象接口：
   - `IdempotencyStore`
   - `RateLimitStore`

2. 默认保留 in-memory 实现，用于开发和单进程。

3. 生产提供 Redis 实现：
   - 幂等：`SET NX EX`。
   - 限流：滑动窗口或 token bucket。
   - key 包含 tenant_id、package_id、plugin_name、capability_name。

4. 配置项：
   - `executor_state_backend=memory|redis`
   - `redis_url`

### 验收标准

- 多进程并发下，同一 idempotency_key 只执行一次写操作。
- 多副本下 rate limit 全局生效。
- Redis 不可用时返回明确错误或降级策略，不静默失效。

---

## 9. P2：CI 与覆盖率门槛

### 未完成内容

当前局部测试可跑，但存在：

- `.pytest_cache` 权限 warning。
- 全量测试可能受本地环境、缓存权限或依赖影响。
- 未设置覆盖率门槛。

### 解决方案

1. 修复测试缓存目录：
   - CI 中显式设置 `PYTEST_ADDOPTS=--cache-clear` 或指定可写 cache dir。
   - 本地清理 `.pytest_cache` 权限问题。

2. 拆分 CI job：
   - api-unit。
   - api-runtime。
   - web-build。
   - migration-check。

3. 增加覆盖率：
   - 初始门槛先设 bundle/executor 相关代码 70%。
   - 稳定后提升到 80%。

4. 输出测试矩阵文档：
   - 哪些测试不依赖数据库。
   - 哪些测试需要数据库。
   - 哪些测试需要用户提供真实联调环境，默认不在 CI 跑。

### 验收标准

- CI 稳定执行 bundle/executor/chat runtime 相关套件。
- 覆盖率报告能定位 bundle/executor 未覆盖分支。
- 真实联调测试默认跳过，只有显式提供环境变量才执行。

---

## 10. P3：Agent CLI Pack / Release 工具链

### 未完成内容

当前 bundle zip 已经是事实上的打包载体，但缺少命令行工具：

- pack。
- validate。
- diff。
- release。
- sign。

### 解决方案

1. 新增 CLI：

   ```text
   agent-package validate <bundle-dir>
   agent-package pack <bundle-dir> --out dist/pkg.zip
   agent-package diff old.zip new.zip
   agent-package inspect pkg.zip
   ```

2. validate 检查：
   - manifest 必填字段。
   - provides 路径存在。
   - knowledge_imports 路径不逃逸。
   - executor 类型合法。
   - platform_plugin 版本范围合法。

3. diff 输出：
   - 新增/删除 capability。
   - skill steps 变化。
   - plugin_config schema 变化。
   - knowledge_imports 变化。

### 验收标准

- 发布前可本地验证 bundle。
- CI 可对 bundle 做静态校验。
- 包升级差异可审计。

---

## 11. 推荐推进顺序

1. 补 API 级 E2E 测试，先把已有闭环固化。
2. 基于用户提供的真实测试环境做 HTTP/MCP 端到端联调。
3. 增强 Planner 结构化输出和参数缺失补问。
4. 做知识导入去重、版本和来源追溯。
5. 做 MCP health check / tools discovery / 写操作治理。
6. 把幂等与限流迁移到 Redis 或统一状态存储。
7. 收敛 CI、覆盖率和测试环境权限。
8. 最后补 agent-cli pack/release 工具链。

---

## 12. 下一步建议

建议下一步先做 **API 级 E2E 测试**，原因：

- 不需要真实业务系统。
- 不需要伪造长期业务数据。
- 可以用测试内临时 bundle fixture，测试结束即清理。
- 能把当前已经实现的上传、配置、Agent 调用和 Trace 主链路固化下来，降低后续重构风险。

该测试完成后，再进入真实 HTTP/MCP 联调会更稳。
