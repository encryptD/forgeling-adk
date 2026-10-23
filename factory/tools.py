"""Human gate, gate callback, and write/verify tools for the factory."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from google.adk.tools import ToolContext
from google.genai import types

from . import verify as _verify

ROOT = Path(__file__).resolve().parent.parent / "cap-app"

ANNOTATIONS_TEMPLATE = """using GatePassService as service from '../../srv/gatepass-service';

annotate service.GatePasses with @(
  UI.SelectionFields: [
    number,
    vehicleNo,
    plant,
    status
  ],
  UI.LineItem: [
    { $Type: 'UI.DataField', Value: number },
    { $Type: 'UI.DataField', Value: vehicleNo },
    { $Type: 'UI.DataField', Value: plant },
    { $Type: 'UI.DataField', Value: status }
  ],
  UI.HeaderInfo: {
    TypeName: 'Gate Pass',
    TypeNamePlural: 'Gate Passes',
    Title: { $Type: 'UI.DataField', Value: number }
  },
  UI.FieldGroup #GeneratedGroup: {
    $Type: 'UI.FieldGroupType',
    Data: [
      { $Type: 'UI.DataField', Value: number },
      { $Type: 'UI.DataField', Value: vehicleNo },
      { $Type: 'UI.DataField', Value: plant },
      { $Type: 'UI.DataField', Value: status }
    ]
  },
  UI.Facets: [
    {
      $Type: 'UI.ReferenceFacet',
      ID: 'GeneratedFacet1',
      Label: 'General',
      Target: '@UI.FieldGroup#GeneratedGroup'
    }
  ]
);
"""

SCHEMA_TEMPLATE = """namespace my.cap;

entity GatePass {
  key ID        : UUID;
      number    : String(20);
      vehicleNo : String(20);
      plant     : String(20);
      status    : String(20);
}
"""


CAP_PACKAGE_TEMPLATE = """{
  "name": "cap-app",
  "version": "1.0.0",
  "private": true,
  "description": "GatePass CAP application",
  "dependencies": {
    "@sap/cds": "^10",
    "@cap-js/sqlite": "^3",
    "better-sqlite3": "^13",
    "express": "^4"
  },
  "devDependencies": {
    "@sap/cds-dk": "^10"
  },
  "scripts": {
    "start": "cds-serve",
    "watch": "cds watch"
  },
  "cds": {
    "requires": {
      "db": {
        "kind": "sqlite",
        "credentials": { "url": ":memory:" }
      }
    }
  }
}
"""

# Default when schema missing; prefer build_service_cds() which matches disk schema.
SERVICE_CDS_TEMPLATE = """using my.cap as db from '../db/schema';

service GatePassService @(path: 'gate-pass') {
  entity GatePasses as projection on db.GatePass;
}

