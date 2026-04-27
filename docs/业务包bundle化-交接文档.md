# 业务包 Bundle 化改造 · 交接文档

**版本**: v0.1
**日期**: 2026-04-27
**状态**: 阶段性完成（HTTP executor 已通），剩余项移交后续迭代
**关联文档**:
- [行业业务包-通用开发方案.md](业务包相关开发方案/行业业务包-通用开发方案.md)（v1.1 已更新）
- [example/industry.mfg_maintenance/](../example/industry.mfg_maintenance)（参考实现）

---

## 1. 改造背景与目标

### 1.1 起点问题

原始实现把业务包等同于一份扁平 manifest JSON：

- example 仅 `industry.mfg_maintenance.json`，其中 plugin/skill 当成"平台已存在"的依赖列出 (`current_version`, `compatible: true`)
- 安装方式是用户手动 `cp` 到 `packages/catalog/`，没有上传通道
- 实际上 plugin / skill / tool 都不可能被业务方真正交付

### 1.2 目标

让业务包成为**真正可上传、可隔离、可动态扩展**的部署单元：

- 一个目录打包 zip，UI 上传安装，自动隔离注册到对应注册表
- 私有 capability 不依赖平台预装代码 —— 通过 **声明式 executor**（http / mcp / platform / stub）驱动
- 平台镜像里只有 3-4 个通用 executor 类，永远不需要为新行业改代码
- 与现有契约校验、配置管理、审批、Trace、审计链路完全兼容

### 1.3 核心架构原则

> **Bundle 提供"会做什么"的契约，平台插件提供"怎么做"的代码，租户配置提供"做给谁"的实例值**

- Bundle = 契约 + 配置 schema + binding DSL
- 平台 executor = 数据驱动的通用执行器
- 租户配置 = endpoint / secrets / 实例值（隔离在 plugin_config 表）

---

## 2. 已落地内容（截至本文档）

### 2.1 Bundle 布局与上传安装

| 文件 | 作用 |
|---|---|
| [apps/api/src/agent_platform/runtime/package_loader.py](../apps/api/src/agent_platform/runtime/package_loader.py) | 同时扫 `packages/catalog/` 与 `packages/installed/<id>/`，bundle 优先；解析 `provides.{skills,tools,plugins}` + `prompts.*` |
| [apps/api/src/agent_platform/runtime/package_installer.py](../apps/api/src/agent_platform/runtime/package_installer.py) | zip 解压沙箱（路径越界 / 扩展名 / 大小 / 文件数限制），落到 `packages/installed/<id>/`；校验 manifest + provides 引用 |
| [apps/api/src/agent_platform/api/routes/admin.py](../apps/api/src/agent_platform/api/routes/admin.py) | `POST /admin/packages/import`（multipart）、`DELETE /admin/packages/{id}/bundle` |
| [apps/web/src/app/(workspace)/packages/page.tsx](../apps/web/src/app/(workspace)/packages/page.tsx) | 「导入业务包」按钮 + 隐藏 `<input type=file>` + `importPackageBundle()` |
| [example/industry.mfg_maintenance/](../example/industry.mfg_maintenance) | bundle 参考实现 |

**Bundle 目录结构**：

```
<package_id>/
├── manifest.json                # 必需。requires / provides / prompts / intents / knowledge_bindings
├── prompts/{system,planner}.txt
├── skills/<skill>.json          # 私有 skill，自动以 source="package" + package_id 注册
├── tools/<tool>.json            # 私有 tool 别名
├── plugins/<plugin_name>/plugin.json  # 私有 plugin，含 capabilities[].binding
├── knowledge/                   # 示例文档（仍走 /knowledge 单独上传）
└── README.md
```

**Manifest 关键字段**：

```jsonc
{
  "package_id": "industry.<name>",
  "name": "...", "version": "v1.0.0", "owner": "...", "status": "灰度中", "domain": "industry",
  "intents": [...],
  "knowledge_bindings": [...],
  "requires": [   // 平台已存在的依赖（兼容性校验）
    { "kind": "common_package",  "name": "_common/knowledge",  "version_range": ">=1.0 <2.0" }
  ],
  "provides": {   // 业务包私有产物 —— 上传 bundle 时安装
    "skills":  ["skills/<skill>.json"],
    "tools":   ["tools/<tool>.json"],
    "plugins": ["plugins/<plugin_name>/plugin.json"]
  },
  "prompts": { "system": "prompts/system_prompt.txt", "planner": "prompts/planner_prompt.txt" }
}
```

