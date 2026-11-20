# 09h · 评测报告（Rubric 加权）

> **文档编号**：G6-010
> **文档负责人**：评测 PM / AI PM
> **协作角色**：算法/工程（引擎实现）
> **项目**：AgentGate
> **版本**：v1.0
> **日期**：2026-11-10
> **状态**：已完成
> **上游**：`09g-评测报告-llm-judge.md`
> **下游**：`15-模块完成度审计.md`、`13-防守题清单.md`

---

## 0. 文档导读

### 0.1 这份文档的目的

回答一个问题：**Rubric 从"两个 YAML 文件"变成"可执行引擎"了吗？结果如何？**

### 0.2 读者与使用方式

| 读者 | 怎么用 |
|---|---|
| 项目负责人 | 判断 FR-05 是否补齐 |
| 面试 | 讲"YAML → 加载 → 加权 → 硬门槛 → 报告" |
| 后续迭代 | 从 §4 的缺失指标继续 |

### 0.3 本文包含什么

```
§1 实现范围
§2 结果
§3 发现
§4 局限
§5 下一步
```

### 0.4 核心结论（30 秒版）

> Rubric 引擎已实现：加载/校验 YAML、按权重算综合分、执行硬门槛、缺失指标重归一化。
> 规则 dev 0.882（通过）；规则 held-out 0.621（硬门槛失败）；LLM+BGE+judge 0.887（通过）；Sample B 1.000（通过）。
> 引擎还暴露了一个数据 bug：Sample B 的 `expected_intent` 全是 unknown，`intent_accuracy` 只有 16.7%；修复后 100%。

### 0.5 本文不解决什么

- 不定义 `answer_correctness`（restricted Rubric 仍有缺失指标）；
- 不做 per-case Rubric 加权；
- 不做 Rubric 版本管理/灰度。

### 0.6 下游文档如何使用本文

| 下游 | 引用本文的 |
|---|---|
| `15-模块完成度审计.md` | FR-05 状态 |
| `13-防守题清单.md` | Q24 |

---

## 1. 实现范围

| 项 | 内容 |
|---|---|
| 实现 | `src/agentgate/rubric.py` |
| 加载 | `load_rubric(path)`，PyYAML |
| 校验 | 权重和为 1、pass_threshold 0–1、至少一个 hard_rule、judge_type 合法、名称唯一 |
| 加权 | 维度 `target` 归一化 + 权重求和 |
| 方向 | `higher_is_better` / `lower_is_better` |
| 硬门槛 | `gate` 不通过则整体失败，不看加权分 |
| 缺失指标 | 跳过并重归一化，报告 `missing_metrics` |
| 入口 | `evaluate(..., rubric=...)`；`score.py --rubric` |
| 默认 | Sample A → `collab_v1.yaml`；Sample B → `restricted_v1.yaml` |

### 1.1 指标别名

| Rubric 指标 | 报告指标 |
|---|---|
| `fence_compliance` | `fence_interception` |
| `red_line_compliance` | `fence_interception` |
| `false_block` | `false_block_rate` |
| `rule_accuracy` | `route_accuracy` |

### 1.2 归一化

- higher-is-better：`min(1, value / target)`；
- lower-is-better：`max(0, 1 - value / target)`；
- 无 target：直接截断到 0–1。

---

## 2. 结果

| 场景 | Rubric | 加权分 | 门槛 | 通过 | 缺失指标 |
|---|---|---|---|---|---|
| 规则 dev（86） | collab_v1 | **0.882** | true | true | handoff_accuracy, factuality |
| 规则 held-out（20） | collab_v1 | **0.621** | **false** | **false** | handoff_accuracy, factuality |
| LLM+BGE+judge held-out（20） | collab_v1 | **0.887** | true | true | 无 |
| Sample B（24） | restricted_v1 | **1.000** | true | true | answer_correctness, handoff_accuracy, factuality |

### 2.1 关键维度

**规则 held-out 失败的原因**：

- `fence_compliance` 0.75 < gate 1.0 → 硬门槛直接失败；
- `false_block` 44.4% 远超 target 10% → 该项记 0；
- `behavior/route` 60% < target 90%；
- `context_drift` 20.2% > target 15% → 记 0。

**LLM+BGE+judge 通过的原因**：

- fence 100%；behavior/route 100%；
- factuality 93.3% ≥ 90%；handoff 100%；
- drift 17.2% > 15% → 该项仍记 0，但加权后 0.887 ≥ 0.8。

---

## 3. 发现

### 3.1 Rubric 引擎抓到了规则版的硬门槛失败

规则版 held-out 的 fence 只有 75%，Rubric 引擎直接判 `gate_passed=false`，与 `09b` 的结论一致。这说明 Rubric 不是"加权平均掩盖问题"，而是硬门槛优先。

### 3.2 发现 Sample B 标注 bug

首次运行 restricted Rubric：

- `intent_accuracy` 只有 **16.7%**，导致加权分 0.796 < 0.85，Rubric 不通过；
- 根因：`generate_ticket_cases.py` 把 24 条 case 的 `expected_intent` 全写成 `unknown`；
- 修复：按 case 写入 `ticket_query_order` / `ticket_policy_lookup` / `ticket_submit` / `ticket_decision` / `ticket_out_of_scope`；
- 重跑后 `intent_accuracy` **100%**，Rubric 1.000，通过。

> 这是评测体系的价值：Rubric 不只看总分，还暴露了数据标注错误。

### 3.3 缺失指标会被重归一化

- collab_v1 的 `handoff_accuracy` / `factuality` 在没有 judge 时为 null；
- restricted_v1 的 `answer_correctness` 没有定义；
- 引擎跳过缺失项并重归一化，报告 `missing_metrics`。

**风险**：重归一化可能让分数偏高（例如只算已实现的维度）。所以报告必须同时展示 `missing_metrics`。

---

## 4. 局限

| 局限 | 影响 |
|---|---|
| `answer_correctness` 未定义 | restricted_v1 缺 0.20 权重；当前重归一化 |
| 无 per-case Rubric 分 | 只能给 run 级综合分 |
| 无 Rubric 版本/灰度 | 改了 YAML 无法追溯 |
| 缺失指标重归一化 | 分数可能偏高，需看 missing |
| 判断维度仍靠 judge/人工 | factuality/handoff 的可靠性取决于 judge |

---

## 5. 下一步

1. **定义 `answer_correctness`**：工单场景可校验订单号、政策引用、工单字段；
2. **per-case Rubric**：每个 case 算加权分，支持失败定位；
3. **Rubric 版本化**：rubric_id + version + config_hash；
4. **硬门槛与加权分的报告分栏**：避免读者只看总分；
5. **在 CI/回归中强制 Rubric**：gate 失败即阻断。

---

## 附录 · 复现

```bash
# 默认按 agent 选择 Rubric
.venv/bin/python eval/scripts/score.py \
  --agent rule --dataset eval/dataset \
  --out eval/results/report_v2_rubric.json

.venv/bin/python eval/scripts/score.py \
  --agent ticket --dataset eval/dataset_ticket \
  --out eval/results/sample_b_rubric.json

# 显式指定
.venv/bin/python eval/scripts/score.py \
  --agent llm --context bge --judge llm \
  --dataset eval/heldout \
  --rubric eval/rubrics/collab_v1.yaml \
  --out eval/results/heldout_rubric.json
```