annotate GatePassService.GatePasses with {
  plant @mandatory;
};
"""

MANIFEST_TEMPLATE = r"""{
  "_version": "1.12.0",
  "sap.app": {
    "id": "gatepass",
    "type": "application",
    "title": "Gate Passes",
    "description": "GatePass List Report",
    "applicationVersion": { "version": "1.0.0" },
    "dataSources": {
      "mainService": {
        "uri": "/odata/v4/gate-pass/",
        "type": "OData",
        "settings": { "odataVersion": "4.0" }
      }
    }
  },
  "sap.ui": {
    "technology": "UI5",
    "deviceTypes": { "desktop": true, "tablet": true, "phone": true }
  },
  "sap.ui5": {
    "flexEnabled": false,
    "dependencies": {
      "minUI5Version": "1.145.0",
      "libs": {
        "sap.m": {},
        "sap.ui.core": {},
        "sap.f": {},
        "sap.fe.templates": {}
      }
    },
    "models": {
      "": {
        "dataSource": "mainService",
        "settings": {
          "synchronizationMode": "None",
          "operationMode": "Server",
          "autoExpandSelect": true,
          "earlyRequests": true,
          "groupId": "$direct"
        }
      }
    },
    "routing": {
      "routes": [
        {
          "pattern": ":?query:",
          "name": "GatePassesList",
          "target": "GatePassesList"
        },
        {
          "pattern": "GatePasses(KEY_TOKEN):?query:",
          "name": "GatePassesObjectPage",
          "target": "GatePassesObjectPage"
        }
      ],
      "targets": {
        "GatePassesList": {
          "type": "Component",
          "id": "GatePassesList",
          "name": "sap.fe.templates.ListReport",
          "options": {
            "settings": {
              "entitySet": "GatePasses",
              "contextPath": "/GatePasses",
              "variantManagement": "Page",
              "initialLoad": true,
              "navigation": {
                "GatePasses": {
                  "detail": { "route": "GatePassesObjectPage" }
                }
              }
            }
          }
        },
        "GatePassesObjectPage": {
          "type": "Component",
          "id": "GatePassesObjectPage",
          "name": "sap.fe.templates.ObjectPage",
          "options": {
            "settings": {
              "entitySet": "GatePasses",
              "contextPath": "/GatePasses"
            }
          }
        }
      }
    }
  }
}
"""

APP_PACKAGE_TEMPLATE = """{
  "name": "gatepass",
  "version": "1.0.0",
  "description": "GatePass Fiori elements UI",
  "private": true,
  "scripts": {
    "start": "ui5 serve --port 8080"
  },
  "devDependencies": {
    "@ui5/cli": "^4",
    "@sap/ux-ui5-tooling": "^1"
  }
}
"""

UI5_YAML_TEMPLATE = """specVersion: "3.0"
metadata:
  name: gatepass
type: application
framework:
  name: SAPUI5
  version: "1.145.0"
server:
  customMiddleware:
    - name: fiori-tools-proxy
      afterMiddleware: compression
      configuration:
        backend:
          - path: /odata
            url: http://localhost:4004
"""

COMPONENT_JS_TEMPLATE = """sap.ui.define(["sap/fe/core/AppComponent"], function (AppComponent) {
  "use strict";
  return AppComponent.extend("gatepass.Component", {
    metadata: { manifest: "json" }
  });
});
"""

INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" style="height:100%">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Gate Passes</title>
  <script
    id="sap-ui-bootstrap"
    src="https://ui5.sap.com/1.145.0/resources/sap-ui-core.js"
    data-sap-ui-theme="sap_horizon"
    data-sap-ui-libs="sap.m,sap.ui.core,sap.f,sap.fe.templates"
    data-sap-ui-resourceroots='{"gatepass":"./"}'
    data-sap-ui-async="true"
    data-sap-ui-compatVersion="edge"
    data-sap-ui-frameOptions="allow"
    data-sap-ui-xx-componentPreload="off"
    data-sap-ui-xx-waitForTheme="true"
  ></script>
  <style>
    html, body { height:100%; width:100%; margin:0; padding:0; }
    #content, .sapUiComponentContainer, .sapMApp, .sapMPage,
    .sapFDynamicPage, .sapFDynamicPageContent, .sapFDynamicPageContentFitContainer {
      height:100%; width:100%;
    }
    #bootMsg { font: 14px/1.4 system-ui,sans-serif; padding: 16px; color:#333; }
  </style>
  <script>
    (function () {
      function show(msg) {
        var el = document.getElementById("bootMsg");
        if (el) el.textContent = msg;
      }
      function start() {
        if (!window.sap || !sap.ui || !sap.ui.require) {
          show("UI5 core failed to load from ui5.sap.com — check network/CDN.");
          return;
        }
        sap.ui.require([
          "sap/ui/core/ComponentContainer",
          "sap/ui/core/Core"
        ], function (ComponentContainer, Core) {
          Core.ready().then(function () {
            var body = document.getElementById("content");
            if (!body) return;
            body.innerHTML = "";
            new ComponentContainer({
              id: "container",
              name: "gatepass",
              height: "100%",
              width: "100%",
              async: true,
              manifest: true,
              handleValidation: true
            }).placeAt("content");
          });
        });
      }
      setTimeout(start, 0);
      setTimeout(function () {
        if (!window.sap) show("Still waiting for UI5 CDN (ui5.sap.com/1.145.0)…");
      }, 12000);
    })();
  </script>
</head>
<body class="sapUiBody sapUiSizeCompact" id="content" style="height:100%;width:100%">
  <div id="bootMsg">Loading Gate Passes…</div>
</body>
</html>
"""