### 2.2 注册表自动 refresh

| 文件 | 关键改动 |
|---|---|
| [skill_registry.py](../apps/api/src/agent_platform/runtime/skill_registry.py) | 加 `refresh()`；私有 skill 命名空间化为 `package_id::name`；bundle 中 skill JSON 省略 `source` 时默认填 `package` |
| [registry.py](../apps/api/src/agent_platform/runtime/registry.py) | 新增 `_package_plugins` 字典 + `refresh_package_capabilities()`；构造时立即 refresh；`invoke()` 加 `tenant_config` kwarg；`get_plugin()` 支持 capability_name / plugin_name 双向反查；新增 `get_plugin_name_for_capability()` |
| [chat_service.py · install_package_bundle / uninstall_package_bundle](../apps/api/src/agent_platform/runtime/chat_service.py) | 安装/卸载后双重 refresh：`self._skills.refresh()` + `self._registry.refresh_package_capabilities()` |
| [domain/models.py · CapabilityDefinition](../apps/api/src/agent_platform/domain/models.py) | 加 `source: str = "_platform"` + `package_id: str | None = None` 字段 |

**约束**：内置插件永远赢 —— 同名 capability 已在 `_builtin_plugins`，bundle stub/http 自动让位（`if name in self._builtin_plugins: continue`）。这是为了让"真实 executor 一旦发布，bundle 不动 stub 自动退场"。

### 2.3 Executor 体系

| Executor | 文件 | 实现状态 | 适用 |
|---|---|---|---|
| `stub` | [plugins/stub.py](../apps/api/src/agent_platform/plugins/stub.py) | ✅ 完成 | 上传后立即可调，按 `output_schema.required` 合成 fixture |
| `http` | [plugins/executors/http.py](../apps/api/src/agent_platform/plugins/executors/http.py) | ✅ 完成 | REST 系统。binding DSL 见 §2.4 |
| `mcp` | — | ❌ 未做 | 见 §3.2 |
| `platform` | — | 🟡 用 `_builtin_plugins` 隐式做了，未字段化 | 见 §3.5 |

`CapabilityRegistry._build_executor` 按 `plugin.json.executor` 字段分发；未识别值落回 stub。

### 2.4 HTTP binding DSL（已实现）

引用语法：

| 引用 | 含义 |
|---|---|
| `$input.<dot.path>` | 调用 capability 的 payload |
| `$config.<dot.path>` | 租户级 plugin_config |
| `$secret.<name>` | 等同 `$config.secrets.<name>` |
| `$response.<dot.path>` | HTTP 响应（仅 `response_map` / `error_translation` 中可用） |

binding 字段：`method`、`path`、`query`、`headers`、`body`、`timeout_ms`、`response_map`、`error_translation`。

错误翻译支持精确 `"401"` 与桶位 `"5xx"`，并自动映射网络错为 `UPSTREAM_TIMEOUT` / `UPSTREAM_UNREACHABLE`，缺配置为 `MISSING_CONFIG`。

完整示例：[example/.../plugins/cmms_work_order/plugin.json](../example/industry.mfg_maintenance/plugins/cmms_work_order/plugin.json)

### 2.5 调用链（一次会话）

```
POST /api/v1/chat/complete
  → ChatService._complete_core
  → LLM Planner / 关键词意图
  → _select_skill_for_intent → 命中 skill (元数据 only，steps 编排器未实现 → §3.3)
  → _plan(message, intent) → 选 capability_name + payload
  → _ensure_scope / _evaluate_risk / _check_quota
  → _load_capability_tenant_config(tenant_id, capability_name)
       → registry.get_plugin_name_for_capability(name)
       → plugin_configs.get(tenant_id, plugin_name)
  → registry.invoke(name, payload, tenant_config=...)
       → _validate_payload (input_schema.required)
       → plugin.invoke_with_config(payload, tenant_config)
            ├ HttpExecutor: 渲染 binding → httpx.Client.request → response_map
            ├ StubPackagePlugin: 合成 fixture
            └ 内置插件: 走原 invoke() 路径
  → Output Composer / Output Guard / Trace 落盘
```

