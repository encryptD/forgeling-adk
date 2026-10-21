---
name: spec-pack
description: Conventions for creating and managing specifications in this factory, product, tech, test. No code.
---

# Spec pack

A spec is three short sections. No code.

## PRODUCT

- Who is affected
- In scope
- Out of scope (name Fiori / plant / BTP explicitly when excluded)
- Acceptance checks

## TECH

- Greenfield or change to existing `cap-app/`
- Namespace (if known)
- Entity, fields with types and lengths
- Service name and entity set name
- **Exact handler file path** (must share basename with service CDS), e.g. `srv/gatepass-service.js` with `srv/gatepass-service.cds`
- Validation rules (what empty means)
- Fiori: none | Mode A | Mode B — if Mode B, name AppId
- Human steps (destinations, roles, transport)

Do not list two handler files. Do not leave handler path ambiguous.

## TEST

- One row per acceptance check
- What cannot be run here (BTP, IdP, etc.)

## Discipline

- Do not invent a business rule that is not in the request.
- Do not say the change is approved.
- If the user said no Fiori, out of scope must include Fiori / `app/`.
- If the user said no plant, out of scope must include plant.
