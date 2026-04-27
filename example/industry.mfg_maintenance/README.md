# 制造业设备运维助手 · 业务包示例

本目录是一个**可上传的业务包 bundle 示例**，面向离散制造与流程行业的设备运维场景。

## 目录结构（Bundle 布局）

```
industry.mfg_maintenance/
├── manifest.json                        # 业务包清单（必需）
├── README.md
├── prompts/                             # 业务包私有提示词
│   ├── system_prompt.txt
│   └── planner_prompt.txt
├── skills/                              # 业务包私有 skill（声明式）
│   ├── fault_triage.json
│   └── spare_lookup_with_alt.json
├── tools/                               # 业务包私有 tool 别名
│   └── dispatch_summary.json
├── plugins/                             # 业务包私有 plugin（声明式 stub，无代码）
│   ├── cmms_work_order/plugin.json
│   ├── scada_alarm_query/plugin.json
│   └── spare_parts_catalog/plugin.json
├── knowledge/                           # 示例文档（仍走 /knowledge 单独上传）
│   ├── SOP-CNC-轴承更换.md
│   ├── SOP-注塑机-料筒清洁.md
│   ├── 故障代码库-AX系列伺服.md
│   └── 历史工单-2025Q4.md
└── conversations.md
```

`manifest.json` 中：
- `requires` —— 依赖**平台已存在的** common_package / platform_skill / 平台 tool（仅做兼容性校验）。
- `provides.{skills,tools,plugins}` —— **本业务包私有的产物**，路径相对 bundle 根；上传时由后端解析并安装。
- `prompts.{system,planner}` —— 指向 `prompts/` 下的纯文本提示词。

## 一、安装方式（首选：UI 上传）

1. 把整个 `industry.mfg_maintenance/` 目录打包成 zip：

   ```bash
   # PowerShell
   Compress-Archive -Path example/industry.mfg_maintenance/* `
                    -DestinationPath industry.mfg_maintenance.zip

   # 或 bash
   cd example && zip -r ../industry.mfg_maintenance.zip industry.mfg_maintenance
   ```

2. 进入平台 **业务包管理 → 导入业务包**，选择刚才的 zip 文件。

   - 调用 `POST /api/v1/admin/packages/import`（multipart `file` + 可选 `overwrite=true`）
   - 后端校验 manifest + provides 路径，解压到 `packages/installed/<package_id>/`
   - SkillRegistry 自动 refresh，私有 skill 出现在 **业务包管理 → Skill** Tab

3. 卸载：`DELETE /api/v1/admin/packages/<package_id>/bundle`，目录会被清理，注册表自动 refresh。

> ⚠️ 第一阶段私有 plugin 仅支持**声明式 stub**（`executor: "stub"`），不接受 Python 代码上传；
> 真实接外部系统时，需要另外发布一个平台级 plugin 包来覆盖同名 capability。

## 二、租户启用

业务包安装后，需要在租户层启用：

1. 进入 **租户与权限 → 选择目标租户 → 业务包**；
2. 主行业包选择 `industry.mfg_maintenance`；
3. 通用包勾选 `_common/knowledge`、`_common/report_gen`；
4. 保存后顶部「包上下文」标签会显示当前激活包。

## 三、知识入库（可选但推荐）

将 `knowledge/` 下文档上传到 **知识库治理 → 上传文档**，并指定知识源：

| 文件 | 知识源 (source) | 备注 |
|---|---|---|
| `SOP-CNC-轴承更换.md` | `equipment_sop` | model=CNC-650 |
| `SOP-注塑机-料筒清洁.md` | `equipment_sop` | vendor=Haitian |
| `故障代码库-AX系列伺服.md` | `fault_codes` | severity=high/mid/low |
| `历史工单-2025Q4.md` | `maintenance_logs` | year=2025 |

知识源 ID 与 manifest 中的 `knowledge_bindings.source` 对齐，RAG 召回会按业务包过滤。

## 四、能力依赖说明

| 类型 | 名称 | 来源 |
|---|---|---|
| common_package | `_common/knowledge` | 平台已发布 |
| common_package | `_common/report_gen` | 平台已发布 |
| platform_skill | `kb_grounded_qa` | 平台已发布 |
| platform_skill | `report_compose` | 平台已发布 |
| **私有 plugin** | `cmms.work_order` / `scada.alarm_query` / `spare_parts.catalog` | **bundle 自带 stub** |
| **私有 skill** | `fault_triage` / `spare_lookup_with_alt` | **bundle 自带** |
| **私有 tool** | `mfg.dispatch_summary` | **bundle 自带（别名 text.extract）** |

## 五、回滚 / 卸载

- UI：业务包管理列表 → 详情页 → 卸载（待接入）
- API：`DELETE /api/v1/admin/packages/industry.mfg_maintenance/bundle`
- 文件层：直接删除 `packages/installed/industry.mfg_maintenance/` 也会在下次进程重启后生效，但**不会自动 refresh** 缓存。
