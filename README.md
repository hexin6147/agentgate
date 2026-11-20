# AgentGate

> **Agent 上线门禁与离线评测沙箱**
> 一个轻量、可运行的 Agent 运行治理与评测平台 POC。
> **名字说明**："上线门禁"不是独立模块，是围栏 + Rubric 硬门槛 + 回归对比的组合概念；"离线评测沙箱"对应 Harness + Mock 工具 + trace + 数据集。
> Python 3.12 · LangGraph · pydantic · lark-oapi · Ollama（Qwen2.5-7B + BGE）
> 测试：**127 passed**

---

## 一分钟速览

**一句话**：业务 Agent 从 Demo 到生产，瓶颈不是"能不能生成"，而是**能不能被管住、被看见、被回归、被复用**。

**四条链路**（瓶颈 → 痛点 → 缺口 → 模块 → 需求 → 代码 → 测试 → 指标 → 状态）：

```
P1 管控规则不可配置
  B/C/E 业务约束·人机协同·工具链路
  → SOP 不遵守 / 越权 / 交接不稳
  → 规则引擎 + 工具围栏 + 人工确认
  → FR-13/14/18
  → rules.py / tools.py / feishu.py
  → test_tools / test_ticket_tools / test_feishu
  → fence_interception / false_block / handoff
  → 🟡 引擎有，业务配置/超时/冲突仲裁没做

P2 过程不可观测
  A/D/E/G 确定性·上下文·工具·成本
  → 幻觉 / 噪声 / 工具失败 / 成本不可控
  → Harness + trace + context + judge
  → FR-08/09/17/18
  → harness.py / trace.py / context.py / judge.py
  → test_core / test_context / test_harness / test_judge
  → trace_completeness / recall / drift（无关混入率）/ factuality
  → 🟡 trace/context 有，timeout/retry/cost/viewer 没做

P3 结果不可回归
  A/F 确定性·评测迭代
  → 无 golden / badcase 难归因 / 修 A 坏 B
  → 用例 + 评测 + 回归 + Rubric
  → FR-03/04/05/06/07/10/11
  → schema.py / runner.py / evaluation.py / rubric.py
  → test_evaluation / test_rubric / test_dataset
  → pass_rate / behavior/route / new_failures / Rubric
  → 🟡 评测/Rubric 有，CaseSet/版本/Markdown/CI 没做

P4 评测基础设施不可复用
  F/H 评测迭代·组织协作
  → 每类 Agent 单独评测 / 口径不一 / 重复造轮子
  → Adapter + 双示例 + Rubric
  → FR-01/02/05/12/15/16
  → factory.py / samples/rd_collab / samples/ticket / rubric.py
  → test_factory / test_ticket_agent / test_rubric
  → Sample B 通过率 / Rubric 可配置数 / 接入耗时
  → 🟡 双范式/Rubric 有，注册/版本/HTTP/覆盖性验证没做
```

**分层结论**：机制层（接入 / 执行 / trace / 判定 / 回归）四个缺口都通了；配置层（围栏、Evaluator 可配）和管理层（注册、版本、CaseSet）没通。详见 [15 §1](docs/15-模块完成度审计.md)。

**两类示例**：

| 示例 | 范式 | 工具 | 红线 | 结果 |
|---|---|---|---|---|
| Sample A 研发协作 Agent | 协作型 | 群聊检索、CI、Mock 变更 | F1–F5 | dev 86/86；held-out 规则版 60% → LLM 版 100% |
| Sample B 售后工单 Agent | 受限型 | 订单、政策、工单 | T1/T2/T5 | 24/24，越权拦截 100% |

**最重要的结论，以及最重要的保留**：

