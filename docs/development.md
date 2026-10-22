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
.venv/Scripts/python -m pip install --require-hashes -r requirements.txt   # Windows
.venv/Scripts/python -m pip install --no-deps -e .
# .venv/bin/python ... the same on macOS / Linux

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

CRM exports: their column names are aliases in `records.py`; `crm.py` recognises the CRM from a signature set of headers (stored on `ImportBatch.recognised` and shown on the preview), joins first and last names, and blanks the buyer on a unit whose status is not booked. To add a CRM, add its headers to `crm.SOURCES` and any new column names to the record type's aliases.

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

### Security

- **Two-step sign-in** (`two_step.py`): TOTP per RFC 6238 with the standard library; the secret is sealed with `LEKHARA_SECRET_KEY`. `POST /auth/login` answers `{"two_step": true, "ticket": ...}` for someone who has it on, and `POST /auth/login/two-step` exchanges the ticket and a code (or a recovery code) for a session. Invitations accepted by an existing account with two-step on need the code too.
- **Limits per network address** (`auth.LoginThrottle`, in memory per process): `LEKHARA_SIGNUPS_PER_HOUR`, `LEKHARA_RESETS_PER_HOUR`, `LEKHARA_FAILED_LOGINS_PER_ADDRESS`. Run the local servers with them raised for the end-to-end scripts, which sign up many firms from one address.
- **Virus checks** (`scan.py`): set `LEKHARA_CLAMAV_URL=tcp://host:3310` to stream every upload, emailed attachment and connector file to clamd. Unset, nothing is scanned.
- **Dependencies are locked**: `api/requirements.txt` pins every Python package with its hashes (development and Postgres extras included). After changing `pyproject.toml`, regenerate it with `uv pip compile pyproject.toml --extra dev --extra postgres --universal --generate-hashes --python-version 3.12 -o requirements.txt`. Dependabot proposes updates weekly.
- **CI security job**: gitleaks over the whole history (`.gitleaks.toml` allows rules pack keys and the RFC 6238 test secret, which look like secrets and are not), `pip-audit` against the lock, Bandit at medium and above, and `npm audit` on what ships to production. The lint tools carry an advisory in `braces` (through `eslint-config-next`) with no fixed version yet; it never reaches production, so `npm audit` runs with `--omit=dev`.
- **Asking again before sensitive steps** (`auth.require_recent`): a route calls it after its own permission checks. Signing in or `POST /auth/confirm` (password, plus the code if two-step is on) sets `UserSession.confirmed_at`, good for 15 minutes; otherwise the API answers 428, and the web app's `send` sends the person to `/confirm?next=` the page they came from. Staff console actions need it too.
- **Sessions**: each records when and from where it was last used (`auth.touch`), and ends after `LEKHARA_SESSION_IDLE_HOURS` (default 12) unused. `GET /auth/sessions`, `POST /auth/sessions/{id}/end` and `/auth/sessions/end-others`.
- **Alerts** (`alerts.py`): a new browser at sign-in (compared with the person's earlier sign-ins in the access log), a full download, and support opening a workspace.
- **The firm's two-step rule** (`PUT /organization/two-step-rule`, owner only): while it is on, someone without two-step gets 403 with `X-Lekhara-Two-Step: required` on everything but the routes in `TWO_STEP_OPEN`, and the web app sends them to `/secure`.
- **Data room visitors** prove their email with a six-digit code (`services.register_visitor`, `verify_visitor`); a room that asks opens only to a verified visitor.
- **Data room protections**: `watermark.py` marks every page of a PDF served from `/shared/{token}/documents/{id}/file` when `DataRoom.watermark` is on, as a separate Helvetica layer merged over each page with pypdf, so the text underneath is untouched. `DataRoom.terms` must be accepted at the gate (`accept_terms` on `POST /shared/{token}/visitor`, or `POST /shared/{token}/visitor/terms` after a change); `DataRoomVisitor.accepted_terms` keeps the words accepted, and `services.needs_terms` compares them with the room's. `services.room_opened` records an open and emails the room's maker (`DataRoom.notify`) on each visitor's first.
- **Leaked passwords** (`passwords.py`): checked against Have I Been Pwned's range API by a five-character hash prefix wherever a password is set. `LEKHARA_PASSWORD_BREACH_CHECK=0` turns it off; the local servers for the end-to-end scripts run with it off, and the tests replace the service with a stand-in.
- **Passkeys** (`passkeys.py`, WebAuthn through py_webauthn; `@simplewebauthn/browser` in `components/passkey-buttons.tsx`): the site a passkey belongs to is the host of `LEKHARA_WEB_URL`, and pages must be served from that address, so set it to the real address in production (`localhost` works locally). A passkey counts as two-step sign-in (`Principal.two_step_on`). The API tests use a software authenticator (`tests/test_passkeys.py`); in a browser, Chrome's DevTools can add a virtual one.
- **Changing the secret key** (`secretbox.py`): set the new key as `LEKHARA_SECRET_KEY` and the old in `LEKHARA_OLD_SECRET_KEYS`, run `python -m lekhara.secretbox reseal`, then drop the old key. A new sealed column must be added to `secretbox.reseal_all`.
- **The access log is chained** (`legal.record`, `seal_log`, `verify_log`): events are written, then chained right after their commit in a short transaction that first writes the chain's end (`access_log_head`) to take the database's lock. `python -m lekhara.legal verify-log` checks it; the daily job does too and logs an error if it is broken.
- **Limits are shared** (`limits.DatabaseStore`, table `rate_limit_events`): every `LoginThrottle` in the app counts in the database, by bucket and hashed key, so several servers enforce one limit.
- **Backups** (`backup.py`): `python -m lekhara.backup create <folder>` with `LEKHARA_BACKUP_KEY` set (a passphrase kept apart from the servers and backups); `check <file>` opens and verifies one without changing anything; `restore <file> <new folder>` unpacks one to swap in. Postgres backups need `pg_dump` (and `pg_restore` to check). Run `create` daily and keep copies in storage that cannot delete them for a set time; test a restore every quarter.
- **Reporting weaknesses**: `/security` explains the protections in plain words, and `/.well-known/security.txt` names the contact (`LEKHARA_CONTACT_EMAIL`).
- **Stored files are checked nightly** (`integrity.py`, job `files.check`): every file a record names is read and compared with its SHA-256. A new column naming a stored file must be added to `integrity.FILE_COLUMNS` (and to the purge in `legal.purge_firm`).
- **Filing rules** (`filing.py`): applied in `services.store_document` when no kind and no checklist item was chosen; inbound mail passes its own guess as the fallback. The rule found earliest in a document's text (title, file name, then pages) wins.
- **Originals** (`originals.py`): numbers are per firm (`O-0001`); labels are Code 128 barcodes drawn by bwip-js on the server (`components/originals.tsx`), which an ordinary reader types back into the search on the Documents tab (`/originals?n=`).
- **CI actions are pinned** to commit SHAs with the version as a comment; Dependabot proposes new pinned versions.
- **Mail senders are verified** (`inbound.sender_verified`): a team member's or trusted sender's mail is read at once only if the receiving service's own `Authentication-Results` header shows DMARC passing, or DKIM or SPF passing for the From domain. Set `LEKHARA_INBOUND_AUTHSERV_ID` to the name the receiving service writes on that header (for example `amazonses.com`); unset, the topmost header is read, since a sender's own sit below it. Anything else is held for someone to allow.
- **Exports keep text as text** (`sheets.py`): every Excel and CSV writer goes through it, so imported text starting with `=` (or `+`, `-`, `@` in CSV) cannot become a formula in someone's spreadsheet. A new writer must use `sheets.append`, `sheets.as_text` or `sheets.csv_value`.
- **Uploads cannot unpack to gigabytes** (`safe_files.check_zip`): called before every `load_workbook`; add it before any new reader of zip-based files. `defusedxml` is installed, which openpyxl uses by itself.
- **Security headers** (`web/next.config.ts`): a Content Security Policy, frames from this site only (documents open in one), `Referrer-Policy: same-origin` (data room links carry their key), and HSTS. Scripts may be inline because nonces do not work with Partial Prerendering. HSTS and `upgrade-insecure-requests` are on for production builds unless `LEKHARA_HTTPS=0`, which a production build run locally over plain HTTP needs (`LEKHARA_HTTPS=0 npx next build`, then `next start`).
- **The API does not describe itself**: `/docs`, `/redoc` and `/openapi.json` are served only with `LEKHARA_API_DOCS=1`. In production, the API should be reachable from the internet only for the routes outsiders use (`/connector/...`, `/inbound/email`, `/health`); everything else comes from the web app over a private network.
- **Row-level security** (`rls.py`, Postgres only): `migrate.upgrade` puts a policy on every table holding a firm's data after each migration, from the models, so a new table with `organization_id` or `project_id` is covered by itself; a table that is a child of one goes in `rls.CHILDREN`. A signed-in person's session is restricted in `current_principal`; everything else (sign-up, shared links, the forwarding address, the connector, jobs, the seed) is unrestricted. In production, run migrations as the database owner and connect the API as a separate role that is not a superuser (`rls.grant` makes one); superusers and owners skip the policies. To run the tests on Postgres: `LEKHARA_TEST_DATABASE_URL=postgresql+psycopg://user:password@host/db python -m pytest` (it drops and recreates the schema, and creates the role `lekhara_app`).

### Terms, privacy and the access log

`api/lekhara/legal.py` holds the version of the terms, privacy notice and data processing terms (`VERSION`; raise it when the texts change, and everyone is asked to accept again), records acceptances, writes the access log (`record`), deletes a person's account (`anonymise`), and closes a firm (`close_firm`, then the daily `legal.daily` job runs `purge_firm` once `delete_after` has passed). The texts are pages in `web/src/app/legal/`. The company's details on them come from `LEKHARA_COMPANY_NAME`, `LEKHARA_COMPANY_ADDRESS`, `LEKHARA_GRIEVANCE_OFFICER` and `LEKHARA_GRIEVANCE_EMAIL`. The web app passes the person's address and browser to the API in `X-Lekhara-Client-IP` and `X-Lekhara-User-Agent` for the log. When adding a table that holds a firm's data, add it to `_purge_scoped` too, children before parents.

### When something goes wrong

`docs/incident-response.md` is the runbook for a security incident: the deadlines, who acts, the commands and the notices.

### Our admin console

`api/lekhara/staff.py` and `/admin` in the web app. Mark someone as staff with `python -m lekhara.staff add their@email` (`remove`, `list`); they must have signed up, and the console stays closed until they turn on two-step sign-in. Staff requests (`/staff/...`) are deliberately not restricted by row-level security, since the console reads across firms; it shows account facts only. Support sessions (`UserSession.support_org_id`) are made by `auth.start_support_session` only while the firm's `SupportGrant` holds; `current_principal` refuses anything but reads on them and writes `support_view` to the firm's access log for each request. The web app keeps the staff member's own session in `lekhara_staff_session` while they look, and puts it back when they end. Payments recorded here set `Organization.paid_until`; `services.access_state` makes the workspace read-only after it.

### The public website

`web/src/app/(site)/` holds the home page (`/welcome`, which `proxy.ts` shows at `/` to anyone without a session cookie), `/pricing` and `/contact`; the policies are in `web/src/app/legal/` and share the website's header and footer (`components/site.tsx`). Contact details and the price come from the API's public `/legal` info: `LEKHARA_CONTACT_EMAIL`, `LEKHARA_CONTACT_PHONE`, `LEKHARA_PRICE_PER_MONTH` (rupees before GST; unset, the pricing page says the price is being set) and `LEKHARA_MONTHS_CHARGED_PER_YEAR` (default 10). A new public route needs adding to `OPEN` in `proxy.ts`.

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

`api/lekhara/bank/`: `reader.py` finds the table of transactions in any bank's export (XLSX via openpyxl, old XLS via xlrd, CSV or text with the delimiter sniffed, HTML tables) by recognising column names (`column_role`), and reads lines, the account, the period and the opening balance; each line gets a key that is the same in any download covering it. `narration.py` reads the payer, the channel, the UTR, and whether a line is interest, a charge, a return or a home-loan disbursement. `plan.py` decides what each line becomes for the account's role (collections or rera), matches buyers, pairs returns, recognises money already in Lekhara, and raises alerts. `service.py` stores the upload and applies or undoes it; `BankAccount` and `BankPayer` remember the builder's choices. `rules.py` keeps the firm's bank rules (`BankRule`, per project or for every project); `service.context` hands them to the plan as `RuleRef`s in order, and `make_plan` lets the first that fits decide a line after the line's own choice and before remembered payers. The word matching is shared with filing rules in `lekhara/matching.py`. Sample statements in each bank's layout are in `api/tests/bank_samples.py`; add real ones from design partners beside them.

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

Forms are server actions. What each does is in `src/app/form-handlers.ts` (call the API, return `{error}`, `{ok}` or redirect); `src/app/actions.ts` exports each one wrapped by `settled` (`src/lib/settle.ts`), so a new handler needs its line there too. Forms are drawn with `ActionForm`, which shows the result in words.

A form sent before the page's scripts have loaded is posted as it is, and Next answers an action with the page resumed from its prerendered shell, which cannot carry the result. So `settled` keeps the result in a cookie for a minute and redirects back to the page; `proxy.ts` hands it to that page once as a request header, and `ActionForm` shows it on the form that was sent (told apart by its action, what is bound to it, its button and its place on the page). Called by the page's own scripts (the `Next-Action` header), nothing changes.

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
