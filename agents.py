"""
agents.py — Agent definitions for the Red/Blue/Audit simulation.

Each agent is a thin wrapper around a single Anthropic Messages API call with
a role-specific system prompt. Agents communicate ONLY through SimulationState
— they never call each other directly — which keeps the orchestration
decoupled and easy to test in isolation.

Scope note: the Red Team agent produces conceptual attack narratives
(vulnerability class, target component, ordered high-level steps) for
tabletop-style threat modeling. It is explicitly instructed NOT to produce
working exploit code, malware, or actionable phishing content.
"""

from __future__ import annotations
import json
import os
import re
from typing import Any, Dict

import anthropic

from state import (
    SimulationState, AttackScenario, DefensePatch, AuditFinding,
    Severity, NextAction, AgentRole,
)

MODEL = os.environ.get("SIM_MODEL", "claude-sonnet-5")


def _extract_json(text: str) -> Dict[str, Any]:
    """Pull a JSON object out of a model response, tolerating code fences
    or stray prose around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)


class BaseAgent:
    role: AgentRole
    system_prompt: str

    def __init__(self, client: anthropic.Anthropic, model: str = MODEL):
        self.client = client
        self.model = model

    def _call(self, user_prompt: str, max_tokens: int = 1200) -> Dict[str, Any]:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, AttributeError) as e:
            raise ValueError(f"{self.role.value} returned non-JSON output:\n{text}") from e

    def run(self, state: SimulationState):
        raise NotImplementedError


class RedTeamAgent(BaseAgent):
    role = AgentRole.RED
    system_prompt = (
        "You are the Red Team agent in an authorized, simulated security "
        "tabletop exercise. Given a system architecture description and any "
        "prior audit feedback, identify ONE realistic vulnerability "
        "(software logic OR social engineering) and describe a conceptual "
        "attack chain against it — high-level ordered steps a real attacker "
        "would take, described narratively for training purposes. Do NOT "
        "produce working exploit code, malware, or ready-to-send phishing "
        "text; describe the pretext and mechanism only, at the level a "
        "threat model or pentest report would.\n\n"
        "If prior audit feedback says the attack surface was not fully "
        "explored, find a DIFFERENT vulnerability than previous rounds, or "
        "go deeper into an unpatched aspect of the same one.\n\n"
        "Respond ONLY with a single JSON object, no prose, no code fences:\n"
        "{\n"
        '  "vulnerability_type": string,\n'
        '  "target_component": string,\n'
        '  "is_social_engineering": boolean,\n'
        '  "severity": "low"|"medium"|"high"|"critical",\n'
        '  "attack_chain": [string, ...],\n'
        '  "rationale": string\n'
        "}"
    )

    def run(self, state: SimulationState) -> SimulationState:
        prior = ""
        if state.latest_audit():
            a = state.latest_audit()
            prior = (
                f"\n\nPrevious audit critique of Red Team: {a.critique_of_red}\n"
                f"Recommended next action: {a.recommended_next_action.value}"
            )
        prompt = (
            f"System architecture:\n{state.target_system}\n"
            f"\nRound: {state.round + 1}"
            f"{prior}"
        )
        data = self._call(prompt)
        attack = AttackScenario(
            round=state.round + 1,
            vulnerability_type=data["vulnerability_type"],
            target_component=data["target_component"],
            is_social_engineering=bool(data["is_social_engineering"]),
            severity=Severity(data["severity"]),
            attack_chain=list(data["attack_chain"]),
            rationale=data["rationale"],
        )
        state.attacks.append(attack)
        state.log(
            "RedTeam",
            f"Round {attack.round}: {attack.vulnerability_type} on "
            f"{attack.target_component} ({attack.severity.value})",
        )
        state.next_agent = AgentRole.BLUE
        return state


class BlueTeamAgent(BaseAgent):
    role = AgentRole.BLUE
    system_prompt = (
        "You are the Blue Team agent in an authorized, simulated security "
        "tabletop exercise. Given a specific attack scenario devised by the "
        "Red Team, propose concrete defensive countermeasures: architectural "
        "changes, controls, policies, monitoring, or training that would "
        "prevent or significantly limit this attack. Be specific about WHAT "
        "changes and WHERE, not generic advice like 'improve security'.\n\n"
        "Respond ONLY with a single JSON object, no prose, no code fences:\n"
        "{\n"
        '  "description": string,\n'
        '  "controls": [string, ...],\n'
        '  "residual_risk": string\n'
        "}"
    )

    def run(self, state: SimulationState) -> SimulationState:
        attack = state.latest_attack()
        prior = ""
        if state.latest_audit():
            a = state.latest_audit()
            prior = f"\n\nPrevious audit critique of Blue Team: {a.critique_of_blue}"
        prompt = (
            f"System architecture:\n{state.target_system}\n\n"
            f"Attack to defend against (round {attack.round}):\n"
            f"Vulnerability: {attack.vulnerability_type}\n"
            f"Target: {attack.target_component}\n"
            f"Severity: {attack.severity.value}\n"
            f"Attack chain: {attack.attack_chain}\n"
            f"Rationale: {attack.rationale}"
            f"{prior}"
        )
        data = self._call(prompt)
        patch = DefensePatch(
            round=state.round + 1,
            addresses_round=attack.round,
            description=data["description"],
            controls=list(data["controls"]),
            residual_risk=data["residual_risk"],
        )
        state.patches.append(patch)
        state.log(
            "BlueTeam",
            f"Round {patch.round}: {len(patch.controls)} controls proposed "
            f"for round {patch.addresses_round} attack",
        )
        state.next_agent = AgentRole.AUDIT
        return state


class AuditorAgent(BaseAgent):
    role = AgentRole.AUDIT
    system_prompt = (
        "You are the independent Security Auditor agent. You review one "
        "Red Team attack scenario and the matching Blue Team defense, and "
        "you critique BOTH sides honestly — do not simply agree with "
        "either. Score how well the defense addresses the attack from 0 "
        "(no mitigation) to 100 (fully mitigated, no meaningful residual "
        "risk). Then recommend what should happen next in the exercise.\n\n"
        "recommended_next_action must be one of:\n"
        '  "red_deepen"  — Blue\'s patch looks solid; Red should probe a '
        "different or deeper angle next round\n"
        '  "blue_refine" — the patch has real gaps; Blue should revise it '
        "before moving on\n"
        '  "escalate"    — residual risk is critical regardless of score; '
        "force another round\n"
        '  "finalize"    — security posture is acceptable, the exercise '
        "can conclude\n\n"
        "Respond ONLY with a single JSON object, no prose, no code fences:\n"
        "{\n"
        '  "score": integer 0-100,\n'
        '  "verdict": "pass"|"partial"|"fail",\n'
        '  "critique_of_red": string,\n'
        '  "critique_of_blue": string,\n'
        '  "recommended_next_action": "red_deepen"|"blue_refine"|"escalate"|"finalize",\n'
        '  "justification": string\n'
        "}"
    )

    def run(self, state: SimulationState) -> SimulationState:
        attack = state.latest_attack()
        patch = state.latest_patch()
        prompt = (
            f"Attack (round {attack.round}): {attack.vulnerability_type} on "
            f"{attack.target_component}, severity {attack.severity.value}\n"
            f"Attack chain: {attack.attack_chain}\n\n"
            f"Defense (round {patch.round}): {patch.description}\n"
            f"Controls: {patch.controls}\n"
            f"Blue's stated residual risk: {patch.residual_risk}\n\n"
            f"Round {state.round + 1} of max {state.max_rounds}. "
            f"Score threshold to finalize: {state.score_threshold}."
        )
        data = self._call(prompt)
        finding = AuditFinding(
            round=state.round + 1,
            score=int(data["score"]),
            verdict=data["verdict"],
            critique_of_red=data["critique_of_red"],
            critique_of_blue=data["critique_of_blue"],
            recommended_next_action=NextAction(data["recommended_next_action"]),
            justification=data["justification"],
        )
        state.audits.append(finding)
        state.current_score = finding.score
        state.log(
            "Auditor",
            f"Round {finding.round}: score={finding.score} "
            f"verdict={finding.verdict} next={finding.recommended_next_action.value}",
        )
        state.next_agent = AgentRole.ROUTER
        return state


class ReportAgent(BaseAgent):
    """Not part of the loop — invoked once at the end to summarize."""
    role = AgentRole.DONE
    system_prompt = (
        "You are a security report writer. Given the full transcript of a "
        "Red/Blue/Audit tabletop exercise, write a concise executive "
        "summary: overall risk posture, the most severe unresolved issue "
        "(if any), and 3 prioritized recommendations. Respond ONLY with a "
        "single JSON object, no prose outside it:\n"
        "{\n"
        '  "executive_summary": string,\n'
        '  "final_score": integer,\n'
        '  "top_recommendations": [string, string, string]\n'
        "}"
    )

    def run(self, state: SimulationState) -> Dict[str, Any]:
        prompt = "Full exercise state:\n" + json.dumps(state.to_dict(), indent=2, default=str)
        return self._call(prompt, max_tokens=800)
