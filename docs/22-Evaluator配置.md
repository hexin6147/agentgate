# 22 · Evaluator 配置

> **文档编号**：G4-010
> **文档负责人**：产品经理（AI PM）
> **项目**：AgentGate —— Agent 上线门禁与离线评测沙箱
> **版本**：v1.0
> **日期**：2026-11-10
> **状态**：配置模型已设计；Evaluator 实体未实现
> **上游**：`08-评测体系.md`、`20-人评机评协同.md`、`19-成本与延迟模型.md`
> **下游**：`05-PRD.md` FR-05/08、`13-防守题清单.md`、`12-面试讲稿.md`

---

## 0. 文档导读

### 0.1 这份文档的目的

回答四个问题：

1. **每个指标到底由谁判**——规则、LLM 还是人？
2. 这个"谁判"是**写在代码里**，还是**可以配**？
3. 两个 evaluator 结论冲突时，听谁的？
4. 一个 evaluator 挂了，指标算通过还是算未判？

### 0.2 读者与使用方式

| 读者 | 怎么用 |
|---|---|
| 评测负责人 | 配置一套 evaluator，跑之前先看成本和覆盖 |
| 业务方 | 知道哪些配置自己能改、哪些不能 |
| 面试 | 回答"你的评测器怎么选、怎么保证不被业务绕过" |

### 0.3 本文包含什么

```
§1 当前的问题：case 级开关，不是 metric 级路由
§2 Evaluator 的三种类型与选择决策树
§3 配置对象模型
§4 冲突与优先级
§5 降级链：未判 ≠ 通过
§6 配置权限：谁能改什么
§7 成本与覆盖预估
§8 版本与可比性
§9 现状与缺口
§10 面试怎么讲
```

### 0.4 核心结论（30 秒版）

> 现在选 evaluator 的方式是 **case 上写一个 `judge_type`**——这是一个**开关**，不是路由。
> 结果是：标 `hard_rule` 的 case 永远不会检查事实性，即使它的输出里全是事实陈述；标 `llm_judge` 的 case 会一次性判四个维度，不管相不相关。
> 正确的粒度是 **metric 级**：每个指标独立声明"由谁判、在什么条件下判、失败怎么办"。
> 三条必须写死的规则：**硬门槛不能被 judge 覆盖、未判不等于通过、evaluator 配置不能由业务关掉。**

### 0.5 本文不解决什么

- 不做 evaluator 的自动选择（用模型选模型）；
- 不做标注平台 UI；
- 不覆盖多模态 evaluator；
- 不做 evaluator 本身的效果优化（见 `20`）。

### 0.6 下游文档如何使用本文

| 下游 | 引用本文的 |
|---|---|
| `05-PRD.md` | FR-05 Rubric 配置、FR-08 trace |
| `13-防守题清单.md` | §4 冲突、§5 未判语义 |
| `12-面试讲稿.md` | §10 60 秒版 |

---

## 1. 当前的问题：case 级开关，不是 metric 级路由

现在的实现是：

```python
# evaluation.py:91
if judge is not None and case.judge_type in ("llm_judge", "human_review"):
    outcome = judge.judge(case, result)   # 一次判四个维度
```

数据里的分布是：`hard_rule` 37 条、`human_review` 24 条、`llm_judge` 25 条。

### 1.1 三个具体后果

| 场景 | 现状 | 应该 |
|---|---|---|
| 一条 `hard_rule` 的 B2 汇总用例 | 不跑 judge，事实性没人管 | 汇总类必须判事实性 |
| 一条 `llm_judge` 的 B1 查询用例 | 跑了 judge，但 `handoff_correct` 无关 | 按行为类只判相关维度 |
| 一条标 `human_review` 的用例 | 实际由 LLM 判（见 `20` §9） | 人评，或明确降级并标注 |

**根因**：`judge_type` 描述的是"这条 case 用什么方式判"，但真实需求是"**这个指标由谁判**"。两者不是一个粒度。

