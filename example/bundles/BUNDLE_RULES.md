# Bundle 制作规则

本文说明业务包 bundle 的通用制作规则。一个 bundle 是可上传、可校验、可安装的目录包，用于声明行业场景、意图、私有能力、提示词和可导入知识文件。

## 1. 基本原则

- bundle 必须以目录为单位组织，根目录必须包含 `manifest.json`。
- bundle 内只放声明、提示词、文档和示例材料；不要上传 Python、Node 或其他可执行代码。
- 私有能力通过声明式 `skill`、`tool`、`plugin` 描述，由平台内置 executor 执行。
- 外部系统对接不要硬编码真实 endpoint、token、租户编码或接口返回；连接参数应放到租户级插件配置。
- 示例或 mock 数据必须明确标注为“模拟/占位”，不要伪装成真实业务数据。

## 2. 推荐目录结构

```text
<package_id>/
├── manifest.json
├── README.md
├── prompts/
│   ├── system_prompt.txt
│   └── planner_prompt.txt
├── skills/
│   └── <skill>.json
├── tools/
│   └── <tool>.json
├── plugins/
│   └── <plugin_name>/
│       └── plugin.json
├── knowledge/
│   └── *.md
└── conversations.md
```

当前运行时会从 `manifest.json` 的 `provides` 字段加载 `skills`、`tools`、`plugins`，会从 `prompts` 字段读取提示词文件，会发现或读取 `knowledge_imports` 指向的知识文件。

## 3. manifest.json 规则

必填字段：

| 字段 | 说明 |
|---|---|
| `package_id` | 业务包唯一 ID，建议使用反向域名或领域前缀，例如 `industry.mfg_maintenance` |
| `name` | 展示名称 |
| `version` | 版本号 |
| `owner` | 维护方 |
| `domain` | 领域，例如 `industry`、`finance`、`hr` |

常用字段：

| 字段 | 说明 |
|---|---|
| `description` | 业务包说明 |
| `intents` | 意图关键词和命中分值，用于对话路由 |
| `requires` | 依赖的平台能力、通用包或 platform skill，只做兼容性/影响分析 |
| `provides` | 本 bundle 提供的私有 skill、tool、plugin 文件路径 |
| `prompts` | 提示词名称到文本文件路径的映射 |
| `knowledge_bindings` | 业务知识源定义，用于说明知识召回边界 |
| `knowledge_imports` | 可选，显式声明要导入的知识文件 |
| `default_outputs` | 推荐输出类型 |

`provides` 中的路径必须是相对 bundle 根目录的路径，不能越界到 bundle 外部：

```json
{
  "provides": {
    "skills": ["skills/fault_triage.json"],
    "tools": ["tools/dispatch_summary.json"],
    "plugins": ["plugins/cmms_work_order/plugin.json"]
  }
}
```

## 4. Plugin 规则

Plugin 文件必须是 JSON object，通常放在 `plugins/<plugin_name>/plugin.json`。

核心字段：

| 字段 | 说明 |
|---|---|
| `name` | 插件名称 |
| `version` | 插件版本 |
| `description` | 插件说明 |
| `executor` | 执行器类型，当前示例使用 `stub` / `http`，平台也支持 `mcp` / `platform` |
| `config_schema` | 租户级连接配置的表单结构 |
| `default_config` | 默认配置 |
| `capabilities` | 插件暴露的 capability 列表 |

Capability 必须明确：

- `name`：能力名，应稳定，不要随意改名。
- `risk_level`：风险等级，例如 `low`、`medium`、`high`。
- `side_effect_level`：副作用等级，例如 `read`、`draft`、`write`。
- `required_scope`：调用所需权限。
- `input_schema` / `output_schema`：输入输出契约。
- `binding`：当 executor 为 `http`、`mcp`、`platform` 时描述实际调用方式。

写操作建议优先做草稿能力：

```json
{
  "risk_level": "medium",
  "side_effect_level": "draft"
}
```

并在 HTTP binding 中配置 `idempotency_key`，避免重复提交造成重复草稿。

## 5. Skill 规则

Skill 文件必须是 JSON object，通常放在 `skills/<skill>.json`。

