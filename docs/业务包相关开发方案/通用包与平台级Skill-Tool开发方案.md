# 通用包与平台级 Skill / Tool 开发方案

**版本**: v1.0
**日期**: 2026-04-26
**状态**: 草案
**关联文档**:
- [可扩展Agent架构-技术开发文档.md](可扩展Agent架构-技术开发文档.md)
- [行业业务包-通用开发方案.md](行业业务包-通用开发方案.md)
- [插件开发指南.md](插件开发指南.md)

---

## 目录

1. [文档目标与读者](#1-文档目标与读者)
2. [三类通用资产的定位](#2-三类通用资产的定位)
3. [平台内置 Tool](#3-平台内置-tool)
4. [平台级 Skill（`_platform` 包）](#4-平台级-skill_platform-包)
5. [通用业务包（`_common`）](#5-通用业务包_common)
6. [装配与运行时](#6-装配与运行时)
7. [治理一致性](#7-治理一致性)
8. [开发与发布流程](#8-开发与发布流程)
9. [评估与回归](#9-评估与回归)
10. [接入到现有仓库](#10-接入到现有仓库)
11. [开发清单](#11-开发清单)
12. [常见问题与设计取舍](#12-常见问题与设计取舍)

---

## 1. 文档目标与读者

### 1.1 目标

回答四个问题：

1. 平台层的 Tool、Skill、通用业务包分别放在哪、归谁维护？
2. 它们如何被任意行业包引用，又怎么不被行业包污染？
3. 装配时它们和行业包如何合并成 Planner 的候选池？
4. 怎么保证通用资产升级不打破任何已上线的行业包？

### 1.2 读者

| 角色 | 关注点 |
|------|------|
| 平台团队 | 全文，重点 §3、§4、§7、§8 |
| 通用包负责人 | §5、§8、§9 |
| 行业包负责人 | §2、§6、§12（如何正确引用） |
| 业务方与产品 | §2、§5（哪些通用能力可直接用） |

### 1.3 与既有文档的关系

[行业业务包通用方案](行业业务包-通用开发方案.md) §5 引入了 Capability / Tool / Skill 三种动作单位，但只讨论了行业包**自带的**私有 Skill。本文专门讲**跨行业可复用**的那部分——平台 Tool、平台 Skill、通用业务包——它们的位置、维护方式、装配方式与治理。

---

## 2. 三类通用资产的定位

### 2.1 三层结构

```text
平台内置 Tool        →  apps/api/src/agent_platform/tools/    （平台代码，随版本发布）
平台级 Skill         →  packages/_platform/skills/             （配置仓库，可热更新）
通用业务包           →  packages/_common/<name>/               （和行业包同构，domain=common）
```

| 维度 | 平台 Tool | 平台 Skill | 通用业务包 |
|------|------|------|------|
| 物理形态 | 代码 | yaml | yaml + skills + prompts |
| 是否调外部系统 | 否（少量例外，如 `web.fetch`） | 否（间接通过 capability） | 是（通过自带或共享插件） |
| 副作用 | 无 / 极弱 | 取决于内部 capability | 可有（写操作走草稿+审批） |
| 状态 | 无状态 | 无状态 | 与会话 / 草稿 / 审批关联 |
| 维护方 | 平台团队 | 平台团队 | 平台团队或行业方案团队 |
| 租户启用 | 平台级开关 | 默认对所有业务包可见 | 租户显式启用 |
| 升级 | 平台版本 | yaml 版本 + 灰度 | 业务包发布流程 |
| 例子 | `text.summarize`、`time.diff` | `kb_grounded_qa`、`document_summarize` | `hr_general`、`meeting_assistant`、`it_helpdesk`、`kb_qa` |

### 2.2 选哪一层？三条判别规则

1. **能不能 yaml 写完？写完是不是稳定？** 是 → 考虑 Skill；否 → 看下一条。
2. **是否需要调外部系统、有副作用、要审批？** 是 → 通用业务包（含自带插件）；否 → 看下一条。
3. **是不是稳定的纯计算 / 文本 / 格式化？** 是 → 平台 Tool。

错误倾向：

- 把"几行胶水 + 几个 capability"做成新插件 → 应做成 Skill
- 把"调外部系统的写操作"塞进 Skill → 必须做成 Capability
- 把"行业专属业务"放进通用包 → 拆回行业包

---

## 3. 平台内置 Tool

### 3.1 适用范围

Tool 是**原子的、无状态的、跨所有业务的小工具**，特点：

- 实现稳定、变更频率低
- 没有外部业务系统依赖
- 所有租户共享一份实现
- 不涉及业务规则与审批

不适合做 Tool：

- 调用客户内部系统（应做 Capability）
- 涉及金额、人员、合同等业务实体（应做 Capability 或 Skill）
- 实现频繁变更（应做 Skill 让它走 yaml 热更新）

### 3.2 标准目录

```text
apps/api/src/agent_platform/tools/
├── __init__.py
├── base.py                  # BaseTool 基类、ToolDefinition dataclass
├── registry.py              # ToolRegistry，启动时全量注册
├── text/
│   ├── summarize.py
│   ├── translate.py
│   └── extract.py
├── time/
│   └── time_ops.py          # time.now / time.parse / time.diff
├── math/
│   └── calc.py
├── unit/
│   └── convert.py
├── code/
│   └── sandbox.py           # 高风险，默认关闭
├── web/
│   └── fetch.py             # 高风险，默认关闭，受白名单
└── image/
    ├── ocr.py
    └── describe.py
```

### 3.3 Tool 实现规范

每个 Tool 一个文件，自带定义：

```python
# tools/text/summarize.py
from agent_platform.tools.base import BaseTool, ToolDefinition

class TextSummarizeTool(BaseTool):
    definition = ToolDefinition(
        name="text.summarize",
        version="1.0.0",
        description="对给定文本生成摘要",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "max_chars": {"type": "integer", "default": 200},
                "language": {"type": "string", "default": "zh"},
            },
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
        side_effect="read",
        risk_level="low",
        idempotent=True,
        cost_hint="low",
        category="text",
    )

    async def invoke(self, payload: dict, ctx) -> dict:
        ...
```

强约束：

- `name` 全局唯一，遵循 `<category>.<verb>` 命名
- `side_effect` 默认 `read`；`web.fetch`、`code.run_sandbox` 等显式声明
- `idempotent=True` 是默认期望；非幂等的 Tool 必须显式标记并通过额外审核
- 不允许 Tool 内部直接读写平台核心表
- 不允许 Tool 调用 capability（要组合就做 Skill）

### 3.4 ToolRegistry

```python
# tools/registry.py
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.definition.name] = tool

    def list_all(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def get(self, name: str) -> BaseTool:
        return self._tools[name]

    async def invoke(self, name: str, payload: dict, ctx) -> dict:
        tool = self.get(name)
        ctx.audit.note(tool=name, version=tool.definition.version)
        return await tool.invoke(payload, ctx)
```

启动时扫描 `tools/` 目录，把所有 `BaseTool` 子类自动注册。

### 3.5 平台级配置（启用与配额）

不是每个 Tool 都开放给所有租户。`configs/tools.yaml` 是平台基线：

```yaml
tools:
  text.summarize:    { enabled: true, default_for_all_packages: true }
  text.translate:    { enabled: true, default_for_all_packages: true }
  text.extract:      { enabled: true, default_for_all_packages: true }
  time.now:          { enabled: true, default_for_all_packages: true }
  time.diff:         { enabled: true, default_for_all_packages: true }
  math.calc:         { enabled: true, default_for_all_packages: true }
  unit.convert:      { enabled: true, default_for_all_packages: true }

  code.run_sandbox:
    enabled: true
    default_for_all_packages: false
    require_explicit_optin: true
    quota_per_tenant_day: 1000
    cpu_ms_per_call: 2000

  web.fetch:
    enabled: true
    default_for_all_packages: false
    require_explicit_optin: true
    domain_whitelist:
      - "*.gov.cn"
      - "wikipedia.org"

  image.ocr:
    enabled: true
    default_for_all_packages: false
    cost_hint: external_paid
```

业务包要使用非默认 Tool 时，在自己的 `capability-map.yaml` 显式列出：

```yaml
tools:
  - text.summarize
  - web.fetch          # 高风险，必须显式 opt-in
```

`PackageLoader` 装配时校验：业务包用了非默认 Tool 但未显式声明 → 装配失败。

### 3.6 租户级覆盖

某些租户出于合规/安全要求需要彻底关闭某 Tool，租户配置可覆盖：

```yaml
# 租户配置
tool_overrides:
  web.fetch: { enabled: false }
  code.run_sandbox: { quota_per_tenant_day: 0 }
```

平台 Tool 优先级：**租户覆盖 > 平台基线 > 业务包白名单**。

---

## 4. 平台级 Skill（`_platform` 包）

### 4.1 定位

平台级 Skill 是"全行业都用得上的 yaml 编排剧本"，例如：

- `kb_grounded_qa`：强引用知识问答（接 `knowledge.search` + 引用拼装）
- `document_summarize`：长文档分段摘要再合并
- `form_extract`：按 schema 抽取表单字段
- `translate_document`：保留格式的文档翻译
- `data_diff_explain`：两组数据差异自然语言解释
- `meeting_minutes`：会议纪要生成
- `safe_math_solve`：分步数学求解

它们和行业 Skill 的区别：**任何行业包都能直接引用，不需要租户启用**。

### 4.2 目录结构

```text
packages/_platform/
├── package.yaml             # domain: platform，由平台官方维护
├── skills/
│   ├── kb_grounded_qa.yaml
│   ├── document_summarize.yaml
│   ├── form_extract.yaml
│   ├── translate_document.yaml
│   ├── data_diff_explain.yaml
│   ├── meeting_minutes.yaml
│   └── safe_math_solve.yaml
├── prompts/                 # skill 共用的提示词模板
│   └── grounded_answer.txt
├── evals/                   # 平台级回归评估集
│   ├── kb_grounded_qa.yaml
│   ├── document_summarize.yaml
│   └── ...
└── README.md
```

### 4.3 `package.yaml`

```yaml
package:
  name: _platform
  display_name: 平台级通用 Skill
  version: 1.4.0
  domain: platform
  description: 平台官方维护的跨行业通用 Skill，所有业务包默认可引用
  visibility: built_in        # 不需要 tenant_package_release
  entry_intents: []           # 不通过意图入口暴露，只对外暴露 skill

skills_export:
  - kb_grounded_qa
  - document_summarize
  - form_extract
  - translate_document
  - data_diff_explain
  - meeting_minutes
  - safe_math_solve

evals:
  suites:
    - evals/kb_grounded_qa.yaml
    - evals/document_summarize.yaml
```

### 4.4 与普通业务包的区别

| 维度 | 普通业务包 | `_platform` |
|------|------|------|
| 维护方 | 行业方案 / 客户团队 | 平台团队 |
| 是否绑定租户 | `tenant_package_release` | 否，**所有租户默认可见** |
| `entry_intents` | 有 | 无 |
| 灰度 | 业务包级 | **单 skill 灰度**（fine-grained） |
| 评估集 | 业务包级 | 平台级回归套件 |
| 升级 | 客户验收后发布 | 平台版本 + 全行业回归 |

### 4.5 Skill 引用语法

业务包 `capability-map.yaml`：

```yaml
intent_to_capabilities:
  policy_qa:
    sequence:
      - skill: kb_grounded_qa@_platform        # 显式平台 skill
        input:
          query: $message.text
          spaces: [policy_docs, regulation]
      - skill: fault_triage                     # 不带 @ 默认本包私有
      - skill: hr_leave_apply@_common/hr_general # 通用包 skill
```

引用语法：

| 写法 | 含义 |
|------|------|
| `skill_name` | 本业务包 `skills/` 下的私有 skill |
| `skill_name@_platform` | 平台级 skill |
| `skill_name@_common/<package>` | 通用业务包提供的 skill |

### 4.6 平台 Skill 的强约束

- **不依赖任何行业包**：可调用的只有平台 Tool + 平台标准 Capability（如 `knowledge.search`、`memory.write`）
- **不能调用某行业插件的 capability**（如 `eam.workorder.draft.create`）
- **输入输出 schema 必须稳定**：破坏性变更需要新版本号
- **必须可降级**：`kb_grounded_qa` 在 `knowledge.search` 不可用时返回明确错误，不静默回退到模型自由生成
- **必须有评估集**：每个 skill 配套 `evals/<skill>.yaml`，每次升级回归

### 4.7 平台 Skill 示例：`kb_grounded_qa`

```yaml
# packages/_platform/skills/kb_grounded_qa.yaml
skill:
  name: kb_grounded_qa
  version: 1.2.0
  description: 在指定知识空间内做强引用问答，无依据时拒答而非编造
  inputs:
    query:    { type: string, required: true }
    spaces:   { type: array<string>, required: true }
    top_k:    { type: integer, default: 6 }
    language: { type: string, default: zh }
  outputs:
    answer:    { type: string }
    sources:   { type: array }
    confidence:{ type: number }

steps:
  - id: rewrite
    tool: text.summarize
    input:
      text: $inputs.query
      max_chars: 80

  - id: retrieve
    capability: knowledge.search
    input:
      query: $rewrite.summary
      spaces: $inputs.spaces
      top_k: $inputs.top_k

  - id: ground_check
    tool: text.extract
    input:
      schema: grounding_score_schema
      source: $retrieve.matches

  - id: compose
    capability: model.generate
    input:
      prompt_template: prompts/grounded_answer.txt
      context:
        query: $inputs.query
        sources: $retrieve.matches
        grounding: $ground_check.score
      refuse_when:
        - grounding.score < 0.4

outputs_mapping:
  answer:     $compose.text
  sources:    $retrieve.matches
  confidence: $ground_check.score
```

---

## 5. 通用业务包（`_common`）

### 5.1 定位

通用业务包是**和行业业务包同构的装配单元**，差别只是它面向"跨行业的通用业务"：

| 包 | 服务对象 | 典型场景 |
|------|------|------|
| `kb_qa` | 所有租户 | 强引用的企业知识库问答 |
| `hr_general` | 所有公司类租户 | 假期、入离职、证明开具草稿 |
| `it_helpdesk` | 所有公司类租户 | 重置密码、报修、权限申请草稿 |
| `meeting_assistant` | 所有租户 | 会议纪要、待办抽取、跟进提醒 |
| `finance_general` | 所有公司类租户 | 报销、发票核验、预算查询 |

### 5.2 目录结构

和行业包完全一致：

```text
packages/_common/<name>/
├── package.yaml             # domain: common
├── capability-map.yaml
├── knowledge-bindings.yaml
├── approval_policy.yaml
├── skills/
├── prompts/
├── evals/
└── README.md
```

并通过自带的插件（如 `hr_general` 用 `it_general_hrms` 插件）接外部系统。

### 5.3 与行业包的差异

| 维度 | 行业包 | 通用包 |
|------|------|------|
| `domain` | `manufacturing` / `finance` / ... | `common` |
| 启用方式 | 租户显式启用 | 租户显式启用 |
| 多包并存 | 一般一个会话主导一个 | **可与行业包同时启用** |
| 入口意图 | 行业专属意图 | 通用意图（如 `meeting_minutes`、`reset_password`） |
| 评估集 | 行业评估集 | 跨租户通用评估集 |

通用包**不是**默认启用的，仍需在租户层 `tenant_package_release` 中显式发布。和行业包的区别在于"语义角色"——它是"横向叠加"，不是"主业务"。

### 5.4 多包路由

一个租户可同时启用 `mfg_equipment_ops` + `hr_general` + `meeting_assistant`。Supervisor 的意图分类按以下优先级：

```text
1. 用户在工作台显式切换的业务包优先
2. 否则按所有已启用包的 entry_intents 做匹配
3. 行业包匹配置信度 ≥ 阈值 → 走行业包
4. 行业包未匹配 → 尝试通用包
5. 都不命中 → 兜底 kb_qa 或通用知识问答
```

冲突意图（如多个包都声明了 `policy_qa`）必须在 `package.yaml` 中带行业前缀避免歧义：

```yaml
entry_intents:
  - mfg.policy_qa            # 行业包
```

```yaml
entry_intents:
  - common.policy_qa         # 通用包
```

### 5.5 通用包的写操作治理

通用包有自己的写操作（如 HR 起草请假单、IT 申请权限、会议生成纪要发到企业微信），治理与行业包一致：

- 写操作必须草稿 + 用户确认 / 审批
- `approval_policy.yaml` 在通用包中独立维护
- 不因为"通用"就放宽审批

---

## 6. 装配与运行时

### 6.1 加载顺序

平台启动时 `PackageLoader` 按以下顺序加载：

```text
1. 平台 Tool（代码扫描 tools/）
2. 平台 Skill（_platform，无需 tenant_release）
3. 通用业务包（_common/*，按 tenant_release 启用）
4. 行业业务包（packages/<industry>/*，按 tenant_release 启用）
```

每一层只能引用前面层的资产，不能反向依赖。这保证：

- 平台 Tool 不依赖 Skill
- 平台 Skill 不依赖任何业务包
- 通用包不依赖行业包
- 行业包可引用所有上面层

### 6.2 候选池计算

`PackageLoader` 在为某次请求装配 `RuntimeView` 时：

```text
候选 Capability =
   行业包 capability-map.include
 + 已启用通用包 capability-map.include
 - 用户 scope 过滤后

候选 Tool =
   ToolRegistry 中 default_for_all_packages=true 的
 + 业务包 capability-map.tools 显式列出的
 - 平台 tools.yaml 中 enabled=false 的
 - 租户 tool_overrides 关闭的
 - 配额 / 域名白名单约束后

候选 Skill =
   行业包 skills/*.yaml
 + _platform/skills/*.yaml （所有租户默认可用）
 + 已启用通用包 skills/*.yaml
```

### 6.3 装配 Trace

每次请求 Trace 增加 `package_assembled` 步骤，记录：

```json
{
  "step": "package_assembled",
  "active_packages": ["mfg_equipment_ops@1.0.0", "hr_general@1.1.0"],
  "platform_skills_visible": 7,
  "tools_available": ["text.summarize", "time.diff", "math.calc"],
  "tools_disabled_by_tenant": ["web.fetch"]
}
```

便于审计"为什么这次只能用这些动作"。

### 6.4 运行时调用

Supervisor 调用统一接口：

```python
result = runtime.invoke_action(
    action_type="capability" | "tool" | "skill",
    name="erp.spare.stock.query" | "text.summarize" | "kb_grounded_qa@_platform",
    payload={...},
    ctx=request_ctx,
)
```

`runtime` 内部根据 `action_type` 路由到对应注册中心，但 Trace、审计、限流都在统一入口处理。

---

## 7. 治理一致性

无论资产来自哪一层，治理规则相同。

### 7.1 Trace 与审计

- 所有 Tool / Skill 调用进 Trace
- Skill 调用产生父 step，内部 capability / tool 是子 step
- 审计台支持按"业务包来源"过滤（行业包 / 通用包 / 平台）

### 7.2 限流与配额

- Tool 默认全局限流；高风险 Tool 可设租户日配额
- Skill 不单独限流（透传到内部 capability）
- 通用包写操作走业务包级配额

### 7.3 安全红线

- 平台 Tool 输出走 OutputGuard，被业务包的红线规则覆盖
- 平台 Skill 内部 capability 调用受租户 scope 过滤；用户没权限时 Skill 整体失败而非静默跳过
- 高风险 Tool（`code.run_sandbox`、`web.fetch`）必须有专门的安全扫描

### 7.4 跨租户隔离

- 平台 Tool 实现是单例共享的，但每次调用的 `ctx` 强制带 `tenant_id`
- 平台 Skill 内部检索 / 记忆调用必须带租户过滤
- 通用包数据严格按租户隔离，**通用 ≠ 跨租户共享**

### 7.5 灰度

- 平台 Tool：随平台版本灰度
- 平台 Skill：**单 skill 灰度**（同一个 skill 多版本并存，按租户百分比切流）
- 通用包：业务包级灰度

---

## 8. 开发与发布流程

### 8.1 平台 Tool 发布流程

```text
1. 写实现 + 自带 ToolDefinition
2. 单元测试 + 安全审查（特别是 web/code 类）
3. 提 PR → 平台代码评审
4. 合入主干 → 随平台版本发布
5. configs/tools.yaml 配置启用与配额基线
```

破坏性变更必须新建 Tool（如 `text.summarize.v2`），旧版本至少保留一个发布周期。

### 8.2 平台 Skill 发布流程

```text
1. 在 packages/_platform/skills/ 写 yaml
2. 写评估集 evals/<skill>.yaml
3. 跑全行业回归（在所有引用此 skill 的业务包上跑评估）
4. 平台团队评审
5. 灰度发布（10% → 50% → 100%）
6. 自动回滚条件：评估集劣化 > 5% 或点踩率上涨
```

### 8.3 通用包发布流程

走与行业包一致的流程（参见 [行业业务包通用方案](行业业务包-通用开发方案.md) §6），区别：

- 评估集要覆盖**多类租户**（金融/制造/政务都要测）
- 灰度阶段需选择跨行业的客户验证
- 升级要做"行业包向后兼容"声明

### 8.4 版本与依赖

业务包 `package.yaml` 引用版本范围：

```yaml
dependencies:
  platform_skills:
    - name: kb_grounded_qa
      version: ">=1.0.0,<2.0.0"
    - name: document_summarize
      version: ">=1.2.0,<2.0.0"
  common_packages:
    - name: hr_general
      version: ">=1.0.0,<2.0.0"
```

`PackageLoader` 启动时校验依赖版本，不满足直接拒绝装配。

---

## 9. 评估与回归

### 9.1 平台 Tool 评估

每个 Tool 有自己的小评估集，重点：

- 输入输出 schema 一致性
- 边界（空、超长、特殊字符）
- 性能（P95 时延）
- 安全（注入、越界、非法 URL）

### 9.2 平台 Skill 评估

每个 Skill 一份独立评估集 `evals/<skill>.yaml`：

- 黄金样本：标准输入 → 期望输出片段（不要求完全一致）
- 引用率：必须从 `sources` 引用支持答案
- 拒答能力：无依据时是否正确拒答
- 跨行业样本：医疗、金融、制造各 10-20 条

### 9.3 全行业回归

平台 Skill / 通用包升级时跑"行业回归"：

```text
对每个引用此资产的业务包：
  跑该业务包的核心评估集 → 对比基线
  劣化超阈值 → 阻断发布
```

回归失败的直接表现：制造业故障处置剧本因 `text.extract` 升级而引用率下降 → 不允许发布。

### 9.4 评估目录约定

```text
packages/_platform/evals/
├── kb_grounded_qa/
│   ├── golden.yaml             # 通用样本
│   ├── refusal.yaml            # 拒答样本
│   └── multi_industry.yaml     # 跨行业样本
└── document_summarize/
    └── golden.yaml
```

---

## 10. 接入到现有仓库

落到当前仓库 `agent-platform/`：

### 10.1 新增目录骨架

```text
agent-platform/
├── apps/api/src/agent_platform/
│   ├── tools/                            # 新增
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── text/
│   │   │   ├── summarize.py
│   │   │   ├── translate.py
│   │   │   └── extract.py
│   │   ├── time/
│   │   │   └── time_ops.py
│   │   ├── math/
│   │   │   └── calc.py
│   │   └── unit/
│   │       └── convert.py
│   └── runtime/
│       ├── package_loader.py             # 新增
│       └── tool_registry.py              # 新增
├── configs/
│   └── tools.yaml                        # 新增
└── packages/
    ├── _platform/
    │   ├── package.yaml                  # 新增
    │   ├── skills/
    │   │   └── kb_grounded_qa.yaml
    │   ├── prompts/
    │   ├── evals/
    │   └── README.md
    └── _common/
        ├── kb_qa/
        │   └── package.yaml
        ├── hr_general/
        ├── it_helpdesk/
        └── meeting_assistant/
```

### 10.2 与现有代码衔接

| 改造点 | 文件 | 动作 |
|------|------|------|
| Tool 注册 | `apps/api/src/agent_platform/tools/registry.py` (新) | 启动时扫描 + 注册 |
| Package 加载 | `runtime/package_loader.py` (新) | 按层加载 `_platform / _common / 行业包` |
| Capability Registry 改造 | `runtime/registry.py` | 由硬编码改为按 package 装载 |
| Supervisor | `runtime/chat_service.py` | 注入候选池（capability + tool + skill） |
| 配置加载 | `bootstrap/` | 加载 `configs/tools.yaml` |

### 10.3 实施顺序建议

```text
第一阶段（2 周）：底座
  - 实现 BaseTool / ToolRegistry
  - 实现 5 个最常用 Tool: text.summarize / text.extract / time.diff / math.calc / unit.convert
  - 写 configs/tools.yaml

第二阶段（2 周）：_platform
  - 创建 packages/_platform/ 骨架
  - 实现 kb_grounded_qa Skill（替换当前 chat_service 的检索回答逻辑）
  - 写评估集

第三阶段（3 周）：第一个通用包
  - 选 kb_qa 或 meeting_assistant 作为首个通用包
  - 走完整发布流程作为模板

第四阶段：行业包接入
  - 制造业业务包改造为引用 kb_grounded_qa 替换内嵌逻辑
  - 验证全链路装配
```

---

## 11. 开发清单

### 11.1 平台 Tool 必交付

- [ ] `tools/<category>/<name>.py` 实现
- [ ] `ToolDefinition` 完整声明
- [ ] 单元测试（schema、边界、性能）
- [ ] 安全审查（特别是 web/code/file 类）
- [ ] `configs/tools.yaml` 启用配置
- [ ] README 段落（在 `tools/README.md` 维护工具索引）

### 11.2 平台 Skill 必交付

- [ ] `packages/_platform/skills/<name>.yaml`
- [ ] 提示词模板（如需）`packages/_platform/prompts/<name>.txt`
- [ ] 评估集 `packages/_platform/evals/<name>/`
  - [ ] golden.yaml
  - [ ] refusal.yaml（如适用）
  - [ ] multi_industry.yaml
- [ ] 全行业回归通过
- [ ] 灰度发布配置
- [ ] CHANGELOG 条目

### 11.3 通用包必交付

完全等同行业包，参考 [行业业务包通用方案](行业业务包-通用开发方案.md) §11，额外要求：

- [ ] 多行业评估集（金融/制造/政务各 ≥ 20 条）
- [ ] 行业兼容性声明（`package.yaml` 中显式列出已验证行业）
- [ ] 与既有行业包的冲突意图声明

---

## 12. 常见问题与设计取舍

### 12.1 为什么 Tool 是代码、Skill 是 yaml？

- **Tool 实现稳定**，频繁热更没意义；走代码可以做静态类型、性能优化、安全审计
- **Skill 是编排**，需要快速迭代、灰度、回滚；yaml 可以热更新而不发版

如果某个 Tool 频繁变更，那它可能不该是 Tool，而是几个更小 Tool + 一个 Skill。

### 12.2 平台 Skill 能否调用行业 Capability？

**不能**。平台 Skill 只能调用平台 Tool 和**平台标准 Capability**（如 `knowledge.search`、`memory.read`、`model.generate`）。否则平台 Skill 就和某行业绑死了。

如果业务上需要"通用模式 + 行业特化"，做法是：

- 平台 Skill 暴露 hook 输入参数
- 行业包在调用时传入行业特定参数

### 12.3 通用包和行业包冲突时听谁的？

按用户上下文：

- 用户显式切换了业务包 → 听用户
- 否则按意图匹配置信度
- 通用包入口意图必须带 `common.` 前缀，避免与行业意图同名歧义

### 12.4 通用包能否被某行业"魔改"？

不可以。如果某行业需要不一样的 HR 流程，应该：

- 在自己行业包里写一个私有 skill，覆盖通用流程
- 而不是 fork 通用包

平台禁止租户级修改通用包 yaml，避免维护噩梦。

### 12.5 平台 Skill 升级会打破行业包吗？

不会，前提是遵守版本规则：

- minor 升级保证向后兼容（输入输出 schema 不变）
- major 升级必须新建版本号，旧版本至少保留一个发布周期
- 全行业回归通过才允许发布

行业包通过版本范围 `">=1.0.0,<2.0.0"` 锁定大版本。

### 12.6 哪些 Tool 应该立刻做？

按价值优先级：

```text
P0（先做）：
  - text.summarize / text.extract / time.diff / math.calc / unit.convert

P1（第二批）：
  - text.translate / time.parse / image.ocr

P2（受控开放）：
  - web.fetch (白名单) / code.run_sandbox

P3（按需）：
  - image.describe / 其他垂直工具
```

### 12.7 通用包从哪个开始做？

推荐顺序：

1. **`kb_qa`** —— 最低风险，纯查询，几乎所有客户都要
2. **`meeting_assistant`** —— 跨行业刚需，写操作仅限草稿
3. **`it_helpdesk`** —— 公司类客户必备
4. **`hr_general`** —— 接 HR 系统，复杂度高，留到后期

---

**结语**

本平台的资产分层信念：

> **代码沉淀稳定，配置沉淀编排，业务包沉淀场景。**

- 平台 Tool 代表"稳定能力"，写在代码里
- 平台 / 通用 Skill 代表"可复用编排"，写在 yaml 里
- 行业 / 通用业务包代表"场景闭环"，写在装配单元里

三层各司其职，新行业接入时绝大多数情况下**只需要做装配 + 加私有 skill + 接行业插件**，不重复造平台 Tool，也不重复写跨行业的通用流程。这是平台规模化扩展的核心。

下一步建议：

1. 实现 `BaseTool / ToolRegistry` 与 5 个 P0 Tool（约 2 周）
2. 创建 `packages/_platform/` 骨架，把现有 `chat_service` 中的"检索 + 引用拼装"提炼为 `kb_grounded_qa` Skill
3. 选 `kb_qa` 作为第一个通用包跑通发布流程，作为后续通用包的模板
