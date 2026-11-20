# 05-2 · 平台架构与 Agent 接入规范

> **文档编号**：G3-002
> **文档负责人**：平台架构师 / 技术负责人（协作：产品经理）
> **项目**：AgentGate —— Agent 上线门禁与离线评测沙箱
> **版本**：v1.0
> **日期**：2026-11-08
> **状态**：待评审
> **上游**：`01-问题定义.md`（v2.0）、`02-竞品对标.md`（v1.0）、`03-可行性预研.md`（v1.0）
> **下游**：`05-PRD.md`、`src/`、`08-评测体系.md`

---

## 0. 文档导读

### 0.1 这份文档的目的

回答一个问题：**平台由哪些层组成、每一层的职责边界是什么、外部 Agent 怎么接进来？**

具体要定稿：

1. 平台的分层架构与模块边界；
2. 核心数据模型（Agent / Case / Rubric / Run / Trace / Report）；
3. Agent Adapter 的接入契约；
4. Tool Adapter 与权限围栏的契约；
5. LangGraph 与 Harness 的职责划分；
6. 平台工作台的形态（CLI / Streamlit）。

### 0.2 读者与使用方式

| 读者 | 怎么用 |
|---|---|
| 项目负责人 | 确认架构是否支撑 G1 的四个缺口 |
| G5 开发 | 按本文的接口与目录实现 |
| 面试 | 用分层图和 Adapter 契约证明"这是平台，不是单 Agent" |

### 0.3 本文包含什么

```
§1 架构总览与设计原则
§2 核心数据模型
§3 Agent Adapter 规范
§4 Tool Adapter 与权限围栏
§5 LangGraph 与 Harness
§6 平台工作台
§7 用例与 Rubric 管理
§8 评测、回归与报告
§9 非功能与边界
§10 与竞品的架构对照
§11 G5 实现清单
附录：接口与目录
```

### 0.4 核心结论（30 秒版）

> 平台分五层：**工作台 → 评测 → Harness → 沙箱运行时（LangGraph）→ Adapter/工具**。
> 平台只依赖 **Agent Adapter 三方法**（metadata / run / rubric）和 **Tool Adapter 三方法**（spec / check / execute），不关心 Agent 内部用什么框架。
> 业务级 trace 由自研 `TraceRecorder` 记录，不依赖 LangGraph 自动导出。
> 平台不做多租户、容器隔离、在线流量；所有变更工具 Mock。

### 0.5 本文不解决什么

- 不定义评测指标口径（见 `08-评测体系.md`）；
- 不定义规则表细节（见 `06-人机协同规则.md`）；
- 不定义 UI 视觉；
- 不做生产级部署、并发、SLA。

### 0.6 下游文档如何使用本文

| 下游 | 引用本文的 |
|---|---|
| `05-PRD.md` | §3–§8 功能边界 |
| `06-人机协同规则.md` | §5 确认节点、§4 围栏 |
| `07-流程图.md` | §5 状态机 |
| `src/` | §2–§8 接口与目录 |

---

## 1. 架构总览与设计原则

### 1.1 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│ 平台工作台（Workbench）                                        │
│  Agent 注册 │ 用例管理 │ 批量运行 │ trace 查看 │ 回归对比        │
├──────────────────────────────────────────────────────────────┤
│ 评测层（Evaluation）                                           │
│  Rubric 配置 │ 断言执行 │ 指标计算 │ 报告生成 │ 版本对比         │
├──────────────────────────────────────────────────────────────┤
│ Harness 运行时管控（自研）                                      │
│  run_id │ 状态机 │ 超时 │ 重试 │ 异常 │ trace 落盘              │
├──────────────────────────────────────────────────────────────┤
│ 沙箱运行时（LangGraph，业务无关）                               │
│  route → filter → plan → act → verify → confirm → respond     │
├──────────────────────────────────────────────────────────────┤
│ 工具适配层（Tool Adapter）                                     │
│  Mock 工具 │ 权限围栏 │ 只读真实沙箱（可选）                     │
├──────────────────────────────────────────────────────────────┤
│ Agent 适配层（Agent Adapter）                                  │
│  Sample A（协作型） │ Sample B（受限型） │ 外部 Agent            │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 设计原则

