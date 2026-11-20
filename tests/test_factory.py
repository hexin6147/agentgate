import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agentgate.factory import build_agent
from agentgate.langgraph_agent import LangGraphAgent
from samples.rd_collab.adapter import RuleBasedAgent


class TestFactory(unittest.TestCase):
    def test_rule_agent(self):
        self.assertIsInstance(build_agent("rule"), RuleBasedAgent)

    def test_llm_agent_constructs_without_network(self):
        # Construction is lazy; no model call happens here.
        self.assertIsInstance(build_agent("llm"), LangGraphAgent)

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            build_agent("unknown")

    def test_rule_agent_with_bge_context(self):
        agent = build_agent("rule", context="bge")
        self.assertIsNotNone(agent.context_filter)

    def test_llm_agent_with_bge_context(self):
        agent = build_agent("llm", context="bge")
        self.assertIsNotNone(agent.core.context_filter)

    def test_unknown_context_raises(self):
        with self.assertRaises(ValueError):
            build_agent("rule", context="unknown")

    def test_ticket_agent(self):
        self.assertIsInstance(build_agent("ticket"), LangGraphAgent)


if __name__ == "__main__":
    unittest.main()
