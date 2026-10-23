"""ForgeLine: triage -> spec -> human gate -> [implement <-> verify] -> review.

Hardening over the original demo:
- The human gate is enforced in code: ``require_gate_approval`` runs as a
  before_agent_callback on build_loop, implement, verify and review, so none of
  them run unless approve_spec recorded ``state["gate_result"]["approved"]``.
- implement is wrapped in a LoopAgent with a deterministic VerifyAgent that
  runs cds compile / build / serve smoke tests (factory/verify.py). Real
  compiler output is written to ``state["verify_result"]`` and fed back to
  implement on the next iteration. The loop exits as soon as verification
  passes, or after MAX_FIX_ITERATIONS.
- Instructions are InstructionProviders (skills_loader.instruction) so skill
  text with braces is passed verbatim instead of being stripped.
"""

from __future__ import annotations

import warnings
from typing import AsyncGenerator

from google.adk.agents import Agent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps import App, ResumabilityConfig
from google.adk.events import Event, EventActions
from google.adk.planners import BuiltInPlanner
from google.adk.tools import FunctionTool
from google.genai import types

from . import verify as verify_mod
from .skills_loader import instruction, skill
from .tools import (
    GATE_STATE_KEY,
    approve_spec,
    require_gate_approval,
    verify_cap_model,
    verify_fiori_mode_b,
    verify_project,
    write_file,
    write_gatepass_annotations_template,
    write_gatepass_manifest_template,
    write_cap_package_template,
    write_gatepass_schema_template,
    write_gatepass_service_template,
    write_gatepass_ui_shell_templates,
)

# LoopAgent / SequentialAgent are deprecated in favour of Workflow in ADK 2.x
# but still supported; Workflow cannot yet host LlmAgent sub-agents this way.
warnings.filterwarnings("ignore", message=r".*(Loop|Sequential)Agent is deprecated.*")

MODEL = "gemini-3.6-flash"
MAX_FIX_ITERATIONS = 3
VERIFY_STATE_KEY = "verify_result"
VERIFY_ATTEMPTS_KEY = "verify_attempts"

# Lean skill bundles — avoid stacking long FE docs into every agent.
CAP = skill("sap-cap", "sap-cap-sqlite", "sap-cap-service-path")
CAP_CORE = skill("sap-cap", "sap-cap-service-path")
FIORI_BOILER = skill("sap-fiori-boilerplate")
SPEC = skill("spec-pack")
GATE = skill("gate")
REVIEW = skill("review")

NO_THINK = BuiltInPlanner(
    thinking_config=types.ThinkingConfig(thinking_budget=0, include_thoughts=False)
)


def clear_gate_decision(callback_context) -> None:
    """Drop any decision from an earlier work item before a new gate runs."""
    if callback_context.state.get(GATE_STATE_KEY) is not None:
        callback_context.state[GATE_STATE_KEY] = None
    return None


def reset_verify_state(callback_context) -> None:
    """Fresh verify feedback for each build loop run."""
    callback_context.state[VERIFY_STATE_KEY] = None
    callback_context.state[VERIFY_ATTEMPTS_KEY] = 0
    return None


class VerifyAgent(BaseAgent):
    """Deterministic (no LLM) verifier step inside the build loop.

    Writes the verifier report to state and escalates (exits the loop) when the
    project verifies, or when the toolchain is missing (retrying cannot help).
    """

    build: bool = True
    smoke: bool = True

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        attempt = int(ctx.session.state.get(VERIFY_ATTEMPTS_KEY) or 0) + 1
        report = verify_mod.run_verification(
            verify_mod.ROOT, build=self.build, smoke=self.smoke
        )
        compact = {
            "ok": report["ok"],
            "toolchain_ok": report["toolchain_ok"],
            "attempt": attempt,
            "max_attempts": MAX_FIX_ITERATIONS,
            "summary": report["summary"],
            "hint": report["hint"],
        }
        if report["ok"]:
            text = f"verify: PASSED on attempt {attempt}.\n{report['summary']}"
        elif not report["toolchain_ok"]:
            text = (
                f"verify: cannot run, toolchain missing. {report['hint']}\n"
                f"{report['summary']}"
            )
        else:
            text = (
                f"verify: FAILED on attempt {attempt}/{MAX_FIX_ITERATIONS}. "
                f"Errors go back to implement.\n{report['summary']}"
            )
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            actions=EventActions(
                state_delta={VERIFY_STATE_KEY: compact, VERIFY_ATTEMPTS_KEY: attempt},
                escalate=bool(report["ok"] or not report["toolchain_ok"]),
            ),
        )


triage = Agent(
    name="triage",
    model=MODEL,
    description="Shapes a CAP change request. Does not design or code.",
    planner=NO_THINK,
    instruction=instruction(
        f"""
You are triage. CAP rules only. Do not write CDS.

{CAP_CORE}

Restate the problem. Objects only if user named them.
mode=greenfield|change, fiori=none|A|B. Size XS/S/M/L. Questions or none.
End WORK ITEM: id, problem, objects, size, mode, fiori, questions, next=ready-to-spec|needs-info.
"""
    ),
    output_key="work_item",
)

