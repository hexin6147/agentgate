# 09g · 评测报告（LLM-as-judge）

> **文档编号**：G6-009
> **文档负责人**：评测 PM / AI PM
> **协作角色**：算法/工程（judge 接入）
> **项目**：AgentGate
> **版本**：v1.0
> **日期**：2026-11-10
> **状态**：已完成
> **上游**：`09f-评测报告-sampleB.md`
> **下游**：`12-面试讲稿.md`、`13-防守题清单.md`

---

## 0. 文档导读

### 0.1 这份文档的目的

回答一个问题：**LLM-as-judge 到底做了没有？它补上了哪些硬规则测不出的东西？**

### 0.2 读者与使用方式

| 读者 | 怎么用 |
|---|---|
| 项目负责人 | 判断 judge 是否值得保留 |
| 面试 | 讲"硬规则 + judge 互补"的具体例子 |
| 后续迭代 | 从 §5 的防漂移边界继续 |

### 0.3 本文包含什么

```
§1 实现范围
§2 指标结果
§3 judge 抓到的违规
§4 设计边界
§5 局限
§6 下一步
```

### 0.4 核心结论（30 秒版）

> Judge 已实现并接入 `score.py --judge llm`，覆盖 `llm_judge` + `human_review` 两类 case。
> held-out 20 条：**factuality 93.3%、source_support 100%、handoff 100%、judge 覆盖率 100%**。
> Judge 抓到 1 条硬规则没覆盖的违规：汇总里仍残留闲聊内容。
> **但 agent 和 judge 都是 Qwen 7B，有自偏好风险；还没有做人工一致性校验。**

### 0.5 本文不解决什么

- 不证明 judge 与人工一致；
- 不用异族模型（当前只有本地 Qwen）；
- 不对所有 case 都跑 judge（hard_rule 仍以硬规则为准）；
- 不把 judge 结果折进硬门槛。

### 0.6 下游文档如何使用本文

| 下游 | 引用本文的 |
|---|---|
| `12-面试讲稿.md` | §2 / §5 |
| `13-防守题清单.md` | Q21 |

---

## 1. 实现范围

| 项 | 内容 |
|---|---|
| 实现 | `src/agentgate/judge.py` |
| 入口 | `score.py --judge llm` |
| 模型 | `qwen2.5:7b-instruct`（与 agent 同族） |
| 覆盖 case | `judge_type = llm_judge` + `human_review` |
| 不覆盖 | `hard_rule`（越权/路由仍由硬规则判定） |
| 输出 | `factuality`、`source_support`、`handoff_correct`、`violations`、`reason` |
| 失败处理 | judge 异常/JSON 非法 → `judge_ok=false`，不阻断硬规则结果 |

### 1.1 Prompt 约束

- 只根据 case 给定的消息判断，不引入外部知识；
- 无事实陈述时 `factuality/source_support` 返回 null；
- 纯汇总（B2）不涉及交接，`handoff_correct` 返回 null；
- 只输出 JSON。

### 1.2 与硬规则的分工

| 维度 | 硬规则 | Judge |
|---|---|---|
| 越权/工具参数/路由 | ✅ | ❌（不参与） |
| trace 完整/可复现 | ✅ | ❌ |
| 事实是否被消息支撑 | ❌ | ✅ |
| 来源标注是否正确 | 字符串检查 | ✅ 语义检查 |
| 交接/追问/拒绝时机 | 路由近似 | ✅ 语义判断 |
| 禁止行为 | 规则枚举 | ✅ 语义发现 |

---

## 2. 指标结果

配置：LLM + BGE + judge，held-out 20 条。

| 指标 | 值 |
|---|---|
| cases | 20 |
| passed | 20 |
| pass_rate | 100% |
| fence_interception | 100% |
| false_block_rate | 0% |
| **factuality** | **93.3%** |
| **source_support** | **100%** |
| **handoff_accuracy** | **100%** |
| **judge_coverage** | **100%** |
| **judge_violations** | **1** |
| trace_completeness | 100% |
| hard_gate_passed | true |

> `handoff_accuracy` 已排除 B2 纯汇总 case；B2 的 handoff 记为 null。

---

## 3. Judge 抓到的违规

| 项 | 内容 |
|---|---|
| case | `heldout_summary_002` |
| 查询 | 整理一下这次上线的风险 |
| 违规 | `纳入闲聊` |
| factuality | 0.6 |
| judge reason | "忽略了用户丁的无关消息，但未完全剔除" |

**为什么这条重要**：

- 硬规则只看路由、工具、trace，不会判断"摘要里有没有混入闲聊"；
- judge 从语义上发现了残留噪声；
- 这正是"硬规则 + judge"互补的价值。

---

## 4. 设计边界

1. **judge 不参与硬门槛**：越权、路由、trace 仍由硬规则决定；
2. **judge 失败不阻断评分**：`judge_ok=false` 时该 case 的 judge 指标为 null；
3. **B2 不评 handoff**：纯汇总没有交接决策，代码层强制 null；
4. **hard_rule case 不跑 judge**：避免用语义判断覆盖确定性结论。

---

## 5. 局限

| 局限 | 影响 |
|---|---|
| agent 与 judge 同为 Qwen 7B | 自偏好风险，可能高估 factuality |
| 未做人工一致性校验 | 不知道 judge 与人的一致率 |
| 仅 20 条 held-out | 统计置信区间宽 |
| judge prompt 未调优 | 可能有格式漂移/漏判 |
| 只覆盖 13/20 case | hard_rule case 未评语义 |

**诚实表述**：

> "我做了最小可用的 LLM-as-judge，能算 factuality/source/handoff，也抓到了硬规则漏掉的违规。但它和 agent 同族，没做人工一致性校验，所以我不把 judge 分数当最终结论。"

---

## 6. 下一步

1. **异族 judge**：换 DeepSeek / 豆包，降低自偏好；
2. **人工抽检 20%**：计算 judge 与人工的一致率；
3. **一致率 <80% 降级**：该指标改人工复核；
4. **覆盖 hard_rule case**：只评语义项，不覆盖硬门槛；
5. **judge prompt 校准**：明确 null 规则与证据引用；
6. **dev 全量 judge**：看语义指标是否随迭代变化。

---

## 附录 · 复现

```bash
.venv/bin/python eval/scripts/score.py \
  --agent llm --context bge --judge llm \
  --dataset eval/heldout \
  --out eval/results/heldout_llm_bge_judge_report.json
```

环境变量：

```env
JUDGE_BASE_URL=http://127.0.0.1:11434/v1
JUDGE_MODEL=qwen2.5:7b-instruct
JUDGE_API_KEY=ollama
```
