# Agent Operating Platform

Agent Operating Platform 是一个面向企业场景的可扩展 Agent 运行与治理平台。当前系统以 FastAPI 后端、Next.js 控制台和 PostgreSQL/pgvector 存储为核心，围绕“业务包 + 通用执行器 + 租户配置”的方式组织行业能力，让 Agent 能在统一对话、知识检索、业务工具调用、审批确认、审计追踪和多租户治理之间形成闭环。

> 当前版本仍是研发阶段实现，适合本地开发、能力验证和业务包机制联调；生产部署前需要补齐真实密钥管理、网络侧出站治理和完整运维配置。

## 核心能力

### 统一对话与执行链路

- 支持同步对话接口与 SSE 流式对话接口。
- 支持会话列表、会话详情、会话删除和请求 Trace 查询。
- 对话链路会结合租户、用户、业务包、知识库和工具权限生成执行策略。
- 支持高风险操作先生成草稿，再由确认接口执行。
- 支持将执行过程、来源引用、能力调用步骤写入 Trace，便于审计和排障。

### 业务包机制

- 支持从 `packages/catalog` 加载内置业务包，也支持上传 zip bundle 安装到 `packages/installed`。
- 业务包可声明 `manifest.json`、私有 skill、tool、plugin、prompt 和知识导入清单。
- bundle 不允许上传 Python 代码；扩展能力通过声明式 executor 运行，降低远程代码执行风险。
- 支持业务包安装、覆盖安装、卸载、详情查看、影响分析和诊断信息展示。
- 支持租户绑定主业务包与通用业务包，前端提供业务包上下文切换。

### Executor 与插件扩展

- `stub` executor：用于业务包能力的占位执行，按输出 schema 生成结构化结果。
- `http` executor：通过声明式 binding 调用 REST 系统，支持 `$input`、`$config`、`$secret`、`$response` 引用。
- `mcp` executor：支持基于 HTTP/streamable-http 的 MCP JSON-RPC 最小闭环。
- `platform` executor：允许业务包显式代理平台内置能力，并做存在性与版本范围校验。
- HTTP/MCP 出站请求会执行基础 URL 校验，并支持 allowlist 配置。
- 插件配置支持租户级保存，`config.secrets` 子树在应用层加密存储，API 展示时返回掩码。

### 知识库与 Wiki 治理

- 支持知识库创建、更新、删除和知识源入库。
- 支持知识源属性、分块、重嵌入和检索。
- 支持 LLM-Wiki 页面列表、页面详情、版本记录、搜索、编译任务和编译记录。
- 支持文件分布概览、分组筛选、覆盖状态查看和来源详情。
- 业务包可声明 `knowledge_imports`，但不会静默写入知识库；需要通过显式导入接口触发。

### 安全、权限与审计

- 支持登录、注册、当前用户查询和 Bearer Token 鉴权。
- 支持租户、用户、角色 scopes 和租户业务包绑定管理。
- 支持工具级覆盖策略，包括 quota、timeout 和 disabled。
- 支持输出红线规则配置。
- 支持安全事件、审计 Trace、发布计划和系统概览查询。
- 支持 MCP Server 注册表管理，包括新增、更新、禁用和删除。

### 业务成果管理

- 支持创建、查询、筛选和更新业务成果。
- 业务成果可绑定 `conversation_id`、`trace_id`、业务包、引用来源和草稿组。
- 前端提供业务成果列表、报告工作区、图表画布和决策卡片等组件。

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic、httpx
- 前端：Next.js 15、React 19、TypeScript
- 存储：PostgreSQL + pgvector
- Python 包管理：uv
- Node 包管理：npm workspaces

## 目录结构

```text
apps/
  api/                         FastAPI 后端、运行时、插件、知识库、Wiki、测试
  web/                         Next.js 控制台
docs/                          PRD、架构设计、业务包与知识库相关方案
example/
  industry.mfg_maintenance/    制造业设备运维业务包示例
migrations/                    Alembic 数据库迁移
packages/
  catalog/                     平台内置业务包目录
  installed/                   上传安装的业务包目录
  shared-contracts/            OpenAPI / SDK 预留目录
scripts/                       本地启动脚本
compose.yaml                   本地 PostgreSQL/pgvector
```

## 快速启动

### 1. 安装依赖

