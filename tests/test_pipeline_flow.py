"""End-to-end orchestration with a scripted fake LLM (no network, no node).

Exercises the real ADK runner: gate pause -> approve/reject resume ->
build_loop (implement <-> verify) -> review, with verification stubbed.
"""

import asyncio
from typing import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from factory import agent as fa
from factory import verify as verify_mod


class ScriptedLlm(BaseLlm):
    """Replies with a function call first (if scripted), then plain text."""

    call: tuple[str, dict] | None = None
    reply: str = "ok"
    calls: int = 0

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        last = llm_request.contents[-1] if llm_request.contents else None
        answered = bool(last and any(p.function_response for p in last.parts or []))
        if self.call and not answered:
            name, args = self.call
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            part = types.Part(text=self.reply)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.fixture
def pipeline(monkeypatch):
    models = {
        "triage": ScriptedLlm(model="fake", reply="WORK ITEM cr-001 next=ready-to-spec"),
        "spec": ScriptedLlm(model="fake", reply="PRODUCT/TECH/TEST pack"),
        "gate": ScriptedLlm(
            model="fake", call=("approve_spec", {"work_item_id": "cr-001", "spec_summary": "s"}),
            reply="gate done",
        ),
        "implement": ScriptedLlm(model="fake", reply="wrote files"),
        "review": ScriptedLlm(model="fake", reply="ready-to-merge"),
    }
    for name, model in models.items():
        monkeypatch.setattr(getattr(fa, name), "model", model)

    results = []

    def fake_verify(root, build=True, smoke=True):
        r = results.pop(0)
        return {"ok": r, "toolchain_ok": True, "steps": [],
                "summary": "[PASSED]" if r else "[FAILED] compile\n  - ERROR srv/x.cds:1:1: boom",
                "hint": None if r else "fix"}

    monkeypatch.setattr(verify_mod, "run_verification", fake_verify)
    runner = Runner(app=fa.app, session_service=InMemorySessionService())
    return runner, models, results


def _confirmation_call(events):
    for ev in events:
        for fc in ev.get_function_calls() or []:
            if fc.name == "adk_request_confirmation":
                return ev, fc
    return None, None


async def _drive(runner, decision):
    session = await runner.session_service.create_session(app_name="factory", user_id="u")
    events = []
    msg = types.Content(role="user", parts=[types.Part(text="CR cr-001 add plant")])
    async for ev in runner.run_async(user_id="u", session_id=session.id, new_message=msg):
        events.append(ev)
    ev, fc = _confirmation_call(events)
    assert fc is not None, "gate did not pause for confirmation"
    paused_authors = [e.author for e in events]
    resume = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
        id=fc.id, name="adk_request_confirmation", response=decision))])
    async for e in runner.run_async(user_id="u", session_id=session.id, new_message=resume,
                                    invocation_id=ev.invocation_id):
        events.append(e)
    session = await runner.session_service.get_session(
        app_name="factory", user_id="u", session_id=session.id)
    return paused_authors, events, session.state


def test_gate_pauses_then_approval_runs_fix_loop(pipeline):
    runner, models, results = pipeline
    results[:] = [False, True]  # first verify fails, second passes
    paused, events, state = asyncio.run(_drive(
        runner, {"confirmed": True, "payload": {"note": "go", "approver": "alice"}}))
    assert "implement" not in paused and "verify" not in paused
    assert state["gate_result"]["approved"] is True
    assert state["gate_result"]["approver"] == "alice"
    assert models["triage"].calls == 1, "resume must not restart from triage"
    assert models["implement"].calls == 2, "implement should run again to fix"
    assert state["verify_result"]["ok"] is True and state["verify_attempts"] == 2
    assert models["review"].calls == 1
    assert results == []


def test_loop_stops_at_max_iterations(pipeline):
    runner, models, results = pipeline
    results[:] = [False] * fa.MAX_FIX_ITERATIONS
    _, _, state = asyncio.run(_drive(runner, {"confirmed": True}))
    assert models["implement"].calls == fa.MAX_FIX_ITERATIONS
    assert state["verify_result"]["ok"] is False
    assert state["verify_attempts"] == fa.MAX_FIX_ITERATIONS


def test_rejection_skips_implement_verify_and_review(pipeline):
    runner, models, results = pipeline
    _, events, state = asyncio.run(_drive(runner, {"confirmed": False, "payload": {"note": "no"}}))
    assert state["gate_result"]["approved"] is False
    assert models["implement"].calls == 0
    assert models["review"].calls == 0
    texts = " ".join(p.text for e in events if e.content for p in e.content.parts or [] if p.text)
    assert "blocked: gate rejected" in texts
