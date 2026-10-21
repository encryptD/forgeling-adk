# Using `sap-fiori-elements` in ForgeLine

This skill teaches factory agents how to emit a **runnable** SAP Fiori elements (OData V4) UI on a CAP service—or to reject incomplete scaffolding in review.

## Location

```text
skills/sap-fiori-elements/
  SKILL.md    # loaded into agent instructions
  USAGE.md    # this file (humans + operators)
```

Loaded by `factory/skills_loader.py`:

```python
skill("sap-fiori-elements")
```

## Who gets the skill

| Agent | Loads skill? | Role |
|-------|--------------|------|
| triage | no (CAP only) | May note Fiori in/out of scope from the user text |
| spec | **yes** | TECH must pick Mode A vs B and name Service / EntitySet / AppId |
| gate | no | Unchanged |
| implement | **yes** | Writes CAP + FE files per mode |
| review | **yes** | Fails incomplete FE apps using the checklist |

Wiring (`factory/agent.py`):

```python
FIORI = skill("sap-fiori-elements")
# injected into spec, implement, and review instructions
```

## Operator: when to invoke a Fiori CR

**CAP only (no UI):**

```text
CR cr-001. Add required Plant on GatePass.
CAP only. Reject save if plant is empty. Do not change Fiori.
```

**Annotations + preview (Mode A):**

```text
CR cr-002. Add Plant to GatePass and show it on the Fiori list/object via annotations only.
Use CAP Fiori preview. Do not scaffold a full webapp.
```

**Full FE app (Mode B):**

```text
CR cr-003. Add required Plant on GatePass and deliver a full Fiori elements app
under app/gatepass (List Report + Object Page) bound to GatePassService.GatePasses.
```

## Modes (quick)

| Mode | Deliverable | Open in browser |
|------|-------------|-----------------|
| A | `annotations.cds` (+ CAP) | `http://localhost:4004/$fiori-preview/<Service>/<EntitySet>#preview-app` |
| B | Full `app/<AppId>/` tree | `http://localhost:4004/<AppId>/webapp/index.html` |

## Local verification (after implement)

```bash
cd cap-app
npx cds watch
```

Open:

- Full app: http://localhost:4004/gatepass/webapp/index.html  
- CAP preview: http://localhost:4004/$fiori-preview/GatePassService/GatePasses#preview-app  

Hard-refresh (Cmd+Shift+R) after FE file changes.

HTTP smoke:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:4004/gatepass/webapp/index.html
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:4004/gatepass/webapp/manifest.json
curl -sS -o /dev/null -w "%{http_code}\n" "https://ui5.sap.com/1.136.0/resources/sap-ui-core.js"
curl -sS "http://localhost:4004/odata/v4/gate-pass/\$metadata" | grep -E 'UI.LineItem|UI.Facets'
curl -sS -X POST http://localhost:4004/odata/v4/gate-pass/GatePasses \
  -H 'Content-Type: application/json' \
  -d '{"number":"T1","vehicleNo":"","plant":"P001","status":"OPEN"}'
```

Expect app assets 200, CDN 200, UI annotations present, and 400 on empty required fields (handler on **GatePasses**, not GatePass).

Browser must show a List Report (filters + table), not a blank page.

## Blank page runbook (Mode B)

If `index.html` loads but the screen is white:

1. Confirm CAP preview works (isolates backend/annotations).
2. Confirm `index.html` contains the **height cascade** CSS for `.sapUiComponentContainer`, `.sapMApp`, `.sapMPage`, `.sapFDynamicPage*`.
3. Confirm CDN bootstrap URL returns 200 (pin a real version such as `1.136.0`, not a missing patch).
4. Confirm `data-sap-ui-xx-componentPreload="off"` when there is no `ui5 build`.
5. In DevTools, FE roots (`ListReport`, `.sapMPage`) must have **non-zero height**. Height 0 with visible DOM text = missing CSS cascade.

## Verify with the factory agent

```bash
cd forgeling-adk
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=...
export GOOGLE_CLOUD_LOCATION=us-central1
python scripts/verify_fiori_skill.py
```

The script runs triage → spec → gate (auto-approve) → implement → review and asserts Mode B structure, OData URI, routing, annotations, handler entity name, UI5 key route token, and CDS namespace consistency.

### ADK instruction pitfalls

- Skill markdown is injected into agent instructions. **Double-brace tokens** are ADK session placeholders — never put UI5 i18n mustache inside `SKILL.md`.
- **Single-brace `{key}`** is also expanded by ADK. In skill text use `KEY_TOKEN`; implement must write the real UI5 route pattern on disk.
- Do not rename CDS `namespace` without updating every `using { ... }`.

## Design intent (failures this skill prevents)

1. Handler bound to DB entity → validations silent  
2. Relative UI5 bootstrap under `cds watch` → blank app  
3. Missing viewport height CSS → blank page (DOM present, paint height 0)  
4. Bad CDN patch version → core/FE libs 404  
5. ListReport without Object Page target → navigation/create broken  
6. Broken HeaderInfo Title syntax → no dynamic title  
7. Missing Facets/FieldGroup → empty object page  
8. Nested CAP `package.json` under `app/` → wrong packaging  
9. `Component-preload.js` 404 noise without build (use preload off in dev)

## Adding the skill to another agent factory

1. Copy `skills/sap-fiori-elements/` into that repo’s skills root.
2. Ensure the loader reads `skills/<name>/SKILL.md`.
3. Inject `skill("sap-fiori-elements")` into spec, implement, and review prompts.
4. Keep `sap-cap` aligned: service entity set names; no nested CAP under `app/`.
5. Restart `adk web` after skill edits.