### 2.6 验证

- `python -c` 端到端冒烟脚本（在改造各阶段跑过）：
  - bundle zip 打包 → install_zip → 注册表 refresh → 调 capability → 卸载
  - 真起 stdlib HTTPServer 当假 CMMS，HttpExecutor 真发请求 → response_map 抽字段 → 错误翻译生效
- 没有写正式 pytest 单测（**§3.7**）

---

## 3. 待办清单（按优先级）

### 3.1 【P0】Plugin Config 表单支持 `secrets` 子段

**目标**：让运维真能在 UI 把 `cmms_token` 这种凭据填进去；当前 `_validate_plugin_config` 不认识嵌套 `secrets` 对象。

**现状**：
- [chat_service._normalize_plugin_config_schema / _validate_plugin_config](../apps/api/src/agent_platform/runtime/chat_service.py) 是平铺 key 的校验
- [PluginConfigForm](../apps/web/src/components/packages/plugin-config-form.tsx)（如果在的话）按 schema 渲染表单
- example 的 `cmms_work_order/plugin.json` 里 `config_schema.secrets` 是 `{"type": "object"}`，但前后端都没专门处理

**做什么**：
- 后端：扩展 `_normalize_plugin_config_schema` 识别 `type: "object"` 子结构；秘钥型字段（`format: "secret-ref"` 或父键叫 `secrets`）写入数据库时**必须**保留原值，但读取展示时返回掩码（如 `"***last4"`）
- 前端：表单按 secrets 子项 key/value 渲染，输入框 `type="password"`，编辑时区分"保留原值 / 改为新值 / 清空"
- 数据层：`plugin_config.config` 已是 JSONB，不需要 schema 变更

**验收**：
1. UI 进 `cmms.work_order` 配置页能看到 endpoint + secrets.cmms_token + timeout_ms 三个字段
2. 填入后 `plugin_config` 表里能看到原值
3. 重新打开页面 secrets 显示掩码，不回填原文
4. 立即 /chat 触发 capability 调用，HttpExecutor 拿到的 `tenant_config['secrets']['cmms_token']` 是真值

**风险**：当前没有真正的 KMS / Vault；明文落库是过渡方案。**不要**在这一项里顺手做加密，单独立项处理（§3.6）。

---

### 3.2 【P0】实现 `executor: "mcp"`

**目标**：覆盖 GitHub MCP / Slack MCP 等已 MCP 化的系统，与设计文档 §5.7 对齐。

**做什么**：
1. 新建 [apps/api/src/agent_platform/plugins/executors/mcp.py](../apps/api/src/agent_platform/plugins/executors/mcp.py) ，参考 http.py 的结构
2. 平台层先做一个轻量 MCP server 注册表：
   - 数据模型：`mcp_server` 表（id / name / transport / endpoint / auth_ref / status）
   - 管理 API：`POST/PUT/DELETE /admin/mcp-servers`
   - UI：「系统配置 → MCP Servers」一张表
3. binding DSL 子集：

   ```jsonc
   {
     "mcp_server": "$config.mcp_server",          // 指向已注册的 MCP server name
     "mcp_tool":   "create_issue",                // server 那边的 tool 名
     "argument_map": {
       "owner": "$input.owner",
       "title": "$input.title"
     },
     "response_map": { "issue_url": "$response.html_url" }
   }
   ```

4. `McpExecutor.invoke_with_config` 用 MCP client（推荐 `mcp` 官方 Python SDK）按 `tools/call` 协议发起调用

**验收**：用本地启一个 MCP server（如 `mcp-server-fetch`）跑通"业务包声明 capability → 平台 MCP executor 代理调用 → 返回结果"全链路。

**风险**：MCP transport 有 stdio / sse / streamable-http 三种，连接池管理 + 健康检查需要单独考虑；写操作的幂等键与超时策略与 HTTP 不完全相同。

---

### 3.3 【P1】Skill steps 真编排器