MODE_B_FILES = (
    "app/gatepass/annotations.cds",
    "app/gatepass/package.json",
    "app/gatepass/ui5.yaml",
    "app/gatepass/webapp/Component.js",
    "app/gatepass/webapp/index.html",
    "app/gatepass/webapp/manifest.json",
)


GATE_STATE_KEY = "gate_result"


def approve_spec(work_item_id: str, spec_summary: str, tool_context: ToolContext) -> dict:
    """Pause until a person approves or rejects the spec pack.

    This tool owns its confirmation (do NOT also wrap it in
    ``FunctionTool(require_confirmation=True)``, which would short-circuit
    rejections before this body runs). First call: request confirmation and
    return ``waiting``. Second call (ADK re-invokes with the person's
    ToolConfirmation): record the decision in ``state["gate_result"]``.

    ``ToolConfirmation.confirmed`` is the single source of truth; the payload
    only carries an optional ``note`` and ``approver``.
    """
    confirmation = tool_context.tool_confirmation
    if not confirmation:
        tool_context.request_confirmation(
            hint=(
                f"Spec ready for {work_item_id}. Approve to allow implement. "
                "Reject to stop. You are the gate; the agents are not. "
                "Optional payload: note, approver."
            ),
            payload={"note": "", "approver": ""},
        )
        return {"status": "waiting", "work_item_id": work_item_id}

    payload = confirmation.payload if isinstance(confirmation.payload, dict) else {}
    approved = bool(confirmation.confirmed)
    decision = {
        "status": "approved" if approved else "rejected",
        "approved": approved,
        "work_item_id": work_item_id,
        "approver": str(payload.get("approver") or tool_context.user_id or "unknown"),
        "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": str(payload.get("note") or ""),
        "spec_summary": spec_summary,
    }
    tool_context.state[GATE_STATE_KEY] = decision
    return decision


def gate_approved(state) -> bool:
    """True only when approve_spec recorded an explicit human approval."""
    decision = state.get(GATE_STATE_KEY) if state is not None else None
    return isinstance(decision, dict) and decision.get("approved") is True


def require_gate_approval(callback_context) -> types.Content | None:
    """before_agent_callback: skip this agent unless the human gate approved.

    Returning Content makes ADK skip the agent's run entirely, so implement,
    verify and review cannot write or judge anything without approval, no
    matter what the model decides.
    """
    if gate_approved(callback_context.state):
        return None
    decision = callback_context.state.get(GATE_STATE_KEY)
    why = (
        f"gate {decision.get('status')} by {decision.get('approver')}"
        if isinstance(decision, dict)
        else "no gate decision recorded"
    )
    return types.Content(
        role="model",
        parts=[types.Part(text=f"blocked: {why}. {callback_context.agent_name} skipped.")],
    )


