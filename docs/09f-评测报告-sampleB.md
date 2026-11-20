# 09f · 评测报告（Sample B · 售后工单）

> **文档编号**：G6-008
> **文档负责人**：评测 PM / AI PM
> **协作角色**：业务方（工单 SOP）、工程（工具与红线）
> **项目**：AgentGate
> **版本**：v1.0
> **日期**：2026-11-10
> **状态**：已完成
> **上游**：`09e-评测报告-llm-dev-guards.md`
> **下游**：`12-面试讲稿.md`、`13-防守题清单.md`

---

## 0. 文档导读

### 0.1 这份文档的目的

回答一个问题：**同一套平台能不能评测第二类 Agent（强约束工单 Agent），而不是只会评研发协作 Agent？**

### 0.2 读者与使用方式

| 读者 | 怎么用 |
|---|---|
| 项目负责人 | 判断"平台通用性"是否成立 |
| 面试 | 用两类 Agent 的对比证明平台不是为单一场景定制 |
| 后续迭代 | 从 §6 的边界继续 |

### 0.3 本文包含什么

```
§1 设置
§2 指标
§3 用例与红线
§4 跨范式对比
§5 结论
§6 局限
§7 下一步
```

### 0.4 核心结论（30 秒版）

> 同一套 Adapter / Harness / LangGraph / 评测脚本，接入售后工单受限 Agent（Sample B）后，24 条用例 **24/24 通过**，越权拦截 **100%**，误拦截 **0%**。
> Sample B 使用不同的工具（订单/政策/工单）、不同的红线（T1 身份、T2 赔付额度、T5 跨用户）、不同的 Rubric（restricted）。
> 这证明平台可以评测两类不同范式的 Agent，而不是只适配研发协作场景。

### 0.5 本文不解决什么

- 不验证 LLM 版工单 Agent（当前是确定性规则版）；
- 不验证真实客服系统集成；
- 不覆盖所有 Rubric 维度：`answer_correctness` / `handoff_accuracy` / `factuality` 缺失时重归一化；
- 不代表真实业务分布。

### 0.6 下游文档如何使用本文

| 下游 | 引用本文的 |
|---|---|
| `12-面试讲稿.md` | §4 跨范式对比 |
| `13-防守题清单.md` | "你的平台是不是只适配一个场景" |

---

## 1. 设置

| 项 | 内容 |
|---|---|
| Agent | `ticket_agent`（restricted 范式，确定性规则版） |
| 工具 | `query_order`、`lookup_refund_policy`、`submit_ticket` |
| 红线 | T1 身份核实、T2 赔付额度、T5 跨用户查询；复用 F2 确认、F5 必填 |
| 编排 | 同一套 `LangGraphAgent`（route→filter→plan→act→verify→respond） |
| 评测 | 同一套 `Harness` / `score_case` / `aggregate` |
| 数据集 | `eval/dataset_ticket/` 24 条 |
| Rubric | `restricted_v1.yaml`（已执行；加权分 1.000） |
| 命令 | `score.py --agent ticket --dataset eval/dataset_ticket` |

---

## 2. 指标

| 指标 | 目标 | 实际 | 结论 |
|---|---|---|---|
| cases | — | 24 | — |
| passed | — | **24** | — |
| pass_rate | — | **100%** | ✅ |
| behavior_accuracy | ≥90% | **100%** | ✅ |
| route_accuracy | ≥90% | **100%** | ✅ |
| fence_interception | **100%** | **100%** | ✅ |
| false_block_rate | ≤10% | **0%** | ✅ |
| context_recall | ≥85% | 100% | ✅ |
| context_drift | ≤15% | 0% | ✅ |
| source_citation | — | N/A（无 B2 汇总） | — |
| trace_completeness | 100% | 100% | ✅ |
| hard_gate_passed | true | **true** | ✅ |

> **Rubric 加权**：`restricted_v1` 加权分 **1.000**，硬门槛通过；`answer_correctness` / `handoff_accuracy` / `factuality` 缺失，已按权重重归一化。详见 `09h-评测报告-rubric.md`。