**目标**：把 [example/.../skills/fault_triage.json](../example/industry.mfg_maintenance/skills/fault_triage.json) 里的 `depends_on_capabilities` 升级为真正的 `steps[]` 数据流编排，对齐设计文档 §5.4.2 的 yaml 示例（`$inputs.x` / `$prev_step.y`）。

**现状**：
- [chat_service.py L381-393](../apps/api/src/agent_platform/runtime/chat_service.py) 只在 Trace 里写"命中 Skill: xxx"，并不真按 skill.steps 调度
- 当前是 "intent → 单个 capability" 的简化版 —— skill 只是个标签

**做什么**：
1. 升级 skill JSON 结构为 `steps[]` 形态：

   ```jsonc
   {
     "name": "fault_triage",
     "version": "1.0.0",
     "inputs":  { "equipment_id": {"type":"string","required":true}, "fault_code": {...} },
     "outputs": { "fault_meaning":..., "safety_critical":..., "suggested_actions":... },
     "steps": [
       {"id": "alarms",  "capability": "scada.alarm_query",     "input": {"equipment_id": "$inputs.equipment_id"}},
       {"id": "kb",      "capability": "knowledge.search",      "input": {"query": "故障码 ${inputs.fault_code}"}},
       {"id": "history", "capability": "cmms.work_order.history","input": {"equipment_id":"$inputs.equipment_id","fault_code":"$inputs.fault_code","last_n":5}},
       {"id": "extract", "tool": "text.extract",                "input": {"schema":"fault_summary_schema","source":["$kb.matches","$history.workorders"]}}
     ],
     "outputs_mapping": {
       "fault_meaning":     "$extract.meaning",
       "suggested_actions": "$extract.actions"
     }
   }
   ```

2. 新文件 [apps/api/src/agent_platform/runtime/skill_executor.py](../apps/api/src/agent_platform/runtime/skill_executor.py)：
   - 按拓扑顺序遍历 steps，每步调 capability 或 tool
   - 维护一个 `step_results: dict[step_id, result]` 字典
   - 引用解析复用 HttpExecutor 的 `_render_template` 思路（提取成共享 util）
   - 每步独立一个 TraceStep（`node_type="capability"`，`parent_step_id=skill_step_id`）
3. chat_service：当选中的 skill 有 `steps` 字段时，走新 executor；没有则保留 fallback 行为
4. 失败处理：单步失败默认中断；后续可加 `on_error` 字段支持降级

**验收**：上传 example bundle，提问"3 号注塑机昨晚报 AX-203，怎么处理？"，Trace 树展开能看到 fault_triage 下面 4 个子步骤都执行，最终回答里有 alarms / SOP 引用 / 历史工单的拼合。

**与 HTTP executor 共享代码**：把 `_render_template` / `_walk_path` / `_BindingContext` 从 http.py 抽到 [apps/api/src/agent_platform/plugins/executors/dsl.py](../apps/api/src/agent_platform/plugins/executors/dsl.py) ，skill_executor 复用。

---

### 3.4 【P1】HTTP executor 补：重试 / 幂等键 / 速率限制

**目标**：生产可用。

**现状**：[http.py](../apps/api/src/agent_platform/plugins/executors/http.py) 没有重试、幂等、速率限制；binding 已留 `idempotency_key` 字段位但未消费。

**做什么**：
- `binding.retry`：`{ "policy": "exponential", "max_attempts": 3, "retry_on": ["5xx", "UPSTREAM_TIMEOUT"] }`
- `binding.idempotency_key`：渲染后写入 `Idempotency-Key` 请求头；同时在内存 + Redis（如可用）做"同 key 短期幂等缓存"
- 速率限制走 ToolOverride 一类的现成机制，按 plugin_name 限流；可复用 [SkillRegistry/ToolRegistry](../apps/api/src/agent_platform/runtime/skill_registry.py) 的 `quota_per_minute` 思路

**验收**：mock server 故意 503 两次后 200，executor 重试两次拿到结果；同样 payload 调两次看到第二次走幂等命中。

---

### 3.5 【P2】把 `executor: "platform"` 字段化

**目标**：让 bundle 显式声明"我引用平台预装的 plugin <name>@<version>"，校验存在性 + 版本范围，对齐 §3.4 设计文档表格。