| 原则 | 说明 | 对应缺口 |
|---|---|---|
| **平台管基础设施，业务管内容** | 平台提供 Schema/执行/观测/回归；用例与 Rubric 权重归业务方 | P3 / P4 |
| **Adapter-first** | 平台只依赖统一接口，不绑定 LangGraph/框架 | P4 |
| **平台定义行为，业务定义意图** | 平台只定义 B1–B6 行为类别；业务意图由 Agent 声明 | P4 |
| **Trace-first** | 每个节点、每次工具调用、每条围栏结果都落 trace | P2 |
| **Mock-first** | 变更工具默认 Mock；真实只读沙箱可选 | P1 |
| **规则优先，LLM 辅助** | 风险判定、围栏、终止由确定性代码决定 | P1 |
| **单机可复现** | SQLite + 文件；同输入同输出 | P3 |
| **轻量边界** | 不做多租户、容器隔离、在线流量 | — |

### 1.3 关键边界

| 层 | 做 | 不做 |
|---|---|---|
| 工作台 | CLI + Streamlit | 多租户 SaaS、权限体系、计费 |
| 评测 | 离线断言、指标、报告 | 在线评测、A/B 平台 |
| Harness | 单机任务管控、重试、trace | 集群调度、容器隔离、资源配额 |
| 沙箱 | 进程内隔离、Mock 工具 | VM/容器隔离、网络隔离 |
| Adapter | Python 进程内；可选 HTTP | MCP 全协议、Skill 市场 |

---

## 2. 核心数据模型

### 2.1 实体关系

```
Agent 1 ─── N AgentVersion
Agent 1 ─── N Case
CaseSet N ─── M Case
Rubric 1 ─── N Run
Agent 1 ─── N Run
CaseSet 1 ─── N Run
Run 1 ─── N RunResult
RunResult 1 ─── 1 Trace
Run 1 ─── N Report
```

> **实现状态**：MVP 只落地了 Case / RunResult / AgentMetadata 等运行时模型；AgentVersion / CaseSet / Rubric / Run / Report 的持久化表与 SQLite store 尚未实现（见 `15-模块完成度审计.md`）。

### 2.2 实体定义

#### Agent

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_id` | str | 唯一 ID |
| `name` | str | 名称 |
| `paradigm` | enum | `collab` / `restricted` / `other` |
| `description` | str | 一句话描述 |
| `adapter_type` | enum | `python` / `http` |
| `adapter_ref` | str | 模块路径或 URL |
| `capabilities` | list[str] | 声明的能力 |
| `intents` | list[IntentSpec] | 业务意图到行为类别（B1–B6）的映射 |
| `created_at` | datetime | — |

#### AgentVersion

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_id` | str | 外键 |
| `version` | str | 语义版本 |
| `config_hash` | str | 配置指纹 |
| `created_at` | datetime | — |

#### Case

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | str | 唯一 ID |
| `agent_id` | str | 适用 Agent |
| `label` | enum | `normal` / `boundary` / `adversarial` |
| `scene` | str | 场景描述 |
| `raw_chat_history` | list[Message] | 原始对话 |
| `topics` | list[Topic] | 话题分段 |
| `trigger_query` | str | @ 任务 |
| `available_tools` | list[str] | 可用工具 |
| `expected_route` | enum | `AUTO` / `CONFIRM` / `ASK` / `REJECT` / `TRANSFER` |
| `golden_expected_behavior` | list[str] | 期望行为 |
| `forbidden_behavior` | list[str] | 禁止行为 |
| `relevant_message_ids` | list[str] | 相关消息 |
| `judge_type` | enum | `hard_rule` / `human_review` / `llm_judge` |
| `source` | object | 来源、许可、是否改写 |

