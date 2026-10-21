---
name: review
description: Independent review of a CAP change against the spec. Do not merge.
---

# Review

You did not write the change. Read the spec before the diff.

## Always fail

- Extra scope (field, file, or Fiori when out of scope)
- Field missing from CDS or wrong type/length vs TECH
- Planned check missing (e.g. vehicleNo reject on CREATE)
- Handler bound to DB entity name instead of service entity set
- Service projection with inline `field @mandatory;` inside `projection on … { *, … }` (CDS parse error; empties UI metadata / filter bar)
- Service `@(path: '/gate-pass')` absolute path (or any leading `/` path) while FE uses `/odata/v4/...` (blank page / OData 404)
- manifest dataSource uri not `/odata/v4/gate-pass/` when service path is `gate-pass`
- `cds compile` would fail on srv/*.cds or annotations not loaded into EDMX (no UI.SelectionFields in metadata)
- Secret in the diff
- More than one service handler `.js` for the same service (e.g. both `gatepass-service.js` and `gate-pass-service.js`)
- Any use of basename `gate-pass-service` when the factory standard is `gatepass-service`
- Handler basename does not match service CDS basename
- `annotations.cds` `using` path points at a missing CDS module or at a `.js` file
- Annotations import `…/gatepass-service` but only `gate-pass-service.cds` exists (or the reverse)
- Fiori app under odd folders like `app/gatepass-fiori` or `app/gatepass-list-report` (must be `app/gatepass`)
- Mode B without `annotations.cds` or without `UI.SelectionFields` (empty filter bar)
- Mode B claimed but missing any of: annotations.cds (app root), Component.js, index.html, manifest.json, ui5.yaml
- manifest i18n/appTitle placeholders without `webapp/i18n/i18n.properties`
- index.html missing `data-sap-ui-resourceroots` for gatepass
- Standalone index not on UI5 1.145.0 or missing ComponentContainer bootstrap (blank page vs fiori-preview)
- CDS `namespace` / `using` mismatch across `db/` and `srv/`
- File content with literal backslash-n sequences instead of real newlines (corrupt YAML/JS)
- Invalid JSON or YAML in written files
- Fiori touched when out of scope (any `app/` UI when spec says no Fiori)
- Files written under nested `cap-app/cap-app/` (path incorrectly prefixed with `cap-app/`)
- File sqlite without deploy path / bare `db.sqlite` URL likely to cause no such table at runtime
- Missing `@cap-js/sqlite` or `better-sqlite3` on CAP 10 package.json
- `@cap-js/sqlite` ^1 (or major < 3) together with `@sap/cds` ^10 (npm ERESOLVE peer)

## Fiori in scope — also fail if

- Missing Mode B file from the Fiori skill set
- Missing Object Page route/target when List Report navigates to detail
- Missing `UI.Facets` / `UI.FieldGroup`
- Broken Facets syntax (`Type:#Collection`, `{$`, missing `UI.ReferenceFacet`)
- HeaderInfo Title without UI.DataField $Type
- manifest `resources.json` / localService without files
- Missing height CSS cascade in `index.html` (blank-page risk)
- CDN bootstrap version not pinned or known-bad
- Wrong OData URI vs live CAP path
- `ui5.yaml` not valid YAML
- Object page pattern still contains skill placeholders (`KEY_TOKEN`, angle-bracket key)

## Process

- End with **ready-to-merge** or **changes-requested** and list concrete fails.
- Do not flag a check that already existed on the MVP when the CR only adds to it. Removing an MVP check is a fail.
- Do not push a fix. Do not merge.
- If implement was blocked, say review skipped.