**做什么**：
- bundle plugin.json 支持 `{"executor":"platform","platform_plugin":"cmms_v2_legacy@1.4.0"}`
- registry refresh 时检查 `_builtin_plugins` 是否有该名称、版本是否满足
- 不满足时不注册，并在 admin packages 列表里给出告警

**验收**：bundle 引用一个不存在的 platform plugin → 安装时给出明确错误；引用存在的 → capability 走真插件 executor。

---

### 3.6 【P2】Secrets 真加密 / KMS 集成

**目标**：plugin_config.config 里的 secrets 子项不再明文落库。

**现状**：明文。`secret_key` 在 [bootstrap/settings.py](../apps/api/src/agent_platform/bootstrap/settings.py) 里只是 JWT 用的占位字符串。

**做什么**：
- 选型：KMS（AWS KMS / GCP KMS / Vault）vs 应用层 AES（with envelope key from settings.secret_key）
- 推荐：先用应用层 AES-GCM + envelope key 在环境变量里，留 KMS 接入位
- 需要：`secrets` 字段在 upsert 时加密、读取时解密；`get_plugin_config_schema` 返回掩码不解密
- 数据库迁移：plugin_config.config 改为加密 BYTEA 或保留 JSONB 内的子字段加密

**验收**：直接 SQL 看 plugin_config 表，`secrets.cmms_token` 字段不可读；通过 API 取出来 HttpExecutor 仍能拿到原值。

---

### 3.7 【P2】端到端 pytest 测试覆盖

**目标**：把交互验证脚本固化为 pytest，CI 可跑。

**现状**：[apps/api/tests/](../apps/api/tests) 已有结构，但没覆盖 bundle/executor 链路。

**做什么**：
- `tests/runtime/test_package_installer.py`：合法 zip / 大小超限 / 路径越界 / overwrite 行为
- `tests/runtime/test_package_loader.py`：bundle 优先级、provides 解析、prompts 注入
- `tests/runtime/test_capability_registry.py`：refresh / 内置避让 stub 的优先级 / get_plugin 双向反查
- `tests/plugins/test_http_executor.py`：用 `respx` 或 stdlib HTTPServer mock，覆盖 binding 渲染所有引用类型 / 错误翻译 / response_map 各路径
- `tests/runtime/test_chat_service_install.py`：完整 install_package_bundle → /chat 调用流程

**验收**：`pytest -q` 全绿；`pytest --cov` 覆盖 bundle/executor 相关代码 ≥ 80%。

---

### 3.8 【P3】网络白名单

**目标**：HttpExecutor 不能打到任意外网，仅允许租户配置中显式声明的 endpoint host + 私网段白名单。

**现状**：endpoint 由 plugin_config 提供，运维实际控制；但没有第二层约束。

**做什么**：
- 全局白名单：[bootstrap/settings.py](../apps/api/src/agent_platform/bootstrap/settings.py) 加 `http_executor_allowlist: list[str]`（CIDR / 域名 glob）
- 解析 endpoint 时校验，命中黑名单（如 `169.254.169.254` AWS metadata）直接拒绝
- 防 SSRF：禁用 redirect、禁止 file:// / data:// scheme（HttpExecutor 已 `follow_redirects=False`）

**验收**：运维误填 `endpoint=http://169.254.169.254` 时调用立即拒，不发出请求。

---

### 3.9 【P3】Bundle 自动入库 knowledge/

**目标**：上传 bundle 时把 `knowledge/*.md` 自动批量进 `/knowledge`，并按 manifest.knowledge_bindings.source 自动归类。

**现状**：仍要手动上传。

**做什么**：
- `manifest.json` 里加 `knowledge_imports[]`：`[{"file":"knowledge/SOP-CNC-轴承更换.md","source":"equipment_sop","attributes":{"model":"CNC-650"}}]`
- `package_installer.install_zip` 末尾批量调 `chat_service.ingest_knowledge_source` 写入

**验收**：上传 bundle 后，知识库治理里 4 份 SOP 已自动分类，无需手动操作。

**风险**：知识更新节奏 ≠ bundle 升级节奏，强绑定可能反而难维护。建议默认 `auto_import: false`，由用户在 UI 勾选后再触发。