```bash
uv sync --dev
npm install
```

### 2. 启动 PostgreSQL

```bash
docker compose up -d postgres
```

### 3. 配置运行参数

后端只支持 PostgreSQL 运行模式，必须配置 `AOP_DATABASE_URL`。LLM 配置可通过环境变量或前端“系统配置”页面维护；未配置 LLM 时，依赖真实模型的对话能力不可用。

macOS / Linux:

```bash
export AOP_DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/agent_platform'
export AOP_LLM_BASE_URL='https://api.openai.com/v1'
export AOP_LLM_MODEL='gpt-4o-mini'
export AOP_LLM_API_KEY='sk-...'
```

Windows PowerShell:

```powershell
$env:AOP_DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/agent_platform'
$env:AOP_LLM_BASE_URL='https://api.openai.com/v1'
$env:AOP_LLM_MODEL='gpt-4o-mini'
$env:AOP_LLM_API_KEY='sk-...'
```

可选配置：

```bash
AOP_PLUGIN_CONFIG_ENCRYPTION_KEY=...
AOP_HTTP_EXECUTOR_ALLOWLIST='["api.example.com","10.0.0.0/8"]'
AOP_SECRET_KEY='change-me'
```

也可以参考 `config.toml.example` 创建本地 `config.toml`。注意不要提交真实密钥。

### 4. 启动 API

macOS / Linux:

```bash
bash scripts/run-api.sh
```

Windows PowerShell:

```powershell
.\scripts\run-api.ps1
```

API 启动时会初始化数据库连接并写入必要的默认租户、默认管理员、基础安全事件和 LLM 配置记录。数据库迁移可手动执行：

```bash
uv run alembic upgrade head
```

默认健康检查：

```text
GET http://127.0.0.1:8000/healthz
```

### 5. 启动 Web 控制台

macOS / Linux:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run dev:web
```

Windows PowerShell:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8000/api/v1'
npm run dev:web
```

访问地址：

- 控制台首页：`http://127.0.0.1:3000/`
- 登录页：`http://127.0.0.1:3000/login`
- 对话页：`http://127.0.0.1:3000/chat`

默认账号：

```text
邮箱：admin@sw.com
密码：Aa111111
租户：sw
角色：platform_admin
```

## 控制台页面

- 运营总览：平台运行指标、租户和能力概览。
- 对话演示：统一对话、业务包上下文选择、Trace 查看。
- 业务包管理：业务包列表、详情、导入、卸载、影响分析、插件配置、发布计划。
- 知识库治理：知识库、知识源、Wiki 页面、Wiki 搜索、编译任务和文件分布。
- 业务成果：报告、图表、决策卡片等结构化输出管理。
- 安全治理：工具覆盖策略、输出红线和安全事件。
- 审计合规：Trace 与执行记录查询。
- 租户与权限：租户、用户、业务包绑定、LLM Runtime、MCP Server 管理。

## 业务包 Bundle 说明

业务包是可上传、可隔离、可动态注册的部署单元。推荐结构如下：

```text
<package_id>/
  manifest.json
  prompts/
    system_prompt.txt
    planner_prompt.txt
  skills/
    <skill>.json
  tools/
    <tool>.json
  plugins/
    <plugin_name>/
      plugin.json
  knowledge/
    *.md
  README.md
```

关键原则：

- `manifest.json` 声明包元数据、依赖、提供的 skills/tools/plugins、prompts、intents 和 knowledge imports。
- 私有 capability 会按业务包注册，内置平台 capability 优先级更高，避免被 bundle 覆盖。
- 外部系统调用通过 `http`、`mcp` 或 `platform` executor 声明，不通过上传代码实现。
- bundle 中的知识文件只有在用户显式触发导入时才进入知识库。

参考实现：

```text
example/industry.mfg_maintenance/
```

## 常用 API

### 基础与认证

- `GET /healthz`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- `GET /api/v1/auth/me`

### 对话与 Trace

- `POST /api/v1/chat/completions`
- `POST /api/v1/chat/completions/stream`
- `GET /api/v1/chat/conversations`
- `POST /api/v1/chat/conversations`
- `GET /api/v1/chat/conversations/{conversation_id}`
- `DELETE /api/v1/chat/conversations/{conversation_id}`
- `GET /api/v1/chat/traces/{trace_id}`
- `POST /api/v1/chat/actions/draft`
- `POST /api/v1/chat/actions/{draft_id}/confirm`