def _normalize_rel_path(path: str) -> str:
    p = path.strip().replace("\\", "/").lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    lowered = p.lower()
    while lowered.startswith("cap-app/"):
        p = p[len("cap-app/") :]
        lowered = p.lower()
    if p in ("", ".", "cap-app") or lowered == "cap-app":
        raise ValueError("path must be a file under cap-app/, e.g. db/schema.cds")
    if ".." in Path(p).parts:
        raise ValueError("path must not contain ..")

    p = p.replace("gate-pass-service", "gatepass-service")
    for alt in (
        "app/gatepass-fiori/",
        "app/gatepass-list-report/",
        "app/gatepass-list/",
    ):
        if p.startswith(alt):
            p = "app/gatepass/" + p[len(alt) :]
            break
    if p.endswith("/webapp/annotations.cds"):
        p = p.replace("/webapp/annotations.cds", "/annotations.cds")
    return p


def _sanitize_content(rel: str, content: str) -> str:
    name = Path(rel).name
    rel_norm = rel.replace("\\", "/")
    if name == "manifest.json" and "webapp/manifest.json" in rel_norm:
        content = content.replace("KEY_TOKEN", "{key}")
        content = content.replace("(<key>)", "({key})")
        content = re.sub(r',?\s*"resources"\s*:\s*"resources\.json"', "", content)
        # Prefer standard CAP OData v4 mount (not bare /gate-pass/)
        if '"uri": "/gate-pass/"' in content:
            content = content.replace('"uri": "/gate-pass/"', '"uri": "/odata/v4/gate-pass/"')
        if '"uri":"/gate-pass/"' in content:
            content = content.replace('"uri":"/gate-pass/"', '"uri":"/odata/v4/gate-pass/"')
    if rel_norm.endswith("gatepass-service.cds") or (
        name.endswith(".cds") and "service" in name.lower()
    ):
        # Absolute path '/gate-pass' bypasses /odata/v4 → FE blank page
        content = content.replace("path: '/gate-pass'", "path: 'gate-pass'")
        content = content.replace('path: "/gate-pass"', "path: 'gate-pass'")
        content = content.replace("path : '/gate-pass'", "path: 'gate-pass'")
        content = content.replace('path : "/gate-pass"', "path: 'gate-pass'")
    return content


def _validate_cds_service(content: str) -> str | None:
    if re.search(
        r"projection\s+on\s+[^\n{]+\{[^}]*@mandatory\s*;",
        content,
        re.I | re.S,
    ):
        return (
            "invalid CDS: do not put field @mandatory inside projection element list; "
            "use plain `as projection on db.GatePass;` then "
            "`annotate GatePassService.GatePasses with { plant @mandatory; }` "
            "or @mandatory on db/schema.cds. "
            "Broken service CDS prevents UI.SelectionFields from reaching $metadata "
            "(empty filter bar)."
        )
    # After sanitize this should be gone; keep as safety net message
    if "'/gate-pass'" in content or '"/gate-pass"' in content:
        if "path" in content:
            return (
                "service path must be relative gate-pass not '/gate-pass' "
                "(leading slash mounts outside /odata/v4 → blank FE)"
            )
    return None