### 1.2 为什么粒度错了会出问题

- **覆盖失真**：`judge_coverage` 显示 100%，但有 37 条根本没跑 judge；
- **成本浪费**：无关维度也在判，多花 token；
- **不可配置**：想给某类业务加一条"必须人评"的规则，只能改代码。

---

## 2. Evaluator 的三种类型与选择决策树

### 2.1 三种类型

| 类型 | 能判什么 | 不能判什么 | 单条成本 |
|---|---|---|---|
| `hard_rule` | 二值、可枚举：围栏、路由、字段、来源有无 | 语义、主观质量 | ≈ 0 |
| `llm_judge` | 语义：事实性、来源对错、交接合理性 | 需要业务解释权的判定 | 1 次调用 |
| `human_review` | 主观、争议、高危 | 大规模全量 | 2–5 分钟 |

### 2.2 选择决策树

```
这个指标能不能用二值规则判定？
├─ 能
│   └─ → hard_rule
└─ 不能
    └─ 有没有可判定的 ground truth（消息、政策、trace）？
        ├─ 有
        │   └─ 风险等级是 L2 / L3 吗？
        │       ├─ 是 → human 100% + judge 全量
        │       └─ 否 → judge 全量 + human 抽检 10%
        └─ 没有
            └─ → 不能进离线评测，标 "未测"
```

### 2.3 落到指标上

| 指标 | 类型 | 理由 |
|---|---|---|
| `fence_interception` | hard_rule | 二值 |
| `route_accuracy` | hard_rule + judge（争议时） | 规则覆盖同义表达不足 |
| `source_citation` | hard_rule（有无）+ judge（对错） | 拆成两个子指标 |
| `factuality` | judge | 语义 |
| `handoff_accuracy` | judge + human 100% | 无唯一答案 |
| `trace_completeness` | hard_rule | 字段校验 |
| 业务承诺合规 | judge + human 100% | 资金 / 合规 |

> 注意 `source_citation` 被拆成"有无"和"对错"两个子指标——**一个指标如果需要两种 evaluator，说明它本来是两件事**。

---

## 3. 配置对象模型

> 以下是**设计稿**，当前代码未消费。

```yaml
evaluator_config_id: sample_a_v1
version: 1.0.0
agent_id: rd_collab

evaluators:
  - id: fence_rule
    type: hard_rule
    metrics: [fence_interception]
    applies_to: {all: true}
    on_failure: fail              # 硬门槛失败 = 整条 case 失败
    cost: {calls: 0}
    editable_by: platform         # 业务不可关闭

  - id: route_rule
    type: hard_rule
    metrics: [route_accuracy, behavior_accuracy]
    applies_to: {all: true}
    cost: {calls: 0}

  - id: source_rule
    type: hard_rule
    metrics: [source_present]
    applies_to: {behavior: [B2, B3]}
    cost: {calls: 0}

  - id: semantic_judge
    type: llm_judge
    metrics: [factuality, source_correct]
    applies_to:
      behavior: [B1, B2, B3]
      label: [normal, boundary, adversarial]
    fallback: skip                # 失败时标"未判"，不算通过
    on_failure: skip
    cost: {calls: 1, tokens_in: 500, tokens_out: 120}

  - id: handoff_judge
    type: llm_judge
    metrics: [handoff_correct]
    applies_to: {behavior: [B3, B6]}
    cost: {calls: 1}

  - id: handoff_human
    type: human_review
    metrics: [handoff_correct]
    applies_to: {behavior: [B3, B6], sample_rate: 1.0}
    cost: {minutes: 3}

  - id: factuality_sample
    type: human_review
    metrics: [factuality]
    applies_to: {sample_rate: 0.1, strata: difficulty}
    cost: {minutes: 3}
```

### 3.1 字段说明

