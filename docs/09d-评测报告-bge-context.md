# 09d · 评测报告（BGE 语义上下文）

> **文档编号**：G6-006
> **文档负责人**：评测 PM / AI PM
> **协作角色**：算法/工程（embedding 接入）
> **项目**：AgentGate
> **版本**：v1.0
> **日期**：2026-11-09
> **状态**：已完成
> **上游**：`09c-评测报告-llm-heldout.md`
> **下游**：`11-迭代记录.md`、`12-面试讲稿.md`

---

## 0. 文档导读

### 0.1 这份文档的目的

回答一个问题：**把上下文筛选从"话题/关键词规则"换成 BGE 语义检索后，drift 有没有下降、代价是什么？**

### 0.2 读者与使用方式

| 读者 | 怎么用 |
|---|---|
| 项目负责人 | 判断语义筛选是否值得保留 |
| 面试 | 讲"语义召回降低噪声，但有召回损失" |
| 后续迭代 | 从 §5/§6 接续阈值与 prompt 优化 |

### 0.3 本文包含什么

```
§1 设置
§2 指标对比
§3 样例
§4 结论
§5 局限
§6 下一步
```

### 0.4 核心结论（30 秒版）

> BGE 语义筛选把 held-out 的 **context_drift 从 23.3% 降到 17.2%**，噪声 `m4` 被丢弃；代价是 **context_recall 从 100% 降到 95.6%**（仍高于 85% 目标）。
> 通过率保持 20/20，越权拦截 100%。
> 来源标注仍是 66.7%，因为 LLM 摘要只引用了 `m2/m3`，没有引用背景 `m1`——这是摘要 prompt 的问题，不是筛选问题。

### 0.5 本文不解决什么

- 不优化摘要 prompt（避免在 held-out 上调参）；
- 不调 threshold/top_k（本轮的 0.35/5 是先验设定）；
- 不覆盖 Sample B。

### 0.6 下游文档如何使用本文

| 下游 | 引用本文的 |
|---|---|
| `11-迭代记录.md` | §2 对比 |
| `12-面试讲稿.md` | §4 结论 |
| 后续 held-out2 | 用新数据调 threshold/prompt |

---

## 1. 设置

| 项 | 内容 |
|---|---|
| Agent | LLM 版：qwen2.5:7b-instruct + 规则兜底 |
| 编排 | LangGraph |
| 上下文筛选 | `quentinz/bge-base-zh-v1.5:latest`（768 维） |
| 参数 | `top_k=5`、`threshold=0.35`（先验设定，未在 held-out 上调） |
| 回退 | embedding 失败 → 原话题/关键词筛选 |
| 数据集 | `eval/heldout/` 20 条 |
| 命令 | `score.py --agent llm --context bge --dataset eval/heldout` |

---

## 2. 指标对比

| 指标 | LLM + 关键词筛选 | LLM + BGE | 变化 |
|---|---|---|---|
| pass_rate | 100% | 100% | 0 |
| fence_interception | 100% | 100% | 0 |
| false_block_rate | 0% | 0% | 0 |
| context_recall | 100% | **95.6%** | **-4.4pp** |
| context_drift | 23.3% | **17.2%** | **-6.1pp** |
| source_citation | 66.7% | 66.7% | 0 |
| trace_completeness | 100% | 100% | 0 |
| hard_gate_passed | true | true | — |

**解读**：

- drift 下降 6.1pp：语义筛选能识别"中午吃什么"这类语义无关消息；
- recall 下降 4.4pp：阈值 0.35 会漏掉少量低相似度但业务相关的消息；
- 通过率不变：说明筛选改善的是质量指标，不是分类正确率；
- 来源标注不变：瓶颈在摘要 prompt，不在筛选。

---

## 3. 样例

输入：`帮我看下这次发版还有啥要注意的`

筛选结果：

```json
{
  "node": "filter",
  "kept": ["m1", "m2", "m3"],
  "dropped": ["m4"],
  "strategy": "semantic"
}
```

`m4` 是"楼下咖啡店关门了"，被语义筛选正确丢弃。

LLM 输出：

```
风险或结论:
1. [m2] 结算服务迁移脚本还没有回滚方案，这可能在发版过程中遇到问题时难以快速恢复，需尽快制定回滚方案。
2. [m3] 对账页面仍在联调，意味着该功能可能还未完全准备好，可能存在不稳定因素，需确保其在发版前完成联调并测试通过。
```

**评价**：

- 噪声不再出现在摘要里；
- 仍只引用 `m2/m3`，没有引用背景 `m1`（"版本 3.1 下周发版"），所以 source_citation 是 2/3；
- 这不是筛选错误，是摘要 prompt 没有要求"引用所有使用到的消息"。

---

## 4. 结论

1. **语义筛选值得保留**：drift 降 6.1pp，噪声被正确丢弃；
2. **代价可控**：recall 95.6%，仍高于 85% 目标；
3. **通过率不受影响**：20/20，越权拦截 100%；
4. **来源标注是下一个瓶颈**：需要改摘要 prompt，而不是继续调筛选；
5. **参数未调优**：0.35/5 是先验值，若在新数据上调参会得到不同结果。

---

## 5. 局限

| 局限 | 影响 |
|---|---|
| held-out 仅 20 条 | 指标波动大 |
| threshold/top_k 未调优 | 不是最优配置 |
| 摘要未人工复核 | 质量只看样例 |
| 单一 embedding 模型 | 未对比其他 BGE 版本 |
| held-out 已用于 LLM 验证 | 不能再用于调 prompt/阈值 |

---

## 6. 下一步

1. **新建 held-out2**：在完全独立的数据上调 threshold/top_k 与摘要 prompt；
2. **摘要 prompt**：明确"引用所有使用到的 message_id，包括背景"；
3. **混合筛选**：语义 + 关键词兜底，降低 recall 损失；
4. **人工复核**：抽检摘要质量；
5. **飞书切换**：`.env` 设 `AGENTGATE_CONTEXT=bge` 即可。

---

## 附录 · 复现

```bash
.venv/bin/python eval/scripts/score.py \
  --agent llm \
  --context bge \
  --dataset eval/heldout \
  --out eval/results/heldout_llm_bge_report.json
```

环境变量：

```env
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:7b-instruct
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=quentinz/bge-base-zh-v1.5:latest
```
