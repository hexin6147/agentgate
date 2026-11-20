import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.feishu import (
    FeishuBot,
    build_confirmation_card,
    build_synthetic_case,
    extract_text,
)


class TestFeishuParsing(unittest.TestCase):
    def test_extract_text_strips_mentions(self):
        message = {"content": '{"text":"@_user_1 汇总本次版本上线的风险"}'}
        self.assertEqual(extract_text(message), "汇总本次版本上线的风险")

    def test_synthetic_case_keeps_trigger_query(self):
        case = build_synthetic_case("汇总本次版本上线的风险")
        self.assertEqual(case.trigger_query, "汇总本次版本上线的风险")
        self.assertEqual(case.agent_id, "rd_collab")


class TestFeishuCard(unittest.TestCase):
    def test_card_has_approve_and_reject(self):
        card = build_confirmation_card(
            task_id="t1",
            title="发起变更评审",
            tool="request_review",
            params={"project_id": "pay"},
            fences=[{"fence_id": "F1", "passed": False, "reason": "not leveled"}],
        )
        actions = [
            element
            for element in card["elements"]
            if element.get("tag") == "action"
        ]
        buttons = [button for element in actions for button in element["actions"]]
        values = [button["value"] for button in buttons]
        self.assertIn({"action": "approve", "task_id": "t1"}, values)
        self.assertIn({"action": "reject", "task_id": "t1"}, values)


class TestFeishuBot(unittest.TestCase):
    def test_bot_replies_with_output(self):
        replies = []

        def reply(text, card=None):
            replies.append((text, card))

        bot = FeishuBot(reply_fn=reply)
        result = bot.handle_text(
            "汇总本次版本上线的风险",
            {"project_id": "pay"},
        )

        self.assertEqual(result.status, "DONE")
        self.assertTrue(replies)
        self.assertIn("数据库", replies[0][0])

    def test_bot_sends_card_when_confirmation_required(self):
        replies = []

        def reply(text, card=None):
            replies.append((text, card))

        bot = FeishuBot(reply_fn=reply)
        result = bot.handle_text(
            "直接发起变更评审",
            {"project_id": "pay", "incident_leveled": True},
        )

        self.assertEqual(result.route, "CONFIRM")
        self.assertTrue(replies)
        card = replies[0][1]
        self.assertIsNotNone(card)
        actions = [e for e in card["elements"] if e.get("tag") == "action"]
        self.assertTrue(actions)


if __name__ == "__main__":
    unittest.main()
