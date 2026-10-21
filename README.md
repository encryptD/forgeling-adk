# ForgeLine on ADK Web

One session. Four agents. One pause.

Triage shapes the request. Spec writes the pack. The run stops. You approve or reject in the ADK Web dialog. Only an approval lets Implement run. Review checks the result and does not merge.

## Run

```bash
cd forgeling-adk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_API_KEY=...   # or use Vertex, see ADK docs
adk web .
```

Open the UI, pick `factory`, and send:

```
CR cr-001. Add a required Plant field on the GatePass header.
CAP only. Reject save if plant is empty. Do not change Fiori.
App is cap-app/db/schema.cds entity GatePass (ID, number, vehicleNo, status)
and cap-app/srv/gatepass-service.js which already rejects an empty vehicleNo.
```

When the dialog appears, that is the gate. Reject once in the demo if you want the panel to see implement skip. Approve on the second run.

## What the panel should see

- Separate agent turns, not one blob of text.
- Spec pack before any code change is described.
- A confirmation dialog that blocks implement.
- Review that can fail the change.

## CAP app (cap-app)

```bash
cd cap-app
npm install   # once
npx cds watch
```

Working UI entry points:

- Full FE app: http://localhost:4004/gatepass/webapp/index.html
- CAP Fiori preview: http://localhost:4004/$fiori-preview/GatePassService/GatePasses#preview-app
- OData: http://localhost:4004/odata/v4/gate-pass/$metadata

Factory skills live under `skills/`. See [`skills/README.md`](./skills/README.md).

### Fiori elements skill (`sap-fiori-elements`)

Prevents incomplete FE apps. Loaded into **spec**, **implement**, and **review**.

| Mode | When | Output |
|------|------|--------|
| A | Annotations / preview only | `annotations.cds` + CAP `/$fiori-preview/...` |
| B | Spec asks for a full FE UI | Full `app/<app>/` tree (manifest, index, Component, i18n, ui5.yaml, annotations) |

Operator guide: [`skills/sap-fiori-elements/USAGE.md`](./skills/sap-fiori-elements/USAGE.md)  
Agent playbook: [`skills/sap-fiori-elements/SKILL.md`](./skills/sap-fiori-elements/SKILL.md)

Example Mode B prompt:

```text
CR cr-003. Add required Plant on GatePass and deliver a full Fiori elements
List Report + Object Page under app/gatepass for GatePassService.GatePasses.
```

Restart `adk web` after skill or `factory/agent.py` edits.

Verify Mode B generation non-interactively:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true   # or a valid GOOGLE_API_KEY
export GOOGLE_CLOUD_PROJECT=...
export GOOGLE_CLOUD_LOCATION=us-central1
python scripts/verify_fiori_skill.py
```

## Not in this demo

ABAP, a real git push, merge. The implement agent writes under `cap-app/`. It does not deploy to BTP.
