---
name: sap-cap
description: Conventions for SAP CAP delivery in this factory. Use when building or changing a CAP app, writing CDS, handlers, services, package.json, or reviewing CAP output.
---

# SAP CAP

## Acceptance rules

- A new field is in CDS, with a type. UI-only is a fail.
- Required means `@mandatory` and/or a before-CREATE handler that rejects empty (null, `""`, whitespace). Prose is not enough.
- Handlers bind to the **service entity set** name (e.g. `GatePasses`), not the DB entity (`GatePass`).
- Service exposure is a projection. Do not expose fields the spec did not name.
- Do not weaken tenant isolation. No cross-tenant read.
- No secrets, no hardcoded destination names.
- If the spec says no Fiori, do **not** emit `app/` (no annotations, no webapp, no ui5.yaml).
- If the spec asks for Fiori / Fiori elements, also follow the `sap-fiori-elements` skill. Incomplete FE apps are a fail.
- Destinations, role collections, and transports are human steps. Do not invent them in code.
- Edit under `cap-app/`. Do not create a nested second CAP root under `app/`.
- `write_file` paths are relative to `cap-app/` already. Use `db/schema.cds`, never `cap-app/db/schema.cds` (that nests `cap-app/cap-app/`).

## Greenfield vs change

- **Greenfield** (spec says no existing app / new CAP app): write only the files TECH named. Typical minimal set:
  - `package.json`
  - `db/schema.cds`
  - `srv/<service-file>.cds`
  - `srv/<service-file>.js`  (exactly one handler file)
- **Change** (existing MVP): edit in place. Do not recreate the whole app. Do not add fields or files the spec did not name.
- Never invent a second parallel service implementation "for safety".

## File naming (critical)

### Canonical GatePass service basename (this factory)

Unless TECH explicitly names a different basename, **always** use:

| Role | Path |
|------|------|
| Service CDS | `srv/gatepass-service.cds` |
| Handler JS | `srv/gatepass-service.js` |
| Annotations using | `from '../../srv/gatepass-service'` |

**Forbidden** (causes dual handlers / broken imports):

- `srv/gate-pass-service.cds`
- `srv/gate-pass-service.js`
- mixing `gatepass-service` and `gate-pass-service` in one project

Service **name** in CDS is still `GatePassService` (PascalCase). File basename is `gatepass-service` (no hyphen between gate and pass).

CAP loads the handler next to the service CDS by **same basename**:

| CDS service file | Handler file | OK? |
|------------------|--------------|-----|
| `srv/gatepass-service.cds` | `srv/gatepass-service.js` | yes |
| `srv/gatepass-service.cds` | `srv/gate-pass-service.js` | no — extra/wrong file |
| both `gatepass-service.js` and `gate-pass-service.js` | | **fail** — dual handlers |

Rules:

1. One service CDS file ↔ **exactly one** handler `.js` with the **same basename**.
2. On a change CR, **edit the existing pair in place**. Do not invent a second basename.
3. Before writing handlers, if `srv/*.cds` already exists, match that basename — do not add another.
4. `annotations.cds` `using … from '…'` must point at the **service CDS module** that exists on disk (e.g. `../../srv/gatepass-service`), never at a `.js` file and never at a basename with no `.cds`.

## CDS shape

```cds
namespace my.cap;   // pick one namespace; keep it stable

entity GatePass {
  key ID        : UUID;
      number    : String(20);
      vehicleNo : String(20);
      plant     : String(20);  // only if TECH names plant
      status    : String(20);
}

// srv/gatepass-service.cds
using my.cap as db from '../db/schema';

service GatePassService @(path: 'gate-pass') {
  entity GatePasses as projection on db.GatePass;
}

// mandatory on service entity — NEVER inside projection { *, field @mandatory; }
annotate GatePassService.GatePasses with {
  plant @mandatory;
};
```

### Projection annotation pitfall (breaks whole model + empty filter bar)

**Forbidden** (CDS parse error; `cds compile` fails; UI annotations never reach `$metadata`):

```cds
entity GatePasses as projection on db.GatePass {
  *,
  plant @mandatory;
};
```

**Required instead:** plain projection `as projection on db.GatePass;` then separate `annotate … with { plant @mandatory; }` or put `@mandatory` on the **db** field in `schema.cds`.

If service CDS does not compile, `app/**/annotations.cds` UI.SelectionFields will not appear in OData metadata → blank List Report filter bar.

- Prefer `using my.cap as db` + `db.Entity`. **Schema must declare the same namespace** (`namespace my.cap;`).
- If schema has **no** namespace, service must use `using { GatePass } from '../db/schema'` (not bare `using from`). Prefer tools: `write_gatepass_schema_template` then `write_gatepass_service_template`.
- **Fail:** `using my.cap as db` while schema has no `namespace my.cap` (cds: Artifact my.cap.GatePass has not been found).
- Do not rename `namespace` unless TECH requires it. If you rename it, update every `using` in the same change.
- Field lengths and names must match TECH exactly (e.g. String(20) not String(100) unless specified).

## Handler shape

Skill text is passed to agents verbatim (InstructionProvider), so braces in examples are safe.
When writing real handler files on disk, either style is fine.

```js
const cds = require('@sap/cds')
module.exports = class GatePassService extends cds.ApplicationService {
  init() {
    this.before('CREATE', 'GatePasses', (req) => {
      const data = req.data || {}
      const vehicleNo = data.vehicleNo
      if (!vehicleNo || String(vehicleNo).trim() === '') {
        req.error(400, 'Vehicle number is required', 'vehicleNo')
      }
    })
    return super.init()
  }
}
```

Also acceptable: `module.exports = cds.service.impl(function () { ... })` with the same entity name and checks.

- Reject blank strings; trim before testing.
- Do not add validations TECH did not name (e.g. min length 3, plant required) unless TECH says so.

## package.json (CAP root)

- Depends on `@sap/cds` ^10, `@cap-js/sqlite` **^3** (not ^1 — peers cds <9 only → npm ERESOLVE), `better-sqlite3` ^13, `express` ^4.
- Prefer tool `write_cap_package_template` for root package.json.
- Dev: `@sap/cds-dk` ^10 for `cds watch` / `cds deploy`.
- Scripts: `start` = cds-serve, `watch` = cds watch.
- Default local DB: sqlite **`:memory:`** so schema auto-deploys (avoids no such table). See skill `sap-cap-sqlite` for file DB + deploy.
- Do not put `@sap/cds` inside `app/*/package.json`.
- Do not use legacy `sqlite3` package as the CAP 10 driver.

## write_file content quality

When calling `write_file`:

- Pass **real multiline text** with actual newline characters.
- Never write a single line that contains the two characters `\` and `n` instead of newlines (breaks YAML/CDS/JS).
- Never write partial stubs or "filename only".
- YAML (`ui5.yaml`) must be valid YAML parseable by a YAML parser.
- JSON must be valid JSON.
- CDS must compile with the sibling files you wrote in the same change.

## Scope discipline

- No plant / Fiori / destinations / roles / BTP unless TECH named them.
- No extra entities, services, or handler files "for later".
- If TECH says CAP only, the change list must not include `app/`.
