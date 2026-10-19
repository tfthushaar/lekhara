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

Record types are defined once in `api/lekhara/records.py` (fields, aliases, parsing); `registers.py` adds, changes and deletes records with a change history; `imports.py` reads Excel or CSV, previews, applies and undoes. To add a record type, define it in `records.py`, add its register functions, and add a handler for it in `imports.py` (how a row is checked, added, updated, undone and exported). Units and buyers, buyer payments, suppliers, bills, orders, landowner payments, approvals and K-RERA filings are in; try the template at `/imports/templates/units.xlsx`.

Editing as a table (`/projects/{id}/table/{kind}`) shows a page of a record type's export rows as inputs and turns the submitted rows into an import batch with `origin` table (`imports.start_rows`), so the change goes through the same preview, apply and undo, and the history records the source as `edited`. Only types an import can update are offered (`imports.EDITABLE_AS_TABLE`); the columns that identify a row are locked (`record_views.LOCKED`).

Debit notes (`plan._net_debit_notes`) reduce the bill they reference before payments are tied to it (`_settle` leaves debit notes out); the service updates a bill already brought in and records its earlier figures in the result as `bills_changed`, which undo restores. Sales vouchers are matched to Lekhara's demands (`plan._sales`, with the demands passed in `Context.demands`); demands with no voucher are reported only when at least one sales voucher matched a demand.

A data room that asks who is visiting (`DataRoom.ask_visitor`) shows nothing until `POST /shared/{token}/visitor` records a `DataRoomVisitor`; the web keeps the returned token in a cookie scoped to that room's link and passes it to the API as `X-Lekhara-Visitor`.

### Onboarding

`api/lekhara/krera_certificate.py` reads a Form C registration certificate's text (`POST /projects/from-certificate`); the web opens the new-project form with what it found. `accounts.gstin_facts` gives a GSTIN's state, PAN and constitution. Pages that would show zeros before data is in ask the set-up checklist (`readiness.py`, `/projects/{id}/setup`) through `web/src/components/needs.tsx`. The firm's `created_on` is passed to the obligations engine as `known_from`: filings due before it are asked about once (`krera:unrecorded`) rather than counted late, and `POST /projects/{id}/filings/earlier` records them all as filed on their due dates.

### Approvals, filings and landowner payments

`api/lekhara/statutory.py` holds approvals (with their status: to apply, applied, granted, lapsing within `approvals.renewal_notice_days`, lapsed) and K-RERA filings (a quarterly report covers a quarter end, an annual audit a 31 March). Landowner payments are in `registers.py`; their history is logged under the landowner, so the landowner's page keeps deleted payments too. `record_views.py` builds the landowner, approvals, K-RERA and table views. Lapsing approvals reach Today through `services.lapsing_approvals` and the obligations engine.

### Tally import

`api/lekhara/tally/`: `reader.py` recognises a file and reads XML or JSON into one tree of nodes (and Excel, CSV or ASCII reports into rows); `book.py` turns nodes into ledgers, groups and vouchers with Tally's conventions (YYYYMMDD dates; a debit is a negative AMOUNT marked deemed positive, turned round so debits are positive); `reports.py` reads the Day Book and other reports; `plan.py` works out suppliers, bills and buyer payments and the alerts; `ledgers.py` maps expense ledgers to cost lines, finds the RERA account and landowners, and works out cost incurred and paid, escrow movements and landowner payments; `service.py` stores the upload, reviews, applies and undoes. Sample exports for tests are in `api/tests/tally_samples.py`; add real exports from design partners beside them. Tally files can be up to `LEKHARA_TALLY_UPLOAD_MB` (default 100).

### Handing over and cancelled bookings

