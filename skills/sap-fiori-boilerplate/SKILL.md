---
name: sap-fiori-boilerplate
description: Mandatory Fiori elements bootstrap checklist for CAP. Use whenever generating or reviewing FE UI (index.html, manifest, Component, annotations, blank page, Mode B). Prevents blank UI and incomplete apps.
---

# Fiori elements boilerplate (mandatory)

Incomplete or wrong bootstrap = blank UI. Follow exactly.

## Paths (GatePass defaults)

- App folder: `app/gatepass/` only
- **Forbidden app ids:** `gatepass-fiori`, `gatepass-list-report`, `gatepass-list`
- Service module: `srv/gatepass-service` (not gate-pass-service)
- annotations: `app/gatepass/annotations.cds` (not under webapp/)
- OData: `/odata/v4/gate-pass/`
- Service CDS path must be relative `gate-pass` (NOT `'/gate-pass'`). Leading slash mounts at `/gate-pass` and blanks FE (404 on `/odata/v4/...`).
- Entity set: `GatePasses`
- Component / resourceroots key / data-name: all exactly `gatepass`

## Mode B — all 6 files or fail

1. `app/gatepass/annotations.cds`
2. `app/gatepass/package.json`
3. `app/gatepass/ui5.yaml`
4. `app/gatepass/webapp/Component.js`
5. `app/gatepass/webapp/index.html`
6. `app/gatepass/webapp/manifest.json`

Never annotations-only. Real newlines (no escaped backslash-n).
Prefer tool `write_gatepass_annotations_template` for annotations.cds (avoids Facets syntax failures).
After writing all 6, call tool `verify_fiori_mode_b` and fix until `ok: true`.

## index.html (blank-page killers)

**Pin UI5 to the same major line CAP fiori-preview uses.** Preview worked at **1.145.0** while standalone **1.136.x** stayed blank in browser.

Must include:

- `src="https://ui5.sap.com/1.145.0/resources/sap-ui-core.js"` — **not** 1.136.0 / 1.136.1
- `data-sap-ui-libs="sap.m,sap.ui.core,sap.f,sap.fe.templates"`
- `data-sap-ui-resourceroots='{"gatepass":"./"}'` (**required**)
- `data-sap-ui-xx-componentPreload="off"`
- `data-sap-ui-async="true"`, theme `sap_horizon`
- CSS: `html,body,#content` + FE containers height/width 100%
- Prefer tool `write_gatepass_ui_shell_templates` for index/Component/ui5/package

### Bootstrap (required for standalone under cds watch)

Do **not** rely on ComponentSupport alone. After core loads, create the component explicitly:

```js
sap.ui.require(["sap/ui/core/ComponentContainer","sap/ui/core/Core"], function (ComponentContainer, Core) {
  Core.ready().then(function () {
    new ComponentContainer({
      id: "container",
      name: "gatepass",
      height: "100%",
      width: "100%",
      async: true,
      manifest: true
    }).placeAt("content");
  });
});
```

Show a visible boot message (`Loading Gate Passes…`) until the container mounts so CDN failures are not a silent blank page.

Open URL: `http://localhost:4004/gatepass/webapp/index.html` (not `/gatepass/index.html`).

## Component.js

Extend `sap/fe/core/AppComponent`, name `gatepass.Component`, `manifest: "json"`.

## manifest.json

- `sap.app.id` = `gatepass`
- Hardcoded `title` / `description` strings only
- **Forbidden unless i18n files written in same change:** `sap.app.i18n`, i18n model, appTitle placeholders, `localService/metadata.xml`
- dataSource uri `/odata/v4/gate-pass/` only, odataVersion 4.0
- `flexEnabled`: **false** (standalone; avoids LREP 404 noise)
- `minUI5Version`: `1.145.0`; libs include `sap.f` + `sap.fe.templates`
- default model `""` → mainService; synchronizationMode None, operationMode Server, autoExpandSelect true, earlyRequests true, groupId $direct
- Routes: list `:?query:` + object page with UI5 `{key}` pattern
- Targets: ListReport + ObjectPage with **both** `entitySet: "GatePasses"` and `contextPath: "/GatePasses"`
- List `navigation.GatePasses.detail.route` = ObjectPage route name
- List `initialLoad`: true

## annotations.cds (drives filter bar + table)

Without this file (or without SelectionFields), the List Report filter bar has **no attribute fields**.
Also requires **valid** `srv/*.cds` (compiles). Invalid service CDS → annotations never enter `$metadata` → empty filter bar even if annotations.cds looks perfect.
Runtime check: `GET /odata/v4/gate-pass/$metadata` must contain `UI.SelectionFields`. Serve **this** `cap-app/` (not a Trash/old copy).

Write this **exact structure** (field list may match schema). Compact `{$Type:...}` is valid CDS — keep `$Type`.

```cds
using GatePassService as service from '../../srv/gatepass-service';

annotate service.GatePasses with @(
  UI.SelectionFields: [ number, vehicleNo, plant, status ],
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
```

- **Required:** SelectionFields, LineItem, FieldGroup, Facets (ReferenceFacet), HeaderInfo Title DataField
- **Forbidden:** missing file; missing SelectionFields; `Type:#Collection`; `{$value` Title hacks
- Mode A = this file only + CAP fiori preview

## ui5.yaml / app package.json

- Valid YAML newlines; framework 1.145.0; proxy `/odata` -> `http://localhost:4004`
- UI-only package.json (`@ui5/cli`, `@sap/ux-ui5-tooling`) — not a second CAP root

## Review fail if any missing

resourceroots, height CSS, UI5 not 1.145.0 on standalone index, ComponentSupport-only bootstrap (no ComponentContainer),
flexEnabled true on standalone, missing entitySet+contextPath, any of 6 Mode B files, Facets/SelectionFields,
wrong service basename, i18n without files, gatepass-fiori / gatepass-list-report folder, missing annotations.cds.
