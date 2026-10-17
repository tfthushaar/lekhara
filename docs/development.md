# Developing Horus

This guide is for the people building Horus. The customer-facing product description is in the [README](../README.md); progress is tracked in [status.md](../status.md).

## Layout

```
api/    Python 3.12, FastAPI. Rules pack, engines, database, HTTP API.
web/    Next.js 16 (App Router, TypeScript). The Horus web app.
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
.venv/Scripts/python -m horus.migrate               # bring the schema up to date
.venv/Scripts/python -m horus.seed                  # load demo data (resets the database)
.venv/Scripts/python -m uvicorn horus.app:app --reload   # http://localhost:8000
```

The demo data is a fictional developer with three Bengaluru projects, dated relative to today. Set `HORUS_TODAY=2026-10-17` to pin the date.

Sign-in is required for everything except `/health` and `/rules`. Run the API with `HORUS_DEMO=1` to list the demo accounts on the sign-in screen; every demo account uses the password `horus-demo`:

| Email | Role |
|---|---|
| promoter@demo.horus | Owner |
| cfo@demo.horus | Finance |
| accounts@demo.horus | Accounts |
| architect@demo.horus | Architect on every project |
| engineer@demo.horus | Engineer on every project |
| ca@demo.horus | Chartered accountant on every project |

Who may do what: the owner, finance and accounts start withdrawals and send them to the bank; only the owner and finance record a release or rejection; each certifier changes and signs only their own certificate, and sees only the projects they certify (escrow and money, not tax or units).

Main endpoints: `/today`, `/projects`, `/projects/{id}` (with `/money`, `/escrow`, `/tax`, `/units`), `/withdrawals/{id}` (with `/certificates/{role}`, `/certificates/{role}/sign`, `/submit`, `/release`, `/reject`) and `/rules`. Interactive docs are at `/docs` while the server runs.

The API uses a local SQLite file unless `HORUS_DATABASE_URL` is set. For Postgres:

```bash
docker compose up -d db
cd api && .venv/Scripts/python -m pip install -e ".[dev,postgres]"
export HORUS_DATABASE_URL=postgresql+psycopg://horus:horus@localhost:5432/horus
```

## Web

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

The web app reads the API from `HORUS_API_URL` (default `http://localhost:8000`). Start the API first, then the web app.

Screens: Today (`/`), Projects, a project's Overview, Escrow, Tax and statutory, and Units and landowners tabs, a Withdrawal request, and Rules.

Every form works without JavaScript: server actions in `src/app/actions.ts` call the API and show its error message in words.

This is Next.js 16 with Cache Components enabled. APIs differ from older versions; read the guides bundled in `web/node_modules/next/dist/docs/` before using a Next.js API. Uncached data must be read inside a `<Suspense>` boundary.

## Database migrations

Schema changes go through Alembic migrations in `api/horus/migrations/versions/`. The API brings the schema up to date on start (`HORUS_AUTO_MIGRATE`, on by default); `python -m horus.migrate` does the same by hand.

After changing a model:

```bash
cd api
.venv/Scripts/python -m horus.migrate revision "describe the change"   # autogenerates from the models
```

Review the generated file, then run the tests: `test_migrations.py` fails if the migrated schema and the models disagree.

## Conventions

- **Money** is stored as integer paise and handled as `Decimal` rupees in code. Never use floats for money.
- **The ledger is append-only.** Corrections are new reversing entries, never edits or deletes.
- **Engines are pure.** `horus/engines/` holds calculations only; `services.py` loads data and runs them; `views.py` shapes JSON.
- **Rules are data.** Every statutory rate, threshold and deadline lives in the versioned rules pack with its legal basis and source quality, never as a literal in an engine.
- **Design:** minimal and monochrome. No emojis, no icons or symbols in the branding, text wordmark only. State is shown with weight, borders and words, not colour.
- **Commits:** update `status.md` in every commit. Do not add AI co-author trailers.
