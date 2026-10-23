# ForgeLine factory skills

Skills are markdown playbooks under `skills/<name>/SKILL.md`.  
`factory/skills_loader.py` strips YAML frontmatter and injects the body into agent instructions **verbatim**.

Agents use `instruction(template, *state_keys)`, an ADK `InstructionProvider`. ADK skips its own `{var}` state injection for providers, so braces in skill code samples (`{ vehicleNo }`, CDS `{ ... }`) are kept as-is; only the listed state keys (`{spec_pack}`, `{verify_result}`, ...) are filled. Do not write `{work_item}`-style state keys inside skill bodies (a unit test enforces this).

```python
from .skills_loader import instruction, skill
CAP = skill("sap-cap")
agent = Agent(..., instruction=instruction(f"{CAP}\nSpec:\n{{spec_pack}}", "spec_pack"))
```

## Catalog

| Folder | Name | Used by | Purpose |
|--------|------|---------|---------|
| `sap-cap/` | sap-cap | triage, spec, implement, review | CAP delivery rules (CDS, handlers, scope) |
| `sap-cap-service-path/` | sap-cap-service-path | implement, review, mvp | Service path vs `/odata/v4/...` FE URI |
| `sap-cap-sqlite/` | sap-cap-sqlite | implement, mvp | SQLite :memory: / deploy bootstrap |
| `sap-fiori-elements/` | sap-fiori-elements | spec, implement, review | Valid Fiori elements apps on CAP |
| `spec-pack/` | spec-pack | spec | PRODUCT / TECH / TEST pack shape |
| `gate/` | gate | gate | Human approval via `approve_spec` |
| `review/` | review | review | Independent check; no merge |

## Fiori skills (keep agent context small)

| Skill | Role | Injected? |
|-------|------|-----------|
| [`sap-fiori-boilerplate`](./sap-fiori-boilerplate/SKILL.md) | **Mandatory** bootstrap + Mode B 6-file checklist | factory implement/review, mvp |
| [`sap-fiori-elements`](./sap-fiori-elements/SKILL.md) | One-screen pointer only | prefer boilerplate instead |
| [`sap-fiori-elements/USAGE.md`](./sap-fiori-elements/USAGE.md) | Long operator docs | **never** inject into agents |

Boilerplate encodes blank-UI fixes: `data-sap-ui-resourceroots`, height CSS, CDN pinned to UI5 **1.145.0** (1.136.x blanked standalone FE), `ComponentContainer` bootstrap, no orphan i18n, contextPath + ObjectPage nav, canonical `app/gatepass/` + `gatepass-service`.

## SQLite bootstrap skill

- **Playbook:** [`sap-cap-sqlite/SKILL.md`](./sap-cap-sqlite/SKILL.md)
- Fixes `no such table: GatePassService_GatePasses` by defaulting to `:memory:` or explicit `cds deploy` for file DBs.
- Loaded with `sap-cap` into factory + MVP agents via `skill("sap-cap", "sap-cap-sqlite")`.

## Service path skill

- **Playbook:** [`sap-cap-service-path/SKILL.md`](./sap-cap-service-path/SKILL.md)
- Prevents blank FE from absolute CDS path `'/gate-pass'` vs manifest `/odata/v4/gate-pass/`.
- Loaded with CAP bundles: `skill("sap-cap", "sap-cap-sqlite", "sap-cap-service-path")`.
- Tools also sanitize absolute paths in `write_file` / `write_gatepass_service_template`.

## Operating rule

**Never patch `cap-app/` to fix agent mistakes.** Fix skills, `factory/agent.py`, `mvp/agent.py`, and `factory/tools.py` only. Re-run agents to regenerate.

## Generation guardrails (2026-10)

Factory + MVP agents were tightened after bad CAP output:

- One service CDS ↔ one handler JS (**same basename**); no dual `gatepass-service.js` + `gate-pass-service.js`
- Annotations `using` must target the service **CDS** module, not a `.js` path
- No Fiori/`app/` when TECH says CAP only; no extra fields (e.g. plant) unless named
- `write_file` rejects content that is mostly escaped `\n` instead of real newlines
- Review fails those defects explicitly

Restart `adk web` after skill or agent edits.

## Conventions for new skills

1. Directory name = skill id passed to `skill("id")`.
2. `SKILL.md` starts with frontmatter:

   ```yaml
   ---
   name: my-skill
   description: What it does and when to trigger it.
   ---
   ```

3. Body is imperative, short, and checklist-friendly (agents load the whole body).
4. Put human-only narrative in `USAGE.md` so `SKILL.md` stays agent-sized.
5. Wire the skill explicitly in `factory/agent.py` for every agent that must obey it.

## Reload

ADK Web picks up Python/skill text on process restart. After editing skills or `agent.py`, restart `adk web`.