| 字段 | 含义 | 谁定 |
|---|---|---|
| `type` | hard_rule / llm_judge / human_review | 平台 |
| `metrics` | 这个 evaluator 产出哪些指标 | 平台 |
| `applies_to` | 什么 case 跑它（行为类 / 标签 / 风险等级 / 抽样率） | 评测 |
| `on_failure` | evaluator 失败时整条 case 判 fail / skip / escalate | 平台 |
| `fallback` | 降级到哪一类 | 平台 |
| `cost` | 调用次数 / token / 分钟 | 平台 |
| `editable_by` | platform / eval / business | 平台 |

### 3.2 为什么 `applies_to` 不能只看 case 标签

如果只看 `label`（normal / boundary / adversarial），就会重蹈 `21` §4.2 的覆辙——**标签和行为类完全绑定**。所以 `applies_to` 必须支持按**行为类**筛选。

---

## 4. 冲突与优先级

两个 evaluator 对同一指标给出不同结论时：

| 情形 | 处理 | 理由 |
|---|---|---|
| rule 判失败，judge 判通过 | **以 rule 为准** | 硬门槛不能被语义模型覆盖 |
| judge 判失败，rule 判通过 | 记录 `judge_violation`，进入争议队列 | 可能是规则覆盖不足 |
| human 与 judge 不一致 | **以 human 为准**，回写定义 | 人评的用途就是校准 |
| rule 与 human 不一致 | 以 human 为准，但要求给出规则修正建议 | 规则也可能写错 |

**核心原则**：

> **硬门槛是单向的：rule 可以否决 judge，judge 不能否决 rule。**

### 4.1 为什么不许 judge 覆盖 rule

越权拦截是一个二值事件：拦住了 / 没拦住。如果允许 LLM 说"虽然没拦住，但意图是好的"，硬门槛就失去了意义。**安全判定不能交给概率模型。**

---

## 5. 降级链：未判 ≠ 通过

### 5.1 降级顺序

```
human → judge → rule → 标"未判"
```

### 5.2 关键语义

| 状态 | 含义 | 报告里怎么显示 |
|---|---|---|
| 通过 | 有 evaluator 判了，且通过 | ✅ |
| 失败 | 有 evaluator 判了，且失败 | ❌ |
| **未判** | 没有可用 evaluator，或 evaluator 异常 | ⚪ **不算通过** |
| 降级通过 | 从 human 降到 judge，且通过 | ✅（标注"降级"） |

### 5.3 为什么"未判"不能算通过

如果 judge 超时就算通过，那么**让 judge 挂掉就能提高通过率**——这是激励机制的错误。所以：

> `pass_rate = 通过 / (通过 + 失败)`，分母**不含未判**；同时报告必须单列 `未判数` 和 `judge_coverage`。

### 5.4 当前实现的一个隐患

`evaluation.py` 里 `judge_ok` 默认为 `None`，judge 异常时保持 `None`，`judge_coverage` 会下降——这是对的。但 `pass_rate` 的计算是否把 `None` 算作通过，需要单独确认。

---

## 6. 配置权限：谁能改什么

| 配置项 | 平台 | 评测 | 业务方 |
|---|---|---|---|
| 指标定义与公式 | ✅ | | |
| Evaluator 类型与实现 | ✅ | | |
| **硬门槛是否启用** | ✅ | | ❌ **不可关** |
| `applies_to` 筛选条件 | | ✅ | |
| 抽样率 | | ✅ | |
| 指标权重 | | ✅ | ✅ |
| 指标目标值 | | ✅ | ✅（需评审） |
| 用例内容与 golden | | | ✅ |

**为什么业务不能关硬门槛**：

> 业务方有动机让门禁更容易通过。如果"越权拦截"可以被关掉，这个平台就退化成了自证工具。

---

## 7. 成本与覆盖预估

配置一旦确定，就能算出跑一遍的代价（公式见 `19`）：

```
总调用数 = Σ_evaluator ( 匹配 case 数 × 抽样率 × 单次调用数 )
总成本   = Σ ( 调用数 × 单次 token 成本 ) + Σ ( 人评条数 × 单条分钟数 × 人工单价 )
```

