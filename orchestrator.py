"""
orchestrator.py — Feedback loop + dynamic routing controller.

The Router is deliberately NOT a static if/else chain over a fixed agent
order. The Auditor agent already produced a semantic judgement
(`recommended_next_action`) grounded in its critique of that round's
attack/defense pair; the Router's job is to turn that judgement into a
concrete state transition, while enforcing two hard guardrails that no LLM
output is allowed to override:

    1. never exceed max_rounds   (cost / runtime bound)
    2. a critical unresolved risk always forces another round, even if the
       numeric score alone would look "good enough"

This "LLM proposes, orchestrator validates" split is the standard safe
pattern for dynamic routing: which branch to take is decided by model
reasoning every round (genuinely dynamic, and different each run), while the
loop's termination guarantees are deterministic so the simulation can't run
away or stop for the wrong reason.
"""

from __future__ import annotations
from typing import Optional

import anthropic

from state import SimulationState, AgentRole, NextAction
from agents import RedTeamAgent, BlueTeamAgent, AuditorAgent, ReportAgent


class Router:
    def decide(self, state: SimulationState) -> None:
        audit = state.latest_audit()
        state.round += 1

        hit_round_limit = state.round >= state.max_rounds
        score_ok = state.current_score >= state.score_threshold

        # Guardrail: critical residual risk overrides everything except the
        # round budget — the exercise cannot "finalize" over a critical gap.
        if audit.recommended_next_action == NextAction.ESCALATE and not hit_round_limit:
            state.next_agent = AgentRole.RED
            state.status = "in_progress"
            state.log(
                "Router",
                f"ESCALATE overrides score — routing to Red Team (round {state.round + 1})",
            )
            return

        if hit_round_limit:
            state.status = "exhausted"
            state.next_agent = AgentRole.DONE
            state.log("Router", "Round limit reached — finalizing")
            return

        if score_ok and audit.recommended_next_action in (
            NextAction.FINALIZE,
            NextAction.RED_DEEPEN,
        ):
            state.status = "complete"
            state.next_agent = AgentRole.DONE
            state.log(
                "Router",
                f"Score {state.current_score} >= threshold {state.score_threshold} — finalizing",
            )
            return

        if audit.recommended_next_action == NextAction.BLUE_REFINE:
            state.next_agent = AgentRole.BLUE
            state.log("Router", f"Routing back to Blue Team to refine round {audit.round} patch")
            return

        # Default: red_deepen or a fail verdict with round budget remaining.
        state.next_agent = AgentRole.RED
        state.log("Router", f"Routing to Red Team for round {state.round + 1}")


class Orchestrator:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        kwargs = {"model": model} if model else {}
        self.red = RedTeamAgent(self.client, **kwargs)
        self.blue = BlueTeamAgent(self.client, **kwargs)
        self.audit = AuditorAgent(self.client, **kwargs)
        self.report = ReportAgent(self.client, **kwargs)
        self.router = Router()

    def run(self, target_system: str, max_rounds: int = 5, score_threshold: int = 80) -> SimulationState:
        state = SimulationState(
            target_system=target_system,
            max_rounds=max_rounds,
            score_threshold=score_threshold,
        )
        state.log(
            "Orchestrator",
            f"Starting exercise (max_rounds={max_rounds}, threshold={score_threshold})",
        )

        while state.next_agent != AgentRole.DONE:
            if state.next_agent == AgentRole.RED:
                state = self.red.run(state)
            elif state.next_agent == AgentRole.BLUE:
                state = self.blue.run(state)
            elif state.next_agent == AgentRole.AUDIT:
                state = self.audit.run(state)
            elif state.next_agent == AgentRole.ROUTER:
                self.router.decide(state)
            else:
                raise RuntimeError(f"Unknown next_agent: {state.next_agent}")

        state.final_report = self.report.run(state)
        state.log("ReportAgent", state.final_report["executive_summary"])
        return state