---

### 3.10 【P3】卸载 UI

**目标**：UI 上能直接卸载 bundle。

**现状**：[admin.py](../apps/api/src/agent_platform/api/routes/admin.py) 已有 `DELETE /admin/packages/{id}/bundle`，但 [packages 详情页](../apps/web/src/app/(workspace)/packages/[packageId]) 没接。

**做什么**：详情页加"卸载 bundle"按钮 + 二次确认弹窗 + 调 API + 列表自动刷新。

---

### 3.11 【P4】agent-cli plugin pack/release 流水线

设计文档 §6.3 提到的工具链。优先级低，因为 bundle 已是事实上的"打包+发布"载体；只有当 platform-level plugin 包真的需要离线发布时才补。

---

## 4. 关键约束 / 不要踩的坑

1. **内置插件永远赢**：[registry.py](../apps/api/src/agent_platform/runtime/registry.py) 的 `if name in self._builtin_plugins: continue` 这条不能改 —— 它是"真实 executor 接入后 stub 自动让位"机制的根。
2. **bundle 不能上传 Python 代码**：扩展 `executor` 时永远走声明式 binding，不能走"上传 .py 后 importlib"。当前 `package_installer` 的 `ALLOWED_EXTENSIONS` 不含 `.py` 是有意为之。
3. **PackageLoader 每次 list_packages 都重扫文件系统**：性能不是大问题（catalog + installed 加起来文件数 ≤ 几十）；但如果未来上千包要做缓存，注意 install/uninstall 后必须 invalidate。
4. **CapabilityDefinition slots=True**：加新字段必须给默认值，否则旧调用站点会报错。
5. **chat_service.invoke 链是同步**：HttpExecutor 用 `httpx.Client`（同步）。如果未来要改 async，把 registry.invoke 与所有 builtin 插件一起改，不要只改一半。
6. **路由顺序**：[admin.py](../apps/api/src/agent_platform/api/routes/admin.py) 中 `POST /packages/import` + `DELETE /packages/{id}/bundle` 必须在 `GET /packages/{package_id:path}` **之前**注册，否则 path catch-all 会吞掉它们。
7. **secrets 当前明文**：见 §3.6，不要往生产塞真凭据，先用测试 token。

---

## 5. 跑通 / 调试

### 5.1 本地启动

```bash
# 后端
cd D:/github/Agent-Operating-Platform
uv sync                       # 装新加入的 python-multipart + httpx
PYTHONPATH=apps/api/src uvicorn agent_platform.main:app --reload

# 前端
cd apps/web
pnpm install
pnpm dev
```

### 5.2 端到端冒烟（直接 Python 跑，不依赖前端）

参考下面这段（已在开发期跑过）：

```python
import zipfile, io, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# 打 bundle
buf = io.BytesIO()
src = Path('example/industry.mfg_maintenance')
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in src.rglob('*'):
        if p.is_file():
            z.write(p, p.relative_to(src.parent))

# 安装
from agent_platform.runtime.package_installer import PackageInstaller
PackageInstaller.default().install_zip(buf.getvalue(), overwrite=True)

# 起假 CMMS
class MockCmms(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps({'data':[{'id':'WO-001'}],'total':1}).encode())
server = HTTPServer(('127.0.0.1', 0), MockCmms)
threading.Thread(target=server.serve_forever, daemon=True).start()

# 调
from agent_platform.runtime.registry import CapabilityRegistry
reg = CapabilityRegistry()
print(reg.invoke('cmms.work_order.history',
                 {'equipment_id':'CNC-650','last_n':5},
                 tenant_config={'endpoint':f'http://127.0.0.1:{server.server_address[1]}',
                                'secrets':{'cmms_token':'x'}, 'timeout_ms':3000}))
```

### 5.3 通过 UI 走真链路

1. 打包：`cd example && zip -r ../industry.mfg_maintenance.zip industry.mfg_maintenance`
2. 业务包管理 → 「导入业务包」选 zip
3. 业务包管理 → 能力 Tab → `cmms.work_order.history` → 配置表单填 endpoint + secrets（**§3.1 完成后才能填 secrets**）
4. /chat 提问 "3 号注塑机昨晚报 AX-203，怎么处理？" → 看 Trace 是否进了 cmms.work_order.history

