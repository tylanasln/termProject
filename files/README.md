# Red / Blue / Audit Security Simulation — Orchestration Capstone

A custom (framework-free) multi-agent orchestration where a **Red Team** agent
devises attack scenarios, a **Blue Team** agent proposes defenses, and an
**Auditor** agent critiques both sides, scores the round, and decides what
happens next — all driven by model reasoning rather than a fixed script.

## Quick start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python main.py
```

This runs the example architecture in `main.py` and writes the full
transcript + scored history to `output/simulation_result.json`. Swap in your
own system by editing `EXAMPLE_ARCHITECTURE` or calling
`Orchestrator().run(your_description, max_rounds=5, score_threshold=80)`
from your own script.

Model defaults to `claude-sonnet-5`; override with `SIM_MODEL=<model-id>`.

## Files

| File | Role |
|---|---|
| `state.py` | `SimulationState` — the single shared object every agent reads/writes |
| `agents.py` | `RedTeamAgent`, `BlueTeamAgent`, `AuditorAgent`, `ReportAgent` |
| `orchestrator.py` | `Router` (dynamic routing) + `Orchestrator` (the loop) |
| `main.py` | Example run |
| `tests/` | Offline unit tests — no API key or network needed |

## Running the tests

The test suite stubs out the `anthropic` package (see `tests/_testkit.py`) so
it runs with zero API calls and zero cost. It's real coverage, not a smoke
test:

```bash
python -m unittest discover -s tests -v
```

- `test_router.py` — every branch of `Router.decide()`: an `escalate`
  verdict overriding a passing score, the `max_rounds` guardrail overriding
  even `escalate`, `blue_refine` routing back to Blue, a low score with
  `red_deepen` routing to Red, and the round counter incrementing correctly.
- `test_json_extraction.py` — the model-output parser handles raw JSON,
  code-fenced JSON, JSON with surrounding prose, and raises on garbage.
- `test_agents_feedback_loop.py` — agents correctly append to
  `SimulationState` and, most importantly, prove the *feedback loop* is
  real: a round-2 prompt to Red/Blue actually contains the literal text of
  the Auditor's round-1 critique, not just a summary of it.

Last run: **15/15 passed**, 0 network calls.

## How this maps to the rubric

**State management.** `SimulationState` is a dataclass carrying the target
system, round number, every `AttackScenario` / `DefensePatch` / `AuditFinding`
so far, the running score, and a timestamped transcript. Agents never talk to
each other directly or keep private memory — they only read and append to
this object, which is what lets the whole exercise be replayed, serialized
(`state.save(...)`), or inspected mid-run.

**Feedback loops.** The Auditor doesn't just emit a score — it writes a
named critique of Red *and* a named critique of Blue every round, and both
critiques are fed back into the *next* round's prompt to that agent
(`agents.py`, the `prior` block in `RedTeamAgent.run` / `BlueTeamAgent.run`).
So round 2's attack is shaped by what the Auditor said was wrong with round
1's attack, and likewise for the patch — this is what makes it a loop with
memory rather than three independent one-shot calls.

**Dynamic routing.** `Router.decide()` does not walk a fixed
Red→Blue→Audit→Red→Blue→Audit sequence. Each round it reads the Auditor's
`recommended_next_action` (`red_deepen` / `blue_refine` / `escalate` /
`finalize`) — a judgement the Auditor made from actually reading that
round's attack and defense — and branches accordingly: weak patches get
sent back to Blue instead of moving on, a critical unresolved risk forces
another round even if the score looks fine, and a clean bill of health ends
the exercise early instead of always burning the full round budget.

The one deliberate piece of non-LLM logic is two guardrails: a hard
`max_rounds` cap, and "escalate" overriding a passing score. I kept these
deterministic on purpose — letting an LLM's own judgement be the *only*
thing that can stop the loop is a real reliability risk (a model can get
stuck agreeing everything's fine, or never converge). This "LLM decides the
branch, orchestrator enforces the bounds" split is the pattern I'd defend if
asked why routing isn't 100% model-driven.

## Scope note on the Red Team agent

Its system prompt restricts it to conceptual attack narratives — vulnerability
class, target component, ordered high-level steps — for tabletop-style threat
modeling. It's explicitly told not to produce working exploit code, malware,
or ready-to-send phishing content. That's both good practice for this kind of
exercise and a constraint I'd keep regardless of what a grader asked for.

## Extending it

- Add a `Governance`/`HumanApproval` agent as a required gate before
  `finalize`, for a human-in-the-loop variant.
- Persist `SimulationState` between runs to build a running vulnerability
  history across multiple target systems.
- Port `Router`/`Orchestrator` to a graph framework (e.g. LangGraph's
  `StateGraph`) if your course requires one — the state shape and routing
  logic here translate directly to graph nodes/edges.
- Add token/cost tracking per agent call for a "cost of the audit" metric.
- Write unit tests that mock the Anthropic client and feed canned JSON
  responses through `Router.decide()` to check branch logic in isolation
  (no API calls needed for that part).

## Submission form

A pre-filled `SENG456_submission_form.pdf` is provided alongside this
project. All technical sections (Project Summary, System Design, Agents/
Tools table, Implementation, Tests & Results, Security checklist,
Conclusion) are already completed from this codebase and the real offline
test run above. Still needed before submitting:

- Personal fields (Full Name, Student ID, Department, Email) and the
  Student Declaration signature block.
- GitHub / Project URL and Submission Date.
- Decide whether to check the last submission-checklist box (demo/video
  links) — left unchecked since no demo exists yet.

A live run against the real Claude API (`python main.py` with
`ANTHROPIC_API_KEY` set) is **optional, not required** — the template's own
checklist only asks for "a test result or sample usage result," which the
offline test suite and the sample input/output already satisfy. Only run
`main.py` if you want to see it work live or want a real transcript for
your own interest; it costs a small amount of real money since it's a paid
API, so there's no need to do it just for this submission.