def _validate_fe_content(rel: str, content: str) -> str | None:
    name = Path(rel).name
    rel_norm = rel.replace("\\", "/")

    if not content or not str(content).strip():
        return f"{rel} content is empty"

    if name.endswith(".cds") or rel_norm.endswith(".cds"):
        cds_err = _validate_cds_service(content)
        if cds_err:
            return cds_err

    if name == "index.html" or rel_norm.endswith("/webapp/index.html"):
        if "data-sap-ui-resourceroots" not in content and "sap-ui-resourceroots" not in content:
            return "index.html missing data-sap-ui-resourceroots"
        if '"gatepass"' not in content and "'gatepass'" not in content:
            return "index.html resourceroots must use key gatepass"
        if "./" not in content:
            return "index.html resourceroots must map gatepass to ./"
        if "gatepass-list-report" in content:
            return "index.html must use component id gatepass"
        if "1.136.0" in content:
            return "index.html uses CDN 1.136.0 which 404s; use 1.145.0"
        if "componentPreload" not in content:
            return "index.html missing data-sap-ui-xx-componentPreload=off"
        if "1.145.0" not in content and "1.145" not in content:
            return "index.html must pin UI5 1.145.0 (1.136.x blanked standalone FE)"
        if "ComponentContainer" not in content and "ComponentSupport" not in content:
            return "index.html missing ComponentContainer (or ComponentSupport) bootstrap"
        if "height" not in content:
            return "index.html missing height CSS"

    if name == "manifest.json" and "webapp/manifest.json" in rel_norm:
        if "{{appTitle}}" in content or "{{appDescription}}" in content:
            return "manifest i18n placeholders without i18n files"
        if "i18n/i18n.properties" in content:
            i18n = ROOT / Path(rel).parent / "i18n" / "i18n.properties"
            if not i18n.exists():
                return "manifest references missing i18n/i18n.properties"
        if "localService/metadata.xml" in content:
            return "manifest must not reference localService/metadata.xml"
        if re.search(r'"resources"\s*:\s*"resources\.json"', content):
            return "manifest must not reference resources.json"
        if "/odata/v4/gate-pass" not in content:
            return "manifest dataSource uri must be /odata/v4/gate-pass/ (not bare /gate-pass/)"
        if "ObjectPage" not in content:
            return "manifest missing ObjectPage target"
        if "ListReport" not in content:
            return "manifest missing ListReport target"
        if "contextPath" not in content:
            return "manifest missing contextPath /GatePasses"
        if "{key}" not in content:
            return "manifest ObjectPage route needs UI5 {key} (or KEY_TOKEN)"
        if '"":' not in content and '"" :' not in content:
            return 'manifest models must include default model key ""'

    if name == "annotations.cds" or rel_norm.endswith("/annotations.cds"):
        if len(content.strip()) < 80:
            return "annotations.cds too short — call write_gatepass_annotations_template"
        if "gate-pass-service" in content:
            return "annotations must import gatepass-service not gate-pass-service"
        if "gatepass-service" not in content:
            return "annotations must using ... from '../../srv/gatepass-service'"
        for needle, msg in (
            ("Facets", "annotations missing UI.Facets"),
            ("FieldGroup", "annotations missing UI.FieldGroup"),
            ("LineItem", "annotations missing UI.LineItem"),
            ("SelectionFields", "annotations missing UI.SelectionFields"),
            ("ReferenceFacet", "annotations missing UI.ReferenceFacet"),
        ):
            if needle not in content:
                return msg
        bad = (
            "{$value",
            "{$Value",
            "Type: #Collection",
            "Type : #Collection",
            "Type:#Collection",
            "Type :#Collection",
        )
        if any(b in content for b in bad):
            return "annotations invalid Facets/Title syntax"
        if "$Type" not in content and "UI.DataField" not in content:
            return "annotations need $Type UI.DataField"

    if name.endswith((".yaml", ".yml")):
        if content.count("\\n") >= 3 and content.count("\n") <= 1:
            return "yaml looks escaped; use real newlines"

    if name == "package.json" and rel_norm.startswith("app/"):
        if '"@sap/cds"' in content and '"@ui5/cli"' not in content:
            return "app/package.json must be UI-only, not CAP root"
        try:
            json.loads(content)
        except Exception as e:
            return f"app/package.json invalid JSON: {e}"

    if name == "package.json" and rel_norm in ("package.json", "./package.json"):
        try:
            pkg = json.loads(content)
        except Exception as e:
            return f"CAP package.json invalid JSON: {e}"
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        cds_v = str(deps.get("@sap/cds", ""))
        sqlite_v = str(deps.get("@cap-js/sqlite", ""))
        better = str(deps.get("better-sqlite3", ""))
        if cds_v and ("^10" in cds_v or cds_v.startswith("10") or ">=10" in cds_v):
            # @cap-js/sqlite v1 peers cds <9 only — npm ERESOLVE with cds 10
            if not sqlite_v:
                return "CAP package.json missing @cap-js/sqlite (need ^3 for cds 10)"
            if re.search(r"(^|[\^~>=]*)1(\.|$)", sqlite_v) and "3" not in sqlite_v.split(".")[0].lstrip("^~>=<"):
                # crude: reject major 1
                major = re.search(r"(\d+)", sqlite_v)
                if major and int(major.group(1)) < 3:
                    return (
                        "CAP package.json: @cap-js/sqlite must be ^3 for @sap/cds ^10 "
                        "(^1 peers cds <9 → npm ERESOLVE). Call write_cap_package_template."
                    )
            if better:
                major = re.search(r"(\d+)", better)
                if major and int(major.group(1)) < 11:
                    return (
                        "CAP package.json: better-sqlite3 should be ^13 for CAP 10 "
                        "(call write_cap_package_template)"
                    )
        if '"sqlite3"' in content and '"@cap-js/sqlite"' in content:
            return "do not use legacy sqlite3 package with @cap-js/sqlite"

    return None