> 同一套 Harness / LangGraph / 评测脚本，评了两类不同范式的 Agent。
> 但我不会说"100% 解决了"——dev 的 100% 有 in-sample 成分，held-out 只有 20 条，评测集是 synthetic template。详见 [§6](#6-评测结果) 和 [§8](#8-局限与后续)。

---

## 目录

1. [问题定义](#1-问题定义)
2. [对标分析](#2-对标分析)
3. [方案架构](#3-方案架构)
4. [模块详细设计](#4-模块详细设计)
5. [评测体系](#5-评测体系)
6. [评测结果](#6-评测结果)
7. [迭代闭环](#7-迭代闭环)
8. [局限与后续](#8-局限与后续)
9. [如何运行](#9-如何运行)
10. [文档索引](#10-文档索引)

---

## 1. 问题定义

### 1.1 业务 Agent 投产的 8 类瓶颈

| 瓶颈 | 表现 |
|---|---|
| 能力与确定性 | 同一输入结果不同、长链路误差、幻觉 |
| 业务约束与合规 | SOP 不遵守、越权、无法追溯 |
| 人机协同 | 何时转人工、追问、拒绝，不稳定 |
| 上下文与知识 | 群聊噪声、跨项目污染、窗口限制 |
| 工具与系统集成 | 参数错误、超时、链路传导 |
| 评测与迭代 | 无 golden、badcase 无法归因、修 A 坏 B |
| 成本与性能 | token、延迟、并发 |
| 组织与协作 | 口径不一、重复造轮子 |

### 1.2 平台收敛出的四个缺口

| 缺口 | 表现 | 平台模块 |
|---|---|---|
| P1 管控规则不可配置 | 交接、权限、工具边界写死 | 规则引擎 + 围栏 |
| P2 过程不可观测 | 拿不到结构化中间状态 | Harness + trace |
| P3 结果不可回归 | 无批量用例、无版本对比 | 用例管理 + 回归 |
| P4 评测不可复用 | 每类 Agent 单独做一套 | Adapter + Rubric |

### 1.3 平台统一什么 vs 业务方自有什么

> **平台不提供万能用例。** 不同业务的 SOP、判定标准、红线完全不同。

| 平台统一提供 | 业务方负责 |
|---|---|
| Adapter 协议、沙箱、Harness、trace | Agent 实现、工具契约 |
| 用例 Schema、执行、结果存储 | **用例内容、golden、业务场景** |
| Rubric 引擎、配置格式 | **评分维度、权重、判定标准** |
| 批跑、回归、报告 | 验收门槛 |

---

## 2. 对标与定位

### 2.1 需求侧证据：成品 SaaS 的边界（非竞品）

> Claude Tag / 豆包工作伙伴是 **Agent 产品**，不是管控/评测平台。
> 把它们当竞品是类别错误——这一节的用途是证明"企业已在部署业务 Agent，但执行链路封闭"，不是对比功能。

| 层 | Claude Tag / 豆包工作伙伴 | 本项目 |
|---|---|---|
| 业务配置 | ✅ 人设、角色、技能、权限、@触发、审计 | ✅ |
| 执行链路 trace | ❌ 无结构化导出 | ✅ 全链路 JSON |
| 调度 | ❌ 不可替换状态机 | ✅ LangGraph + 自研 Harness |
| 人机规则 | ❌ 内置逻辑 + prompt | ✅ 规则引擎 |
| 批量回归 | ❌ 无原生支持 | ✅ |
| 第三方 Agent | ❌ | ✅ Adapter |

### 2.2 真正的竞品：平台厂商与工具

**平台厂商**：公开资料显示，火山 AgentKit、美团 Agent 评测平台、腾讯云 ADP、阿里云 Agent Sandbox、华为 AgentArts、Pyra 都在建「运行沙箱 + trace + 用例/Rubric + 回归」。它们的产品化重点同样是**评测基础设施**，不是内置万能用例。

**工具类**：LangSmith / LangFuse 强在 trace 与离线评测，但不做执行前拦截；Guardrails / NeMo Guardrails 强在运行时拦截，但不做评测与回归。

本项目的差异不在"更大"，而在：

- 把「执行前围栏」与「回归门禁」接在同一条 trace 上；
- 轻量、可运行、个人可复现；
- 双范式示例；
- 明确简化点，不吹"对标大厂"。

### 2.3 形态选择：平台，不是应用（非竞品对比）

> 这是立项时的**产品形态选择**，不是与某类产品的对比。

| 维度 | 应用 | 平台 |
|---|---|---|
| 核心对象 | 一个 Agent | 任意 Agent + 评测基础设施 |
| 价值 | 这个 Agent 好用 | 平台能接入、观测、回归不同 Agent |
| 用例归属 | 应用自带 | **业务方自带** |
| 面试叙事 | "我做了个机器人" | "我做的是上线门禁" |

---

## 3. 方案架构

```
┌──────────────────────────────────────────────────────────────┐
│ 平台工作台（CLI / Streamlit）                                  │
│  Agent 注册 │ 用例管理 │ 批量运行 │ trace 查看 │ 回归对比        │
├──────────────────────────────────────────────────────────────┤
│ 评测层                                                        │
│  Rubric 配置 │ 断言执行 │ 指标计算 │ 报告生成 │ 版本对比         │
├──────────────────────────────────────────────────────────────┤
│ Harness 运行时管控（自研）                                      │
│  run_id │ 状态机 │ 超时 │ 重试 │ 异常 │ trace 落盘              │
├──────────────────────────────────────────────────────────────┤
│ LangGraph 编排                                                 │
│  route → filter → plan → act → verify → respond               │
├──────────────────────────────────────────────────────────────┤
│ 工具适配层                                                     │
│  Mock 工具 │ F1–F5 / T1/T2/T5 围栏 │ 只读真实沙箱（可选）        │
├──────────────────────────────────────────────────────────────┤
│ Agent 适配层                                                   │
│  Sample A（协作型） │ Sample B（受限型） │ 外部 Agent            │
└──────────────────────────────────────────────────────────────┘
```

**设计原则**：

| 原则 | 说明 |
|---|---|
| Adapter-first | 平台只依赖 2 个必需方法，不绑定框架 |
| Trace-first | 每节点、每工具、每围栏都落 trace |
| Mock-first | 变更工具默认 Mock，零副作用 |
| 规则优先 | 允许/确认/拒绝/终止由代码决定 |
| 平台定义行为，业务定义意图 | 平台只定义 B1–B6，业务声明自己的 intents |
| 内容归业务方 | 平台给用例/Rubric 骨架，不给通用内容 |

---

## 4. 模块详细设计

> 完整的「实现 / 简化 / 工业补齐」见 [docs/14-简化点与工业补齐.md](docs/14-简化点与工业补齐.md)。

### 4.1 Agent Adapter

```python
metadata() -> AgentMetadata
run(task, tools, trace) -> AgentResult
rubric() -> Rubric | None
```

> 设计 3 个；当前 Sample A/B 只实现 `metadata + run`，`rubric()` 是可选占位，Rubric 由 `score.py` 外部传入。

**原型实现**：鸭子类型；Sample A/B 各实现 `metadata + run`。
**简化点**：进程内调用，无 HTTP/gRPC、无沙箱隔离、无版本热加载。
**工业补齐**：远程 Agent 注册、版本灰度、能力发现、资源配额。

### 4.2 行为分类 B1–B6 + 业务意图

| 编号 | 行为 | 默认动作 |
|---|---|---|
| B1 | 读取/检索 | 自动 |
| B2 | 生成/汇总/草稿 | 自动（人审核） |
| B3 | 结论/建议/定级 | 人工确认 |
| B4 | 写入/变更 | 围栏 + 确认 |
| B5 | 超边界 | 拒绝 |
| B6 | 信息不足 | 追问 |

业务意图由 Agent 声明，映射到 B1–B6。平台不定义"客服的查订单"或"研发的汇总风险"。

### 4.3 规则引擎 R1–R6

| 规则 | 行为 | 动作 |
|---|---|---|
| R1 | B1/B2 | AUTO |
| R2 | B3 | CONFIRM |
| R3 | B6 | ASK |
| R4 | B5 | REJECT |
| R5 | B4 | CONFIRM + 围栏 |
| R6 | 冲突 | R4 > R2 > R5 > R3 > R1 |

### 4.4 Mock 工具与围栏

**Sample A**：5 读 + 3 Mock 变更 + 2 交互；F1–F5（定级、确认令牌、跨项目、CI 只读、必填）。
**Sample B**：3 工单工具；T1 身份、T2 赔付额度、T5 跨用户；复用 F2/F5。

**原则**：Schema → 权限 → 前置条件 → 人工确认 → 执行 → 审计；同输入同输出；故障可注入。

> 当前围栏是代码写死；目标设计是业务注册工具时配置 schema / 风险级 / 前置条件 / 确认要求。

### 4.5 Harness 与 trace

- 已实现：`run_id`、case context 合并、异常隔离、trace 落盘；未实现：超时、重试、显式状态机。
- 每步记录 `seq/node/ts/decision/tool/params/fence_checks/executed`；
- 评测脚本只依赖 trace，不依赖日志文本。

### 4.6 LangGraph 编排

`route → filter → plan → act → verify → respond`，分支 `reject/ask/confirm`。
Harness 在外层，LangGraph 在内层；业务 Agent 可替换，图不变。

### 4.7 LLM 意图分类 + 摘要 + 护栏

- LLM 主分类（`qwen2.5:7b-instruct`），规则兜底；
- LLM 摘要要求引用 `[message_id]`，失败回退模板；
- 三类确定性护栏：写操作、模糊查询、汇总一致性；
- **动作与围栏仍由规则决定**。

### 4.8 BGE 语义上下文筛选

`bge-base-zh-v1.5` + cosine + top_k/threshold；embedding 失败回退规则筛选。
held-out 上 drift 23.3% → 17.2%，recall 100% → 95.6%。

### 4.9 飞书接入

- 长连接（lark-oapi）、@ 解析、群历史、回复；
- 交互卡片确认/驳回、回调、待确认任务；
- 使用 `tenant_access_token`，不需要 `user_access_token`。

### 4.10 评测

- 平台级 + Agent 级两类指标；
- 硬门槛 / 基线相对 / 业务推导 / 工程约束 / 待校准；
- 硬规则 / 人工复核 / LLM judge 三轨（人工复核已设计，**当前未执行**）；
- Rubric 加载/校验/加权/硬门槛：`src/agentgate/rubric.py`；
- 回归门禁：越权拦截 <100%、P0 对抗失败、trace 不完整、可复现失败 → 阻断。

---

## 5. 评测体系

### 5.1 数据集

| 数据集 | 数量 | 用途 |
|---|---|---|
| `eval/dataset` | 86 | Sample A dev：normal 37 / boundary 24 / adversarial 25 |
| `eval/heldout` | 20 | Sample A held-out，不参与关键词设计 |
| `eval/dataset_ticket` | 24 | Sample B：normal 8 / boundary 8 / adversarial 8 |

> **数据真实性**：当前 86/20/24 几乎全是 synthetic template + 2 条手写；未下载公开语料，`source.url` 为空。公开数据源见 `04`，接入是下一步。

### 5.2 指标

**平台级**：接入耗时、trace 完整率、回归自动化率、运行可复现率、Rubric 可配置数。

**Agent 级**：意图/行为/规则准确率、越权拦截率、误拦截率、上下文召回/漂移、交接准确率、事实忠实度、来源标注率。

> 平台级指标评平台，Agent 级指标评被测 Agent；同一报告，不同对象。Rubric 加权只用 Agent 级指标。

### 5.3 硬门槛

| 门槛 | 条件 |
|---|---|
| 越权拦截 | 100% |
| 红线合规 | 100% |
| trace 完整 | 100% |
| 可复现 | 100% |

> 硬门槛优先于加权分：越权拦截不达标，加权分再高也失败。

### 5.4 三轨判定

| 方式 | 适用 |
|---|---|
| 硬规则 | 越权、工具参数、路由、trace、来源 |
| 人工复核（已设计，**未执行**） | 交接时机、不必要介入、争议；当前 24 条 `human_review` 实际仍由 LLM judge 判定 |
| LLM judge（已实现） | 事实忠实度、来源支撑、交接时机、禁止行为；`--judge llm` |

> 越权/参数/路由不允许 judge 单独定论。
> **口径说明**：`judge_coverage` 显示 100%，但这个数字把"有人判过"和"该由人判的由人判了"混在一起；人评覆盖率实际是 0。详见 [20](docs/20-人评机评协同.md) §9。

---

## 6. 评测结果

### 6.1 核心结果

| 场景 | 配置 | passed | fence | false block | 说明 |
|---|---|---|---|---|---|
| Sample A dev | 规则 + 关键词筛选 | 86/86 | 100% | 0% | **in-sample**（关键词按 dev 失败调过） |
| Sample A held-out | 规则 | 12/20 (60%) | 75% | 44.4% | 规则版泛化不足 |
| Sample A held-out | LLM + 关键词筛选 | 20/20 | 100% | 0% | 5 条曾做探针 |
| Sample A held-out | LLM + BGE | 20/20 | 100% | 0% | drift 17.2%，recall 95.6% |
| Sample A held-out | LLM + BGE + judge | 20/20 | 100% | 0% | factuality 93.3%，handoff 100%，judge 判出 1 条违规 |
| Sample A dev | LLM + BGE + 护栏 | 86/86 | 100% | 0% | **in-sample**（护栏按 dev 失败设计） |
| Sample B dev | 规则 | 24/24 | 100% | 0% | 受限范式基线 |

### 6.2 关键发现

1. **规则版泛化差**：同集 100%，held-out 60%；
2. **LLM 分类器明显更好**：同一 held-out，60% → 100%；
3. **规则仍然必要**：围栏/动作/终止不能交给 LLM；
4. **BGE 降噪有效**：drift 23.3% → 17.2%，代价是 recall 100% → 95.6%；
5. **来源标注仍是短板**：held-out 66.7%，dev 73.3%；
6. **平台通用性成立**：Sample B 24/24，换的只是 Adapter/Tools/Rubric；
7. **judge 补上语义质量**：factuality 93.3%，抓到 1 条硬规则漏掉的"纳入闲聊"；但同族模型有自偏好风险；
8. **Rubric 加权可用**：规则 dev 0.882 通过；规则 held-out 0.621 被硬门槛拦下；LLM+BGE+judge 0.887；Sample B 1.000；
9. **围栏的贡献可量化（消融）**：关掉围栏后，33 条对抗用例中有 **23 条真的执行了高危写操作**；打开后 **0 条**。45 条正常用例两种模式表现一致。详见 [09i](docs/09i-消融实验-围栏.md)。

### 6.3 诚实的保留

- dev 的 100% 有 in-sample 成分；
- held-out 只有 20 条，且 5 条在实现前做过探针；
- 评测集是合成的，不代表真实业务分布；
- 摘要质量只看了样例，没有大规模人工复核；
- **三轨只跑了两轨**：人评 0 条，24 条 `human_review` 实际由 LLM judge 判定；
- **长链路未测**：当前是单轮用例 + 单次工具调用，没有步级/任务级/恢复级指标；
- **成本与延迟未采集**：`LLMClient.chat` 丢弃了 `response.usage`，所以成本数字是结构推算，不是账单。

---

## 7. 迭代闭环

```
v1 规则版 59/86 (68.6%)
  ↓ badcase 归因（5 组 27 条）
关键词 + 显式短语 + 最长匹配
  ↓
v2 规则版 86/86 (100%)
  ↓ held-out
规则版 12/20 (60%)  ← 过拟合被证实
  ↓ 接 LLM
LLM 版 20/20 (100%)
  ↓ 加 BGE
drift 23.3% → 17.2%
  ↓ dev 复跑
LLM+BGE 79/86 (91.9%)
  ↓ 加三类护栏
dev 86/86 (100%)，held-out 仍 20/20
```

每一步都有报告：`09`、`09b`、`09c`、`09d`、`09e`、`09f`。

---

## 8. 局限与后续

### 8.1 已知局限

| 局限 | 影响 |
|---|---|
| 合成数据 | 不代表真实业务分布 |
| dev 有 in-sample 调参 | 100% 不是泛化 |
| held-out 小且部分被探针 | 置信区间宽 |
| 无真实用户 | 需求可信度靠公开 JD/竞品 |
| Mock 工具 | 不验证真实系统集成 |
| 单机/单租户 | 不做权限、并发、配额 |
| Adapter 契约不完整 | 表面是 `metadata()` + `run()`，但 LangGraph 包装还会调用业务的 `_filter` / `_plan` / `_summarize` 等私有钩子；`factory.py` 用 `if/else` 注册，接第三个 Agent 要改平台 |
| 人评为 0 | 24 条 `human_review` 实际由 LLM 判，无一致率数据 |
| 长链路未支持 | 无多步用例，无步级/任务级/恢复级指标 |
| 成本/延迟未采集 | `usage` 与 `latency_ms` 未落 trace，无预算线 |
| CaseSet 无版本与冻结 | 用目录当用例集，held-out 的探针只能靠自觉标注 |
| 数据集为 synthetic | 未接公开语料，`source.url` 为空 |
| 业务配置层未实现 | 人设/角色/技能/权限/触发/审计只有零散对应 |
| 上线门禁无独立服务 | 是围栏 + 硬门槛 + 回归的组合概念 |
| restricted Rubric 的 answer_correctness 未定义 | 该维度缺失，权重被重归一化 |
| judge 与 agent 同族 | Qwen 7B 自偏好风险，未做人工一致性校验 |
| source_citation 未达标 | 摘要 prompt 与上下文筛选仍需优化 |
| Sample B 无 LLM 版 | 跨范式 LLM 对比未做 |

### 8.2 如果继续做

1. **人评一致性**：30 条双盲，算人机一致率与 κ，校准 judge（[20](docs/20-人评机评协同.md) §10）；
2. **held-out2 + 真实脱敏数据**：替换 synthetic，验证 LLM+护栏；
3. **长链路**：多步用例 + 步级/任务级/恢复级指标（[18](docs/18-业务指标与评测指标映射.md) §4.5）；
4. **成本与延迟采集**：`usage` → trace → 预算线（[19](docs/19-成本与延迟模型.md) §11）；
5. **配置层与管理层**：围栏/Evaluator 可配、注册、版本、CaseSet 冻结（[22](docs/22-Evaluator配置.md)、[25](docs/25-Agent接入SOP.md) §9）；
6. **摘要 prompt**：引用所有使用的 message_id，忽略无关闲聊；
7. **Streamlit / 生产化**：多租户、权限、真实系统适配、并发。

---

## 9. 如何运行

### 9.1 安装

```bash
cd /Users/xinhe/PycharmProjects/PythonProject/AgentGate
source .venv/bin/activate
pip install -r requirements.txt
```

### 9.2 测试

```bash
pytest -q
# 127 passed
```

### 9.3 离线评测

```bash
# Sample A：规则版
.venv/bin/python eval/scripts/score.py \
  --agent rule --dataset eval/dataset \
  --out eval/results/report_v2.json

# Sample A：LLM + BGE
.venv/bin/python eval/scripts/score.py \
  --agent llm --context bge --dataset eval/heldout \
  --out eval/results/heldout_llm_bge_report_v2.json

# Sample B：工单
.venv/bin/python eval/scripts/score.py \
  --agent ticket --dataset eval/dataset_ticket \
  --out eval/results/sample_b_report.json
```

### 9.4 飞书

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
AGENTGATE_AGENT=llm      # rule / llm
AGENTGATE_CONTEXT=bge    # rule / bge
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:7b-instruct
EMBEDDING_MODEL=quentinz/bge-base-zh-v1.5:latest
```

```bash
.venv/bin/python run.py feishu
```

### 9.5 目录

```
src/agentgate/        # 平台核心：models/schema/trace/tools/intents/rules/harness/eval/llm/context/langgraph
src/samples/rd_collab # Sample A
src/samples/ticket    # Sample B
eval/                 # 数据集、Rubric、脚本、报告
docs/                 # 00–31 文档
tests/                # 127 个测试
```

---

## 10. 文档索引

| 文档 | 内容 |
|---|---|
| [00-产品经理工作计划全景](docs/00-产品经理工作计划全景.md) | 8 周计划、阶段门、文档规范 |
| [00-立项书](docs/00-立项书.md) | 问题假设、投资决策、Go/No-Go |
| [01-问题定义](docs/01-问题定义.md) | 8 类瓶颈、四缺口、用户分层、指标树 |
| [02-竞品对标](docs/02-竞品对标.md) | 竞品角色分层、大厂平台、LangSmith 类工具、差异化 |
| [03-可行性预研](docs/03-可行性预研.md) | 飞书、LangGraph、Adapter、Mock、评测 |
| [04-数据源盘点](docs/04-数据源盘点.md) | 公开数据源、加工、合规 |
| [05-PRD](docs/05-PRD.md) | 18 条需求、验收标准 |
| [05-1-风险准入判定](docs/05-1-风险准入判定.md) | L0–L3、V1/V2 |
| [05-2-平台架构与Agent接入规范](docs/05-2-平台架构与Agent接入规范.md) | 分层、数据模型、Adapter/Tool 契约 |
| [06-人机协同规则](docs/06-人机协同规则.md) | B1–B6、R1–R6、冲突仲裁 |
| [07-流程图](docs/07-流程图.md) | 端到端、单任务、围栏、回归 |
| [08-评测体系](docs/08-评测体系.md) | 指标、Schema、Rubric、门禁 |
| [09-评测报告-v1](docs/09-评测报告-v1.md) | 规则版基线 |
| [09b-评测报告-heldout](docs/09b-评测报告-heldout.md) | 规则版 60% |
| [09c-评测报告-llm-heldout](docs/09c-评测报告-llm-heldout.md) | LLM 版 20/20 |
| [09d-评测报告-bge-context](docs/09d-评测报告-bge-context.md) | BGE 降 drift |
| [09e-评测报告-llm-dev-guards](docs/09e-评测报告-llm-dev-guards.md) | 护栏后 dev 86/86 |
| [09f-评测报告-sampleB](docs/09f-评测报告-sampleB.md) | 双范式验证 |
| [09g-评测报告-llm-judge](docs/09g-评测报告-llm-judge.md) | LLM-as-judge 实现与结果 |
| [09h-评测报告-rubric](docs/09h-评测报告-rubric.md) | Rubric 加权、硬门槛与结果 |
| [09i-消融实验-围栏](docs/09i-消融实验-围栏.md) | 关掉围栏：23/33 对抗用例执行高危写入 |
| [10-badcase归因](docs/10-badcase归因.md) | 5 组失败、根因、修复 |
| [11-迭代记录](docs/11-迭代记录.md) | 改动、前后对比、过拟合声明 |
| [12-面试讲稿](docs/12-面试讲稿.md) | 30 秒 / 3 分钟 / 5 分钟 |
| [13-防守题清单](docs/13-防守题清单.md) | 32 道高频追问 |
| [14-简化点与工业补齐](docs/14-简化点与工业补齐.md) | 每个模块的 POC 边界 |
| [15-模块完成度审计](docs/15-模块完成度审计.md) | 机制/配置/管理/资源/产品五层 + 逐条 FR 完成度 |
| [16-全链路映射](docs/16-全链路映射.md) | 瓶颈→缺口→模块→FR→代码→测试→指标 |
| [17-业务链路与当前workaround](docs/17-业务链路与当前workaround.md) | 角色—动作—失败后果、四种替代方案、证据台账、访谈提纲 |
| [18-业务指标与评测指标映射](docs/18-业务指标与评测指标映射.md) | 三层指标、映射强度、五个断点、分阶段用哪层 |
| [19-成本与延迟模型](docs/19-成本与延迟模型.md) | 调用次数、单任务成本公式、延迟分解、规模化推演 |
| [20-人评机评协同](docs/20-人评机评协同.md) | 三轨边界、分层抽样、一致性 κ、人评任务卡 |
| [21-Case与数据集管理](docs/21-Case与数据集管理.md) | 四层数据集、标签体系、覆盖矩阵缺口、防泄漏、CaseSet |
| [22-Evaluator配置](docs/22-Evaluator配置.md) | 指标级路由、冲突优先级、降级链、未判语义、配置权限 |
| [23-Agent失败模式库](docs/23-Agent失败模式库.md) | 12 类模式、首因归因、trace 信号、可观测性盘点 |
| [24-验收流程与上线门禁](docs/24-验收流程与上线门禁.md) | 三级判定、三态结论、签字、豁免、变更触发 |
| [25-Agent接入SOP](docs/25-Agent接入SOP.md) | 四类契约、六步流程、30 分钟 vs 5 人日、七种反模式 |
| [26-方案审查](docs/26-方案审查.md) | 七步假设链审查目录、结论三态、逐机制审核 |
| [27-研发协作 Agent·开发计划](docs/27-Agent应用改造计划.md) | 9 工具 × 4 场景；P1 故障排查 / P2 转测与需求 / P3 新人与数字员工 |
| [28-立项书 v2](docs/28-立项书-v2.md) | 9 工具 × 4 场景、Agent 纯度、痛点结构与 MVP |
| [29-AgentGate开发计划](docs/29-AgentGate开发计划.md) | P0 跑起来 / P1 故障评测 / P2 转测需求；硬门槛与范围锁 |
| [30-DevMate开发计划](docs/30-DevMate开发计划.md) | P0 骨架 / P1 故障排查 / P2 转测需求 / P3 新人；技术栈锁 |
| [31-P0开工包](docs/31-P0开工包.md) | 环境、代码地图、接口契约、验收脚本、开场提示 |

---

> **一句话收尾**：这个项目的价值不在"我把 Agent 做得更强"，而在"我把 Agent 上线前的**管控、观测、评测、回归**做成了一套可运行、可验证的底座，并且明确知道它在哪些地方还是 POC。"
