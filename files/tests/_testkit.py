"""
_testkit.py — shared test setup.

Injects a minimal stub for the `anthropic` package into sys.modules if the
real package isn't installed, so this whole test suite runs offline with
zero network calls and zero API cost. If the real `anthropic` package IS
installed (e.g. in the student's dev environment), this does nothing and
the real package is used untouched.

Also puts the project root on sys.path so `import state`, `import agents`,
`import orchestrator` work when tests are run from anywhere.
"""

import os
import sys
import types

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if "anthropic" not in sys.modules:
    try:
        import anthropic  # noqa: F401  -- real package available, use it
    except ImportError:
        stub = types.ModuleType("anthropic")

        class _StubAnthropic:
            def __init__(self, *args, **kwargs):
                pass

        stub.Anthropic = _StubAnthropic
        sys.modules["anthropic"] = stub


class FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, text: str):
        self.content = [FakeTextBlock(text)]


class FakeClient:
    """Stands in for anthropic.Anthropic(). Queue up JSON strings; each
    call to messages.create() pops the next one and records the call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            text = self._outer._responses.pop(0)
            return FakeResponse(text)

    @property
    def messages(self):
        return FakeClient._Messages(self)
