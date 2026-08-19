"""
state.py — Shared state management for the Red/Blue/Audit security simulation.

This module defines the single source of truth that is threaded through every
agent call. Every agent reads from and writes to this object; nothing lives
only in an agent's local memory. This is what gives the orchestration its
"state management" property required by the capstone brief.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import json
import time


class AgentRole(str, Enum):
    RED = "red_team"
    BLUE = "blue_team"
    AUDIT = "auditor"
    ROUTER = "router"
    DONE = "done"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NextAction(str, Enum):
    RED_DEEPEN = "red_deepen"    # patch looks solid; Red should probe a new/deeper angle
    BLUE_REFINE = "blue_refine"  # patch has real gaps; Blue should revise it
    ESCALATE = "escalate"        # critical unresolved risk; force another round regardless of score
    FINALIZE = "finalize"        # posture acceptable; exercise can conclude


@dataclass
class AttackScenario:
    round: int
    vulnerability_type: str          # e.g. "Broken Access Control", "Pretexting / Social Engineering"
    target_component: str
    is_social_engineering: bool
    severity: Severity
    attack_chain: List[str]          # ordered narrative steps, NOT working exploit code
    rationale: str


@dataclass
class DefensePatch:
    round: int
    addresses_round: int             # which AttackScenario.round this responds to
    description: str
    controls: List[str]              # concrete mitigations / architectural changes
    residual_risk: str


@dataclass
class AuditFinding:
    round: int
    score: int                       # 0-100 security score for this round
    verdict: str                     # "pass" | "partial" | "fail"
    critique_of_red: str
    critique_of_blue: str
    recommended_next_action: NextAction
    justification: str


@dataclass
class SimulationState:
    target_system: str
    max_rounds: int = 5
    score_threshold: int = 80
    round: int = 0
    status: str = "in_progress"      # in_progress | complete | exhausted
    next_agent: AgentRole = AgentRole.RED
    attacks: List[AttackScenario] = field(default_factory=list)
    patches: List[DefensePatch] = field(default_factory=list)
    audits: List[AuditFinding] = field(default_factory=list)
    current_score: int = 0
    transcript: List[str] = field(default_factory=list)
    final_report: Optional[dict] = None

    def log(self, speaker: str, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.transcript.append(f"[{stamp}] ({speaker}) {message}")

    def latest_attack(self) -> Optional[AttackScenario]:
        return self.attacks[-1] if self.attacks else None

    def latest_patch(self) -> Optional[DefensePatch]:
        return self.patches[-1] if self.patches else None

    def latest_audit(self) -> Optional[AuditFinding]:
        return self.audits[-1] if self.audits else None

    def to_dict(self) -> dict:
        def conv(o):
            d = dict(o.__dict__)
            for k, v in d.items():
                if isinstance(v, Enum):
                    d[k] = v.value
            return d

        return {
            "target_system": self.target_system,
            "round": self.round,
            "status": self.status,
            "current_score": self.current_score,
            "attacks": [conv(a) for a in self.attacks],
            "patches": [conv(p) for p in self.patches],
            "audits": [conv(a) for a in self.audits],
            "transcript": self.transcript,
            "final_report": self.final_report,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
