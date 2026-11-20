# [P0] 运行与观测

- **状态**：closed（本地验收完成）
- **GitHub issue**：https://github.com/hexin6147/agentgate/issues/1
- **对应计划**：`docs/29-AgentGate开发计划.md` §5 / §6 P0；`docs/31-P0开工包.md` §8
- **验收脚本**：`scripts/check_p0.py`
- **验收结果**：30/30 PASS（3 个真实 case，LLM agent + Ollama）
- **pytest**：151 passed

## 背景

P0 只做运行与观测：run_id、工具注入、异常隔离、trace、存储、usage。
本 issue 的动工前 GAP 与口径见 `docs/31-P0开工包.md` §8：

- rule agent 不调 LLM，按字面跑 3 个 case 时 usage 为空；
- 因此验收的 3 个 case 改走 `factory.build_agent("llm", context="rule")`；
- scenario 通过 Harness / Runner 可选参数透传；
- git / issue 采用本地验收，remote issue 后续补。

## 完成项

- [x] `src/agentgate/logging.py`：JSON Lines，必填 ts/level/event/trace_id/run_id
- [x] `src/agentgate/store.py`：runs / spans / usage / reports + 索引
- [x] `src/agentgate/trace.py`：start_span / end_span / spans；record 保持旧结构
- [x] `src/agentgate/usage.py` + `llm.py`：prompt/completion/latency，签名不变
- [x] `src/agentgate/harness.py`：根 span、日志上下文、store 落库、异常隔离、usage 采集
- [x] `src/agentgate/tools.py`：工具 span（假工具测试覆盖）
- [x] `scripts/check_p0.py`：run_id / trace_id / scenario 查询、span 深度、日志、usage、步骤还原
- [x] 新增测试 >= 10（当前 151 条测试）

## 验证

```bash
pytest -q
python scripts/check_p0.py
```

最后结果：

```text
P0 CHECK: 30/30 PASS
```

## 后续

- GitHub issue 已建：https://github.com/hexin6147/agentgate/issues/1
- P1 再引入超时/重试、外层状态机、步数/Token 限额与轨迹评测。
