# 可扩展Agent架构 - 通用能力模块化方案

**版本**: v1.1
**日期**: 2026-04-18
**状态**: 正式版（增强版）

---

## 目录

1. [设计理念](#1-设计理念)
2. [整体架构](#2-整体架构)
3. [核心模块设计](#3-核心模块设计)
4. [通用能力模块](#4-通用能力模块)
5. [行业插件模块](#5-行业插件模块)
6. [插件化框架](#6-插件化框架)
7. [企业场景实现](#7-企业场景实现)
8. [开发规范](#8-开发规范)
9. [运行时与安全治理](#9-运行时与安全治理)
10. [评估与回归体系](#10-评估与回归体系)
11. [部署拓扑与伸缩策略](#11-部署拓扑与伸缩策略)

---

## 1. 设计理念

### 1.1 核心原则

```
┌─────────────────────────────────────────────────────────────────┐
│                      设计原则                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 通用能力下沉                                                │
│     - 记忆、推理、检索等通用能力抽取为底层模块                   │
│     - 行业相关逻辑在上层实现                                     │
│                                                                  │
│  2. 插件化架构                                                  │
│     - 能力模块可插拔                                             │
│     - 新行业/场景只需添加插件                                   │
│     - 核心框架保持稳定                                           │
│                                                                  │
│  3. 可定制开发                                                  │
│     - 模块之间通过接口通信                                       │
│     - 可按需替换默认实现                                         │
│     - 支持二次开发                                               │
│                                                                  │
│  4. 层级隔离                                                    │
│     - 底层框架不了解上层业务                                     │
│     - 上层插件不触及核心代码                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 层级架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          上层：行业/场景插件层                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  HR插件    │  │  法务插件   │  │  财务插件   │  │  客服插件   │       │
│  │            │  │            │  │            │  │            │       │
│  │ • 假期计算 │  │ • 合同审核 │  │ • 报表生成 │  │ • 问答处理 │       │
│  │ • 组织查询 │  │ • 风险识别 │  │ • 预算审核 │  │ • 工单流转 │       │
│  │ • 政策解读 │  │ • 合规检查 │  │ • 发票核验 │  │ • 知识库   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          中层：Agent编排层                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Supervisor Agent                                  │   │
│  │  • 意图理解    • 任务分解    • 结果整合    • 自我纠错               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                     │
│  ┌────────────────────────────────────┼────────────────────────────────────┐ │
│  │                    Plugin Protocol Layer                             │ │
│  │              (插件协议层 - 标准化的插件调用接口)                      │ │
│  └────────────────────────────────────┴────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          底层：通用能力模块层                                │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
│  │  Memory   │ │  Planner  │ │  Retriever│ │  Monitor  │ │  Storage  │   │
│  │           │ │           │ │           │ │           │ │           │   │
│  │ 记忆管理  │ │  任务规划 │ │  检索引擎 │ │  监控追踪 │ │  存储抽象 │   │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 模块分类

| 类别 | 模块 | 说明 | 可插拔 |
|------|------|------|--------|
| **通用能力** | Memory | 记忆存储与检索 | 是 |
| **通用能力** | Planner | 任务规划与分解 | 是 |
| **通用能力** | Retriever | 检索能力抽象 | 是 |
| **通用能力** | Monitor | 监控与追踪 | 是 |
| **通用能力** | Storage | 存储抽象层 | 是 |
| **行业插件** | HRPlugin | HR业务能力 | 否(业务层) |
| **行业插件** | LegalPlugin | 法务业务能力 | 否(业务层) |
| **行业插件** | FinancePlugin | 财务业务能力 | 否(业务层) |

---

## 2. 整体架构

### 2.1 模块关系图

```
                           ┌──────────────────┐
                           │   Supervisor     │
                           │   (调度中心)     │
                           └────────┬─────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │  Intent   │   │  Memory  │   │  Planner  │
            │  意图理解  │   │   记忆   │   │   规划   │
            └───────────┘   └───────────┘   └───────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │   Plugin Protocol     │
                         │   (插件协议层)       │
                         └──────────┬──────────┘
                                    │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│   HRPlugin    │          │ LegalPlugin   │          │ FinancePlugin │
│               │          │               │          │               │
│ • LeaveCalc   │          │ • Contract    │          │ • Report     │
│ • OrgQuery    │          │ • RiskDetect │          │ • Budget     │
│ • PolicySearch│          │ • Compliance  │          │ • Invoice    │
└───────────────┘          └───────────────┘          └───────────────┘
        │                            │                            │
        └────────────────────────────┼────────────────────────────┘
                                     │
                            ┌────────┴────────┐
                            │   Storage       │
                            │   (存储抽象)    │
                            └─────────────────┘
```

### 2.2 请求处理流程

```
用户: "张三的年假还剩几天？他想申请下周三到周五休假"

┌──────────────────────────────────────────────────────────────────────────┐
│                        处理流程                                          │
└──────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐
  │  1. Intent      │ ←── 输入: 自然语言query
  │     意图理解     │
  └────────┬────────┘
           │ IntentResult{type: "leave_request", entities: {...}}
           ▼
  ┌─────────────────┐
  │  2. Memory     │ ←── 查询会话上下文
  │     记忆查询    │
  └────────┬────────┘
           │ Context{employee_id: "zhangsan", ...}
           ▼
  ┌─────────────────┐
  │  3. Planner    │ ←── 生成执行计划
  │     任务规划    │
  └────────┬────────┘
           │ Plan{tasks: [Task1, Task2, Task3]}
           ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                    Plugin Protocol Layer                          │
  │                                                                  │
  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
  │  │ HRPlugin    │  │ HRPlugin    │  │ HRPlugin    │            │
  │  │ (LeaveBal)  │  │ (PolicyChk) │  │ (Validation)│            │
  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
  └─────────┼─────────────────┼─────────────────┼──────────────────────┘
            │                 │                 │
            ▼                 ▼                 ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                      结果整合                                      │
  └──────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────┐
  │  4. Memory     │ ←── 更新会话记忆
  │     记忆存储    │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  5. Response   │ →── 输出: 自然语言响应
  │     响应生成    │
  └─────────────────┘
```

---

## 3. 核心模块设计

### 3.1 模块接口定义

```python
# ============================================================
# 核心模块接口定义
# ============================================================
# 所有通用模块都实现统一的基础接口
# 采用Protocol（协议）而非抽象基类，实现更灵活
# ============================================================

from typing import Protocol, Any, Dict, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

# --------------------------------------------------------
# 基础数据结构
# --------------------------------------------------------

@dataclass
class Context:
    """会话上下文"""
    session_id: str
    user_id: str
    timestamp: float
    data: Dict[str, Any]

@dataclass
class IntentResult:
    """意图理解结果"""
    intent_type: str           # 意图类型
    confidence: float          # 置信度
    entities: Dict[str, Any]   # 提取的实体
    raw_query: str            # 原始query

@dataclass
class Plan:
    """执行计划"""
    task_id: str
    steps: List["Task"]
    metadata: Dict[str, Any]

@dataclass
class Task:
    """子任务"""
    task_id: str
    plugin_name: str           # 调用的插件名
    method_name: str           # 插件方法
    params: Dict[str, Any]     # 参数
    dependencies: List[str]    # 依赖的前置任务ID

@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    status: str                # success, failure, partial
    data: Any
    error: Optional[str] = None


# --------------------------------------------------------
# 通用模块接口定义
# --------------------------------------------------------

class IIntentClassifier(Protocol):
    """意图理解模块接口"""

    async def classify(self, query: str, context: Context) -> IntentResult:
        """
        分析用户query，返回意图结果

        Args:
            query: 用户输入
            context: 会话上下文

        Returns:
            IntentResult: 意图分析结果
        """
        ...

    async def get_supported_intents(self) -> List[str]:
        """获取支持的意图类型列表"""
        ...


class IMemory(Protocol):
    """记忆模块接口"""

    async def retrieve(self, key: str, context: Context) -> Optional[Any]:
        """
        根据key检索记忆

        Args:
            key: 记忆键
            context: 当前上下文

        Returns:
            记忆值，不存在返回None
        """
        ...

    async def store(self, key: str, value: Any, context: Context) -> None:
        """存储记忆"""
        ...

    async def search(self, query: str, context: Context, limit: int = 10) -> List[Any]:
        """
        语义搜索记忆

        Args:
            query: 搜索query
            context: 上下文
            limit: 返回数量

        Returns:
            相关记忆列表
        """
        ...


class IPlanner(Protocol):
    """规划模块接口"""

    async def plan(self, intent: IntentResult, context: Context) -> Plan:
        """
        根据意图生成执行计划

        Args:
            intent: 意图结果
            context: 上下文

        Returns:
            Plan: 执行计划
        """
        ...


class IRetriever(Protocol):
    """检索模块接口"""

    async def retrieve(
        self,
        query: str,
        context: Context,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        检索相关内容

        Args:
            query: 检索query
            context: 上下文
            top_k: 返回数量
            filters: 过滤条件

        Returns:
            检索结果列表
        """
        ...


class IStorage(Protocol):
    """存储模块接口"""

    async def get(self, key: str) -> Optional[Any]:
        ...

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def query(self, query: str, params: Dict[str, Any]) -> List[Any]:
        """执行查询"""
        ...


class IMonitor(Protocol):
    """监控模块接口"""

    async def log(self, event: str, data: Dict[str, Any]) -> None:
        """记录事件"""
        ...

    async def trace(self, operation: str, func, *args, **kwargs):
        """追踪操作"""
        ...

    async def metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        ...


# --------------------------------------------------------
# 插件接口定义
# --------------------------------------------------------

class IPlugin(Protocol):
    """插件基础接口"""

    @property
    def name(self) -> str:
        """插件名称"""
        ...

    @property
    def version(self) -> str:
        """插件版本"""
        ...

    @property
    def supported_intents(self) -> List[str]:
        """支持的意图类型"""
        ...

    async def initialize(self, config: Dict[str, Any]) -> None:
        """初始化插件"""
        ...

    async def execute(self, method: str, params: Dict[str, Any], context: Context) -> TaskResult:
        """
        执行插件方法

        Args:
            method: 方法名
            params: 参数
            context: 上下文

        Returns:
            TaskResult: 执行结果
        """
        ...

    async def health_check(self) -> bool:
        """健康检查"""
        ...
```

### 3.2 模块注册中心

```python
# ============================================================
# 模块注册中心 - ModuleRegistry
# ============================================================
# 功能:
#   1. 统一管理所有模块的注册与发现
#   2. 支持模块的热插拔
#   3. 提供模块的依赖注入
#
# 使用方式:
#   registry = ModuleRegistry()
#   registry.register(IntentClassifier, OpenAIIntentClassifier)
#   classifier = registry.get(IntentClassifier)
# ============================================================

from typing import Type, TypeVar, get_origin, get_args, Dict, List, Optional
import importlib

T = TypeVar('T')


class ModuleRegistry:
    """
    模块注册中心

    核心功能:
        1. 接口与实现的映射管理
        2. 单例/非单例模式支持
        3. 依赖注入
        4. 模块生命周期管理
    """

    def __init__(self):
        # 接口 -> 实现类 的映射
        self._implementations: Dict[Type, Type] = {}
        # 接口 -> 实例 的映射（单例模式）
        self._singletons: Dict[Type, Any] = {}
        # 模块配置
        self._configs: Dict[Type, Dict[str, Any]] = {}

    def register(
        self,
        interface: Type[T],
        implementation: Type[T],
        singleton: bool = True,
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        注册模块实现

        Args:
            interface: 接口类型（如IIntentClassifier）
            implementation: 实现类（如OpenAIIntentClassifier）
            singleton: 是否单例模式
            config: 模块配置
        """
        # 验证实现类是否实现了接口
        if not self._verify_implementation(interface, implementation):
            raise ValueError(
                f"{implementation.__name__} must implement {interface.__name__}"
            )

        self._implementations[interface] = implementation
        self._configs[interface] = config or {}

        # 如果是单例模式且已有实例，清除
        if interface in self._singletons:
            del self._singletons[interface]

    def get(self, interface: Type[T]) -> T:
        """
        获取模块实例

        Args:
            interface: 接口类型

        Returns:
            模块实例
        """
        if interface not in self._implementations:
            raise KeyError(f"No implementation registered for {interface.__name__}")

        impl_class = self._implementations[interface]
        config = self._configs.get(interface, {})

        # 单例模式
        if interface in self._singletons:
            return self._singletons[interface]

        # 创建实例（注入依赖）
        instance = self._create_instance(impl_class, config)

        # 如果配置为单例，缓存实例
        # 注意：这里简化了判断，实际需要从config中读取singleton设置
        self._singletons[interface] = instance

        return instance

    def get_all_implementations(self, interface: Type[T]) -> List[Type[T]]:
        """
        获取某个接口的所有实现类

        用于插件发现等场景
        """
        if interface not in self._implementations:
            return []
        return [self._implementations[interface]]

    def unregister(self, interface: Type[T]) -> None:
        """注销模块"""
        if interface in self._implementations:
            del self._implementations[interface]
        if interface in self._singletons:
            del self._singletons[interface]
        if interface in self._configs:
            del self._configs[interface]

    def _verify_implementation(self, interface: Type, implementation: Type) -> bool:
        """验证实现类是否实现了接口"""
        # 检查是否有@runtime_checkable装饰器
        if hasattr(interface, '__protocol_attrs__'):
            # Protocol类型，使用isinstance检查
            try:
                return isinstance(object(), interface)
            except:
                return True
        else:
            # 普通抽象基类
            return issubclass(implementation, interface)

    def _create_instance(self, impl_class: Type, config: Dict[str, Any]) -> Any:
        """
        创建模块实例

        支持依赖注入：
        - 检查构造函数参数类型
        - 自动从注册中心获取依赖的模块
        """
        import inspect

        # 获取构造函数签名
        sig = inspect.signature(impl_class.__init__)
        kwargs = {}

        for param_name, param in sig.parameters.items():
            # 跳过self
            if param_name == 'self':
                continue

            # 获取参数类型注解
            param_type = param.annotation

            # 如果参数有类型注解且在注册中心有实现，从注册中心获取
            if param_type != inspect.Parameter.empty:
                try:
                    kwargs[param_name] = self.get(param_type)
                except KeyError:
                    # 注册中心没有，使用默认值
                    if param.default != inspect.Parameter.empty:
                        kwargs[param_name] = param.default

        # 创建实例
        return impl_class(**kwargs)


# 全局注册中心实例
registry = ModuleRegistry()
```

### 3.3 能力契约与 Schema 治理

`v1.0` 中的 `Plugin Protocol Layer` 已经定义了统一入口，但在企业级落地时，统一入口还不足以保证稳定性。  
`v1.1` 增加“能力契约”约束，要求每个插件不仅能被调用，还必须以标准化方式声明“能做什么、如何调用、失败时怎么处理、是否有副作用”。

#### 设计目标

- 让 Planner 只基于已声明能力进行规划，减少 LLM 幻觉调用
- 让 Supervisor 在执行前即可完成参数校验、权限校验和风险识别
- 让插件升级具备兼容边界，避免方法签名漂移影响上层编排

#### 能力契约结构

```python
@dataclass
class CapabilitySpec:
    """插件能力声明"""
    capability_name: str               # 唯一能力名，如 hr.leave.balance.get
    method_name: str                   # 对应插件内部方法
    description: str                   # 能力描述
    input_schema: Dict[str, Any]       # JSON Schema / Pydantic Schema
    output_schema: Dict[str, Any]      # 输出结构Schema
    side_effect: str                   # none / read / write / external_action
    idempotent: bool                   # 是否幂等
    timeout_seconds: int               # 默认超时
    required_permissions: List[str]    # 调用所需权限
    tags: List[str]                    # 检索、审批、HR等标签
    version: str = "1.0.0"
```

#### 契约要求

1. 插件发布时必须声明 `CapabilitySpec`
2. Planner 只能从已注册能力中选择，不直接拼接任意 `method_name`
3. 所有输入在调用前必须经过 schema 校验
4. 输出需符合标准 schema，便于结果整合和评估
5. 写操作能力必须显式声明 `side_effect != none`

#### 推荐的调用流程

```text
Planner生成候选任务
    -> Capability Registry校验
    -> 参数Schema校验
    -> 权限检查
    -> 风险级别判断
    -> 执行插件
    -> 输出Schema校验
```

#### 版本兼容策略

- 插件版本用于发布管理
- 能力版本用于调用兼容控制
- 新增字段时优先向后兼容，避免直接修改既有必填参数
- 废弃能力需经历 `active -> deprecated -> removed` 三阶段

### 3.4 任务运行时语义

`v1.0` 已有 `Plan/Task/TaskResult` 结构，但缺少运行时策略定义。  
`v1.1` 增加任务状态机、重试策略、人工审批点和补偿机制，使平台具备可控的执行语义。

#### 扩展数据结构

```python
@dataclass
class TaskPolicy:
    """任务执行策略"""
    timeout_seconds: int = 30
    max_retries: int = 0
    retry_backoff_seconds: int = 0
    idempotency_key: Optional[str] = None
    requires_approval: bool = False
    compensation_action: Optional[str] = None


@dataclass
class Task:
    task_id: str
    plugin_name: str
    method_name: str
    params: Dict[str, Any]
    dependencies: List[str]
    policy: Optional[TaskPolicy] = None
    task_type: str = "read"           # read / write / approval_required
    priority: str = "normal"          # low / normal / high
```

#### 任务状态机

```text
pending
  -> ready
  -> running
  -> success
  -> failed
  -> partial
  -> waiting_approval
  -> cancelled
  -> compensated
```

#### 运行时约束

- `read` 类任务允许自动重试，但需限制最大次数
- `write` 类任务必须带幂等键，避免重复写入
- `approval_required` 类任务在执行前必须暂停并等待人工确认
- 依赖任务失败时，下游任务默认不执行，除非策略显式允许降级

#### 补偿机制

对于有副作用的操作，平台必须支持以下两类补偿策略之一：

- 业务补偿：例如撤销审批、恢复状态、回滚数据库记录
- 标记补偿：无法物理回滚时，写入审计记录并提示人工介入

### 3.5 上下文与权限边界

企业级 Agent 不能只依赖 `session_id` 和 `user_id`，还需要明确租户、角色和数据访问范围。  
因此 `v1.1` 将 `Context` 从“会话对象”升级为“执行上下文”。

#### 推荐上下文结构

```python
@dataclass
class Context:
    session_id: str
    user_id: str
    tenant_id: str
    org_id: Optional[str]
    role: str
    permissions: List[str]
    data_scope: Dict[str, Any]
    request_id: str
    timestamp: float
    data: Dict[str, Any]
```

#### 权限边界原则

- Planner 可以看到能力元数据，但不能绕过权限直接调用高风险能力
- Retriever 必须基于 `tenant_id` 与 `data_scope` 做过滤
- Memory 的长期记忆写入必须带来源和可见范围
- 所有写操作都必须记录 `request_id`、操作者和目标资源

#### 最小权限原则

- 插件默认仅拥有声明所需的最小能力
- 高风险插件不应直接获得底层数据库全表访问权限
- 推荐通过平台提供的受限工具访问业务系统，而不是让插件直接持有通用管理员凭据

---

## 4. 通用能力模块

### 4.1 记忆模块 (Memory)

```python
# ============================================================
# Memory模块 - 记忆管理
# ============================================================
# 功能:
#   1. 短期记忆 - 当前会话上下文
#   2. 长期记忆 - 跨会话积累的知识
#   3. 语义记忆 - 向量化的可检索记忆
#
# 实现类:
#   - InMemoryStore: 纯内存实现（开发测试用）
#   - RedisMemory: Redis存储（生产环境）
#   - HybridMemory: 混合存储（短期+长期）
# ============================================================


class BaseMemory(ABC):
    """
    记忆模块基类

    记忆类型:
        1. 短期记忆 (Short-term): 当前会话，当前对话窗口内
        2. 长期记忆 (Long-term): 跨会话积累
        3. 语义记忆 (Semantic): 向量化存储，支持语义检索
    """

    def __init__(self, vector_store: Optional[IRetriever] = None):
        self.vector_store = vector_store

    @abstractmethod
    async def get_short_term(self, session_id: str) -> Dict[str, Any]:
        """获取短期记忆"""
        pass

    @abstractmethod
    async def set_short_term(self, session_id: str, data: Dict[str, Any]) -> None:
        """设置短期记忆"""
        pass

    @abstractmethod
    async def get_long_term(self, user_id: str) -> Dict[str, Any]:
        """获取长期记忆"""
        pass

    @abstractmethod
    async def set_long_term(self, user_id: str, data: Dict[str, Any]) -> None:
        """设置长期记忆"""
        pass

    async def search_semantic(
        self,
        query: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        语义搜索记忆

        Args:
            query: 搜索query
            user_id: 用户ID（用于隔离搜索范围）
            limit: 返回数量

        Returns:
            相关记忆列表
        """
        if not self.vector_store:
            return []

        # 添加用户过滤
        results = await self.vector_store.retrieve(
            query=query,
            context=Context(user_id=user_id),
            top_k=limit,
            filters={"user_id": user_id, "type": "memory"}
        )
        return results


class HybridMemory(BaseMemory):
    """
    混合记忆存储

    架构:
        - 短期记忆: Redis（快速读写）
        - 长期记忆: PostgreSQL（持久化）
        - 语义记忆: Vector Store（语义检索）
    """

    def __init__(
        self,
        redis_client: "RedisClient",
        pg_client: "PostgreSQLClient",
        vector_store: Optional[IRetriever] = None
    ):
        super().__init__(vector_store)
        self.redis = redis_client
        self.pg = pg_client

    async def get_short_term(self, session_id: str) -> Dict[str, Any]:
        """
        获取短期记忆

        从Redis读取，TTL默认30分钟
        """
        key = f"memory:short:{session_id}"
        data = await self.redis.get(key)

        if data:
            return data

        # 返回空结构
        return {
            "messages": [],
            "entities": {},
            "variables": {}
        }

    async def set_short_term(self, session_id: str, data: Dict[str, Any]) -> None:
        """设置短期记忆，TTL 30分钟"""
        key = f"memory:short:{session_id}"
        await self.redis.set(key, data, ttl=1800)  # 30分钟

    async def get_long_term(self, user_id: str) -> Dict[str, Any]:
        """
        获取长期记忆

        从PostgreSQL读取用户历史数据
        """
        query = """
            SELECT memory_type, content, embedding
            FROM user_memories
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 100
        """
        results = await self.pg.query(query, [user_id])

        memories = {
            "preferences": {},
            "interactions": [],
            "knowledge": []
        }

        for row in results:
            if row["memory_type"] == "preference":
                memories["preferences"].update(row["content"])
            elif row["memory_type"] == "interaction":
                memories["interactions"].append(row["content"])
            elif row["memory_type"] == "knowledge":
                memories["knowledge"].append(row["content"])

        return memories

    async def set_long_term(self, user_id: str, data: Dict[str, Any]) -> None:
        """持久化长期记忆到PostgreSQL"""
        # 批量写入
        records = []

        for pref_key, pref_value in data.get("preferences", {}).items():
            records.append({
                "user_id": user_id,
                "memory_type": "preference",
                "content": {pref_key: pref_value}
            })

        for interaction in data.get("interactions", []):
            records.append({
                "user_id": user_id,
                "memory_type": "interaction",
                "content": interaction
            })

        if records:
            await self.pg.batch_insert("user_memories", records)

    async def store_semantic(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general"
    ) -> None:
        """
        存储语义记忆到向量库

        用于后续的语义检索
        """
        if not self.vector_store:
            return

        # 生成向量并存储
        await self.vector_store.store(
            text=content,
            metadata={
                "user_id": user_id,
                "type": "memory",
                "memory_type": memory_type
            }
        )
```

### 4.2 规划模块 (Planner)

```python
# ============================================================
# Planner模块 - 任务规划
# ============================================================
# 功能:
#   1. 意图理解结果 -> 执行计划
#   2. 识别任务依赖关系
#   3. 确定任务执行顺序（串行/并行）
#
# 实现类:
#   - RulePlanner: 基于规则的简单规划
#   - LLMPlanner: 基于LLM的智能规划
# ============================================================


class BasePlanner(ABC):
    """规划器基类"""

    def __init__(self, llm: Optional[Any] = None):
        self.llm = llm

    @abstractmethod
    async def plan(self, intent: IntentResult, context: Context) -> Plan:
        """根据意图生成执行计划"""
        pass

    def _create_task(
        self,
        task_id: str,
        plugin_name: str,
        method_name: str,
        params: Dict[str, Any],
        dependencies: List[str] = None
    ) -> Task:
        """创建任务的辅助方法"""
        return Task(
            task_id=task_id,
            plugin_name=plugin_name,
            method_name=method_name,
            params=params,
            dependencies=dependencies or []
        )

    def _topological_sort(self, tasks: List[Task]) -> List[List[Task]]:
        """
        拓扑排序，将任务分为可并行执行的批次

        Returns:
            List[List[Task]]: 每批任务可以并行执行
        """
        # 构建依赖图
        task_map = {t.task_id: t for t in tasks}
        in_degree = {t.task_id: 0 for t in tasks}
        dependents = {t.task_id: [] for t in tasks}

        for task in tasks:
            for dep in task.dependencies:
                if dep in task_map:
                    in_degree[task.task_id] += 1
                    dependents[dep].append(task.task_id)

        # Kahn算法
        batches = []
        remaining = set(task_map.keys())

        while remaining:
            # 找到所有入度为0的任务（无依赖）
            ready = [t for t in remaining if in_degree[t] == 0]

            if not ready:
                # 循环依赖，报错
                raise ValueError("Circular dependency detected")

            batches.append([task_map[t] for t in ready])

            # 移除已处理的任务
            for task_id in ready:
                remaining.remove(task_id)
                for dependent in dependents[task_id]:
                    in_degree[dependent] -= 1

        return batches


class LLMPlanner(BasePlanner):
    """
    基于LLM的智能规划器

    优势:
        1. 可处理复杂、模糊的意图
        2. 自动拆解任务步骤
        3. 智能识别依赖关系
    """

    def __init__(
        self,
        llm: Any,
        plugin_registry: "PluginRegistry",
        default_intents: Optional[Dict[str, List[Dict]]] = None
    ):
        super().__init__(llm)
        self.plugin_registry = plugin_registry
        # 意图 -> 任务模板的默认映射
        self.default_intents = default_intents or {}

    async def plan(self, intent: IntentResult, context: Context) -> Plan:
        """
        使用LLM生成执行计划

        流程:
            1. 获取当前可用的插件列表
            2. 构建规划Prompt
            3. LLM生成计划
            4. 验证并返回Plan对象
        """
        # 获取可用插件信息
        plugins = self.plugin_registry.list_plugins()
        plugin_info = [
            {
                "name": p.name,
                "supported_intents": p.supported_intents,
                "methods": self._get_plugin_methods(p)
            }
            for p in plugins
        ]

        # 检查是否有默认模板
        if intent.intent_type in self.default_intents:
            # 使用默认模板
            return await self._plan_from_template(
                intent,
                context,
                self.default_intents[intent.intent_type]
            )

        # 使用LLM智能规划
        return await self._plan_with_llm(intent, context, plugin_info)

    async def _plan_with_llm(
        self,
        intent: IntentResult,
        context: Context,
        plugin_info: List[Dict]
    ) -> Plan:
        """使用LLM生成计划"""
        prompt = f"""基于以下信息生成任务执行计划：

意图类型: {intent.intent_type}
置信度: {intent.confidence}
提取实体: {intent.entities}
可用插件: {plugin_info}

要求:
1. 将任务分解为具体的子任务
2. 每个子任务指定: plugin_name, method_name, params
3. 识别任务间的依赖关系
4. 输出为JSON格式

输出格式:
{{
  "tasks": [
    {{
      "task_id": "t1",
      "plugin_name": "HRPlugin",
      "method_name": "get_leave_balance",
      "params": {{"employee_id": "zhangsan"}},
      "dependencies": []
    }}
  ]
}}
"""
        response = await self.llm.generate(prompt)

        # 解析响应，构建Plan
        tasks = self._parse_llm_response(response)
        batches = self._topological_sort(tasks)

        return Plan(
            task_id=f"plan_{intent.intent_type}_{int(time.time())}",
            steps=tasks,
            metadata={"intent": intent.to_dict(), "batches": len(batches)}
        )

    async def _plan_from_template(
        self,
        intent: IntentResult,
        context: Context,
        template: List[Dict]
    ) -> Plan:
        """基于模板生成计划"""
        tasks = []
        task_id = 1

        for step in template:
            # 填充模板参数
            params = {
                k: intent.entities.get(v, v) for k, v in step.get("params", {}).items()
            }

            tasks.append(self._create_task(
                task_id=f"t{task_id}",
                plugin_name=step["plugin_name"],
                method_name=step["method_name"],
                params=params,
                dependencies=step.get("dependencies", [])
            ))
            task_id += 1

        batches = self._topological_sort(tasks)

        return Plan(
            task_id=f"plan_{intent.intent_type}_{int(time.time())}",
            steps=tasks,
            metadata={"template": True, "batches": len(batches)}
        )
```

### 4.3 检索模块 (Retriever)

```python
# ============================================================
# Retriever模块 - 检索能力抽象
# ============================================================
# 功能:
#   1. 对检索能力进行抽象
#   2. 支持多种检索后端（向量库、全文搜索等）
#   3. 统一的检索接口
#
# 实现类:
#   - VectorRetriever: 向量数据库检索
#   - FullTextRetriever: 全文检索
#   - HybridRetriever: 混合检索
# ============================================================


class BaseRetriever(ABC):
    """检索器基类"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        context: Context,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """执行检索"""
        pass

    async def store(
        self,
        text: str,
        metadata: Dict[str, Any],
        vector: Optional[List[float]] = None
    ) -> str:
        """
        存储文档

        Args:
            text: 文档内容
            metadata: 元数据
            vector: 向量（可选）

        Returns:
            存储ID
        """
        raise NotImplementedError


class VectorRetriever(BaseRetriever):
    """
    向量检索器

    使用向量数据库实现语义检索
    """

    def __init__(
        self,
        vector_store: Any,  # Milvus/Pinecone client
        embedding_model: Any,  # Embedding模型
        name: str = "vector_retriever"
    ):
        super().__init__(name)
        self.vector_store = vector_store
        self.embedding_model = embedding_model

    async def retrieve(
        self,
        query: str,
        context: Context,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行向量检索

        流程:
            1. 将query向量化
            2. 在向量库中搜索
            3. 返回结果
        """
        # 生成query向量
        query_vector = await self.embedding_model.embed(query)

        # 执行搜索
        results = await self.vector_store.search(
            vector=query_vector,
            top_k=top_k,
            filter=filters
        )

        # 格式化结果
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "score": r["score"],
                "metadata": r.get("metadata", {})
            }
            for r in results
        ]


class HybridRetriever(BaseRetriever):
    """
    混合检索器

    结合向量检索和全文检索
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        bm25_retriever: "BM25Retriever",
        fusion_method: str = "rrf"  # rrf or weighted
    ):
        super().__init__("hybrid_retriever")
        self.vector = vector_retriever
        self.bm25 = bm25_retriever
        self.fusion_method = fusion_method

    async def retrieve(
        self,
        query: str,
        context: Context,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        执行混合检索

        流程:
            1. 并行执行向量检索和BM25检索
            2. RRF融合结果
            3. 返回融合后的结果
        """
        # 并行检索
        vector_task = self.vector.retrieve(query, context, top_k * 2, filters)
        bm25_task = self.bm25.retrieve(query, context, top_k * 2, filters)

        vector_results, bm25_results = await asyncio.gather(
            vector_task, bm25_task
        )

        # RRF融合
        fused = self._rrf_fusion(vector_results, bm25_results, k=60)

        return fused[:top_k]

    def _rrf_fusion(
        self,
        results1: List[Dict],
        results2: List[Dict],
        k: int = 60
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion

        公式: score(d) = Σ 1/(k + rank(d))

        优点:
            - 无需训练
            - 对不同检索源公平
            - 简单高效
        """
        scores = {}

        # 处理第一组结果
        for rank, doc in enumerate(results1, 1):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)

        # 处理第二组结果
        for rank, doc in enumerate(results2, 1):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)

        # 按分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: -scores[x])

        # 构建最终结果
        doc_map = {r["id"]: r for r in results1 + results2}
        return [doc_map[doc_id] for doc_id in sorted_ids]
```

### 4.4 记忆治理策略

`v1.0` 已经完成了短期、长期、语义记忆的分类，但在企业环境中，更关键的是“什么信息可以被记住、以什么置信度记住、记多久、谁能看见”。

#### 记忆分层建议

| 记忆类型 | 示例 | 写入条件 | 生命周期 |
|------|------|------|------|
| 会话记忆 | 当前对话实体、临时变量 | 当前请求自动写入 | 会话级，短TTL |
| 用户偏好 | 语言偏好、常用部门 | 用户确认或高置信度提取 | 中长期 |
| 业务事实 | 员工编号、审批状态 | 来自可信系统回写 | 与源系统一致 |
| 经验知识 | 常见问答、风险案例 | 经过审核或评估验证 | 长期，定期重建 |

#### 记忆写入规则

- 来自用户自然语言的内容默认不直接写入长期业务事实
- 长期记忆必须带 `source`、`confidence`、`updated_at`
- 可冲突事实优先以外部系统记录为准
- 用户纠正后的事实必须覆盖旧记忆，并保留审计历史

#### 敏感信息治理

- PII 字段在进入向量库前需要脱敏或分片
- 敏感记忆可只保留索引，不直接保留明文
- 不同租户的语义记忆索引必须物理或逻辑隔离

---

## 5. 行业插件模块

### 5.1 插件基类

```python
# ============================================================
# 插件基类
# ============================================================
# 所有行业插件都继承自BasePlugin
# 提供统一的生命周期管理
# ============================================================


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str
    author: str
    supported_intents: List[str]
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他插件


class BasePlugin(ABC):
    """
    插件基类

    插件开发规范:
        1. 继承BasePlugin
        2. 定义supported_intents
        3. 实现execute方法
        4. 注册到PluginRegistry
    """

    # 类属性，由子类覆盖
    metadata: PluginMetadata

    def __init__(self):
        self._initialized = False
        self._config = {}

    async def initialize(self, config: Dict[str, Any]) -> None:
        """
        初始化插件

        插件启动时调用，用于:
            - 加载配置
            - 初始化资源连接
            - 注册自定义能力
        """
        self._config = config
        self._initialized = True

    async def execute(
        self,
        method: str,
        params: Dict[str, Any],
        context: Context
    ) -> TaskResult:
        """
        执行插件方法

        统一入口，内部根据method分发到具体方法
        """
        if not self._initialized:
            return TaskResult(
                task_id=params.get("task_id", ""),
                status="failure",
                data=None,
                error="Plugin not initialized"
            )

        # 方法派发
        method_map = {
            m: getattr(self, m)
            for m in dir(self)
            if not m.startswith('_') and callable(getattr(self, m))
        }

        if method not in method_map:
            return TaskResult(
                task_id=params.get("task_id", ""),
                status="failure",
                data=None,
                error=f"Unknown method: {method}"
            )

        try:
            result = await method_map[method](params, context)
            return result
        except Exception as e:
            return TaskResult(
                task_id=params.get("task_id", ""),
                status="failure",
                data=None,
                error=str(e)
            )

    async def health_check(self) -> bool:
        """健康检查"""
        return self._initialized

    @classmethod
    def get_metadata(cls) -> PluginMetadata:
        """获取插件元数据"""
        return cls.metadata
```

### 5.2 HR插件示例

```python
# ============================================================
# HR插件 - 人力资源业务能力
# ============================================================
# 功能范围:
#   - 假期计算与查询
#   - 组织架构查询
#   - 政策制度问答
#   - 请假申请处理
#
# 依赖模块:
#   - Memory (短期/长期记忆)
#   - Retriever (政策检索)
# ============================================================


class HRPlugin(BasePlugin):
    """
    HR业务插件

    提供企业人力资源相关的智能化能力
    """

    metadata = PluginMetadata(
        name="HRPlugin",
        version="1.0.0",
        description="HR业务能力插件",
        author="Enterprise AI Team",
        supported_intents=[
            "leave_request",      # 请假申请
            "leave_balance",      # 假期余额查询
            "org_query",          # 组织架构查询
            "policy_question",   # 政策咨询
            "employee_info"      # 员工信息查询
        ],
        dependencies=[]  # 可选依赖其他插件
    )

    def __init__(
        self,
        memory: IMemory,
        retriever: IRetriever,
        employee_db: IStorage
    ):
        super().__init__()
        self.memory = memory
        self.retriever = retriever
        self.employee_db = employee_db

        # 假期政策规则
        self.leave_policy = {
            "annual": {
                "rules": [
                    {"min_years": 0, "max_years": 1, "days": 5},
                    {"min_years": 1, "max_years": 5, "days": 10},
                    {"min_years": 5, "max_years": 10, "days": 15},
                    {"min_years": 10, "max_years": None, "days": 20}
                ]
            }
        }

    # --------------------------------------------------------
    # 假期余额查询
    # --------------------------------------------------------
    async def get_leave_balance(
        self,
        params: Dict[str, Any],
        context: Context
    ) -> TaskResult:
        """
        查询员工假期余额

        Args:
            params: {
                "employee_id": "zhangsan",
                "leave_type": "annual"  # optional
            }
        """
        employee_id = params.get("employee_id")
        leave_type = params.get("leave_type", "annual")

        # 1. 查询员工信息
        employee = await self.employee_db.get(f"employee:{employee_id}")
        if not employee:
            return TaskResult(
                task_id=params.get("task_id", ""),
                status="failure",
                data=None,
                error="员工不存在"
            )

        # 2. 查询假期余额
        balance_key = f"leave_balance:{employee_id}:{leave_type}"
        balance = await self.employee_db.get(balance_key)

        # 3. 存储到记忆（用于后续任务）
        await self.memory.store(
            key=f"leave_balance:{context.session_id}",
            value={
                "employee_id": employee_id,
                "employee_name": employee["name"],
                "balance": balance,
                "leave_type": leave_type
            },
            context=context
        )

        return TaskResult(
            task_id=params.get("task_id", ""),
            status="success",
            data={
                "employee_id": employee_id,
                "employee_name": employee["name"],
                "balance": balance,
                "leave_type": leave_type
            }
        )

    # --------------------------------------------------------
    # 假期政策检索
    # --------------------------------------------------------
    async def search_policy(
        self,
        params: Dict[str, Any],
        context: Context
    ) -> TaskResult:
        """
        检索HR政策制度

        Args:
            params: {
                "query": "年假是如何计算的",
                "top_k": 5  # optional
            }
        """
        query = params.get("query")
        top_k = params.get("top_k", 5)

        # 使用Retriever检索相关政策
        results = await self.retriever.retrieve(
            query=query,
            context=context,
            top_k=top_k,
            filters={"type": "hr_policy"}
        )

        # 提取关键信息
        policies = [
            {
                "title": r.get("title", ""),
                "text": r.get("text", "")[:500],  # 截取摘要
                "score": r.get("score", 0)
            }
            for r in results
        ]

        return TaskResult(
            task_id=params.get("task_id", ""),
            status="success",
            data={"policies": policies}
        )

    # --------------------------------------------------------
    # 请假申请验证
    # --------------------------------------------------------
    async def validate_leave_request(
        self,
        params: Dict[str, Any],
        context: Context
    ) -> TaskResult:
        """
        验证请假申请是否合理

        Args:
            params: {
                "employee_id": "zhangsan",
                "leave_type": "annual",
                "start_date": "2026-04-23",
                "end_date": "2026-04-25",
                "reason": "个人原因"
            }
        """
        employee_id = params.get("employee_id")
        leave_type = params.get("leave_type")
        start_date = params.get("start_date")
        end_date = params.get("end_date")

        # 1. 获取假期余额
        balance_result = await self.get_leave_balance(
            {"employee_id": employee_id, "leave_type": leave_type},
            context
        )

        if balance_result.status != "success":
            return balance_result

        balance = balance_result.data["balance"]

        # 2. 计算申请天数
        days = self._calculate_days(start_date, end_date)

        # 3. 验证
        validation = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        if days > balance:
            validation["valid"] = False
            validation["errors"].append(
                f"申请天数({days}天)超过可用余额({balance}天)"
            )

        # 检查是否提前申请（假设需提前3天）
        if not self._check_advance_application(start_date):
            validation["warnings"].append("建议提前3天申请")

        status = "success" if validation["valid"] else "failure"

        return TaskResult(
            task_id=params.get("task_id", ""),
            status=status,
            data=validation
        )

    def _calculate_days(self, start_date: str, end_date: str) -> int:
        """计算日期范围的天数"""
        from datetime import datetime
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        return (end - start).days + 1

    def _check_advance_application(self, start_date: str) -> bool:
        """检查是否提前申请"""
        from datetime import datetime, timedelta
        target = datetime.strptime(start_date, "%Y-%m-%d")
        return (target - datetime.now()).days >= 3
```

### 5.3 合同审核插件示例

```python
# ============================================================
# LegalPlugin - 法务业务能力
# ============================================================
# 功能范围:
#   - 合同条款提取
#   - 风险点识别
#   - 合规性检查
#   - 修订建议生成
# ============================================================


class LegalPlugin(BasePlugin):
    """
    法务业务插件

    提供合同审核、风险识别等法务能力
    """

    metadata = PluginMetadata(
        name="LegalPlugin",
        version="1.0.0",
        description="法务业务能力插件",
        author="Enterprise AI Team",
        supported_intents=[
            "contract_review",    # 合同审核
            "risk_identify",      # 风险识别
            "compliance_check",   # 合规检查
            "clause_extract"      # 条款提取
        ],
        dependencies=["HRPlugin"]  # 可能需要调用HR数据
    )

    def __init__(
        self,
        memory: IMemory,
        retriever: IRetriever,
        llm: Any
    ):
        super().__init__()
        self.memory = memory
        self.retriever = retriever
        self.llm = llm

    async def review_contract(
        self,
        params: Dict[str, Any],
        context: Context
    ) -> TaskResult:
        """
        审核合同

        Args:
            params: {
                "contract_text": "合同全文...",
                "contract_type": "labor",  # labor/purchase/nda
                "scope": ["risk", "compliance"]
            }
        """
        contract_text = params.get("contract_text")
        contract_type = params.get("contract_type", "general")
        scope = params.get("scope", ["risk"])

        results = {
            "contract_type": contract_type,
            "risk_count": 0,
            "risks": [],
            "compliance_score": 100,
            "suggestions": []
        }

        # 1. 提取条款
        clauses = await self._extract_clauses(contract_text, contract_type)

        # 2. 风险识别
        if "risk" in scope:
            for clause in clauses:
                risks = await self._identify_risks(
                    clause,
                    contract_type
                )
                results["risks"].extend(risks)

        # 3. 合规检查
        if "compliance" in scope:
            compliance_issues = await self._check_compliance(
                clauses,
                contract_type
            )
            results["compliance_issues"] = compliance_issues
            results["compliance_score"] -= len(compliance_issues) * 5

        # 4. 生成修订建议
        results["suggestions"] = await self._generate_suggestions(
            results["risks"],
            results.get("compliance_issues", [])
        )

        results["risk_count"] = len(results["risks"])

        return TaskResult(
            task_id=params.get("task_id", ""),
            status="success",
            data=results
        )

    async def _extract_clauses(
        self,
        text: str,
        contract_type: str
    ) -> List[Dict]:
        """提取合同条款"""
        prompt = f"""从以下合同文本中提取条款：

合同类型: {contract_type}

合同内容:
{text}

提取以下格式的条款列表:
[
  {{
    "id": "第1条",
    "title": "条款标题",
    "content": "条款内容",
    "type": "payment/duration/liability/..."
  }}
]
"""
        response = await self.llm.generate(prompt)

        # 解析LLM响应
        try:
            import json
            return json.loads(response)
        except:
            return [{"id": "unknown", "title": "条款", "content": text, "type": "general"}]

    async def _identify_risks(
        self,
        clause: Dict,
        contract_type: str
    ) -> List[Dict]:
        """识别条款风险"""
        # 检索相关风险案例
        similar = await self.retriever.retrieve(
            query=clause["content"],
            context=None,
            top_k=3,
            filters={"type": "risk_case", "contract_type": contract_type}
        )

        risks = []

        # 基于案例分析风险
        for case in similar:
            if case.get("score", 0) > 0.8:
                risks.append({
                    "clause_id": clause.get("id"),
                    "clause_title": clause.get("title"),
                    "risk_level": case.get("risk_level", "medium"),
                    "description": case.get("description"),
                    "suggestion": case.get("suggestion")
                })

        return risks
```

---

## 6. 插件化框架

### 6.1 插件注册与管理

```python
# ============================================================
# 插件注册与发现机制
# ============================================================


class PluginRegistry:
    """
    插件注册中心

    功能:
        1. 插件注册与发现
        2. 插件生命周期管理
        3. 插件依赖管理
    """

    def __init__(self, module_registry: ModuleRegistry):
        self.module_registry = module_registry
        self._plugins: Dict[str, BasePlugin] = {}
        self._metadata: Dict[str, PluginMetadata] = {}

    def register_plugin(
        self,
        plugin_class: Type[BasePlugin],
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        注册插件

        Args:
            plugin_class: 插件类
            config: 插件配置
        """
        metadata = plugin_class.metadata
        plugin_name = metadata.name

        # 检查依赖
        for dep in metadata.dependencies:
            if dep not in self._plugins:
                raise ValueError(
                    f"Plugin {plugin_name} depends on {dep}, "
                    f"but {dep} is not registered"
                )

        # 创建插件实例
        plugin = plugin_class()

        # 注入依赖
        dependencies = self._resolve_dependencies(plugin, config or {})
        for dep_name, dep_instance in dependencies.items():
            setattr(plugin, dep_name, dep_instance)

        # 初始化
        plugin.initialize(config or {})

        # 注册
        self._plugins[plugin_name] = plugin
        self._metadata[plugin_name] = metadata

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """获取插件实例"""
        return self._plugins.get(name)

    def list_plugins(self) -> List[BasePlugin]:
        """列出所有已注册的插件"""
        return list(self._plugins.values())

    def list_plugin_metadata(self) -> List[PluginMetadata]:
        """列出所有插件元数据"""
        return list(self._metadata.values())

    def find_plugin_by_intent(self, intent: str) -> Optional[BasePlugin]:
        """
        根据意图查找支持该意图的插件

        Args:
            intent: 意图类型

        Returns:
            支持该意图的插件
        """
        for plugin in self._plugins.values():
            if intent in plugin.metadata.supported_intents:
                return plugin
        return None

    def unregister_plugin(self, name: str) -> None:
        """注销插件"""
        if name in self._plugins:
            del self._plugins[name]
        if name in self._metadata:
            del self._metadata[name]

    def _resolve_dependencies(
        self,
        plugin: BasePlugin,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析插件依赖"""
        # 检查插件构造函数参数
        import inspect
        sig = inspect.signature(plugin.__class__.__init__)
        dependencies = {}

        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'config'):
                continue

            param_type = param.annotation

            # 从模块注册中心获取依赖
            if self.module_registry:
                try:
                    dependencies[param_name] = self.module_registry.get(param_type)
                except:
                    pass

        return dependencies
```

### 6.2 插件市场 (Plugin Marketplace)

```python
# ============================================================
# 插件市场 - Plugin Marketplace
# ============================================================
# 功能:
#   1. 插件的远程发布与发现
#   2. 插件版本管理
#   3. 插件市场API
# ============================================================


@dataclass
class PluginPackage:
    """插件包"""
    metadata: PluginMetadata
    source_code_url: str
    checksum: str
    readme: str
    changelog: str


class PluginMarketplace:
    """
    插件市场

    支持:
        1. 从市场安装插件
        2. 发布自研插件到市场
        3. 插件版本管理
    """

    def __init__(self, storage: IStorage):
        self.storage = storage
        self._cache: Dict[str, PluginPackage] = {}

    async def search(
        self,
        query: str,
        category: Optional[str] = None
    ) -> List[PluginPackage]:
        """
        搜索插件

        Args:
            query: 搜索关键词
            category: 插件类别（可选）

        Returns:
            匹配的插件列表
        """
        # 查询市场索引
        index = await self._get_market_index()

        results = []
        for pkg_info in index:
            # 简单匹配
            if query.lower() in pkg_info["metadata"].name.lower():
                results.append(pkg_info)
            elif query.lower() in pkg_info["metadata"].description.lower():
                results.append(pkg_info)

        return results

    async def install(
        self,
        plugin_name: str,
        version: str = "latest"
    ) -> BasePlugin:
        """
        安装插件

        Args:
            plugin_name: 插件名
            version: 版本号

        Returns:
            安装的插件实例
        """
        # 获取插件包信息
        pkg = await self._get_package(plugin_name, version)

        # 下载源码
        source_code = await self._download_source(pkg.source_code_url)

        # 验证checksum
        if not self._verify_checksum(source_code, pkg.checksum):
            raise ValueError("Plugin checksum mismatch")

        # 动态导入
        plugin_class = self._load_plugin_class(source_code, plugin_name)

        # 创建插件注册中心（这里简化处理）
        registry = PluginRegistry(registry)

        # 注册
        registry.register_plugin(plugin_class)

        return registry.get_plugin(plugin_name)

    async def publish(
        self,
        plugin_class: Type[BasePlugin],
        source_code: str,
        metadata: PluginMetadata
    ) -> str:
        """
        发布插件到市场

        Args:
            plugin_class: 插件类
            source_code: 插件源码
            metadata: 插件元数据

        Returns:
            插件包ID
        """
        # 计算checksum
        import hashlib
        checksum = hashlib.sha256(source_code.encode()).hexdigest()

        # 创建插件包
        pkg = PluginPackage(
            metadata=metadata,
            source_code_url="",  # 上传到OSS后的URL
            checksum=checksum,
            readme="",
            changelog=""
        )

        # 存储
        await self.storage.set(
            f"plugin:{metadata.name}:{metadata.version}",
            pkg
        )

        return f"{metadata.name}@{metadata.version}"

    async def _get_market_index(self) -> List[PluginPackage]:
        """获取市场索引"""
        # 简化：实际应该从远程服务获取
        return []

    async def _get_package(
        self,
        name: str,
        version: str
    ) -> PluginPackage:
        """获取插件包"""
        key = f"plugin:{name}:{version}"
        if key not in self._cache:
            self._cache[key] = await self.storage.get(key)
        return self._cache[key]

    def _verify_checksum(self, source: str, expected: str) -> bool:
        """验证checksum"""
        import hashlib
        return hashlib.sha256(source.encode()).hexdigest() == expected

    def _load_plugin_class(
        self,
        source_code: str,
        class_name: str
    ) -> Type[BasePlugin]:
        """动态加载插件类"""
        # 简化实现
        # 实际应该使用importlib动态导入
        exec(source_code)
        return locals()[class_name]
```

### 6.3 企业内部插件仓库与安全边界

`v1.1` 对插件分发策略做了收敛：默认推荐企业内部插件仓库，而不是直接开放式“插件市场”。  
原因是企业侧更关注可控、可审计、可回滚，而不是任意动态扩展。

#### 推荐的企业分发模型

```text
开发团队提交插件
    -> CI校验（Schema / 单测 / 安全扫描）
    -> 签名打包
    -> 发布到内部仓库
    -> 平台审批接入
    -> 灰度启用
    -> 全量发布
```

#### 安全边界要求

- 禁止直接执行未经签名和审批的远程源码
- 插件安装包必须包含版本、依赖、能力清单、权限声明
- 插件升级必须支持灰度发布和快速回滚
- 高风险插件建议运行在隔离沙箱或独立进程中

#### 插件准入检查清单

1. 是否声明完整 capability schema
2. 是否声明所需权限与副作用级别
3. 是否通过单元测试、契约测试和安全扫描
4. 是否具备版本兼容说明和回滚方案

---

## 7. 企业场景实现

### 7.1 快速构建HR智能助手

```python
# ============================================================
# 构建HR智能助手示例
# ============================================================
# 目标: 快速构建一个HR智能问答助手
#
# 步骤:
#   1. 初始化核心模块
#   2. 注册通用能力
#   3. 注册HR插件
#   4. 启动服务
# ============================================================


async def build_hr_assistant(config: Dict[str, Any]) -> "AgentService":
    """
    构建HR智能助手

    Args:
        config: {
            "llm": {...},
            "vector_store": {...},
            "employee_db": {...}
        }
    """

    # 1. 初始化模块注册中心
    module_reg = ModuleRegistry()

    # 2. 注册通用能力
    # 意图分类器
    module_reg.register(
        IIntentClassifier,
        OpenAIIntentClassifier,
        config={"api_key": config["llm"]["api_key"]}
    )

    # 记忆模块
    module_reg.register(
        IMemory,
        HybridMemory,
        config={
            "redis": config["redis"],
            "pg": config["postgresql"],
            "vector_store": config["vector_store"]
        }
    )

    # 检索模块
    module_reg.register(
        IRetriever,
        HybridRetriever,
        config={"vector_store": config["vector_store"]}
    )

    # 规划器
    module_reg.register(
        IPlanner,
        LLMPlanner,
        config={
            "llm": config["llm"],
            "plugin_registry": None  # 后续注入
        }
    )

    # 3. 创建插件注册中心
    plugin_reg = PluginRegistry(module_reg)

    # 注册HR插件
    plugin_reg.register_plugin(
        HRPlugin,
        config={
            "leave_policy": config.get("leave_policy", {})
        }
    )

    # 注册知识检索增强插件（可选）
    plugin_reg.register_plugin(
        KnowledgePlugin,
        config={
            "vector_store": config["vector_store"]
        }
    )

    # 4. 创建Supervisor Agent
    supervisor = SupervisorAgent(
        intent_classifier=module_reg.get(IIntentClassifier),
        memory=module_reg.get(IMemory),
        planner=module_reg.get(IPlanner),
        plugin_registry=plugin_reg
    )

    # 5. 创建服务
    service = AgentService(supervisor=supervisor)

    return service


# 使用示例
async def main():
    config = {
        "llm": {"api_key": "sk-..."},
        "redis": {"host": "localhost", "port": 6379},
        "postgresql": {"host": "localhost", "port": 5432},
        "vector_store": {"type": "milvus", "host": "localhost"}
    }

    service = await build_hr_assistant(config)

    # 启动服务
    await service.start()

    # 处理请求
    response = await service.handle(
        user_id="user123",
        session_id="sess_abc",
        query="张三还有几天年假？"
    )

    print(response)
```

### 7.2 扩展为法务助手

```python
# ============================================================
# 扩展为法务助手
# ============================================================
# 在HR助手基础上添加法务能力
# ============================================================


async def build_legal_assistant(base_service: "AgentService"):
    """
    在现有服务基础上添加法务插件

    Args:
        base_service: 已有的Agent服务
    """

    plugin_reg = base_service.supervisor.plugin_registry

    # 注册法务插件
    plugin_reg.register_plugin(
        LegalPlugin,
        config={
            "risk_case_library": "..."
        }
    )

    # 更新意图分类器支持新意图
    # （如果需要新增intent类型）

    return base_service


# 使用示例
async def main():
    # 先构建HR助手
    hr_service = await build_hr_assistant(config)

    # 扩展为法务助手
    full_service = await build_legal_assistant(hr_service)

    # 现在可以处理两种类型的请求
    response1 = await full_service.handle(
        query="张三还有几天年假？",
        ...
    )  # HR问题

    response2 = await full_service.handle(
        query="帮我审核这份劳动合同",
        ...
    )  # 法务问题
```

### 7.3 企业级完整方案

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        企业级Agent平台架构                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                     统一接入层 (API Gateway)                        │   │
│  │         认证 / 限流 / 路由 / 监控 / 日志                            │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│  ┌─────────────────────────────────┼───────────────────────────────────┐   │
│  │                      Agent 调度层                                  │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                   Supervisor Agent                         │   │   │
│  │  │  • 意图理解    • 任务分解    • 结果整合    • 自我纠错    │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                                │                                 │   │
│  │  ┌─────────────────────────────┼─────────────────────────────┐   │   │
│  │  │              Plugin Protocol Layer                       │   │   │
│  │  │  • 统一接口    • 生命周期    • 依赖管理                │   │   │
│  │  └─────────────────────────────┼─────────────────────────────┘   │   │
│  └─────────────────────────────────┼───────────────────────────────────┘   │
│                                    │                                     │
├─────────────────────────────────────┼───────────────────────────────────┤
│                               插件层                                     │
│                                                                             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐             │
│  │   HRPlugin     │ │ LegalPlugin    │ │ FinancePlugin  │             │
│  │                │ │                │ │                │             │
│  │ • 假期计算     │ │ • 合同审核     │ │ • 报表生成     │             │
│  │ • 组织查询     │ │ • 风险识别     │ │ • 预算审核     │             │
│  │ • 政策问答     │ │ • 合规检查     │ │ • 发票核验     │             │
│  └────────┬──────┘ └────────┬──────┘ └────────┬──────┘             │
│           │                  │                  │                      │
│  ┌────────┴──────────────────┴──────────────────┴────────┐            │
│  │                   业务工具层                           │            │
│  │  • 员工数据库    • 审批流    • 文档系统    • ...    │            │
│  └───────────────────────────────────────────────────────┘            │
│                                                                             │
├───────────────────────────────────────────────────────────────────────────┤
│                               核心能力层                                     │
│                                                                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐               │
│  │  Memory   │ │  Planner  │ │ Retriever │ │  Monitor  │               │
│  │           │ │           │ │           │ │           │               │
│  │  统一接口 │ │  统一接口 │ │  统一接口 │ │  统一接口 │               │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘               │
│                                                                             │
├───────────────────────────────────────────────────────────────────────────┤
│                               基础设施层                                     │
│                                                                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐               │
│  │ PostgreSQL│ │   Redis   │ │  Milvus   │ │   LLM    │               │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘               │
│                                                                             │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 开发规范

### 8.1 新插件开发模板

```python
# ============================================================
# 插件开发模板
# ============================================================
# 新建插件时，复制此模板进行开发
# ============================================================


# Step 1: 定义插件元数据
metadata = PluginMetadata(
    name="MyPlugin",           # 插件名称（唯一标识）
    version="1.0.0",          # 语义化版本
    description="我的插件",      # 插件描述
    author="Team Name",        # 开发团队
    supported_intents=[        # 支持的意图列表
        "my_action_1",
        "my_action_2"
    ],
    dependencies=[]           # 依赖的其他插件（如需要）
)


# Step 2: 定义插件类
class MyPlugin(BasePlugin):
    """
    我的插件

    功能说明:
        1. 功能1描述
        2. 功能2描述
    """

    # Step 3: 设置元数据
    metadata = metadata

    def __init__(
        self,
        # Step 4: 声明依赖接口
        memory: IMemory,           # 必需：记忆模块
        retriever: IRetriever,     # 必需：检索模块
        # 可选：其他依赖...
    ):
        super().__init__()
        self.memory = memory
        self.retriever = retriever

    # Step 5: 实现业务方法
    async def my_action_1(
        self,
        params: Dict[str, Any],
        context: Context
    ) -> TaskResult:
        """
        功能1的实现

        Args:
            params: {
                "param1": "value1",
                ...
            }

        Returns:
            TaskResult: 执行结果
        """
        try:
            # 业务逻辑
            result = await self._do_something(params)

            return TaskResult(
                task_id=params.get("task_id", ""),
                status="success",
                data=result
            )
        except Exception as e:
            return TaskResult(
                task_id=params.get("task_id", ""),
                status="failure",
                data=None,
                error=str(e)
            )


# Step 6: 注册到插件注册中心
# 在应用启动时调用
def register_my_plugin(registry: PluginRegistry):
    registry.register_plugin(MyPlugin, config={})
```

### 8.2 通用能力替换示例

```python
# ============================================================
# 替换通用能力实现
# ============================================================
# 默认实现可能不满足需求时，可替换
# ============================================================


# 示例：将默认的记忆模块替换为增强版
class EnhancedMemory(BaseMemory):
    """
    增强版记忆模块

    在基础功能上增加:
        1. 自动摘要生成
        2. 记忆压缩
        3. 优先级标记
    """

    async def get_short_term(self, session_id: str) -> Dict[str, Any]:
        # 原有逻辑
        data = await super().get_short_term(session_id)

        # 增强：自动生成摘要
        if data.get("messages"):
            data["summary"] = await self._generate_summary(
                data["messages"]
            )

        return data


# 替换注册
def use_enhanced_memory(registry: ModuleRegistry):
    registry.unregister(IMemory)
    registry.register(
        IMemory,
        EnhancedMemory,
        config={"enable_summary": True}
    )
```

### 8.3 评估与回归规范

为了让平台迭代可控，`v1.1` 明确要求每次新增插件、替换通用能力或升级模型时，都要经过最小评估集验证。

#### 评估层次

| 层次 | 目标 | 示例指标 |
|------|------|------|
| Intent评估 | 意图识别正确 | intent accuracy, entity recall |
| Planner评估 | 计划合理且可执行 | valid plan rate, dependency error rate |
| Retriever评估 | 检索结果相关 | recall@k, mrr, 命中率 |
| Plugin评估 | 业务执行正确 | task success rate, business assertion pass rate |
| End-to-End评估 | 用户结果可用 | completion rate, 人工介入率, 平均耗时 |

#### 最小回归集要求

- 每个核心 intent 至少保留 10 条稳定样例
- 每个高风险写操作至少保留 3 条审批/拒绝/回滚样例
- 每次模型升级需回归历史失败案例
- 每次插件升级需执行契约测试，验证 input/output schema 未破坏兼容性

#### 推荐的数据集组成

- 标准样例：覆盖主流程
- 边界样例：缺参、歧义、多实体、跨部门权限
- 失败样例：插件超时、检索为空、外部系统异常
- 安全样例：越权访问、提示注入、敏感信息泄露尝试

---

## 9. 运行时与安全治理

### 9.1 Supervisor 的受控执行原则

Supervisor 在 `v1.1` 中不再只是“任务调度中心”，还承担以下职责：

- 对 Planner 生成结果做静态校验
- 根据能力契约做权限和风险检查
- 控制重试、超时、取消和人工审批
- 在失败时生成结构化诊断信息

推荐执行顺序：

```text
意图识别
 -> 检索上下文
 -> 生成候选计划
 -> 计划校验
 -> 权限校验
 -> 风险分级
 -> 执行
 -> 结果整合
 -> 审计与评估回写
```

### 9.2 风险分级

| 风险等级 | 定义 | 示例 | 默认策略 |
|------|------|------|------|
| L1 | 无副作用读取 | 查余额、查政策 | 自动执行 |
| L2 | 低风险写入 | 保存草稿、记录反馈 | 自动执行，保留审计 |
| L3 | 中风险写入 | 发起审批、更新工单 | 视策略审批 |
| L4 | 高风险动作 | 财务打款、合同正式提交 | 强制人工确认 |

### 9.3 审计要求

所有高价值请求都需要记录以下信息：

- `request_id`
- 调用人、租户、角色
- 计划内容与实际执行链路
- 插件名、能力名、入参与出参摘要
- 是否人工审批、审批人是谁
- 最终结果、失败原因、补偿动作

### 9.4 多租户隔离策略

建议平台至少满足以下隔离要求：

- 检索索引按租户隔离
- 长期记忆按租户隔离
- 监控与日志支持按租户过滤
- 插件配置按环境、租户、组织分级覆盖

---

## 10. 评估与回归体系

### 10.1 评估目标

平台评估不只看模型回答是否“像样”，而是看整条链路是否“可执行、可控、可复现”。

因此 `v1.1` 建议将评估拆成 3 条主线：

- 质量主线：结果是否正确、完整、可解释
- 稳定性主线：失败率、超时率、回退率是否可控
- 安全主线：越权、误执行、敏感信息暴露是否被拦截

### 10.2 核心指标建议

| 维度 | 指标 |
|------|------|
| 质量 | intent accuracy, entity F1, retrieval recall@k, task success rate |
| 时延 | p50/p95/p99 latency, plugin timeout rate |
| 成本 | token cost per request, retrieval cost, external API cost |
| 稳定性 | retry rate, fallback rate, plan validation failure rate |
| 安全 | permission deny rate, approval intercept rate, prompt injection block rate |

### 10.3 回归执行策略

- 日常开发跑最小回归集
- 插件升级跑插件专项回归
- 模型升级跑全链路回归与历史问题集
- 生产问题复盘后，将对应 case 沉淀为永久回归样例

---

## 11. 部署拓扑与伸缩策略

### 11.1 推荐部署拆分

为了兼顾稳定性和扩展性，建议将平台拆成以下独立组件：

- `API Gateway`：认证、限流、租户路由
- `Supervisor Service`：编排、计划校验、风险控制
- `Plugin Runtime`：执行插件能力
- `Memory Service`：会话/长期记忆管理
- `Retrieval Service`：向量检索、全文检索、重排
- `Evaluation & Audit Service`：评估回写、链路审计

### 11.2 有状态与无状态拆分

| 组件 | 类型 | 说明 |
|------|------|------|
| API Gateway | 无状态 | 可水平扩展 |
| Supervisor Service | 无状态 | 可水平扩展，依赖外部状态存储 |
| Plugin Runtime | 半无状态 | 可按插件类别拆分扩容 |
| Memory Service | 有状态 | 依赖 Redis / PostgreSQL |
| Retrieval Service | 有状态 | 依赖向量库和索引 |

### 11.3 弹性策略

- 高并发读取类插件可独立扩容
- 高风险写入插件建议限流，并开启串行队列
- 检索与 Embedding 建议做缓存，降低重复请求成本
- 长耗时任务建议异步化，通过任务队列与回调机制返回结果

### 11.4 故障降级建议

| 故障点 | 降级策略 |
|------|------|
| 向量库异常 | 回退到全文检索或结构化检索 |
| LLM规划失败 | 回退到模板计划 |
| 单插件超时 | 标记失败并进入部分完成模式 |
| 审批系统异常 | 暂停高风险写操作并提示人工处理 |

---

## 附录

### A. 模块接口列表

| 接口 | 说明 | 默认实现 |
|------|------|---------|
| IIntentClassifier | 意图理解 | OpenAIIntentClassifier |
| IMemory | 记忆管理 | HybridMemory |
| IPlanner | 任务规划 | LLMPlanner |
| IRetriever | 检索能力 | HybridRetriever |
| IStorage | 存储抽象 | RedisStorage |
| IMonitor | 监控追踪 | PrometheusMonitor |

### B. 插件列表

| 插件 | 版本 | 支持意图 |
|------|------|---------|
| HRPlugin | 1.0.0 | leave_request, leave_balance, org_query, policy_question |
| LegalPlugin | 1.0.0 | contract_review, risk_identify, compliance_check |
| FinancePlugin | 1.0.0 | report_generate, budget_check, invoice_verify |

---

**文档版本历史**

| 版本 | 日期 | 修改内容 |
|------|------|---------|
| v1.1 | 2026-04-18 | 补充能力契约、运行时语义、权限边界、记忆治理、企业内部分发、评估回归、部署伸缩 |
| v1.0 | 2026-04-18 | 初稿：可扩展Agent架构方案 |