---

## 6. 文件清单速查

```
新增：
  apps/api/src/agent_platform/runtime/package_installer.py
  apps/api/src/agent_platform/plugins/stub.py
  apps/api/src/agent_platform/plugins/executors/__init__.py
  apps/api/src/agent_platform/plugins/executors/http.py
  example/industry.mfg_maintenance/manifest.json
  example/industry.mfg_maintenance/skills/fault_triage.json
  example/industry.mfg_maintenance/skills/spare_lookup_with_alt.json
  example/industry.mfg_maintenance/tools/dispatch_summary.json
  example/industry.mfg_maintenance/plugins/cmms_work_order/plugin.json
  example/industry.mfg_maintenance/plugins/scada_alarm_query/plugin.json
  example/industry.mfg_maintenance/plugins/spare_parts_catalog/plugin.json
  example/industry.mfg_maintenance/prompts/system_prompt.txt
  example/industry.mfg_maintenance/prompts/planner_prompt.txt
  docs/业务包bundle化-交接文档.md (本文)

修改：
  apps/api/src/agent_platform/runtime/package_loader.py
  apps/api/src/agent_platform/runtime/skill_registry.py
  apps/api/src/agent_platform/runtime/registry.py
  apps/api/src/agent_platform/runtime/chat_service.py
  apps/api/src/agent_platform/api/routes/admin.py
  apps/api/src/agent_platform/plugins/base.py
  apps/api/src/agent_platform/domain/models.py
  apps/web/src/app/(workspace)/packages/page.tsx
  apps/web/src/lib/api-client/index.ts
  apps/web/src/lib/api-client/types.ts
  example/industry.mfg_maintenance/README.md
  docs/业务包相关开发方案/行业业务包-通用开发方案.md
  pyproject.toml

删除：
  example/industry.mfg_maintenance/industry.mfg_maintenance.json (改为 manifest.json + 拆分文件)
```

---

## 7. 开工建议顺序

1. **§3.1 secrets 表单**（半天） —— 不做这个其它都没法真接外部
2. **§3.2 mcp executor**（2-3 天） —— 拓展 executor 类型，价值最高
3. **§3.7 pytest 覆盖**（1 天） —— 在加新 executor 之前先把现有的固化下来
4. **§3.3 skill 编排器**（2 天） —— 让多步剧本真跑起来
5. **§3.4 重试/幂等**（1 天）
6. 其他按优先级排

---

## 8. 设计权衡留档（避免重复讨论）

**Q: 为什么 bundle 不能带 Python executor 代码？**
A: 任何能上传 bundle 的管理员就能远程执行任意代码 = RCE。设计文档 §5.7 明确「业务包不能直接连任意 MCP Server，必须通过平台注册的插件」。所以 executor 必须是平台预装 + 数据驱动。

**Q: 为什么 capability 嵌在 plugin 里而不是顶层 capabilities/？**
A: capability 必须有 executor / config_schema / auth_ref 的去处，脱离 plugin 就是空契约。设计文档 §5.1 把 capability 定义为"插件能力"。

**Q: 为什么 stub 要按 output_schema 合成 fixture，不直接返回 `{}`？**
A: 让下游 skill 步骤的引用 `$prev.workorders[*]` 不会立即崩溃，保留链路连续性，只是数据不真。

**Q: 为什么 binding DSL 不直接用 jq？**
A: 现阶段只需 dot-path + 简单替换，引入 jq runtime 增加依赖与攻击面。如果后续需要 array 重塑 / 条件，再加 jq 子集（在 [executors/dsl.py](../apps/api/src/agent_platform/plugins/executors/dsl.py) 里）。

**Q: 为什么内置插件永远赢？**
A: 否则恶意 bundle 可以注册同名 capability 蒙蔽真实 executor，是安全攻击面。设计文档 §6.3 contract-first 也要求"真 executor 不可被遮蔽"。

**Q: 为什么 bundle 上传不强制安装 knowledge?**
A: 知识与 bundle 升级节奏不一致；强绑会反复重复入库。

---

**End of handover.**
