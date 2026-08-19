import json
import unittest
import _testkit  # noqa: F401
from _testkit import FakeClient

from state import SimulationState, AgentRole, Severity, NextAction
from agents import RedTeamAgent, BlueTeamAgent, AuditorAgent

RED_JSON = json.dumps({
    "vulnerability_type": "Broken Access Control",
    "target_component": "Admin panel",
    "is_social_engineering": False,
    "severity": "high",
    "attack_chain": ["Log in as low-privilege support agent", "Access admin-only refund endpoint directly by URL"],
    "rationale": "No server-side role check on the refund endpoint.",
})

BLUE_JSON = json.dumps({
    "description": "Enforce role-based access control on all admin endpoints.",
    "controls": ["Add server-side RBAC middleware", "Add audit logging on refund endpoint"],
    "residual_risk": "Low, pending a full endpoint audit.",
})

AUDIT_JSON = json.dumps({
    "score": 55,
    "verdict": "partial",
    "critique_of_red": "Good find, but only tested one endpoint.",
    "critique_of_blue": "Middleware helps but other admin routes are unchecked.",
    "recommended_next_action": "blue_refine",
    "justification": "Patch is incomplete relative to the attack surface.",
})


class TestRedTeamAgent(unittest.TestCase):
    def test_run_appends_attack_and_routes_to_blue(self):
        client = FakeClient([RED_JSON])
        agent = RedTeamAgent(client, model="test-model")
        state = SimulationState(target_system="test system")

        state = agent.run(state)

        self.assertEqual(len(state.attacks), 1)
        self.assertEqual(state.attacks[0].vulnerability_type, "Broken Access Control")
        self.assertEqual(state.attacks[0].severity, Severity.HIGH)
        self.assertEqual(state.next_agent, AgentRole.BLUE)


class TestBlueTeamAgent(unittest.TestCase):
    def test_run_appends_patch_and_routes_to_audit(self):
        client = FakeClient([RED_JSON, BLUE_JSON])
        red = RedTeamAgent(client, model="test-model")
        blue = BlueTeamAgent(client, model="test-model")
        state = SimulationState(target_system="test system")

        state = red.run(state)
        state = blue.run(state)

        self.assertEqual(len(state.patches), 1)
        self.assertEqual(state.patches[0].addresses_round, state.attacks[0].round)
        self.assertEqual(state.next_agent, AgentRole.AUDIT)


class TestFeedbackLoopThreading(unittest.TestCase):
    """The feedback loop only works if each round's prompt actually contains
    the previous round's audit critique -- this proves that wiring."""

    def test_round_two_red_prompt_contains_prior_critique(self):
        client = FakeClient([RED_JSON, BLUE_JSON, AUDIT_JSON, RED_JSON])
        red = RedTeamAgent(client, model="test-model")
        blue = BlueTeamAgent(client, model="test-model")
        audit = AuditorAgent(client, model="test-model")
        state = SimulationState(target_system="test system")

        state = red.run(state)
        state = blue.run(state)
        state = audit.run(state)
        self.assertEqual(state.audits[0].recommended_next_action, NextAction.BLUE_REFINE)

        state.round += 1  # simulate what Router does before the next agent runs
        state = red.run(state)  # round 2 Red call

        second_red_call = client.calls[-1]
        prompt_sent = second_red_call["messages"][0]["content"]
        self.assertIn("Good find, but only tested one endpoint.", prompt_sent)

    def test_blue_prompt_contains_prior_critique_of_blue(self):
        client = FakeClient([RED_JSON, BLUE_JSON, AUDIT_JSON, BLUE_JSON])
        red = RedTeamAgent(client, model="test-model")
        blue = BlueTeamAgent(client, model="test-model")
        audit = AuditorAgent(client, model="test-model")
        state = SimulationState(target_system="test system")

        state = red.run(state)
        state = blue.run(state)
        state = audit.run(state)
        state = blue.run(state)  # Router sent it back to Blue for refinement

        second_blue_call = client.calls[-1]
        prompt_sent = second_blue_call["messages"][0]["content"]
        self.assertIn("Middleware helps but other admin routes are unchecked.", prompt_sent)


if __name__ == "__main__":
    unittest.main()