### 业务包、插件与 MCP

- `GET /api/v1/admin/packages`
- `GET /api/v1/admin/packages/impact`
- `POST /api/v1/admin/packages/import`
- `DELETE /api/v1/admin/packages/{package_id}/bundle`
- `POST /api/v1/admin/packages/knowledge/import`
- `GET /api/v1/admin/packages/{package_id}`
- `GET /api/v1/admin/plugins/{plugin_name}/config-schema`
- `PUT /api/v1/admin/plugins/{plugin_name}/config`
- `GET /api/v1/admin/mcp-servers`
- `POST /api/v1/admin/mcp-servers`
- `PUT /api/v1/admin/mcp-servers/{server_name}`
- `DELETE /api/v1/admin/mcp-servers/{server_name}`

### 知识库与 Wiki

- `GET /api/v1/admin/knowledge`
- `POST /api/v1/admin/knowledge/ingest`
- `POST /api/v1/admin/knowledge/reembed`
- `GET /api/v1/admin/knowledge-bases`
- `POST /api/v1/admin/knowledge-bases`
- `PUT /api/v1/admin/knowledge-bases/{knowledge_base_code}`
- `DELETE /api/v1/admin/knowledge-bases/{knowledge_base_code}`
- `GET /api/v1/admin/wiki/pages`
- `GET /api/v1/admin/wiki/search`
- `POST /api/v1/admin/wiki/compile`
- `GET /api/v1/admin/wiki/file-distribution/overview`

### 治理、租户与成果

- `GET /api/v1/admin/security`
- `PUT /api/v1/admin/security/tool-overrides`
- `PUT /api/v1/admin/security/redlines`
- `GET /api/v1/admin/traces`
- `GET /api/v1/admin/system`
- `GET /api/v1/admin/releases`
- `PUT /api/v1/admin/releases/{release_id}`
- `GET /api/v1/admin/tenants`
- `POST /api/v1/admin/tenants`
- `PUT /api/v1/admin/tenants/{target_tenant_id}`
- `DELETE /api/v1/admin/tenants/{target_tenant_id}`
- `GET /api/v1/outputs`
- `POST /api/v1/outputs`
- `GET /api/v1/outputs/{output_id}`
- `PATCH /api/v1/outputs/{output_id}`

## 验证

后端局部测试：

```bash
uv run pytest apps/api/tests/test_chat_api.py -q
uv run pytest apps/api/tests/test_chat_runtime_chain.py -q
uv run pytest apps/api/tests/test_package_bundle_pipeline.py -q
uv run pytest apps/api/tests/test_http_executor.py -q
uv run pytest apps/api/tests/test_mcp_executor.py -q
uv run pytest apps/api/tests/test_wiki_api.py -q
```

前端构建：

```bash
npm run build:web
```

全量后端测试可直接运行：

```bash
uv run pytest
```

## 开发注意事项

- 当前运行时存储为 PostgreSQL only，未配置 `AOP_DATABASE_URL` 时后端不能正常启动。
- 不要把真实业务配置、凭据、租户数据、接口返回或测试结果硬编码到代码和文档中。
- 不要为了联调伪造会被误认为真实的数据；如必须使用模拟数据，需要明确标注并先获得许可。
- 新增数据库字段应通过迁移或变更 SQL 管理，不要用代码逻辑绕过数据结构问题。
- 业务包扩展优先使用声明式 executor，不引入任意代码上传机制。
- 生产环境必须替换默认 `AOP_SECRET_KEY`，并配置独立的 `AOP_PLUGIN_CONFIG_ENCRYPTION_KEY`。
- HTTP/MCP executor 的 allowlist 只能作为应用层保护，生产环境仍建议配置网络层 egress policy 或代理。

## 相关文档

- `docs/可扩展Agent平台-通用PRD-v1.0.md`
- `docs/可扩展Agent架构-技术开发文档.md`
- `docs/业务包bundle化-交接文档.md`
- `docs/业务包相关开发方案/行业业务包-通用开发方案.md`
- `docs/LLM-Wiki独立模块化改造技术方案.md`
- `example/industry.mfg_maintenance/README.md`
