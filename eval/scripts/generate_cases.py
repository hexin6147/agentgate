#!/usr/bin/env python3
"""Generate synthetic evaluation cases (stdlib only).

This is a seed dataset for the offline pipeline.  It intentionally includes
supported phrasings (expected to pass) and paraphrases (expected to expose the
rule-based agent's matching gaps).  Do not treat it as a substitute for
real-world cases.
"""
from __future__ import annotations

import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET = os.path.join(ROOT, "eval", "dataset")
random.seed(20261109)

SERVICES = ["支付服务", "订单服务", "搜索服务", "用户服务", "库存服务"]
VERSIONS = ["1.2", "1.3", "2.0-rc1", "1.4.2"]
RISKS = [
    "数据库迁移有风险，索引没做完",
    "缓存配置还没对齐",
    "依赖版本冲突待确认",
    "灰度开关还没配置",
]
NOISE = ["中午吃什么", "周末有人打球吗", "这个表情包不错"]


def msg(mid, user, text):
    return {
        "message_id": mid,
        "user": user,
        "ts": "2026-11-09T10:00:00",
        "msg": text,
    }


def make_case(
    case_id,
    label,
    scene,
    history,
    topics,
    query,
    intent,
    behavior,
    route,
    relevant,
    tools,
    judge_type,
    difficulty,
    golden,
    forbidden,
):
    return {
        "case_id": case_id,
        "agent_id": "rd_collab",
        "label": label,
        "scene": scene,
        "raw_chat_history": history,
        "topics": topics,
        "trigger_query": query,
        "available_tools": tools,
        "expected_intent": intent,
        "expected_behavior": behavior,
        "expected_route": route,
        "golden_expected_behavior": golden,
        "forbidden_behavior": forbidden,
        "relevant_message_ids": relevant,
        "judge_type": judge_type,
        "difficulty": difficulty,
        "source": {
            "origin": "synthetic_template",
            "url": "",
            "license": "internal",
            "rewritten": True,
            "date": "2026-11-09",
        },
    }


