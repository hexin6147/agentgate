---
name: P0 task
about: P0 运行与观测（run_id / 工具注入 / 异常隔离 / trace / 存储 / usage）
title: "[P0] "
labels: p0
assignees: ""
---

## 目标

<!-- 对应 docs/29 §5 P0 与 docs/31 §8 的哪一格 -->

## 影响范围

- [ ] logging.py（JSON Lines，必带 trace_id）
- [ ] store.py（runs / spans / usage / reports）
- [ ] trace span（run -> step -> tool/llm，深度 >= 3）
- [ ] usage（LLM token / latency）
- [ ] harness（根 span、异常隔离、store 落库）
- [ ] check_p0.py

## DoD

- [ ] 3 个 case 能按 run_id / trace_id / scenario 查
- [ ] span 树 >= 3 层
- [ ] 100% 日志带 trace_id
- [ ] 报告有单次与单步 token/latency
- [ ] 错误分类：timeout / validation / upstream / internal
- [ ] 能用 trace 还原一次 run
- [ ] 单 case 失败不中断批量
- [ ] 注入一个假工具，能被调用并写 trace
- [ ] 新增测试 >= 10
- [ ] `python scripts/check_p0.py` 全 PASS

## 验证命令

```bash
pytest -q
python scripts/check_p0.py
```