建议字段：

| 字段 | 说明 |
|---|---|
| `name` | skill 名称 |
| `description` | skill 说明 |
| `version` | skill 版本 |
| `depends_on_capabilities` | 依赖的 capability |
| `depends_on_tools` | 依赖的平台 tool |
| `steps` | 可选，声明式编排步骤 |
| `outputs_mapping` | 可选，把步骤结果映射为 skill 输出 |

当使用 `steps` 时，输入引用应使用当前运行时支持的变量风格，例如 `$inputs.xxx`、`$steps.<step_id>.xxx`。

## 6. Tool 规则

Tool 文件必须是 JSON object，通常放在 `tools/<tool>.json`。

Tool 适合声明平台已有工具的别名或轻量包装，不适合承载业务系统调用逻辑。业务系统调用应优先放在 plugin capability 中。

## 7. Prompt 规则

Prompt 文件放在 `prompts/` 下，由 `manifest.json` 的 `prompts` 字段引用：

```json
{
  "prompts": {
    "system": "prompts/system_prompt.txt",
    "planner": "prompts/planner_prompt.txt"
  }
}
```

规则：

- prompt 文件应使用 UTF-8 文本。
- 不要把真实密钥、真实租户配置或真实接口返回写入 prompt。
- system prompt 描述角色、边界和回答风格；planner prompt 描述能力选择与编排约束。

## 8. Knowledge 规则

知识文件可放在 `knowledge/` 下，当前自动发现 `.md` 和 `.txt` 文件。

默认行为：

- bundle 安装时不会静默写入知识库。
- 需要通过显式导入接口或 UI 操作导入知识。
- 若未声明 `knowledge_imports`，运行时会发现 `knowledge/` 下的 `.md` / `.txt`，并生成待导入清单。

显式声明示例：

```json
{
  "knowledge_imports": [
    {
      "file": "knowledge/SOP-CNC-轴承更换.md",
      "name": "CNC 轴承更换 SOP",
      "source_type": "equipment_sop",
      "knowledge_base_code": "maintenance",
      "owner": "bundle:industry.mfg_maintenance",
      "auto_import": false,
      "attributes": {
        "equipment_model": "CNC-650"
      }
    }
  ]
}
```

## 9. 与上游系统示例的关系

bundle 负责描述业务包自身：

- 业务场景和意图。
- 私有 skill / tool / plugin 声明。
- prompt 和知识文件。
- 需要哪些能力来完成任务。

上游系统示例负责描述企业已有系统如何被调用：

- REST API / MCP endpoint。
- mock 服务。
- HTTP / MCP 插件 binding。
- 租户级 endpoint、token、timeout 等配置。

当前配套上游系统示例位于：

```text
example/upstream_systems/upstream.mfg_maintenance_system/
```

如果真实项目中已有 CMMS、SCADA、备件目录等系统，应优先把真实连接方式放到租户插件配置中，而不是写进 bundle。

## 10. 打包与安装

PowerShell：

```powershell
Compress-Archive -Path example/bundles/industry.mfg_maintenance/* `
                 -DestinationPath example/bundles/industry.mfg_maintenance.zip `
                 -Force
```

bash：

```bash
cd example/bundles
zip -r industry.mfg_maintenance.zip industry.mfg_maintenance
```

安装后，平台会：

1. 校验 zip 路径不能越界。
2. 读取 `manifest.json`。
3. 校验 `provides` 引用的文件存在且是 JSON object。
4. 读取 prompt 文件。
5. 生成 knowledge import 清单。
6. 将 bundle 安装到 `packages/installed/<package_id>/`。

## 11. 校验清单

提交或上传前至少检查：

- `manifest.json` 是合法 JSON。
- `package_id`、`name`、`version`、`owner`、`domain` 已填写。
- `provides` 中所有路径都存在。
- skill / tool / plugin 文件都是 JSON object。
- prompt 引用路径存在。
- knowledge 文件不包含真实敏感信息。
- plugin 中没有真实 endpoint、token、租户编码或接口返回。
- 写操作 capability 标明风险和副作用，必要时使用草稿和幂等键。
- 本地打包后的 zip 根目录结构符合预期。
