"""Live Feishu long-connection runner.

Run from the project virtualenv:

    cp .env.example .env      # fill FEISHU_APP_ID / FEISHU_APP_SECRET
    python -m agentgate.feishu_ws

The process keeps an in-memory pending-task map so a card approval can resume
the same case with a confirmation token.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

from .factory import build_agent
from .feishu import FeishuBot, build_synthetic_case, extract_text
from .harness import Harness
from .tools import ToolRegistry

PENDING: Dict[str, Dict[str, Any]] = {}


def _reply(
    client: Any,
    message_id: str,
    text: Optional[str] = None,
    card: Optional[Dict[str, Any]] = None,
) -> Any:
    if card is not None:
        content = json.dumps(card, ensure_ascii=False)
        msg_type = "interactive"
    else:
        content = json.dumps({"text": text or ""}, ensure_ascii=False)
        msg_type = "text"

    body = (
        ReplyMessageRequestBody.builder()
        .content(content)
        .msg_type(msg_type)
        .build()
    )
    request = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(body)
        .build()
    )
    response = client.im.v1.message.reply(request)
    if not response.success():
        print(f"[feishu] reply failed: {response.code} {response.msg}", flush=True)
    return response


def run() -> None:
    load_dotenv()
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise SystemExit("FEISHU_APP_ID / FEISHU_APP_SECRET missing in .env")

    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
    tools = ToolRegistry()
    harness = Harness(
        tools,
        trace_dir=os.getenv("AGENTGATE_TRACE_DIR", "eval/results"),
    )
    agent = build_agent(
        os.getenv("AGENTGATE_AGENT", "rule"),
        os.getenv("AGENTGATE_CONTEXT", "rule"),
    )
    bot = FeishuBot(
        reply_fn=lambda text, card=None: None,
        agent=agent,
        tools=tools,
        harness=harness,
    )
    default_project = os.getenv("AGENTGATE_PROJECT_ID", "demo")

    def on_message(data: Any) -> None:
        message = data.event.message
        text = extract_text(message)
        if not text:
            return

        ctx = {
            "project_id": default_project,
            "incident_leveled": os.getenv(
                "AGENTGATE_INCIDENT_LEVELED", "false"
            ).lower()
            == "true",
        }
        case = build_synthetic_case(text)

        def reply(text_out: str, card: Optional[Dict[str, Any]] = None) -> None:
            _reply(client, message.message_id, text_out, card)

        result = bot.handle_case(case, ctx, reply_fn=reply)
        if result.route == "CONFIRM":
            PENDING[result.run_id] = {"case": case, "ctx": ctx}
            print(f"[feishu] pending {result.run_id}", flush=True)
        else:
            print(f"[feishu] handled {result.case_id}: {result.status}", flush=True)

    def on_card(data: Any) -> None:
        event = data.event
        value = (event.action.value if event and event.action else None) or {}
        action = value.get("action")
        task_id = value.get("task_id")
        message_id = (
            event.context.open_message_id
            if event and event.context
            else None
        )

        if not task_id or task_id not in PENDING:
            if message_id:
                _reply(client, message_id, "任务已过期或不存在。")
            return

        entry = PENDING.pop(task_id)

        if action == "reject":
            if message_id:
                _reply(client, message_id, "已驳回。")
            return

        if action == "approve":
            ctx = dict(entry["ctx"])
            operator = getattr(event.operator, "open_id", "unknown")
            ctx["confirmation_token"] = f"feishu-{operator}"
            result = bot.harness.run_case(bot.agent, entry["case"], ctx)
            if message_id:
                _reply(client, message_id, result.output)
            return

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .register_p2_card_action_trigger(on_card)
        .build()
    )
    ws = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    print("[feishu] starting long connection...", flush=True)
    ws.start()


if __name__ == "__main__":
    run()