### 7.1 示例（当前 86 条）

| Evaluator | 匹配 case | 抽样 | 调用数 |
|---|---|---|---|
| fence_rule | 86 | 100% | 0 |
| route_rule | 86 | 100% | 0 |
| semantic_judge | 49（B1/B2/B3） | 100% | 49 |
| handoff_judge | 24（B3/B6） | 100% | 24 |
| handoff_human | 24 | 100% | 24 次人评（≈1.2h） |
| factuality_sample | 49 | 10% | 5 次人评（≈0.25h） |

> 合计：73 次模型调用 + 29 次人评。**比现在的"49 条全跑 judge"更省，覆盖更准。**

### 7.2 配置对话框应该显示什么

| 项 | 为什么 |
|---|---|
| 覆盖 case 数 | 避免"配了但没生效" |
| 模型调用数 | 成本 |
| 人评条数与耗时 | 排期 |
| 未覆盖的指标 | 避免"以为测了" |

---

## 8. 版本与可比性

### 8.1 每次 run 必须记录

| 字段 | 用途 |
|---|---|
| `evaluator_config_id` + `version` | 知道用哪套配置 |
| 配置内容 hash | 防止"版本号没改但内容改了" |
| `case_set_id` + `version` | 知道跑了哪批用例 |
| `agent_version` | 知道测的哪版 Agent |

### 8.2 可比性规则

> **不同 evaluator 配置的两个 run，不能直接比分数。**

原因：换了 evaluator 就等于换了尺子。回归对比必须先校验配置一致，不一致时只允许比"同一指标在相同 evaluator 下的值"。

---

## 9. 现状与缺口

| 能力 | 状态 | 说明 |
|---|---|---|
| 三轨判定 | 🟡 | 有 `judge_type`，但是 case 级开关 |
| Metric 级路由 | ❌ | 无 |
| Evaluator 实体 | ❌ | 无配置文件、无加载器 |
| 冲突优先级 | ❌ | 代码里只有"judge 不影响硬门槛"，无显式仲裁 |
| 降级链 | ❌ | judge 异常时静默跳过 |
| 未判语义 | 🟡 | `judge_ok=None` 存在，但报告未单列 |
| 配置版本 | ❌ | 无 |
| 配置权限 | ❌ | 无 |

**对外表述**：

> "我的 evaluator 选择现在是 case 级的：这条 case 标了 `llm_judge` 就跑 judge，标了 `hard_rule` 就不跑。粒度不对——应该是每个指标独立声明由谁判。这个我设计好了，还没实现。"

---

## 10. 面试怎么讲（60 秒）

> "选评测器这件事，我一开始做错了一个粒度。
>
> 我是在 case 上写一个 `judge_type`，标了 `llm_judge` 就跑模型判，标了 `hard_rule` 就不跑。但这是**开关**，不是**路由**。结果是一条汇总类用例如果标了 hard_rule，它的事实性就永远没人查。
>
> 正确的粒度是**指标级**：每个指标独立声明由谁判、在什么条件下判、挂了怎么办。
>
> 我定了三条死规则：第一，硬门槛不能被 judge 覆盖——越权是二值事件，不能交给概率模型；第二，**未判不等于通过**，否则让 judge 挂掉就能提高通过率；第三，硬门槛的开关键只有平台有，业务不能关，否则平台就变成了自证工具。"

### 10.1 三个可能的追问

| 追问 | 应答 |
|---|---|
| 为什么不让 judge 判越权？ | "越权是拦住了/没拦住，不是'意图好不好'。让模型判安全，等于把一票否决变成概率。" |
| 未判的 case 怎么算分？ | "不算进 pass_rate 的分母，但报告单列未判数和覆盖率。不能把'没测'混进'通过'。" |
| 配置改了怎么保证可比？ | "run 里记配置 hash，配置不同不允许直接比分数——换了尺子就不能比长度。" |
