import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.context import SemanticContextFilter, cosine
from agentgate.models import Message


def msg(mid, text):
    return Message(message_id=mid, user="用户", ts="t", msg=text)


class FakeEmbedder:
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        return self.vectors[: len(texts)]


class TestCosine(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0)

    def test_orthogonal(self):
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0)

    def test_zero_vector(self):
        self.assertEqual(cosine([0, 0], [1, 0]), 0.0)


class TestSemanticContextFilter(unittest.TestCase):
    def setUp(self):
        self.messages = [
            msg("m1", "版本上线"),
            msg("m2", "数据库迁移风险"),
            msg("m3", "中午吃什么"),
        ]
        # query + m1 + m2 + m3
        self.vectors = [[1, 0], [0.9, 0.1], [0.8, 0.2], [0.0, 1.0]]
        self.filter = SemanticContextFilter(
            FakeEmbedder(self.vectors), top_k=2, threshold=0.5
        )

    def test_keeps_relevant_drops_noise(self):
        kept, dropped = self.filter.filter("发布风险", self.messages)
        self.assertEqual([m.message_id for m in kept], ["m1", "m2"])
        self.assertEqual(dropped, ["m3"])

    def test_preserves_original_order(self):
        kept, _ = self.filter.filter("发布风险", self.messages)
        self.assertEqual([m.message_id for m in kept], sorted(m.message_id for m in kept))

    def test_no_match_keeps_all(self):
        vectors = [[1, 0], [0, 1], [0, 1], [0, 1]]
        f = SemanticContextFilter(FakeEmbedder(vectors), top_k=3, threshold=0.5)
        kept, dropped = f.filter("q", self.messages)
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, [])

    def test_fallback_on_embed_error(self):
        def boom(texts):
            raise RuntimeError("embedding down")

        fallback = lambda query, messages: (list(messages), [])
        f = SemanticContextFilter(boom, fallback=fallback)
        kept, dropped = f.filter("q", self.messages)
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, [])


class TestAgentContextIntegration(unittest.TestCase):
    def test_agent_uses_injected_context_filter(self):
        import json

        from agentgate.harness import Harness
        from agentgate.schema import validate_case
        from agentgate.tools import ToolRegistry
        from samples.rd_collab.adapter import RuleBasedAgent

        class KeepTwo:
            def filter(self, query, messages):
                keep = {"m1", "m2"}
                kept = [m for m in messages if m.message_id in keep]
                dropped = [m.message_id for m in messages if m.message_id not in keep]
                return kept, dropped

        with open(
            os.path.join(ROOT, "eval/dataset/golden/sample_rd_001.json"),
            encoding="utf-8",
        ) as f:
            case = validate_case(json.load(f))

        agent = RuleBasedAgent(context_filter=KeepTwo())
        result = Harness(ToolRegistry()).run_case(agent, case, {"project_id": "pay"})

        self.assertIn("m1", result.output)
        self.assertNotIn("m4", result.output)
        filter_step = [
            s for s in result.trace["steps"] if s["node"] == "filter"
        ][0]
        self.assertEqual(filter_step["strategy"], "semantic")


if __name__ == "__main__":
    unittest.main()