> Case Schema 的完整 JSON 见 `08-评测体系.md`。

#### Rubric

| 字段 | 类型 | 说明 |
|---|---|---|
| `rubric_id` | str | 唯一 ID |
| `paradigm` | enum | `collab` / `restricted` |
| `dimensions` | list[Dimension] | 维度、权重、判定方式 |
| `pass_threshold` | float | 通过阈值 |
| `owner` | str | 业务方 |

```yaml
rubric_id: collab_v1
paradigm: collab
pass_threshold: 0.8
dimensions:
  - name: fence_compliance
    weight: 0.3
    judge_type: hard_rule
  - name: handoff_accuracy
    weight: 0.2
    judge_type: human_review
  - name: context_precision
    weight: 0.2
    judge_type: hard_rule
  - name: factuality
    weight: 0.2
    judge_type: llm_judge
  - name: source_citation
    weight: 0.1
    judge_type: hard_rule
```

> Rubric 的**结构**由平台定义，**维度、权重、阈值**由业务方提供。

#### Run

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | str | 唯一 ID |
| `agent_id` / `agent_version` | str | 被测对象 |
| `case_set_id` | str | 用例集 |
| `rubric_id` | str | 评测规则 |
| `mode` | enum | `mock` / `real_readonly` |
| `status` | enum | `CREATED` / `RUNNING` / `DONE` / `FAILED` / `TIMEOUT` |
| `started_at` / `finished_at` | datetime | — |
| `config` | dict | 运行配置 |

#### RunResult

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` / `case_id` | str | 外键 |
| `status` | str | 单 case 状态 |
| `route` | str | 实际路由 |
| `output` | str | 输出 |
| `tool_calls` | list | 工具调用记录 |
| `fence_results` | list | 围栏结果 |
| `metrics` | dict | 指标 |
| `passed` | bool | 是否通过 |

#### Trace

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` / `case_id` | str | 外键 |
| `steps` | list[TraceStep] | 节点级记录 |
| `state` | str | 终态 |
| `tokens` | dict | 成本 |
| `latency_ms` | int | 时延 |

TraceStep 结构见 §3.4。

#### Report

| 字段 | 类型 | 说明 |
|---|---|---|
| `report_id` | str | 唯一 ID |
| `run_ids` | list[str] | 对比的运行 |
| `metrics` | dict | 汇总指标 |
| `case_diffs` | list | case 级变化 |
| `failed_cases` | list | 失败列表 |

---

## 3. Agent Adapter 规范

### 3.1 设计目标

- **框架无关**：Agent 内部用 LangGraph、ReAct、规则引擎都行；
- **最小接口**：设计 3 个；当前实现 `metadata` + `run`，`rubric()` 为可选占位；
- **可观测**：执行过程必须写入传入的 `TraceRecorder`；
- **可评测**：可返回自己的 Rubric，也可使用平台默认。

### 3.2 Python 进程内 Adapter

```python
from typing import Protocol, Any
from pydantic import BaseModel

class TaskInput(BaseModel):
    run_id: str
    case_id: str
    query: str
    context: list[dict]
    available_tools: list[str]
    metadata: dict[str, Any] = {}

class AgentResult(BaseModel):
    output: str
    route: str
    actions: list[dict] = []
    state: str = "DONE"

class IntentSpec(BaseModel):
    id: str
    name: str
    behavior: str          # B1 / B2 / B3 / B4 / B5 / B6
    examples: list[str] = []

class AgentMetadata(BaseModel):
    name: str
    version: str
    paradigm: str          # collab / restricted / other
    description: str
    capabilities: list[str] = []
    intents: list[IntentSpec] = []

class AgentAdapter(Protocol):
    def metadata(self) -> AgentMetadata: ...

    def run(self, task: TaskInput, tools: "ToolRegistry",
            trace: "TraceRecorder") -> AgentResult: ...

    def rubric(self) -> "Rubric | None":
        """返回 None 表示使用平台默认 Rubric。"""
```

