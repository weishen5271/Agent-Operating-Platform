# 制造业设备运维助手 · 业务包示例

本目录是一个**可直接落地的业务包示例**，面向离散制造与流程行业的设备运维场景。

## 目录结构

```
industry.mfg_maintenance/
├── industry.mfg_maintenance.json   # 业务包 manifest（核心文件）
├── README.md                        # 本说明
├── knowledge/                       # 示例知识库文档（可上传到 /knowledge）
│   ├── SOP-CNC-轴承更换.md
│   ├── SOP-注塑机-料筒清洁.md
│   ├── 故障代码库-AX系列伺服.md
│   └── 历史工单-2025Q4.md
└── conversations.md                 # 样例提问，可在 /chat 直接验证效果
```

## 一、安装方式

平台业务包通过 `packages/catalog/*.json` 自动加载。将 manifest 复制到 catalog 目录即可：

```bash
cp example/industry.mfg_maintenance/industry.mfg_maintenance.json \
   packages/catalog/
```

随后访问 **业务包管理 → 业务包列表**，会出现「制造业设备运维助手 v1.0.0」。

> 也可以等界面侧的"导入契约"按钮接通后端后，直接通过 UI 上传 JSON。当前版本（Stage 5）该入口仍是占位，落盘到 `packages/catalog/` 是最稳妥的路径。

## 二、租户启用

业务包加载后，需要在租户层启用：

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

知识源 ID 与 manifest 中的 `knowledge_bindings.source` 对齐，RAG 召回会自动按业务包过滤。

## 四、能力依赖说明

| 类型 | 名称 | 用途 |
|---|---|---|
| common_package | `_common/knowledge` | 通用知识问答骨架 |
| common_package | `_common/report_gen` | 停机分析报告渲染 |
| platform_skill | `kb_grounded_qa` v1.3.1 | 带证据链的多轮问答 |
| platform_skill | `report_compose` v0.5.2 | 业务报告章节组装 |
| plugin | `cmms.work_order` v1.1.0 | CMMS 工单创建/查询（外部对接） |
| plugin | `scada.alarm_query` v0.4.3 | SCADA 报警实时检索（外部对接） |
| plugin | `spare_parts.catalog` v1.0.6 | 备件库存与供应商查询 |

> 上述插件中带"外部对接"标注的需要单独部署连接器；未部署时插件调用会以 stub 回退，不影响知识问答与报告生成主链路。

## 五、典型使用流程

1. 工程师在 `/chat` 发起："**3 号注塑机昨晚报 AX-203 报警，怎么处理？**"
2. 路由命中 `fault_diagnosis` 意图，调用 `kb_grounded_qa`：
   - 召回 `fault_codes` 命中 AX-203（伺服过流）
   - 召回 `maintenance_logs` 同型号历史相似工单 2 条
3. 助手返回处置步骤 + 引用证据。
4. 用户点 **"保存为成果"** → 生成 `recommendation` 类型业务成果（决策卡片视图）。
5. 一周复盘时输入："**汇总上周停机时长超过 30 分钟的事件并出报告**" → 走 `downtime_analysis` 意图 → 生成 `report` 成果（报告视图，含摘要/章节/图表占位）。

## 六、版本与负责人

- **版本**：v1.0.0（首发）
- **状态**：灰度中（建议先在 1~2 个工厂试点）
- **负责人**：智能制造方案组
- **回滚**：删除 `packages/catalog/industry.mfg_maintenance.json` 即可下线，租户配置会自动回退到默认主包。