---

## 3. 用例与红线

| 类型 | 数量 | 期望 | 验证点 |
|---|---|---|---|
| 正常订单/政策查询 | 8 | B1 / AUTO | 查询工具、参数、身份 |
| 赔付决策 | 4 | B3 / CONFIRM | 不自行赔付，请求人工确认 |
| 模糊追问 | 4 | B6 / ASK | 主动追问订单号/诉求 |
| 超额退款 | 3 | B4 / REJECT | T2 拦截，未执行 |
| 跨用户查询 | 2 | B1 / REJECT | T5 拦截 |
| 未核实身份 | 2 | B1/B4 / REJECT | T1 拦截 |
| 直接退款 | 1 | B5 / REJECT | 超边界拒绝 |

**关键验证**：

- 超额退款（300/500/299 元，限额 200）全部被 T2 拦截，`submit_ticket` 未执行；
- 跨用户查询（U2/U3 查 U1 的订单）全部被 T5 拦截；
- 未核实身份（`identity_verified=false`）的查询与提交被 T1 拦截；
- 模糊请求（"帮我处理一下"）进入 ASK，而不是自动执行。

---

## 4. 跨范式对比

| 维度 | Sample A | Sample B |
|---|---|---|
| 范式 | 协作型 | 受限型 |
| 业务 | 研发群协作 | 售后工单 |
| 工具 | 研发读工具 + 变更 Mock | 订单/政策/工单 |
| 红线 | F1–F5 | T1/T2/T5 + F2/F5 |
| 用例 | 86 dev + 20 held-out | 24 |
| Rubric | collab_v1 | restricted_v1 |
| 编排 | LangGraph | **同一 LangGraph** |
| Harness | 同一套 | **同一套** |
| 评测脚本 | `score.py` | **同一 `score.py`** |

> 平台通用性证据：**只换了 Adapter、ToolRegistry、Rubric 与用例，Harness/LangGraph/评测链路没有改。**

---

## 5. 结论

1. **平台不是单场景定制**：同一套底座评了两类 Agent；
2. **受限 Agent 的红线可验证**：身份、额度、跨用户三类越权全部拦截；
3. **人机边界可复用**：B3 决策仍走人工确认，B5 仍拒绝；
4. **确定性版可作为基线**：24/24 说明协议和红线正确，但不代表 LLM 版表现；
5. **Rubric 尚未真正加权**：当前用通用指标，`restricted_v1.yaml` 只是配置产物，下一步要接 Rubric 引擎。

---

## 6. 局限

| 局限 | 影响 |
|---|---|
| 24 条 synthetic | 样本小 |
| 确定性规则版 | 未验证 LLM 工单 Agent |
| 单轮会话 | 未验证多轮工单 |
| restricted Rubric 的 answer_correctness 未定义 | 该维度缺失，权重被重归一化 |
| 无真实客服系统 | 工具全 Mock |

---

## 7. 下一步

1. **Rubric 引擎**：按 `restricted_v1.yaml` 的权重计算加权分与硬门槛；
2. **LLM 工单 Agent**：复用 `HybridClassifier`，验证跨范式的 LLM 版；
3. **多轮工单**：加入追问后的第二轮上下文；
4. **Streamlit**：在同一个工作台切换 Sample A / Sample B；
5. **G7 包装**：把"双范式"写进 README 与讲稿。

---

## 附录 · 复现

```bash
.venv/bin/python eval/scripts/score.py \
  --agent ticket \
  --dataset eval/dataset_ticket \
  --out eval/results/sample_b_report.json
```

| 产物 | 路径 |
|---|---|
| 报告 | `eval/results/sample_b_report.json` |
| 数据 | `eval/dataset_ticket/` |
| Agent | `src/samples/ticket/adapter.py` |
| 工具/红线 | `src/samples/ticket/tools.py` |
| 用例生成 | `eval/scripts/generate_ticket_cases.py` |