def write_file(path: str, content: str) -> dict:
    """Write one file under the project cap-app directory."""
    try:
        rel = _normalize_rel_path(path)
    except ValueError as e:
        return {"ok": False, "error": str(e), "path_in": path}

    target = (ROOT / rel).resolve()
    root = ROOT.resolve()
    if not str(target).startswith(str(root)):
        return {"ok": False, "error": "path outside cap-app", "path_in": path}

    if content is None:
        return {"ok": False, "error": "content is null", "path_in": path}

    content = _sanitize_content(rel, str(content))

    if (
        content.count("\\n") >= 3
        and content.count("\n") <= 1
        and rel.endswith((".yaml", ".yml", ".cds", ".js", ".json", ".html", ".properties"))
    ):
        return {
            "ok": False,
            "error": "content looks escaped (literal backslash-n); pass real newlines",
            "path_in": path,
        }

    fe_err = _validate_fe_content(rel, content)
    if fe_err:
        return {"ok": False, "error": fe_err, "path_in": path, "rel": rel}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {
        "ok": True,
        "path": str(target),
        "rel": rel,
        "path_in": path,
        "stripped_prefix": path.strip().replace("\\", "/").lstrip("/") != rel,
    }


def write_gatepass_annotations_template() -> dict:
    """Write known-good app/gatepass/annotations.cds (SelectionFields + Facets)."""
    return write_file("app/gatepass/annotations.cds", ANNOTATIONS_TEMPLATE)



def _read_schema_namespace_entity() -> tuple[str | None, str]:
    """Return (namespace or None, entity name) from db/schema.cds."""
    schema = ROOT / "db" / "schema.cds"
    if not schema.is_file():
        return "my.cap", "GatePass"
    body = schema.read_text()
    ns_m = re.search(r"^\s*namespace\s+([\w.]+)\s*;", body, re.M)
    ent_m = re.search(r"\bentity\s+(\w+)\b", body)
    ns = ns_m.group(1) if ns_m else None
    ent = ent_m.group(1) if ent_m else "GatePass"
    return ns, ent


def build_service_cds() -> str:
    """Service CDS aligned to current db/schema.cds namespace (or bare entity)."""
    ns, ent = _read_schema_namespace_entity()
    if ns:
        return (
            f"using {ns} as db from '../db/schema';\n\n"
            f"service GatePassService @(path: 'gate-pass') {{\n"
            f"  entity GatePasses as projection on db.{ent};\n"
            f"}}\n\n"
            f"annotate GatePassService.GatePasses with {{\n"
            f"  plant @mandatory;\n"
            f"}};\n"
        )
    # No namespace: entity must be imported by name
    return (
        f"using {{ {ent} }} from '../db/schema';\n\n"
        f"service GatePassService @(path: 'gate-pass') {{\n"
        f"  entity GatePasses as projection on {ent};\n"
        f"}}\n\n"
        f"annotate GatePassService.GatePasses with {{\n"
        f"  plant @mandatory;\n"
        f"}};\n"
    )


