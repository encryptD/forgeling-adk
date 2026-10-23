import warnings

from google.adk.agents import Agent, SequentialAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.tools import FunctionTool
from google.adk.planners import BuiltInPlanner
from google.genai import types

from factory.agent import clear_gate_decision
from factory.skills_loader import instruction, skill
from factory.tools import (
    approve_spec,
    require_gate_approval,
    verify_cap_model,
    verify_fiori_mode_b,
    write_file,
    write_gatepass_annotations_template,
    write_gatepass_manifest_template,
    write_cap_package_template,
    write_gatepass_schema_template,
    write_gatepass_service_template,
    write_gatepass_ui_shell_templates,
)

warnings.filterwarnings("ignore", message=r".*SequentialAgent is deprecated.*")

MODEL = "gemini-3.6-flash"
CAP = skill("sap-cap", "sap-cap-sqlite", "sap-cap-service-path")
FIORI = skill("sap-fiori-boilerplate")  # short; no long FE docs
GATE = skill("gate")
REVIEW = skill("review")
NO_THINK = BuiltInPlanner(
    thinking_config=types.ThinkingConfig(thinking_budget=0, include_thoughts=False)
)

read_spec = Agent(
    name="spec_reader",
    model=MODEL,
    description="Reads the dropped product spec. Does not code.",
    planner=NO_THINK,
    instruction=instruction(f"""
The user dropped a spec for a new CAP app. There is no existing app.
Follow the CAP skill. Do not write code.

{CAP}

Restate scope, out of scope, entity, fields with types/lengths, service name, entity set,
exact handler file basename, validations, and whether Fiori is forbidden.
Five to fifteen lines. If Fiori is not requested, say fiori=none.
"""),
    output_key="mvp_brief",
)

gate = Agent(
    name="gate",
    model=MODEL,
    planner=NO_THINK,
    description="Pauses until a person approves the MVP brief.",
    instruction=instruction(f"""
{GATE}
Read the brief:
{{mvp_brief}}

If it is a greeting, small talk, or not a CAP spec, reply that you are waiting for a spec. Do not call approve_spec.
If it is a CAP spec or real brief, call approve_spec once. work_item_id is mvp-001. Summary is the brief above.
""", "mvp_brief"),
    # approve_spec owns its confirmation and writes state["gate_result"].
    tools=[FunctionTool(approve_spec)],
    before_agent_callback=clear_gate_decision,
)

build = Agent(
    name="builder",
    model=MODEL,
    planner=NO_THINK,
    description="Emits a new CAP app from the approved brief.",
    instruction=instruction(f"""
You are the builder. Follow the CAP skill. Fiori only if the brief explicitly requires it.

{CAP}

{FIORI}

Read {{gate_result}}. If approved is not true, reply: blocked, brief not approved. No files.
If approved, call write_file once per file with full content and real newlines. Do not only print files.

## write_file paths (critical)
The tool root IS already cap-app/. Pass paths RELATIVE to that folder only:
- GOOD: package.json , db/schema.cds , srv/gatepass-service.cds , srv/gatepass-service.js
- BAD:  cap-app/package.json , cap-app/db/schema.cds  (creates nested cap-app/cap-app/)
Never prefix paths with cap-app/.

## Default CAP-only MVP (when fiori=none)
Write exactly these paths (no cap-app/ prefix) unless the brief names different basenames:
- package.json
- db/schema.cds
- srv/gatepass-service.cds
- srv/gatepass-service.js

Rules:
- One handler only: srv/gatepass-service.js matching srv/gatepass-service.cds
- NEVER write srv/gate-pass-service.cds or srv/gate-pass-service.js (forbidden basename)
- Handler listens on 'GatePasses' (service entity set)
- Fields/types/lengths exactly as brief; no plant unless brief includes plant
- No app/ directory when fiori=none
- namespace stable; service using matches schema namespace
- package.json is CAP root with @sap/cds + @cap-js/sqlite + better-sqlite3; not a UI package
- package.json: write_cap_package_template or deps @sap/cds ^10, @cap-js/sqlite ^3 (not ^1), better-sqlite3 ^13\n- Default cds.requires.db to sqlite :memory: so tables auto-deploy on watch (see sap-cap-sqlite skill)

## If brief requires Fiori Mode B
AppId folder is app/gatepass/ only (never gatepass-fiori / gatepass-list-report).
Write the FULL Mode B file set from the Fiori skill in one go:
Prefer write_gatepass_annotations_template for annotations.cds;
then package.json, ui5.yaml, webapp/Component.js, index.html, manifest.json.
Then call verify_fiori_mode_b; if ok is false, fix and re-verify.

Then list the paths you wrote and verify result. Label it the MVP.
""", "gate_result"),
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
    output_key="mvp_app",
    before_agent_callback=require_gate_approval,
)

review = Agent(
    name="review",
    model=MODEL,
    description="Checks the MVP against the brief.",
    instruction=instruction(f"""
You are review.

{REVIEW}

{CAP}

{FIORI}

Read {{mvp_brief}} and {{mvp_app}}. If blocked, say review skipped.
Fail if app/ exists when fiori=none, dual handlers, basename mismatch, extra fields, corrupt file content,
or files landed under nested cap-app/cap-app/ instead of cap-app/ root.
""", "mvp_brief", "mvp_app"),
    tools=[FunctionTool(verify_cap_model), FunctionTool(verify_fiori_mode_b)],
    output_key="review_note",
    before_agent_callback=require_gate_approval,
)

root_agent = SequentialAgent(
    name="mvp",
    description="Build a new CAP app from a dropped spec, with a human gate.",
    sub_agents=[read_spec, gate, build, review],
)

app = App(
    name="mvp",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
