"""approve_spec confirmation semantics and the code-enforced gate callback."""

from types import SimpleNamespace

from google.adk.tools.tool_confirmation import ToolConfirmation

from factory.tools import (
    GATE_STATE_KEY,
    approve_spec,
    gate_approved,
    require_gate_approval,
)


class FakeToolContext:
    def __init__(self, confirmation=None, user_id="u-1"):
        self.tool_confirmation = confirmation
        self.user_id = user_id
        self.state = {}
        self.requested = None

    def request_confirmation(self, *, hint=None, payload=None):
        self.requested = {"hint": hint, "payload": payload}


def test_first_call_requests_confirmation_and_records_nothing():
    ctx = FakeToolContext()
    out = approve_spec("cr-001", "summary", ctx)
    assert out["status"] == "waiting"
    assert ctx.requested and "cr-001" in ctx.requested["hint"]
    assert GATE_STATE_KEY not in ctx.state


def test_approval_records_approver_timestamp_note():
    conf = ToolConfirmation(confirmed=True, payload={"note": "lgtm", "approver": "alice"})
    ctx = FakeToolContext(conf)
    out = approve_spec("cr-001", "summary", ctx)
    rec = ctx.state[GATE_STATE_KEY]
    assert out == rec
    assert rec["approved"] is True and rec["status"] == "approved"
    assert rec["approver"] == "alice" and rec["note"] == "lgtm"
    assert rec["decided_at"].endswith("+00:00")
    assert ctx.requested is None


def test_approver_defaults_to_user_id():
    ctx = FakeToolContext(ToolConfirmation(confirmed=True), user_id="encryptD")
    assert approve_spec("cr-1", "s", ctx)["approver"] == "encryptD"


def test_rejection_is_recorded_and_payload_cannot_override_it():
    # Old code treated payload.approved=True as approval even when the person
    # rejected; confirmed is now the single source of truth.
    conf = ToolConfirmation(confirmed=False, payload={"approved": True, "note": "no"})
    ctx = FakeToolContext(conf)
    rec = approve_spec("cr-001", "summary", ctx)
    assert rec["approved"] is False and rec["status"] == "rejected"
    assert ctx.state[GATE_STATE_KEY]["note"] == "no"


def test_non_dict_payload_is_tolerated():
    ctx = FakeToolContext(ToolConfirmation(confirmed=True, payload="yes"))
    assert approve_spec("cr-1", "s", ctx)["approved"] is True


def _cb(state):
    return SimpleNamespace(state=state, agent_name="implement")


def test_gate_callback_blocks_without_decision():
    out = require_gate_approval(_cb({}))
    assert out is not None and "blocked" in out.parts[0].text
    assert "implement skipped" in out.parts[0].text


def test_gate_callback_blocks_on_rejection():
    out = require_gate_approval(
        _cb({GATE_STATE_KEY: {"approved": False, "status": "rejected", "approver": "bob"}})
    )
    assert out is not None and "rejected by bob" in out.parts[0].text


def test_gate_callback_blocks_on_model_text():
    # A model writing "approved" text must not open the gate.
    assert require_gate_approval(_cb({GATE_STATE_KEY: "approved: true"})) is not None
    assert require_gate_approval(_cb({GATE_STATE_KEY: {"approved": "true"}})) is not None


def test_gate_callback_allows_explicit_approval():
    assert require_gate_approval(_cb({GATE_STATE_KEY: {"approved": True}})) is None
    assert gate_approved({GATE_STATE_KEY: {"approved": True}})
    assert not gate_approved(None)