`api/lekhara/handover_desk.py` holds the possession letter (`/units/{id}/possession-letter`), the association checklist (`ASSOCIATION_ITEMS`, stored as `HandoverItem`; the first and last items are the project's `association_formed_on` and `common_areas_conveyed_on`), and `cancel_booking`. A cancellation is a `BookingCancellation`; the unit's demands and receipts get its `cancellation_id`, so collections and handover count only rows without one, the 70% check in the collections engine gets every payment (`all_payments`), and a case counts the payments of the booking it cancelled (`services._case_inputs`).

### Packs

`api/lekhara/packs.py` builds the withdrawal pack for the escrow bank, the quarterly progress report and the annual audit pack as a `Pack` of headed sections of figures, written as a PDF by `to_pdf` or as an Excel workbook by `to_xlsx`, so the two always agree. Routes: `/withdrawals/{id}/pack.pdf` and `/projects/{id}/packs/{qpr|audit}/{period end}.{pdf|xlsx}`. The PDF writer in `pdf.py` takes lines; a line starting with `## ` is a bold heading, one starting with `|| ` is fixed-width (for figures that line up), and a line that is exactly `\f` starts a new page. Historical figures come from `services._money` and `services._escrow` at the period's end, not a full snapshot, so older periods do not need every rule to have been in force.

### Terms, privacy and the access log

`api/lekhara/legal.py` holds the version of the terms, privacy notice and data processing terms (`VERSION`; raise it when the texts change, and everyone is asked to accept again), records acceptances, writes the access log (`record`), deletes a person's account (`anonymise`), and closes a firm (`close_firm`, then the daily `legal.daily` job runs `purge_firm` once `delete_after` has passed). The texts are pages in `web/src/app/legal/`. The company's details on them come from `LEKHARA_COMPANY_NAME`, `LEKHARA_COMPANY_ADDRESS`, `LEKHARA_GRIEVANCE_OFFICER` and `LEKHARA_GRIEVANCE_EMAIL`. The web app passes the person's address and browser to the API in `X-Lekhara-Client-IP` and `X-Lekhara-User-Agent` for the log. When adding a table that holds a firm's data, add it to `_purge_scoped` too, children before parents.

### The forwarding address and background jobs

`api/lekhara/inbound.py` gives each project an address (`<mail_token>@LEKHARA_INBOUND_DOMAIN`), keeps each email (`InboundMessage`) and file (`InboundItem`), decides whether the sender is trusted (the firm's team, `TrustedSender` rows, and the mail service's Authentication-Results), and routes each file to the Tally import, the bank statement import, an Import centre preview or the document vault. Mail arrives at `POST /inbound/email` (raw MIME, a form field `email`/`body-mime`/`raw`, or JSON `{raw: base64, to: [...]}`, with the header `X-Lekhara-Inbound-Secret` or `?secret=` matching `LEKHARA_INBOUND_SECRET`), or from a mailbox polled every two minutes when `LEKHARA_INBOUND_IMAP_URL` is set. To try it locally, start the API with `LEKHARA_INBOUND_SECRET=...` and post an `.eml` file with curl.

`api/lekhara/jobs.py` is the job queue: `enqueue`, `@handler(kind)`, `every(kind, seconds)` for periodic work, and `run_pending`, which the API runs in a worker thread (`LEKHARA_WORKER=0` turns it off; `python -m lekhara.jobs` runs it on its own). Tests call `run_pending` directly.

Statement passwords are sealed with `LEKHARA_SECRET_KEY` (`lekhara/secretbox.py`); set it in production, and keep it, or the stored passwords cannot be opened. PDF statements are read by `lekhara/bank/pdf.py`.

### The Lekhara Connector for Tally

`connector/lekhara_connector.py` is the program for the builder's Tally computer (standard library only; `connector/build.ps1` packages it with PyInstaller; `connector/README.md` is for the builder). It asks TallyPrime's XML server for "List of Accounts" (all masters) and the "Day Book" for a date range, and posts them to `POST /connector/tally` with its key in `X-Lekhara-Connector`. `api/lekhara/connectors.py` links a computer (`POST /projects/{id}/connectors` makes a one-time code; `POST /connector/link` exchanges it for the key), keeps the latest masters, combines them with the vouchers under one root, skips a sync identical to the last, and runs the Tally import and applies it. `tests/test_connector.py` runs the real program against the API with a stand-in Tally; to try it by hand, start the API and run `python connector/lekhara_connector.py link CODE --server http://localhost:8000 --tally http://localhost:9000`.

### GSTR-2B

`api/lekhara/gst/`: `reader.py` reads GSTR-2B JSON (by key, wherever it sits: `ctin`, `trdnm`, `inv` with `inum`, `dt`, `txval`, `igst`/`cgst`/`sgst`/`cess`, `itcavl`, `rev`; notes under `nt`), GSTR-2A JSON (item details `itm_det`), and the GSTR-2B Excel (B2B and CDNR sheets, two-row headers, matched by column meaning). `plan.py` matches invoices to bills by supplier GSTIN or name and `fold_number`, and lists agreements, differences, missing bills, unreported bills for the return's month and GSTIN updates; `service.py` uploads, applies (bills get `source_ref` `gstr2b:<gstin>:<number>`) and undoes. Samples are in `api/tests/gst_samples.py`.

### The review queue

`api/lekhara/review.py` gathers, for the projects a person can import into, everything that waits for a choice: bank statements without an account or with payments to place (statements from the last `RECENT_DAYS` are re-planned from their cached files), Tally imports and Import centre batches not yet applied, held emails and inbound files that could not be read. `GET /review` lists them; `/today` carries the count as `to_review`. When a new import waits for a choice, add it here so it never goes unseen.

### Suppliers, bills and commitments

`api/lekhara/purchases.py` adds, changes and deletes suppliers (firm-wide), bills and commitments (per project) with a change history; `imports.py` has a handler for each. Records that carry money into the append-only ledger (a bill with a cost line, a commitment) go through `sync_ledger`, which adds the entries that bring the ledger to the record's current figures under a reference prefix (`bill:<id>:`, `commitment:<id>:`), so edits and deletes never rewrite history.

### Bank statements

`api/lekhara/bank/`: `reader.py` finds the table of transactions in any bank's export (XLSX via openpyxl, old XLS via xlrd, CSV or text with the delimiter sniffed, HTML tables) by recognising column names (`column_role`), and reads lines, the account, the period and the opening balance; each line gets a key that is the same in any download covering it. `narration.py` reads the payer, the channel, the UTR, and whether a line is interest, a charge, a return or a home-loan disbursement. `plan.py` decides what each line becomes for the account's role (collections or rera), matches buyers, pairs returns, recognises money already in Lekhara, and raises alerts. `service.py` stores the upload and applies or undoes it; `BankAccount` and `BankPayer` remember the builder's choices. Sample statements in each bank's layout are in `api/tests/bank_samples.py`; add real ones from design partners beside them.

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
