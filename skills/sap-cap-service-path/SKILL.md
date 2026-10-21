---
name: sap-cap-service-path
description: Validate CAP service path vs Fiori OData URI. Use when writing srv/*.cds path annotations, manifest dataSources, ui5 proxy, blank FE page, or OData 404 on /odata/v4/.
---

# CAP service path ↔ FE OData URI

Mismatch = blank Fiori page (metadata 404) even when CDS compiles.

## Rule (GatePass defaults)

| Layer | Required value |
|-------|----------------|
| Service CDS | `@(path: 'gate-pass')` — **no leading slash** |
| Live OData | `/odata/v4/gate-pass/` |
| `manifest.json` `sap.app.dataSources.mainService.uri` | `/odata/v4/gate-pass/` |
| ui5 proxy (if any) | `/odata` → `http://localhost:4004` |

CAP mounts relative paths under protocol prefix (`protocols.odata-v4.path` = `/odata/v4`).  
A path that **starts with `/`** is absolute from server root.

## Forbidden

```cds
service GatePassService @(path: '/gate-pass') { ... }
```

That serves only at `/gate-pass/…` while FE still calls `/odata/v4/gate-pass/…` → **404** → blank UI.

Also forbidden:

- manifest uri `/gate-pass/` (missing `/odata/v4`)
- manifest uri with wrong service segment
- service path `gatepass` vs uri `gate-pass` (hyphen mismatch)

## Required service shape

```cds
service GatePassService @(path: 'gate-pass') {
  entity GatePasses as projection on db.GatePass;
}
```

Prefer tool `write_gatepass_service_template` (sanitizes absolute path).

## Required manifest fragment

```json
"dataSources": {
  "mainService": {
    "uri": "/odata/v4/gate-pass/",
    "type": "OData",
    "settings": { "odataVersion": "4.0" }
  }
}
```

Prefer tool `write_gatepass_manifest_template`.

## Validate before done

With `cds watch` from **this** `cap-app/`:

1. `GET /odata/v4/gate-pass/$metadata` → **200** (not 404)
2. Body includes `UI.SelectionFields` when annotations exist
3. `GET /odata/v4/gate-pass/GatePasses` → **200**
4. Welcome page / FE must not be the only place that works at bare `/gate-pass`

If bare `/gate-pass/$metadata` is 200 but `/odata/v4/gate-pass/$metadata` is 404 → path still absolute; fix CDS path, restart watch.

## Review / implement fail if

- Service `path` contains leading `/gate-pass` or any leading `/` service path paired with FE
- Manifest uri is not exactly under `/odata/v4/gate-pass`
- FE Mode B claimed while OData v4 URL would 404
- Path token differs across CDS path, manifest uri, and proxy (e.g. `gatepass` vs `gate-pass`)