def write_gatepass_service_template() -> dict:
    """Write valid srv/gatepass-service.cds aligned to db/schema.cds namespace."""
    return write_file("srv/gatepass-service.cds", build_service_cds())


def write_gatepass_schema_template() -> dict:
    """Write db/schema.cds with stable namespace my.cap (matches default service using)."""
    return write_file("db/schema.cds", SCHEMA_TEMPLATE)


def write_cap_package_template() -> dict:
    """Write CAP root package.json with cds10-compatible sqlite peers."""
    return write_file("package.json", CAP_PACKAGE_TEMPLATE)


def write_gatepass_manifest_template() -> dict:
    """Write known-good app/gatepass/webapp/manifest.json."""
    return write_file("app/gatepass/webapp/manifest.json", MANIFEST_TEMPLATE)


def write_gatepass_ui_shell_templates() -> dict:
    """Write package.json, ui5.yaml, Component.js, index.html for app/gatepass."""
    results = {
        "package": write_file("app/gatepass/package.json", APP_PACKAGE_TEMPLATE),
        "ui5": write_file("app/gatepass/ui5.yaml", UI5_YAML_TEMPLATE),
        "component": write_file("app/gatepass/webapp/Component.js", COMPONENT_JS_TEMPLATE),
        "index": write_file("app/gatepass/webapp/index.html", INDEX_HTML_TEMPLATE),
    }
    return {"ok": all(r.get("ok") for r in results.values()), "results": results}


def verify_cap_model() -> dict:
    """Run cds compile * --to edmx and report parsed compiler errors.

    When an app/**/annotations.cds exists, the compiled EDMX must also contain
    UI.SelectionFields and UI.LineItem.
    """
    errors: list[str] = []
    svc = ROOT / "srv" / "gatepass-service.cds"
    if svc.is_file():
        bad = _validate_cds_service(svc.read_text())
        if bad:
            errors.append(f"srv/gatepass-service.cds: {bad}")

    step = _verify.check_compile(ROOT)
    if step["status"] == _verify.SKIPPED:
        return {
            "ok": False,
            "errors": errors + [step["reason"]],
            "hint": _verify.NPM_HINT,
        }
    errors.extend(step["errors"])
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": step["warnings"],
        "hint": None
        if not errors
        else "fix the files named in errors (file:line:col), then re-verify",
    }


def verify_project() -> dict:
    """Run the full verifier: static checks, cds compile, cds build, serve smoke test.

    Returns ok, toolchain_ok, per-step errors and a short summary.
    """
    return _verify.run_verification(ROOT)


def verify_fiori_mode_b() -> dict:
    """Check Mode B files on disk and that CAP model exposes SelectionFields."""
    errors: list[str] = []
    present: list[str] = []

    for bad in ("app/gatepass-list-report", "app/gatepass-fiori", "app/gatepass-list"):
        if (ROOT / bad).exists():
            errors.append(f"forbidden app folder present: {bad}")

    for rel in MODE_B_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
            continue
        present.append(rel)
        text = path.read_text()
        if len(text.strip()) < 20:
            errors.append(f"too small {rel}")
            continue
        fe_err = _validate_fe_content(rel, text)
        if fe_err:
            errors.append(f"{rel}: {fe_err}")

    model = verify_cap_model()
    if not model.get("ok"):
        errors.extend(f"model: {e}" for e in model.get("errors") or [])

    return {
        "ok": not errors,
        "present": present,
        "errors": errors,
        "required": list(MODE_B_FILES),
        "model": model,
        "hint": (
            None
            if not errors
            else (
                "Use write_gatepass_service_template, write_gatepass_annotations_template, "
                "write_gatepass_manifest_template, write_gatepass_ui_shell_templates; "
                "then verify_fiori_mode_b. Run cds watch from THIS cap-app only (not Trash)."
            )
        ),
    }
