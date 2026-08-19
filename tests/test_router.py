import unittest
import _testkit  # noqa: F401  -- sets up sys.path + anthropic stub

from state import SimulationState, AuditFinding, NextAction, AgentRole
from orchestrator import Router


def make_state(round_=0, max_rounds=5, threshold=80, score=50):
    s = SimulationState(target_system="dummy system", max_rounds=max_rounds, score_threshold=threshold)
    s.round = round_
    s.current_score = score
    return s


def add_audit(state, action: NextAction, score: int):
    state.current_score = score
    state.audits.append(
        AuditFinding(
            round=state.round + 1,
            score=score,
            verdict="partial",
            critique_of_red="ok",
            critique_of_blue="ok",
            recommended_next_action=action,
            justification="test",
        )
    )


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_escalate_overrides_passing_score(self):
        """A critical unresolved risk must force another round even if the
        numeric score already clears the threshold."""
        state = make_state(round_=0, threshold=80)
        add_audit(state, NextAction.ESCALATE, score=95)
        self.router.decide(state)
        self.assertEqual(state.next_agent, AgentRole.RED)
        self.assertEqual(state.status, "in_progress")

    def test_finalize_on_passing_score(self):
        state = make_state(round_=0, threshold=80)
        add_audit(state, NextAction.FINALIZE, score=85)
        self.router.decide(state)
        self.assertEqual(state.next_agent, AgentRole.DONE)
        self.assertEqual(state.status, "complete")

    def test_red_deepen_on_passing_score_also_finalizes(self):
        """A solid patch + no critical follow-up shouldn't burn extra rounds."""
        state = make_state(round_=0, threshold=80)
        add_audit(state, NextAction.RED_DEEPEN, score=90)
        self.router.decide(state)
        self.assertEqual(state.next_agent, AgentRole.DONE)
        self.assertEqual(state.status, "complete")

    def test_blue_refine_routes_to_blue(self):
        state = make_state(round_=0, threshold=80)
        add_audit(state, NextAction.BLUE_REFINE, score=40)
        self.router.decide(state)
        self.assertEqual(state.next_agent, AgentRole.BLUE)
        self.assertEqual(state.status, "in_progress")

    def test_low_score_red_deepen_routes_to_red(self):
        state = make_state(round_=0, threshold=80)
        add_audit(state, NextAction.RED_DEEPEN, score=40)
        self.router.decide(state)
        self.assertEqual(state.next_agent, AgentRole.RED)

    def test_round_limit_forces_finalize_even_on_escalate(self):
        """The hard guardrail: round budget beats every LLM recommendation,
        including ESCALATE, so the loop can never run forever."""
        state = make_state(round_=4, max_rounds=5, threshold=80)
        add_audit(state, NextAction.ESCALATE, score=20)
        self.router.decide(state)
        self.assertEqual(state.next_agent, AgentRole.DONE)
        self.assertEqual(state.status, "exhausted")

    def test_round_counter_increments_each_decision(self):
        state = make_state(round_=2, threshold=80)
        add_audit(state, NextAction.BLUE_REFINE, score=40)
        self.router.decide(state)
        self.assertEqual(state.round, 3)


if __name__ == "__main__":
    unittest.main()
