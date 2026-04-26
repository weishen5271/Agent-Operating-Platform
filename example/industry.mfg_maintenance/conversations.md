# 样例对话 · 制造业设备运维助手

将以下问句直接粘到 `/chat`，验证业务包是否正确激活与召回。每个问句后标注期望命中的意图与知识源。

## 一、知识问答（knowledge_query）

> CNC-650 主轴轴承更换的扭矩要求是多少？

- 期望意图：`knowledge_query`
- 期望召回：`equipment_sop` → SOP-CNC-轴承更换
- 期望要点："80 → 120 → 150 N·m 三段式"

> 注塑机出现黑点应该怎么清洗料筒？

- 期望意图：`knowledge_query`
- 期望召回：`equipment_sop` → SOP-注塑机-料筒清洁
- 期望要点：清洗料、降温清洗法、判定标准

## 二、故障诊断（fault_diagnosis）

> 3 号注塑机昨晚报 AX-203 报警，怎么处理？

- 期望意图：`fault_diagnosis`
- 期望召回：`fault_codes` AX-203 + `maintenance_logs` MWO-2025-1142、1188
- 期望成果保存类型：`recommendation`（决策卡片）

> 主轴振动 5 mm/s 持续报警，可能是什么原因？

- 期望意图：`fault_diagnosis`
- 期望召回：MWO-2025-1273 + SOP-CNC-轴承更换
- 期望要点：列出可能原因（轴承磨损、预紧力、动平衡）+ 建议下一步

## 三、备件采购（procurement_draft）

> 帮我起草一份 NSK 7014C P4 轴承的采购申请，2 套。

- 期望意图：`procurement_draft`
- 期望调用：`spare_parts.catalog` 插件查询库存
- 期望成果保存类型：`action_plan`

## 四、保养计划（maintenance_plan）

> 给 CNC 加工中心制定一份月度预防性保养计划。

- 期望意图：`maintenance_plan`
- 期望召回：多份 SOP
- 期望成果保存类型：`report`

## 五、停机分析（downtime_analysis）

> 汇总 2025 Q4 AX-203 类故障，分析根因并给出改善建议。

- 期望意图：`downtime_analysis`
- 期望召回：`maintenance_logs` 全量 + `fault_codes` AX-203
- 期望成果：报告（含 Q4 统计、占比、改善行动）

---

## 验证 RAG 隔离

将主行业包切换为别的（如 `industry.hr`）后，再问"AX-203 怎么处理？"，应该**召回不到** `fault_codes`，回答会回退到通用知识；切回 `industry.mfg_maintenance` 后能再次命中。可用此验证业务包-知识源隔离生效。
