#!/usr/bin/env python3
"""Run the factory agent to generate a Mode B Fiori elements app and validate it.

Auto-approves the human gate so the run is non-interactive.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factory.agent import root_agent  # noqa: E402

APP_NAME = "factory"
USER_ID = "verify-user"
PROMPT = """\
CR cr-fe-verify-001. Deliver a full Fiori elements UI (Mode B) for GatePass.

No blocking questions. Answers already decided:
- plant stays @mandatory on CDS AND handler rejects empty plant and empty vehicleNo
- Handler entity name is GatePasses (service projection), not GatePass
- Do not change field list beyond ensuring plant remains
- Fiori Mode B is required (full app under app/gatepass)
- Out of scope: XSUAA, destinations, FLP, ABAP, recreating CAP root

Existing CAP MVP under cap-app/ (edit in place):
- db/schema.cds entity GatePass (ID, number, vehicleNo, plant @mandatory, status)
- srv/gatepass-service.cds service GatePassService entity GatePasses
- srv/gatepass-service.js CREATE checks on GatePasses

FE requirements (sap-fiori-elements Mode B):
- app/gatepass with annotations.cds, package.json, ui5.yaml
- webapp/Component.js, index.html (CDN UI5 bootstrap), manifest.json (List+ObjectPage),
  i18n/i18n.properties
- OData URI /odata/v4/gate-pass/
- annotations: HeaderInfo Title bound to number, LineItem, FieldGroup, Facets

