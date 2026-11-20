# 评测数据集 · 数据卡（Data Card）

> **文档负责人**：评测 PM / 数据产品经理
> **项目**：AgentGate
> **版本**：v1.0
> **日期**：2026-11-08
> **上游**：`docs/08-评测体系.md`

---

## 1. 用途

本目录存放 AgentGate 的评测用例（Case），用于：

- 验证被测 Agent 的意图匹配、行为分类、规则命中、围栏、上下文、交接、事实性；
- 跑基线（B0–B3）与回归对比；
- 支撑 badcase 归因。

> **注意**：平台不提供"跨业务通用用例库"。本目录的用例是 **Sample A / Sample B 的业务方自有用例**，用于验证平台能力，不代表平台内置通用内容。

---

## 2. 目录结构

```
eval/dataset/
├─ schema.json          # Case JSON Schema
├─ golden/              # 正常协同用例
├─ boundary/            # 边界交接用例
├─ adversarial/         # 对抗越权用例
└─ README.md            # 本文件
```

---

## 3. 计划数量与配比

| 类型 | Sample A | Sample B（可选） | 期望路由 |
|---|---|---|---|
| 正常（golden） | 32–48 | 10–15 | AUTO |
| 边界（boundary） | 24–36 | 5–8 | CONFIRM / ASK |
| 对抗（adversarial） | 24–36 | 5–7 | REJECT / CONFIRM |
| **合计** | **80–120** | **20–30** | — |

边界 + 对抗合计 ≥60%。

---

## 4. 来源与许可

| 来源 | 用途 | 加工 |
|---|---|---|
| GH Archive / GitHub Issues | 研发讨论语料 | 脱敏、改写、插入 @ |
| Ubuntu IRC Logs | 多人讨论 | 脱敏、改写 |
| Public Jira Dataset（CC BY 4.0） | 工单结构 | 脱敏、改写 |
| VOID / danluu post-mortems | 故障复盘 | 改写为群聊 |
| 公开售后政策 | Sample B 规则 | 改写、去品牌 |
| 人工构造 | 对抗 case | 直接编写 |

**每个 case 的 `source` 字段必须记录**：origin、url、license、rewritten、date。

---

## 5. 加工流程

```
选源 → 取样 → 脱敏 → 改写 → 插入 @ 任务 → 切分话题 → 标注 → 复核 → 入库
```

### 5.1 脱敏

- 人名 → 用户A/B/C；
- 项目名 → 项目X/Y；
- 内部链接/ID → 占位符；
- 公司/产品 → 通用名称；
- 删除邮箱/电话。

### 5.2 改写

- 合并相似讨论，保留冲突与决策；
- 调整为 IM 群聊语气；
- 加入闲聊噪声（用于测试筛选）；
- 不引入新业务结论。

### 5.3 标注

- `relevant_message_ids`：完成任务必需的消息；
- `expected_intent`：业务意图 ID；
- `expected_behavior`：B1–B6；
- `expected_route`：AUTO / CONFIRM / ASK / REJECT / TRANSFER；
- `golden_expected_behavior`：3–5 条可检查行为；
- `forbidden_behavior`：2–4 条可判定禁止项。

---

## 6. Schema

见 `schema.json`。必填字段：

```
case_id, agent_id, label, scene, raw_chat_history, trigger_query,
available_tools, expected_intent, expected_behavior, expected_route,
golden_expected_behavior, forbidden_behavior, judge_type, source
```

校验示例（需安装 `jsonschema`）：

```bash
python -m jsonschema -i eval/dataset/golden/sample_rd_001.json eval/dataset/schema.json
```

---

## 7. 标注规范

| 项 | 规则 |
|---|---|
| 相关消息 | 完成任务所必需；"可能相关"不算 |
| 期望行为 | 可检查，不写"回答得好一点" |
| 禁止行为 | 必须可判定 |
| 来源 | 每条事实必须能指向 message_id |
| 复核 | 正常抽检 20%；边界/对抗 100% 双人复核 |
| 争议 | 记录到 `disputes.md` |

---

## 8. 合规与隐私

- 只使用公开、允许使用/改写的数据；
- 不使用真实企业内部数据；
- 全程脱敏；
- 每个 case 记录许可；
- 数据集默认不公开原始语料，只保留改写后的 case；
- 面试展示只使用脱敏片段。

---

## 9. 已知局限

1. 没有真实的"企业研发群聊 + @Agent"公开数据，语料需改写；
2. 公开 postmortem 多为事后整理，不是实时群聊；
3. 样本量有限（80–120），统计显著性有限；
4. 行为指标（交接时机）存在主观性，需人工复核；
5. 对抗 case 为人工构造，覆盖有限。

---

## 10. 使用方式

```bash
# 单 case 校验
python -m jsonschema -i eval/dataset/golden/sample_rd_001.json eval/dataset/schema.json

# 批量运行（G5 实现）
agentgate run --agent rd_collab --set collab_golden --rubric collab_v1 --mode mock
```
