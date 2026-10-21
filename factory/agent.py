"""ForgeLine demo: triage -> spec -> human gate -> implement -> review."""

from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import FunctionTool
from google.adk.planners import BuiltInPlanner
from google.genai import types

from .skills_loader import skill
from .tools import (
    approve_spec,
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

MODEL = "gemini-3.6-flash"

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

triage = Agent(
    name="triage",
    model=MODEL,
    description="Shapes a CAP change request. Does not design or code.",
    planner=NO_THINK,
    instruction=f"""
You are triage. CAP rules only. Do not write CDS.

{CAP_CORE}

Restate the problem. Objects only if user named them.
mode=greenfield|change, fiori=none|A|B. Size XS/S/M/L. Questions or none.
End WORK ITEM: id, problem, objects, size, mode, fiori, questions, next=ready-to-spec|needs-info.
""",
    output_key="work_item",
)

spec = Agent(
    name="spec",
    model=MODEL,
    planner=NO_THINK,
    description="Writes the CAP spec pack and stops.",
    instruction=f"""
You are spec. Read {{work_item}}.

{CAP_CORE}

{SPEC}

TECH paths: srv/gatepass-service.cds + srv/gatepass-service.js only (never gate-pass-service).
fiori none|A|B; if B AppId=gatepass. No app/ if no Fiori. No invented fields.
""",
    output_key="spec_pack",
)

gate = Agent(
    name="gate",
    model=MODEL,
    planner=NO_THINK,
    description="Stops until a person approves the spec.",
    instruction=f"""
{GATE}
Call approve_spec once with work item id and 5-line summary of {{spec_pack}}.
""",
    tools=[FunctionTool(approve_spec, require_confirmation=True)],
    output_key="gate_result",
)

implement = Agent(
    name="implement",
    model=MODEL,
    planner=NO_THINK,
    description="Writes CAP/FE files after approval.",
    instruction=f"""
You are implement.

{CAP}

{FIORI_BOILER}

Read {{gate_result}}. If not approved: blocked. No write_file.
Read {{spec_pack}}. Only TECH scope.

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
Then verify_fiori_mode_b. If ok is false, fix and re-verify.
Never leave gatepass-list-report. Mode A: annotations only. none: no app/.
""",
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
)

review = Agent(
    name="review",
    model=MODEL,
    planner=NO_THINK,
    description="Reviews change vs spec. Does not merge.",
    instruction=f"""
You are review.

{REVIEW}

{CAP_CORE}

{FIORI_BOILER}

Read {{spec_pack}} and {{change}}. Skip if implement blocked.
Call verify_fiori_mode_b when Fiori Mode B was in scope; fail if ok is false.
Fail incomplete Mode B, missing SelectionFields in model, bad projection @mandatory, dual handlers.
End ready-to-merge or changes-requested.
""",
    tools=[FunctionTool(verify_fiori_mode_b), FunctionTool(verify_cap_model)],
    output_key="review_note",
)

root_agent = SequentialAgent(
    name="forgeling",
    description="CAP delivery factory: triage, spec, human gate, implement, review.",
    sub_agents=[triage, spec, gate, implement, review],
)