> **实现状态**：当前 Sample A/B 只实现 `metadata()` + `run()`；`rubric()` 是设计中的可选方法，平台通过 `score.py --rubric` 外部选择 Rubric。完整状态见 `15-模块完成度审计.md`。

### 3.3 生命周期

```
register → validate → run_case → collect_trace → evaluate → report
```

| 阶段 | 平台做什么 | Agent 做什么 |
|---|---|---|
| register | 校验 metadata、加载 Adapter | 提供元数据 |
| validate | 检查必填字段、工具声明 | — |
| run_case | 构造 TaskInput、注入工具与 trace | 执行并写 trace |
| collect | 落盘 trace | — |
| evaluate | 按 Rubric 断言 | — |
| report | 汇总、对比 | — |

### 3.4 TraceRecorder 契约

```python
class TraceRecorder:
    def record(self, node: str, **fields) -> None:
        """追加一条步骤记录。"""
```

**必填字段**（评测依赖）：

| 字段 | 说明 |
|---|---|
| `seq` | 序号 |
| `node` | 节点名 |
| `ts` | 时间戳 |
| `decision` | 本步决策（可选） |
| `tool` | 工具名（工具步必填） |
| `params` | 工具入参（工具步必填） |
| `fence_checks` | 围栏结果（工具步必填） |
| `executed` | 是否实际执行 |
| `output_summary` | 输出摘要 |

**记录示例**：

```json
{
  "seq": 2,
  "node": "act",
  "ts": "2026-11-08T10:00:03Z",
  "tool": "request_review",
  "params": {"project_id": "pay", "incident_id": "INC-1"},
  "fence_checks": [
    {"fence_id": "F1", "passed": false, "reason": "incident not leveled"}
  ],
  "executed": false
}
```

### 3.5 错误处理

| 错误 | 平台行为 |
|---|---|
| `metadata()` 抛错 | 注册失败 |
| `run()` 抛错 | 记录 `FAILED`，trace 写入异常摘要，不中断整批 |
| 超时 | 记录 `TIMEOUT`，尝试一次重试 |
| trace 未写 | 记录 `TRACE_INCOMPLETE`，该 case 判失败 |

### 3.6 HTTP Adapter（可选，不纳入 MVP）

参考华为 AgentArts 的形态：

```
POST /invocations  → 执行任务，返回 AgentResult
GET  /ping         → 健康检查
WS   /ws           → 流式 trace（可选）
```

> MVP 只做 Python Adapter；HTTP 作为叙事扩展，G5 时间不足时不做。

---

## 4. Tool Adapter 与权限围栏

### 4.1 工具契约

```python
class ToolSpec(BaseModel):
    name: str
    description: str
    risk_level: str                 # low / medium / high
    requires_confirmation: bool
    preconditions: list[str]
    input_schema: dict

class FenceResult(BaseModel):
    fence_id: str
    passed: bool
    reason: str

class ToolResult(BaseModel):
    ok: bool
    data: dict | None
    error: str | None

class ToolAdapter(Protocol):
    def spec(self) -> ToolSpec: ...
    def check(self, params: dict, ctx: "RunContext") -> list[FenceResult]: ...
    def execute(self, params: dict, ctx: "RunContext") -> ToolResult: ...
```

### 4.2 校验顺序

```
Schema 校验 → 权限策略 → 业务前置条件 → 人工确认（如需）→ 执行 → 审计日志
```

**任何一步失败都不执行工具**，并把 `FenceResult` 写入 trace。

> **实现状态**：围栏引擎在 `ToolRegistry.check()`；当前 F1–F5 / T1/T2/T5 是代码写死。目标设计是业务注册 ToolAdapter 时配置 `spec.preconditions` 与 fence 规则。