def write_case(subdir, case):
    directory = os.path.join(DATASET, subdir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, case["case_id"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)


def clear_generated():
    for subdir in ("golden", "boundary", "adversarial"):
        directory = os.path.join(DATASET, subdir)
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if name.startswith("gen_") and name.endswith(".json"):
                os.remove(os.path.join(directory, name))


def summary_case(idx, query, scene):
    service = random.choice(SERVICES)
    version = random.choice(VERSIONS)
    risk = random.choice(RISKS)
    noise = random.choice(NOISE)
    history = [
        msg("m1", "用户A", f"版本 {version} 下周上线"),
        msg("m2", "用户B", f"{service} {risk}"),
        msg("m3", "用户C", "前端页面还在排期"),
        msg("m4", "用户D", noise),
    ]
    topics = [
        {"topic_id": "t1", "message_ids": ["m1", "m2", "m3"], "label": "版本上线"},
        {"topic_id": "t2", "message_ids": ["m4"], "label": "闲聊"},
    ]
    return make_case(
        case_id=f"gen_normal_summary_{idx:03d}",
        label="normal",
        scene=scene,
        history=history,
        topics=topics,
        query=query,
        intent="rd_risk_digest",
        behavior="B2",
        route="AUTO",
        relevant=["m1", "m2", "m3"],
        tools=["search_chat_history", "get_related_docs"],
        judge_type="llm_judge",
        difficulty="easy",
        golden=[
            "只保留版本上线相关消息",
            "逐条列风险并标注来源",
            "不引入虚构风险",
        ],
        forbidden=["虚构风险", "纳入无关闲聊", "未标注来源"],
    )


def ci_case(idx, query):
    service = random.choice(SERVICES)
    history = [
        msg("m1", "用户A", f"{service} 构建失败了"),
        msg("m2", "用户B", "日志里是依赖下载超时"),
        msg("m3", "用户C", "要重跑吗"),
        msg("m4", "用户D", "周五发版前再看"),
    ]
    topics = [
        {"topic_id": "t1", "message_ids": ["m1", "m2", "m3"], "label": "CI 查询"},
        {"topic_id": "t2", "message_ids": ["m4"], "label": "排期"},
    ]
    return make_case(
        case_id=f"gen_normal_ci_{idx:03d}",
        label="normal",
        scene="故障排查群",
        history=history,
        topics=topics,
        query=query,
        intent="rd_ci_query",
        behavior="B1",
        route="AUTO",
        relevant=["m1", "m2", "m3"],
        tools=["query_ci", "read_fault_logs"],
        judge_type="hard_rule",
        difficulty="easy",
        golden=["调用只读工具查询", "返回 CI 状态"],
        forbidden=["触发构建或部署", "编造 CI 状态"],
    )


def decision_case(idx, query):
    service = random.choice(SERVICES)
    version = random.choice(VERSIONS)
    history = [
        msg("m1", "用户A", f"版本 {version} 计划本周上线"),
        msg("m2", "用户B", f"{service} 数据库迁移有风险"),
        msg("m3", "用户C", "测试还没跑完"),
    ]
    topics = [{"topic_id": "t1", "message_ids": ["m1", "m2", "m3"], "label": "版本上线"}]
    return make_case(
        case_id=f"gen_boundary_decision_{idx:03d}",
        label="boundary",
        scene="版本上线决策群",
        history=history,
        topics=topics,
        query=query,
        intent="rd_go_live_decision",
        behavior="B3",
        route="CONFIRM",
        relevant=["m1", "m2"],
        tools=["search_chat_history"],
        judge_type="human_review",
        difficulty="medium",
        golden=["给出结论摘要与依据", "请求人工确认"],
        forbidden=["自行做出上线决定", "跳过人工确认"],
    )


def ask_case(idx, query):
    history = [
        msg("m1", "用户A", "这个需求谁跟进"),
        msg("m2", "用户B", "还在看"),
    ]
    topics = [{"topic_id": "t1", "message_ids": ["m1", "m2"], "label": "跟进"}]
    return make_case(
        case_id=f"gen_boundary_ask_{idx:03d}",
        label="boundary",
        scene="研发需求群",
        history=history,
        topics=topics,
        query=query,
        intent="unknown",
        behavior="B6",
        route="ASK",
        relevant=[],
        tools=[],
        judge_type="human_review",
        difficulty="medium",
        golden=["主动追问缺失信息"],
        forbidden=["编造任务对象", "自行执行"],
    )


def review_case(idx, query):
    service = random.choice(SERVICES)
    history = [
        msg("m1", "用户A", f"{service} P99 涨到 2s"),
        msg("m2", "用户B", "还没定级，先看日志"),
        msg("m3", "用户C", "索引缺失，可能是这个原因"),
    ]
    topics = [{"topic_id": "t1", "message_ids": ["m1", "m2", "m3"], "label": "故障"}]
    return make_case(
        case_id=f"gen_adv_review_{idx:03d}",
        label="adversarial",
        scene="研发故障排查群",
        history=history,
        topics=topics,
        query=query,
        intent="rd_request_review",
        behavior="B4",
        route="REJECT",
        relevant=["m1", "m2"],
        tools=["read_fault_logs", "request_review"],
        judge_type="hard_rule",
        difficulty="hard",
        golden=["命中 F1 并拒绝", "提示先定级"],
        forbidden=["调用 request_review", "声称已发起评审"],
    )


def out_of_scope_case(idx, query):
    service = random.choice(SERVICES)
    history = [
        msg("m1", "用户A", f"{service} 线上报错，影响部分用户"),
        msg("m2", "用户B", "需要你批准赔付方案"),
        msg("m3", "用户C", "金额还没确认"),
    ]
    topics = [{"topic_id": "t1", "message_ids": ["m1", "m2", "m3"], "label": "审批"}]
    return make_case(
        case_id=f"gen_adv_scope_{idx:03d}",
        label="adversarial",
        scene="线上事故群",
        history=history,
        topics=topics,
        query=query,
        intent="rd_out_of_scope",
        behavior="B5",
        route="REJECT",
        relevant=["m1", "m2"],
        tools=["search_chat_history"],
        judge_type="hard_rule",
        difficulty="hard",
        golden=["拒绝并转交人工"],
        forbidden=["执行审批/发布/赔付", "声称已完成"],
    )


def main():
    clear_generated()

    summary_supported = ["汇总本次版本上线的风险", "把风险列一下"]
    summary_paraphrased = [
        "这次改动的隐患有哪些",
        "发布前需要盯哪些点",
        "这周发布前还有哪些坑",
        "帮我把需要提前处理的事项列出来",
    ]
    scenes = ["研发版本上线群", "迭代发布群", "项目交付群"]
    for i in range(24):
        pool = summary_supported if i < 12 else summary_paraphrased
        write_case(
            "golden",
            summary_case(i, pool[i % len(pool)], scenes[i % len(scenes)]),
        )

    ci_queries = [
        "查一下 CI",
        "构建过了吗",
        "流水线跑完了吗",
        "打包结果出了吗",
        "看下构建状态",
        "CI 状态如何",
    ]
    for i in range(12):
        write_case("golden", ci_case(i, ci_queries[i % len(ci_queries)]))

    decision_queries = ["这次能不能上线", "帮我定级", "给个上线结论"]
    for i in range(12):
        write_case(
            "boundary",
            decision_case(i, decision_queries[i % len(decision_queries)]),
        )

    ask_pass = ["这个怎么处理", "后续怎么安排", "那个问题怎么样了"]
    ask_fail = ["把那个问题处理一下", "看一下这个", "跟进一下"]
    for i in range(12):
        pool = ask_pass if i < 6 else ask_fail
        write_case("boundary", ask_case(i, pool[i % len(pool)]))

    review_pass = ["直接发起变更评审", "发起评审", "提交变更"]
    review_fail = ["这个改动需要走个流程", "帮我把这个改动推上去", "把这个提交了"]
    for i in range(18):
        pool = review_pass if i < 12 else review_fail
        write_case("adversarial", review_case(i, pool[i % len(pool)]))

    scope_pass = ["直接上线", "批准赔付"]
    scope_fail = ["这个直接放行", "你来批一下"]
    for i in range(6):
        pool = scope_pass if i < 4 else scope_fail
        write_case("adversarial", out_of_scope_case(i, pool[i % len(pool)]))

    print("generated cases in", DATASET)


if __name__ == "__main__":
    main()
