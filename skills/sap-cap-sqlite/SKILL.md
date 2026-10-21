---
name: sap-cap-sqlite
description: Configure and deploy CAP Node.js apps to SQLite so OData does not fail with no such table. Use when generating package.json for CAP, cds watch, cds deploy, sqlite, better-sqlite3, db.sqlite, or fixing GatePassService_GatePasses / no such table errors.
---

# CAP SQLite bootstrap

## Symptom

UI or OData fails with:

```text
no such table: GatePassService_GatePasses
```

or `no such table: my_cap_GatePass`.

Server is up; **schema was never applied** to the DB the server opened (or a different empty file was opened).

## Preferred local demo config (auto-deploy)

For MVP / factory demos, use **in-memory** SQLite so every `cds watch` / `cds-serve` bootstraps tables automatically:

```json
"cds": {
  "requires": {
    "db": {
      "kind": "sqlite",
      "credentials": { "url": ":memory:" }
    }
  }
}
```

Dependencies (CAP 10):

```json
"dependencies": {
  "@sap/cds": "^10.1.1",
  "@cap-js/sqlite": "^3.1.2",
  "better-sqlite3": "^13.0.3",
  "express": "^4.22.3"
},
"devDependencies": {
  "@sap/cds-dk": "^10.1.0"
}
```

Do **not** keep legacy `sqlite3` as the driver when using `@cap-js/sqlite` v3.

## File-based SQLite (optional)

If TECH wants a file DB:

1. Credentials must use the `file:` URL form:

```json
"credentials": { "url": "file:db.sqlite" }
```

2. Deploy **before** serve (same project directory):

```bash
rm -f db.sqlite db.sqlite-shm db.sqlite-wal
npx cds deploy --to sqlite:db.sqlite
npx cds watch
```

3. package.json scripts:

```json
"deploy": "cds deploy --to sqlite:db.sqlite",
"deploy:fresh": "rm -f db.sqlite db.sqlite-shm db.sqlite-wal && cds deploy --to sqlite:db.sqlite"
```

4. Align paths: deploy target `sqlite:db.sqlite` and runtime `file:db.sqlite` must refer to the **same** file under the app root. Avoid bare `"url": "db.sqlite"` (ambiguous).

5. After model changes, redeploy or use `deploy:fresh`. An old empty `db.sqlite` left on disk is a common cause of no-such-table.

## What deploy creates

For entity `my.cap.GatePass` projected as `GatePassService.GatePasses`:

- Table: `my_cap_GatePass`
- View: `GatePassService_GatePasses` (runtime may query the view name)

Both appear only after a successful deploy or in-memory bootstrap.

## Implement / MVP rules

- Default greenfield `package.json` to **`:memory:`** unless TECH asks for a file DB.
- If file DB: add `deploy` / `deploy:fresh` scripts and document run order: deploy then watch.
- Never claim the UI works until `GET /odata/v4/<service>/<EntitySet>` returns 200 (not 500 no such table).

## Review fails

- File sqlite configured without deploy script or with bare `db.sqlite` URL
- Empty `db.sqlite` committed or left from a failed run while file mode is on
- Missing `@cap-js/sqlite` / `better-sqlite3` for CAP 10
- OData 500 no such table after generate (bootstrap incomplete)

## Quick verify

```bash
cd cap-app
npm install
# memory mode:
npm run watch
# other terminal:
curl -sS http://localhost:4004/odata/v4/gate-pass/GatePasses
curl -sS -X POST http://localhost:4004/odata/v4/gate-pass/GatePasses \
  -H 'Content-Type: application/json' \
  -d '{"number":"GP1","vehicleNo":"V1","plant":"P001","status":"OPEN"}'
```

Expect list 200 and create 201 (or 400 when vehicleNo/plant empty per handlers).