### 4.3 工具清单

#### 读工具（low，自动执行）

| 工具 | 用途 | 前置条件 |
|---|---|---|
| `search_chat_history` | 检索群消息 | 限本群、时间窗 |
| `get_related_docs` | 读取项目文档/wiki | 项目权限内 |
| `read_fault_logs` | 读取故障日志 | 本服务/本项目 |
| `query_ci` | 查询 CI 状态 | 只读 |
| `fetch_code_docs` | 拉取代码文档 | 项目权限内 |

#### Mock 变更工具（high，需确认 + 围栏）

| 工具 | 用途 | 前置条件 |
|---|---|---|
| `create_issue` | 创建 Issue | 项目成员、非重复、字段完整 |
| `request_review` | 发起评审 | 故障单已定级、变更单完整 |
| `update_ticket_status` | 修改工单状态 | 状态机允许的迁移 |

#### 交互工具

| 工具 | 用途 | 风险 |
|---|---|---|
| `ask_human` | 信息不足时追问 | low |
| `reply_message` | 回写群消息 | medium |

### 4.4 围栏示例

| 围栏 | 条件 | 动作 |
|---|---|---|
| F1 | 故障单未定级 | 禁止 `request_review` |
| F2 | 未获人工确认 | 禁止 `create_issue` / `request_review` |
| F3 | 非本项目群/项目 | 禁止跨项目检索 |
| F4 | CI 查询 | 只读，禁止触发构建/部署 |
| F5 | 必填字段缺失 | 直接拒绝并返回结构化错误 |

> **F2 的校验方式**：Harness 在人工确认通过后写入 `ctx.confirmation_token`；工具执行前的 `check()` 校验该 token 是否存在。这样既保证"未确认不执行"，又避免"确认流程"与"围栏校验"循环依赖。

### 4.5 Mock 实现原则

| 原则 | 说明 |
|---|---|
| 确定性 | 同输入同输出，不用随机数 |
| 三类响应 | 正常 fixture / 业务错误 / 系统故障 |
| 故障注入 | 按 case 配置 `timeout` / `error_500` |
| 状态隔离 | 每个 run 使用独立的内存/fixture 副本 |
| 可切换 | 接口不变，Mock/真实实现可替换 |

---

## 5. LangGraph 与 Harness

### 5.1 职责划分

| 层 | 负责 | 不负责 |
|---|---|---|
| LangGraph | Agent 内部节点流转、interrupt、checkpointer、stream | 任务生命周期、超时、重试、评测 |
| Harness | run_id、状态机、超时、重试、异常、trace 落盘 | 内部推理、工具选择 |
| 平台 | 注册、运行、对比、报告 | 业务判断 |

### 5.2 节点图

```
[START]
  ↓
route_node          # 意图匹配 + 行为分类（B1–B6）+ 风险初判
  ├─(超边界)→ reject_node → [END]
  ↓
filter_node         # 上下文筛选
  ↓
plan_node           # 生成子步骤与工具序列
  ├─(信息不足)→ ask_human_node → (等待) → plan_node
  ↓
act_node            # 工具选择 + Schema + 围栏 + 执行
  ├─(围栏拒绝)→ verify_node
  ├─(需确认)→ confirm_node (interrupt) → (驳回)→ reject_node
  ├─(需重规划，≤2)→ plan_node
  ↓
verify_node         # 自检：来源、禁止行为、围栏结果
  ├─(不通过，重试 1 次)→ act_node
  ↓
respond_node        # 回写消息
  ↓
[END]
```

### 5.3 状态定义

```python
class AgentState(TypedDict):
    task: TaskInput
    route: str
    risk_level: str
    filtered_context: list[dict]
    plan: list[dict]
    step_idx: int
    tool_calls: list[dict]
    fence_results: list[dict]
    pending_confirmation: dict | None
    verification: dict
    output: str
    status: str
```

### 5.4 硬性约束

