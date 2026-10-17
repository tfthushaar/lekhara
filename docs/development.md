# Developing Lekhara

This guide is for the people building Lekhara. The customer-facing product description is in the [README](../README.md); progress is tracked in [status.md](../status.md).

## Layout

```
api/    Python 3.12, FastAPI. Rules pack, engines, database, HTTP API.
web/    Next.js 16 (App Router, TypeScript). The Lekhara web app.
docs/   Developer documentation.
```

## Prerequisites

- Python 3.12+
- Node.js 20.9+ (24 recommended)
- Docker (optional, for local Postgres)

## API

```bash
cd api
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # Windows
# .venv/bin/python -m pip install -e ".[dev]"        # macOS / Linux

.venv/Scripts/python -m pytest                       # tests
.venv/Scripts/python -m ruff check .                 # lint
.venv/Scripts/python -m lekhara.migrate               # bring the schema up to date
.venv/Scripts/python -m lekhara.seed                  # load demo data (resets the database)
.venv/Scripts/python -m uvicorn lekhara.app:app --reload   # http://localhost:8000
```

The demo data is a fictional developer with three Bengaluru projects, dated relative to today. Set `LEKHARA_TODAY=2026-10-17` to pin the date.

Anyone can create a builder firm at `/signup` (the API's `/auth/signup`): the firm gets its own workspace and a free month (`LEKHARA_TRIAL_DAYS`, default 30), after which an unpaid workspace is read-only. The demo firm is the sample: every signed-in person can look at its projects, and only its own members can change them.

Emails (confirmation, password reset, invitations) are kept in the `outbound_emails` table. Set `LEKHARA_SMTP_URL` (for example `smtp://user:password@smtp.example.com:587`) and `LEKHARA_MAIL_FROM` to send them; without SMTP they are written to the API's log, which is how to follow the links locally. Links point at `LEKHARA_WEB_URL` (default `http://localhost:3000`).

Sign-in is required for everything except `/health`, `/rules`, sign-up, password reset, invitations and shared data rooms. Run the API with `LEKHARA_DEMO=1` to list the demo accounts on the sign-in screen; every demo account uses the password `lekhara-demo`:

| Email | Role |
|---|---|
| promoter@demo.lekhara | Owner |
| cfo@demo.lekhara | Finance |
| accounts@demo.lekhara | Accounts |
| architect@demo.lekhara | Architect on every project |
| engineer@demo.lekhara | Engineer on every project |
| ca@demo.lekhara | Chartered accountant on every project |

Who may do what: the owner, finance and accounts start withdrawals and send them to the bank; only the owner and finance record a release or rejection; each certifier changes and signs only their own certificate, and sees only the projects they certify (escrow and money, not tax or units).

Main endpoints: `/today`, `/projects`, `/projects/{id}` (with `/money`, `/escrow`, `/collections`, `/handover`, `/disputes`, `/documents`, `/tax`, `/units`, `/setup`; `PUT` changes its details and `POST /progress` records certified progress), `/withdrawals/{id}`, `/demands/{id}`, `/units/{id}/handover`, `/cases/{id}`, `/documents/{id}`, `/rooms/{id}`, `/shared/{token}` (no sign-in) and `/rules`. Interactive docs are at `/docs` while the server runs.

### Import centre

Record types are defined once in `api/lekhara/records.py` (fields, aliases, parsing); `registers.py` adds, changes and deletes records with a change history; `imports.py` reads Excel or CSV, previews, applies and undoes. To add a record type, define it in `records.py`, add its register functions, and add a handler for it in `imports.py` (how a row is checked, added, updated, undone and exported). Units and buyers, and buyer payments, are in; try the template at `/imports/templates/units.xlsx`.

### Tally import

`api/lekhara/tally/`: `reader.py` recognises a file and reads XML or JSON into one tree of nodes (and Excel, CSV or ASCII reports into rows); `book.py` turns nodes into ledgers, groups and vouchers with Tally's conventions (YYYYMMDD dates; a debit is a negative AMOUNT marked deemed positive, turned round so debits are positive); `reports.py` reads the Day Book and other reports; `plan.py` works out suppliers, bills and buyer payments and the alerts; `ledgers.py` maps expense ledgers to cost lines, finds the RERA account and landowners, and works out cost incurred and paid, escrow movements and landowner payments; `service.py` stores the upload, reviews, applies and undoes. Sample exports for tests are in `api/tests/tally_samples.py`; add real exports from design partners beside them. Tally files can be up to `LEKHARA_TALLY_UPLOAD_MB` (default 100).

### Project set-up

`api/lekhara/readiness.py` checks, per project, each kind of data the engines work from and returns one item for each: done, partial, stale (accounts older than `STALE_DAYS`, progress older than `PROGRESS_STALE_DAYS`) or missing, what it switches on, and where in the web app it comes in. When a new engine needs a new kind of data, add an item there so builders are told about it. Project details and certified progress are changed through `registers.update_project` and `registers.record_progress`, which validate and write to the change history.

### Workspace export

`api/lekhara/export.py` builds the ZIP behind `GET /organization/export` (owner and finance only, open when read-only): a write-only openpyxl workbook with one sheet per entry in `SHEETS`, the same rows as JSON, every vault file, and a read-me. Each sheet is a model and how its rows are picked out for the firm (`Scope`); all columns are exported except those in `LEFT_OUT`. A new table must go into `SHEETS` or into `NOT_EXPORTED` with the reason; a test fails until it does.

### Document vault

Files are kept on local disk under `LEKHARA_STORAGE_DIR` (default `api/storage`, not committed), addressed by their SHA-256. Uploads are limited to `LEKHARA_MAX_UPLOAD_MB` (default 20). The demo seed writes real PDFs there, so search works on them. Only the owner and finance can share documents outside the company; the demo data room opens at `http://localhost:3000/shared/demo-sarjapur-finance-review` without signing in.

The API uses a local SQLite file unless `LEKHARA_DATABASE_URL` is set. For Postgres:

```bash
docker compose up -d db
cd api && .venv/Scripts/python -m pip install -e ".[dev,postgres]"
export LEKHARA_DATABASE_URL=postgresql+psycopg://lekhara:lekhara@localhost:5432/lekhara
```

## Web

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

The web app reads the API from `LEKHARA_API_URL` (default `http://localhost:8000`). Start the API first, then the web app.

Screens: Today (`/`), Projects, a project's Overview, Escrow, Collections, Handover, Disputes, Documents, Tax and statutory, and Units and landowners tabs, a Withdrawal request, a unit's handover page, a case, a document, a data room, demand letters, and Rules. `/shared/{token}` is the page outsiders see; `/files/{id}` and `/shared/{token}/files/{id}` pass files through from the API.

Every form works without JavaScript: server actions in `src/app/actions.ts` call the API and show its error message in words.

This is Next.js 16 with Cache Components enabled. APIs differ from older versions; read the guides bundled in `web/node_modules/next/dist/docs/` before using a Next.js API. Uncached data must be read inside a `<Suspense>` boundary.

## Database migrations

Schema changes go through Alembic migrations in `api/lekhara/migrations/versions/`. The API brings the schema up to date on start (`LEKHARA_AUTO_MIGRATE`, on by default); `python -m lekhara.migrate` does the same by hand.

After changing a model:

```bash
cd api
.venv/Scripts/python -m lekhara.migrate revision "describe the change"   # autogenerates from the models
```

Review the generated file, then run the tests: `test_migrations.py` fails if the migrated schema and the models disagree.

## Conventions

- **Money** is stored as integer paise and handled as `Decimal` rupees in code. Never use floats for money.
- **The ledger is append-only.** Corrections are new reversing entries, never edits or deletes.
- **Engines are pure.** `lekhara/engines/` holds calculations only; `services.py` loads data and runs them; `views.py` shapes JSON.
- **Rules are data.** Every statutory rate, threshold and deadline lives in the versioned rules pack with its legal basis and source quality, never as a literal in an engine.
- **Design:** minimal and monochrome. No emojis, no icons or symbols in the branding, text wordmark only. State is shown with weight, borders and words, not colour.
- **Commits:** update `status.md` in every commit. Do not add AI co-author trailers.
