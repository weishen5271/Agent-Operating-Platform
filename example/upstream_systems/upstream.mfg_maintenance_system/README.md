# 制造业设备运维上游系统示例

本目录是 `example/bundles/industry.mfg_maintenance/` 业务包配套的**上游系统对接示例**。

它不是新的业务包 bundle，而是展示一个企业已有的设备运维系统如何把能力暴露给 Agent Operating Platform：

- 上游系统提供工单、报警、备件目录等 HTTP REST API。
- 上游系统也可以把同一组能力暴露为 MCP `tools/call`。
- AOP 通过声明式 `http` / `mcp` executor 绑定这些接口。
- 业务包中的设备故障诊断、备件查询、工单草稿等能力通过 capability 名称调用这些上游能力。

> 本目录中的接口、字段、endpoint 和 token 名称均为“占位/模拟”的接口契约示例，不代表真实业务数据、真实接口返回或真实租户配置。

内置 mock 数据覆盖 CNC 加工中心、注塑机、自动包装线等典型设备，包含历史维修工单、SCADA 报警、备件库存、替代件和工单草稿返回。数据尽量贴近制造业运维系统形态，但所有响应都会保留 `simulated: true` 标记。

## 目录结构

```text
upstream.mfg_maintenance_system/
├── README.md
├── openapi.json
├── scripts/
│   └── server.mjs
└── plugins/
    ├── maintenance_system/
    │   └── plugin.json
    └── maintenance_system_mcp/
        └── plugin.json
```

## 与 bundle 的对应关系

| bundle 场景 | HTTP capability | MCP capability |
|---|---|---|
| 查询历史维修案例 | `cmms.work_order.history` | `mcp.cmms.work_order.history` |
| 生成维修派工草稿 | `cmms.work_order.draft.create` | `mcp.cmms.work_order.draft.create` |
| 查询实时报警 | `scada.alarm_query` | `mcp.scada.alarm_query` |
| 查询备件与替代料 | `spare_parts.catalog.lookup` | `mcp.spare_parts.catalog.lookup` |

HTTP 示例刻意使用了和业务包示例中相同的 capability 名称，便于说明：业务包负责“什么时候调用什么能力”，上游系统插件负责“这个能力怎么调用企业已有系统”。MCP 示例使用 `mcp.` 前缀，避免和 HTTP 插件同时安装时 capability 名称冲突。

## 一键启动

启动示例上游系统服务：

```powershell
node example/upstream_systems/upstream.mfg_maintenance_system/scripts/server.mjs
```

默认监听一个端口，同时提供 REST 和 MCP：

```text
REST base URL: http://127.0.0.1:18081
MCP endpoint:  http://127.0.0.1:18081/mcp
```

## HTTP 接口示例

示例接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/healthz` | 健康检查 |
| `GET` | `/api/v1/equipment` | 查询设备台账 |
| `GET` | `/api/v1/workorders` | 查询历史维修工单 |
| `POST` | `/api/v1/workorders/drafts` | 创建维修工单草稿 |
| `GET` | `/api/v1/alarms` | 查询设备报警流水 |
| `GET` | `/api/v1/spare-parts` | 查询备件目录与替代件 |

调用示例：

```powershell
Invoke-RestMethod `
  -Headers @{ Authorization = 'Bearer local-dev-token' } `
  'http://127.0.0.1:18081/api/v1/workorders?tenant_id=tenant-placeholder&equipment_id=EQ-CNC-650-01&limit=3'
```

[openapi.json](openapi.json) 描述了这组 HTTP REST API。它只描述接口结构，不包含真实业务数据。

对应的 AOP 插件声明：

```text
plugins/maintenance_system/plugin.json
```

租户插件配置示例：

```json
{
  "endpoint": "http://127.0.0.1:18081",
  "tenant_id": "tenant-placeholder",
  "secrets": {
    "maintenance_token": "local-dev-token"
  },
  "timeout_ms": 5000
}
```

本地联调时，AOP 的 HTTP executor 默认会拦截 localhost；如确需本地验证，需要在开发环境 allowlist 中显式放行 `127.0.0.1`。

## MCP 接口示例

MCP 工具：

| MCP tool | 说明 |
|---|---|
| `equipment.lookup` | 查询模拟设备台账 |
| `work_order.history` | 查询模拟历史维修工单 |
| `work_order.draft.create` | 创建模拟维修工单草稿 |
| `alarm.query` | 查询模拟设备报警流水 |
| `spare_parts.lookup` | 查询模拟备件目录与替代件 |

调用示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Headers @{ Authorization = 'Bearer local-dev-token'; Accept = 'application/json'; 'Content-Type' = 'application/json' } `
  -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"manual","version":"dev"}}}' `
  'http://127.0.0.1:18081/mcp'
```

对应的 AOP 插件声明：

```text
plugins/maintenance_system_mcp/plugin.json
```

租户插件配置示例：

```json
{
  "mcp_server": "http://127.0.0.1:18081/mcp",
  "secrets": {
    "maintenance_token": "local-dev-token"
  },
  "timeout_ms": 8000
}
```

本地联调时，AOP 的 MCP executor 同样会执行出站地址校验；如确需本地验证，需要在开发环境 allowlist 中显式放行 `127.0.0.1`。

## 接入方式

### 1. 选择接入协议

- REST 系统优先参考 `plugins/maintenance_system/plugin.json`。
- MCP Server 优先参考 `plugins/maintenance_system_mcp/plugin.json`。

### 2. 注册或放入插件声明

插件声明可以作为平台级插件登记，也可以放入业务包 bundle 的 `plugins/` 目录后在 `manifest.json` 中引用。

### 3. 配置租户连接参数

在控制台插件配置中为目标租户填写连接参数，配置结构以所选插件的 `config_schema` 为准。

真实环境中应使用平台的插件配置加密存储或企业密钥管理系统；不要把真实 endpoint、token、租户编码提交到仓库。

## 设计边界

- 本示例提供可运行的 HTTP / MCP 本地服务，但返回内容全部是“模拟/占位”，只用于验证协议和字段映射。
- 写操作只示例“创建工单草稿”，并配置 `side_effect_level: draft` 与幂等键，避免示例暗示 Agent 可直接落库执行高风险操作。
- 上游系统返回结构通过 `response_map` 收敛成平台 capability 的稳定输出结构，避免业务包直接依赖外部接口细节。