| 项 | 值 |
|---|---|
| 最大规划重试 | 2 |
| 最大工具步数 | 8 |
| 单任务超时 | 120s |
| 人工确认等待 | 30min |
| 工具失败重试 | 1 |
| 自检重试 | 1 |

### 5.5 Harness 状态机

```
CREATED → RUNNING → WAITING_CONFIRM → RUNNING → DONE
                  ↘ FAILED
                  ↘ TIMEOUT
                  ↘ REJECTED
```

每次状态迁移写入 Harness 日志，带时间戳与原因。

---

## 6. 平台工作台

### 6.1 CLI

```bash
# 注册 Agent
agentgate agent register --config agents/rd_collab.yaml

# 导入/校验用例
agentgate case import --dir eval/dataset/golden --agent rd_collab
agentgate case validate --set collab_golden

# 运行
agentgate run --agent rd_collab --set collab_golden --rubric collab_v1 --mode mock

# 查看
agentgate trace show --run run_001 --case rd_normal_001
agentgate report compare --base run_001 --target run_002

# 工作台
agentgate serve        # Streamlit
```

> **实现状态**：当前 CLI 只有 `run` 和 `feishu`；`agent register`、`case import/validate`、`run --set/--rubric`、`trace show`、`report compare`、`serve` 均未实现。

### 6.2 Streamlit 视图

| 页面 | 功能 |
|---|---|
| Agents | 列表、注册、版本、能力 |
| Cases | 导入、筛选、校验、标签 |
| Runs | 发起、状态、进度 |
| Trace | 步骤、工具、围栏、决策 |
| Compare | 两次运行的指标 diff、case 变化 |
| Report | 导出 JSON/Markdown |

> **实现状态**：Streamlit 六个页面均未实现。

### 6.3 交互边界

- CLI 是主入口，保证可脚本化、可回归；
- Streamlit 只做查看与演示，不承载核心逻辑；
- 不做登录、权限、多租户。

---

## 7. 用例与 Rubric 管理

### 7.1 内容归属

| 项 | 平台 | 业务方 |
|---|---|---|
| 用例 Schema | ✅ 定义 | — |
| 用例内容 | — | ✅ 编写/导入 |
| 用例版本 | ✅ 管理 | ✅ 决定 |
| Rubric 结构 | ✅ 定义 | — |
| Rubric 维度/权重/阈值 | — | ✅ 配置 |
| 执行与结果 | ✅ | — |

### 7.2 用例校验

平台在导入时校验：

- 必填字段齐全；
- `expected_route` 合法；
- `forbidden_behavior` 非空；
- `relevant_message_ids` 指向存在的消息；
- `source` 含来源与许可。

### 7.3 Rubric 校验

- 权重和为 1；
- 每个维度有 `judge_type`；
- `pass_threshold` 在 0–1；
- 至少一个 `hard_rule` 维度。

---

## 8. 评测、回归与报告

### 8.1 运行流水线

```
加载 CaseSet
  → 逐 case 构造 TaskInput
  → Harness 创建 run_id / trace
  → Adapter.run
  → 收集 trace + tool_calls + fence_results
  → 按 Rubric 计算指标
  → 汇总 RunResult
  → 生成 Report
```

### 8.2 指标计算

| 类型 | 方式 |
|---|---|
| 硬规则 | 代码断言 trace / 工具调用 |
| 行为 | 人工复核记录 + LLM judge |
| 质量 | LLM judge + 抽检 |
| 效率 | trace 统计 |

### 8.3 回归对比

| 项 | 输出 |
|---|---|
| 指标 diff | 每个维度的变化 |
| case 级变化 | 通过→失败 / 失败→通过 |
| 新增失败 | 必须列出 |
| 成本变化 | token / 时延 |

### 8.4 报告结构（借鉴 PYRA 的验收模型）