Write complete file contents via write_file. next=ready-to-spec immediately.
"""

CAP_APP = ROOT / "cap-app"
REQUIRED_MODE_B = [
    "app/gatepass/annotations.cds",
    "app/gatepass/package.json",
    "app/gatepass/ui5.yaml",
    "app/gatepass/webapp/Component.js",
    "app/gatepass/webapp/index.html",
    "app/gatepass/webapp/manifest.json",
]


def _text_of(event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(p.text or "" for p in event.content.parts)


def _pending_confirmation(events):
    for event in reversed(events):
        lr = getattr(event, "long_running_tool_ids", None) or []
        if not lr:
            continue
        for fc in event.get_function_calls() or []:
            if fc.id in lr and fc.name == "adk_request_confirmation":
                return event, fc
    return None, None


async def _run_once(runner: InMemoryRunner, session_id: str, message: types.Content, invocation_id=None):
    events = []
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
        invocation_id=invocation_id,
    ):
        events.append(event)
        author = getattr(event, "author", "?")
        text = _text_of(event)
        if text.strip():
            print(f"\n[{author}]\n{text[:2000]}")
        for fc in event.get_function_calls() or []:
            print(f"  -> call {fc.name}({json.dumps(fc.args or {}, ensure_ascii=False)[:300]})")
        for fr in event.get_function_responses() or []:
            print(f"  <- resp {fr.name}: {json.dumps(fr.response or {}, ensure_ascii=False)[:300]}")
        if getattr(event, "long_running_tool_ids", None):
            print(f"  [paused HITL] {event.long_running_tool_ids}")
    return events


def validate_generated_app() -> list[str]:
    errors = []
    for rel in REQUIRED_MODE_B:
        path = CAP_APP / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
            continue
        if path.stat().st_size < 20:
            errors.append(f"too small {rel}")

    manifest_path = CAP_APP / "app/gatepass/webapp/manifest.json"
    if manifest_path.is_file():
        try:
            m = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"manifest json: {e}")
            m = {}
        ds = (
            m.get("sap.app", {})
            .get("dataSources", {})
            .get("mainService", {})
            .get("uri", "")
        )
        if "gate-pass" not in ds:
            errors.append(f"odata uri unexpected: {ds!r}")
        routes = m.get("sap.ui5", {}).get("routing", {}).get("routes", [])
        targets = m.get("sap.ui5", {}).get("routing", {}).get("targets", {})
        if len(routes) < 2:
            errors.append("manifest needs List + Object routes")
        # navigation detail route must exist as a route name
        nav_routes = set()
        for t in targets.values():
            nav = (
                t.get("options", {})
                .get("settings", {})
                .get("navigation", {})
            )
            for ent in nav.values():
                detail = (ent or {}).get("detail", {}) or {}
                if "route" in detail:
                    nav_routes.add(detail["route"])
        route_names = {r.get("name") for r in routes}
        for nr in nav_routes:
            if nr not in route_names and nr not in targets:
                errors.append(f"dangling navigation route {nr}")
        has_object = any(
            (t.get("name") or "").endswith("ObjectPage")
            or "ObjectPage" in (t.get("name") or "")
            for t in targets.values()
        )
        if not has_object:
            errors.append("no ObjectPage target")

    index = CAP_APP / "app/gatepass/webapp/index.html"
    if index.is_file():
        html = index.read_text()
        if "sap-ui-core.js" not in html:
            errors.append("index.html missing sap-ui-core.js")
        if "resources/sap-ui-core.js" in html and "ui5.sap.com" not in html and "sapui5" not in html.lower():
            # relative bootstrap without CDN is fragile under cds watch
            errors.append("index.html uses relative UI5 bootstrap without CDN")
        if "sap/fe/core/AppComponent" not in html and "ComponentSupport" not in html:
            errors.append("index.html missing ComponentSupport bootstrap")

    ann = CAP_APP / "app/gatepass/annotations.cds"
    if ann.is_file():
        text = ann.read_text()
        for needle in (
            "UI.LineItem",
            "UI.HeaderInfo",
            "UI.Facets",
            "UI.FieldGroup",
            "UI.SelectionFields",
        ):
            if needle not in text:
                errors.append(f"annotations missing {needle}")
        if "$value" in text and "Title" in text:
            # common broken Title pattern
            if "Title" in text and "$value" in text:
                errors.append("annotations may use broken HeaderInfo Title $value pattern")

    bad_apps = [
        "app/gatepass-list-report",
        "app/gatepass-fiori",
        "app/gatepass-list",
    ]
    for bad in bad_apps:
        if (CAP_APP / bad).exists():
            errors.append(f"forbidden app folder: {bad}")

    handler = CAP_APP / "srv/gatepass-service.js"
    if handler.is_file():
        js = handler.read_text()
        if "'GatePasses'" not in js and '"GatePasses"' not in js:
            errors.append("handler not bound to GatePasses service entity")
        if "'GatePass'" in js and "'GatePasses'" not in js:
            errors.append("handler still bound only to DB entity GatePass")


    # Route must use real UI5 {key} token, not skill placeholders
    if manifest_path.is_file():
        raw = manifest_path.read_text()
        if 'KEY_TOKEN' in raw or '(<key>)' in raw:
            errors.append('manifest still has skill placeholder instead of UI5 {key} route token')
        import re
        if not re.search(r'\(\{key\}\)', raw):
            # allow only if no object page - but we require object page
            if 'ObjectPage' in raw:
                errors.append('ObjectPage route missing UI5 ({key}) pattern')

    # CDS namespace consistency
    schema = CAP_APP / 'db/schema.cds'
    service = CAP_APP / 'srv/gatepass-service.cds'
    if schema.is_file() and service.is_file():
        import re
        ns = re.search(r'namespace\s+([\w.]+)', schema.read_text())
        using = re.search(r'using\s*\{\s*([\w.]+)\s+as', service.read_text())
        if ns and using and ns.group(1) != using.group(1):
            errors.append(f'namespace mismatch schema={ns.group(1)} service using={using.group(1)}')

    return errors


async def main() -> int:
    print("== factory skill verification ==")
    print(f"cwd skill FIORI loaded via root_agent={root_agent.name}")
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    print(f"session={session.id}")

    msg = types.Content(role="user", parts=[types.Part(text=PROMPT)])
    events = await _run_once(runner, session.id, msg)

    # Auto-approve gate if paused
    for round_i in range(3):
        session = await runner.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session.id
        )
        all_events = list(session.events)
        event, fc = _pending_confirmation(all_events)
        if not fc:
            break
        print(f"\n== auto-approving gate (round {round_i+1}) fc_id={fc.id} ==")
        approve = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=fc.id,
                        name="adk_request_confirmation",
                        response={"confirmed": True, "payload": {"approved": True, "note": "verify skill"}},
                    )
                )
            ],
        )
        events = await _run_once(
            runner,
            session.id,
            approve,
            invocation_id=getattr(event, "invocation_id", None),
        )

    print("\n== filesystem validation ==")
    errors = validate_generated_app()
    present = [rel for rel in REQUIRED_MODE_B if (CAP_APP / rel).is_file()]
    print("present:", *present, sep="\n  ")
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        return 1
    print("PASS: Mode B Fiori elements app satisfies sap-fiori-elements checklist")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
