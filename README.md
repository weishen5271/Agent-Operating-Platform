# Agent-Operating-Platform

可扩展 Agent 平台的 P0a 开发骨架，当前后端运行模式已收敛为 `PostgreSQL only`，不再保留内存实现。

## 当前状态

- `apps/api`：FastAPI 后端，提供工作台、统一对话、trace、审批确认、管理接口
- `PostgreSQL`：唯一运行时存储，未配置 `AOP_DATABASE_URL` 时服务直接启动失败
- `apps/web`：Next.js 控制台界面
- `compose.yaml`：提供本地 PostgreSQL 开发实例
- `seed data`：首次启动自动初始化默认租户、用户、知识源、安全事件和 LLM 配置记录

## 目录结构

```text
apps/
  api/        FastAPI 对话与工作台 API
  web/        Next.js 工作台与对话页
packages/
  shared-contracts/  OpenAPI / SDK 预留目录
docs/         PRD、技术设计、排期文档
scripts/      启动脚本
compose.yaml  本地 PostgreSQL
```

## 快速启动

### 0. 安装依赖

```bash
uv sync --dev
npm install
```

### 1. 启动 PostgreSQL

```bash
docker compose up -d postgres
```

### 2. 启动 API

macOS / Linux:

```bash
export AOP_DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/agent_platform'
export AOP_LLM_BASE_URL='https://api.openai.com/v1'
export AOP_LLM_MODEL='gpt-4o-mini'
export AOP_LLM_API_KEY='sk-...'
bash scripts/run-api.sh
```

Windows PowerShell:

```powershell
$env:AOP_DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/agent_platform'
$env:AOP_LLM_BASE_URL='https://api.openai.com/v1'
$env:AOP_LLM_MODEL='gpt-4o-mini'
$env:AOP_LLM_API_KEY='sk-...'
.\scripts\run-api.ps1
```

API 启动时会自动执行 `alembic upgrade head`，本地也可以手动运行：

```bash
uv run alembic upgrade head
```

### 3. 启动 Web

macOS / Linux:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run dev:web
```

Windows PowerShell:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8000/api/v1'
npm run dev:web
```

默认访问：

- 工作台首页：`http://127.0.0.1:3000/`
- 统一对话页：`http://127.0.0.1:3000/chat`

## 当前 API

- `GET /healthz`
- `GET /api/v1/workspace/home`
- `POST /api/v1/chat/completions`
- `GET /api/v1/chat/traces/{trace_id}`
- `POST /api/v1/chat/actions/draft`
- `POST /api/v1/chat/actions/{draft_id}/confirm`
- `GET /api/v1/admin/packages`
- `GET /api/v1/admin/system`
- `GET /api/v1/admin/security`
- `GET /api/v1/admin/knowledge`
- `GET /api/v1/admin/traces`
- `GET /api/v1/admin/llm-runtime`
- `POST /api/v1/admin/llm-runtime`

## 验证

先确保 PostgreSQL 已启动并已设置 `AOP_DATABASE_URL`：

```bash
uv run pytest apps/api/tests/test_chat_api.py
npm run build --workspace @agent-platform/web
```

## 下一步建议

- 为 capability 执行链补数据库级权限审计与错误码
- 基于 OpenAPI 生成 `packages/shared-contracts`