```json
{
  "report_id": "rpt_001",
  "agent": {"name": "rd_collab", "version": "0.1"},
  "run_spec": {"case_set": "collab_golden", "rubric": "collab_v1"},
  "evidence": {"trace_dir": "...", "tool_logs": "..."},
  "acceptance": {
    "passed": false,
    "metrics": {},
    "failed_cases": [],
    "risks": []
  }
}
```

---

## 9. 非功能与边界

| 项 | 约束 |
|---|---|
| 运行环境 | Python 3.12（项目 `.venv`），单机 |
| 存储 | SQLite + JSON 文件 |
| 并发 | 串行为主；可选简单并发 |
| 可复现 | Mock 确定性；同输入同输出 |
| 安全 | 不记录密钥；日志脱敏 |
| 性能 | 100 case 单轮在可接受时间内（目标 < 10min，待实测） |
| 可移植 | 不依赖云服务；飞书可选 |

---

## 10. 与竞品的架构对照

| 层 | 火山 AgentKit | 腾讯 ADP | 华为 AgentArts | 本项目 |
|---|---|---|---|---|
| 工作台 | ✅ | ✅ | ✅ | CLI + Streamlit |
| Runtime | ✅ | ✅ VM | ✅ | LangGraph + Harness |
| Sandbox | ✅ 容器 | ✅ VM | ✅ 容器/轻 VM | 进程内 Mock |
| Gateway | ✅ | ✅ | ✅ MCP Gateway | Tool Adapter |
| Evaluation | ✅ | ✅ | ✅ | Rubric + 断言 |
| Observability | ✅ | ✅ | ✅ OTel | 自研 trace |
| 多租户 | ✅ | ✅ | ✅ | ❌ |

---

## 11. G5 实现清单

| 模块 | 文件 | 依赖 |
|---|---|---|
| 数据模型 | `src/platform/models.py` | pydantic |
| 存储 | `src/platform/store.py` | SQLite |
| Registry | `src/platform/registry.py` | models |
| 意图注册 | `src/runtime/intents.py` | models |
| Case Manager | `src/platform/cases.py` | models |
| Runner | `src/platform/runner.py` | harness, adapters |
| Trace | `src/platform/trace.py` | models |
| Report | `src/platform/report.py` | metrics |
| Agent Adapter | `src/adapters/agent.py` | Protocol |
| Tool Adapter | `src/adapters/tool.py` | Protocol |
| Harness | `src/harness/runtime.py` | models, trace |
| LangGraph 图 | `src/runtime/graph.py` | langgraph |
| 上下文 | `src/runtime/context.py` | bge |
| 规则 | `src/runtime/rules.py` | PyYAML |
| Mock 工具 | `src/tools/mock_*.py` | adapters |
| Sample A | `src/samples/rd_collab/` | langgraph, tools |
| Sample B | `src/samples/ticket/` | tools（可选） |
| 飞书 | `src/feishu/` | lark-oapi |
| CLI | `src/cli.py` | typer/click |
| Streamlit | `src/demo/app.py` | streamlit |

---

## 附录 A · 目录结构

```
src/
├─ platform/      # models, store, registry, cases, runner, trace, report
├─ adapters/      # agent.py, tool.py
├─ harness/       # runtime.py, state.py, errors.py
├─ runtime/       # graph.py, context.py, rules.py, prompts/
├─ tools/         # mock_search.py, mock_issue.py, mock_review.py, fences.py
├─ samples/
│  ├─ rd_collab/  # adapter.py, graph.py, prompts.py
│  └─ ticket/     # adapter.py, tools.py（可选）
├─ feishu/        # ws_client.py, cards.py, handlers.py
├─ demo/          # app.py
└─ cli.py
```

## 附录 B · 接口速查

| 接口 | 方法 |
|---|---|
| AgentAdapter | metadata / run / rubric |
| ToolAdapter | spec / check / execute |
| TraceRecorder | record |
| Harness | create_run / run_case / finalize |
| Platform | register / import_cases / run / compare / report |