spec = Agent(
    name="spec",
    model=MODEL,
    planner=NO_THINK,
    description="Writes the CAP spec pack and stops.",
    instruction=instruction(
        f"""
You are spec. Read the work item:
{{work_item}}

{CAP_CORE}

{SPEC}

TECH paths: srv/gatepass-service.cds + srv/gatepass-service.js only (never gate-pass-service).
fiori none|A|B; if B AppId=gatepass. No app/ if no Fiori. No invented fields.
""",
        "work_item",
    ),
    output_key="spec_pack",
)

gate = Agent(
    name="gate",
    model=MODEL,
    planner=NO_THINK,
    description="Stops until a person approves the spec.",
    instruction=instruction(
        f"""
{GATE}
Call approve_spec once with work item id and 5-line summary of this spec pack:
{{spec_pack}}
""",
        "spec_pack",
    ),
    # approve_spec requests its own confirmation; no require_confirmation here.
    # It writes the decision to state["gate_result"] itself (no output_key, so
    # model text can never overwrite the recorded decision).
    tools=[FunctionTool(approve_spec)],
    before_agent_callback=clear_gate_decision,
)

implement = Agent(
    name="implement",
    model=MODEL,
    planner=NO_THINK,
    description="Writes CAP/FE files after approval; fixes verifier errors.",
    instruction=instruction(
        f"""
You are implement.

{CAP}

{FIORI_BOILER}

Gate decision: {{gate_result}}
Spec pack (only TECH scope):
{{spec_pack}}

## Verifier feedback (previous attempt)
{{verify_result}}

If verifier feedback is "(not set)", this is the first attempt: implement the spec.
Otherwise fix ONLY what the verifier reported (file:line:col messages are real
`cds compile` / `cds build` / smoke-test output) with write_file, then stop.
The verifier re-runs automatically after you; do not loop on verify tools.

## write_file paths
Relative to cap-app/ only. Never prefix cap-app/.
GOOD: db/schema.cds, srv/gatepass-service.js, app/gatepass/...
BAD: cap-app/..., gate-pass-service, gatepass-fiori, gatepass-list-report, webapp/annotations.cds

## CAP
One pair srv/gatepass-service.cds + .js. Handler entity GatePasses.
Prefer write_gatepass_service_template for service CDS when plant is mandatory.
NEVER write projection with inline field @mandatory inside braces — CDS parse error empties filter bar metadata.
package.json: prefer write_cap_package_template (cds ^10 + @cap-js/sqlite ^3 + better-sqlite3 ^13). NEVER @cap-js/sqlite ^1 with cds 10 (npm ERESOLVE). db :memory: unless file DB requested.

## Fiori Mode B — prefer templates (do not invent FE files)
1. write_gatepass_schema_template (namespace my.cap)
2. write_gatepass_service_template  (path gate-pass NO leading slash)
3. write_gatepass_annotations_template
4. write_gatepass_manifest_template  (uri /odata/v4/gate-pass/)
5. write_gatepass_ui_shell_templates
You may call verify_fiori_mode_b once to self-check before stopping.
Never leave gatepass-list-report. Mode A: annotations only. none: no app/.
""",
        "gate_result",
        "spec_pack",
        "verify_result",
    ),
    tools=[
        FunctionTool(write_file),
        FunctionTool(write_cap_package_template),
        FunctionTool(write_gatepass_schema_template),
        FunctionTool(write_gatepass_service_template),
        FunctionTool(write_gatepass_annotations_template),
        FunctionTool(write_gatepass_manifest_template),
        FunctionTool(write_gatepass_ui_shell_templates),
        FunctionTool(verify_cap_model),
        FunctionTool(verify_fiori_mode_b),
    ],
    output_key="change",
    before_agent_callback=require_gate_approval,
)

verifier = VerifyAgent(
    name="verify",
    description="Runs cds compile/build and a serve smoke test; no LLM.",
    before_agent_callback=require_gate_approval,
)

build_loop = LoopAgent(
    name="build_loop",
    description="implement -> verify, repeated until verification passes.",
    sub_agents=[implement, verifier],
    max_iterations=MAX_FIX_ITERATIONS,
    before_agent_callback=[require_gate_approval, reset_verify_state],
)

review = Agent(
    name="review",
    model=MODEL,
    planner=NO_THINK,
    description="Reviews change vs spec. Does not merge.",
    instruction=instruction(
        f"""
You are review.

{REVIEW}

{CAP_CORE}

{FIORI_BOILER}

Spec pack:
{{spec_pack}}

Implement's change note:
{{change}}

Verifier result (authoritative, from real cds compile/build/smoke runs):
{{verify_result}}

If the verifier result is not ok, end changes-requested and list its errors.
Call verify_fiori_mode_b when Fiori Mode B was in scope; fail if ok is false.
Fail incomplete Mode B, missing SelectionFields in model, bad projection @mandatory, dual handlers.
End ready-to-merge or changes-requested.
""",
        "spec_pack",
        "change",
        "verify_result",
    ),
    tools=[
        FunctionTool(verify_fiori_mode_b),
        FunctionTool(verify_cap_model),
        FunctionTool(verify_project),
    ],
    output_key="review_note",
    before_agent_callback=require_gate_approval,
)

root_agent = SequentialAgent(
    name="forgeling",
    description="CAP delivery factory: triage, spec, human gate, implement+verify loop, review.",
    sub_agents=[triage, spec, gate, build_loop, review],
)

# Resumable so the gate's confirmation pauses the whole sequence and an
# approval resumes at the gate (then build_loop, review) instead of
# restarting from triage. `adk web` prefers `app` over `root_agent`.
app = App(
    name="factory",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
