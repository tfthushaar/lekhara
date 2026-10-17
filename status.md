# Lekhara status

Last updated: 2026-10-17, with the commit "Add the Import centre for units and buyers".

## What we are building

Lekhara is an owner-side platform for Karnataka builders, in two layers:

1. **Only in Lekhara:** everything outside the ERP. What a project owes, and is owed by, K-RERA, the escrow bank and its certifiers, the tax department, landowners, buyers' home-loan banks, lenders, authorities, buyers in disputes, the sub-registrar and the residents' association. Escrow certification, K-RERA, real-estate tax, JDA landowners, registration and handover, disputes, home-loan disbursements, plotted layouts, guarantees and insurance, approval conditions, workspaces for certifiers, lenders and landowners, India-native feasibility, delay prediction.
2. **Also in Lekhara, done better:** the inside modules a builder needs if they have no ERP or CRM. Sales and bookings, collections, channel partners, agreements and e-stamping, a buyer portal, payables on WhatsApp, contractor billing, procurement, an approvals tracker, site progress from photos, snags and defects, title due diligence, notices, estimation, a document vault, board packs. Each can run in coexist mode, reading from the customer's own tool instead.

Lekhara connects read-only, reads documents with AI from several providers (with an India-only option), keeps two ledgers (obligations and money), and prepares every filing, certificate and pack before it is due. People sign; Lekhara prepares.

Lekhara is sold as a self-serve monthly SaaS: one subscription per builder firm, covering all its projects and people, after a one-month free trial, paid through Razorpay. A builder signs up and uses it on their own data the same day, without our help. Every record can be imported from a file, fed from a connected source, or typed and edited in Lekhara, and everything can be exported at any time.

Launch market: Bengaluru, then the rest of Karnataka, then other states. The full plan is v7.1 (kept outside the repository).

## Done

- Repository set up: customer-facing README, developer guide, CI for API and web.
- API skeleton (Python, FastAPI) with a health check and tests.
- Web app shell (Next.js 16) with the Lekhara text wordmark and the monochrome design system.
- Karnataka rules pack v1: 53 rates, thresholds and deadlines as dated data, each with its legal basis, source quality and what to confirm it against. Lekhara settings are marked as settings, not law.
- Money truth engine: cost lines, ledger stages (committed, incurred, paid, retention, advances), anticipated final cost, cost to complete, contingency, land and development totals for RERA, point-in-time positions, and alerts for overruns, low contingency and spending ahead of certified progress.
- Escrow and certification engine: drawable amount (limited by cost incurred and paid, or by the account balance, whichever is lower), 70% deposit check, the ongoing-project deposit rule, next certificate cycle, drafts of the architect's, engineer's and CA's certificates prepared from the books, and the checks a bank or K-RERA auditor would run.
- Real-estate tax engine: the 80% registered-supplier meter, GST on development rights at completion, the s.43CA guidance-value check, s.194-IC landowner TDS, the MSME 45-day clock, BOCW labour cess and delay interest owed to buyers.
- Obligations engine: one dated, plain-language list per project of what is owed, to whom, by when and what is at stake, most urgent first. Every amount carries a label, and only real exposures count as money at stake.
- Database models (SQLite locally, Postgres-ready) with money stored as exact paise, and an append-only ledger and escrow account.
- HTTP API: Today, projects, money, escrow, tax, units and the rules pack; the full withdrawal workflow with its checks enforced.
- Demo data: a fictional developer with three Bengaluru projects, dated relative to today.
- JDA basics: every unit is marked as the developer's or the landowner's; landowners carry their share, deposit and payments, with the TDS check.
- Web app: Today, Projects, a project's Overview, Escrow, Collections, Handover, Disputes, Documents, Tax and statutory, and Units and landowners tabs, the Withdrawal request, a unit's handover page, a case page, a document page, a data room page, the shared data room page for outsiders, demand letters and Rules. Every form works without JavaScript. Pages use the full width of the window, with a 40px margin (16px on phones); paragraphs and label-and-figure lists keep a reading width.
- Database migrations (Alembic, inside the package). The API brings the schema up to date on start; the demo seed builds the schema through migrations; a test fails if the migrated schema and the models ever disagree.
- Sign-in, organisations, roles and certifier seats:
  - Email and password sign-in (scrypt-hashed passwords, hashed session tokens, 14-day sessions, sign-out, throttling of repeated failed attempts).
  - The developer's team: owner, finance, accounts, viewer. Owner, finance and accounts start withdrawals and send them to the bank; only owner and finance record what the bank did.
  - Certifier seats: the architect, engineer and CA see only the projects they certify, change and sign only their own certificate (signed under their own name and firm), and get a Today list of certificates waiting for them.
  - Every withdrawal records who started, signed, sent and released it.
  - Web: a sign-in page (with one-click demo accounts in demo mode), a user menu with sign-out, screens and buttons that follow each person's permissions. Tested end to end with six separate people.
- Collections (the first "also in Lekhara, done better" module):
  - A payment plan per project: booking, agreement, certified-progress stages and possession.
  - Demands ready to raise appear the moment the architect's certificate reaches a stage, on Today and on the project's Collections tab; one click raises them for every booked unit, with GST.
  - Buyers' payments are matched to their demands in order (TDS a buyer deducts counts as paid); overdue instalments and the interest on them, at the same rate the promoter owes on delay (marked to confirm).
  - A month-end check that 70% of everything buyers paid was in the RERA account.
  - A printable demand letter per demand, with the instalment, GST, due date and the buyer's TDS note.
- Registration and handover desk:
  - The occupancy certificate is recorded per project; until it is in, every unit waits for it, and the possession instalment becomes ready to raise only once it is.
  - Every booked unit moves through the same steps: occupancy certificate, final e-Khata (needed for registration in Bengaluru since July 2025), final demand, paid in full, sale deed drafted, appointment, registered, possession. Each unit waits at the first step not done.
  - A Handover tab: units registered and handed over, money still owed by buyers whose deed is not registered, where units are held up, and the units grouped by what to do next.
  - A page per unit: the steps, a form for the next step (e-Khata, deed drafted, appointment, registration with its document number, possession), corrections, a printable sale deed fact sheet for the lawyer and an estimate of the buyer's stamp duty, cess and registration fee (rates marked to confirm).
  - On Today: units not yet registered and the money waiting on them, and the date by which the common areas are due to go to the association (three months after the occupancy certificate under RERA where no local law says otherwise; marked to confirm for Karnataka).
  - Tested end to end: one unit taken from a drafted deed to possession, an e-Khata recorded on another, certifiers kept out.
- Disputes and orders desk:
  - One register of every case: K-RERA, its adjudicating officer and Appellate Tribunal, the district, state and national consumer commissions, the High Court and civil courts.
  - What each case could cost, worked out from what the buyer actually paid: a refund with interest from each payment, or interest for the delay from the promised possession date (or the payment, if later), at the delay-interest rate; otherwise the amount claimed.
  - Orders: refunds and interest are worked out to the day and stop growing once paid in full; fixed sums for compensation, costs and penalties. The date to comply by, and the last day to appeal with the deposit an appeal needs first (K-RERA to the Tribunal in 60 days with the full amount owed to the buyer, or 30% of a penalty; consumer appeals in 45 or 30 days with half the amount; all marked to confirm).
  - Hearings, payments under orders (append-only) and settlements, with what a settlement saves against the order or the estimate. Cases close themselves when an order is paid or a settlement is paid in full.
  - Patterns: how many complaints came after the promised possession date, how many booked units have a case, and cases by relief and forum.
  - On Today: replies due, hearings in the next 30 days, orders to pay (past their date shown as overdue, with the K-RERA recovery warning), the last day to appeal and settlements to pay. Each opens its case.
  - Tested end to end: a new case recorded against a unit and taken through a hearing, an order and payment; a settlement agreed on another; certifiers kept out.
- Document vault and data rooms (the second "also in Lekhara, done better" module):
  - Upload PDFs, Word and Excel files, photos and text files up to 20 MB, each filed against the project and, where it belongs, a unit, a case or a withdrawal. The file type is checked against its contents; the same file is never stored twice.
  - Versions: a new version replaces the old one everywhere it counts, and every version is kept. Archiving keeps the file but takes it out of the checklist, search and data rooms.
  - Search with citations: the text of every PDF page is read on upload, and a search shows each match with the words around it and the page it is on.
  - A checklist of what banks, K-RERA and buyers ask for (K-RERA registration, title, encumbrance, JDA, plan sanction, commencement, environmental clearance, fire NOC, designated account letter, insurance, occupancy certificate), each with why it matters; items can be marked not needed, with a reason. Per-record checks for registered sale deeds, final e-Khata, order copies and the signed certificates behind each released withdrawal.
  - Expiry: approvals and policies show on Today 60 days before they lapse, and as overdue once they have.
  - Data rooms: the owner or finance shares chosen documents with a lender or investor through a link that closes on a chosen date (up to 90 days), can be replaced or closed at any time, and is shown only once (Lekhara keeps only a fingerprint of it). Outsiders open it without signing in; every opening and download is recorded.
  - Documents sections on each case and unit page. Demo files are generated as real PDFs so search works on them.
  - Tested end to end: a missing title deed filed from the checklist and found by searching its text, a new version of a fire NOC, a data room made, opened and downloaded from by an outsider, then closed; certifiers kept out.
- Self-serve start (the first part of the self-serve foundation):
  - Sign-up for a builder firm: name, firm, email and password. The firm's workspace and its one-month free trial start at once; no card is needed.
  - Each firm's data is kept apart: a project, and everything filed under it, is visible only to the firm's team and to the certifiers invited to it. Tested across every project screen, case filing and upload.
  - Sample projects: the three demo projects are a read-only sample every signed-in person can explore; nothing in them can be changed by anyone outside the sample firm.
  - Adding a project from its K-RERA registration (name, number, dates, locality, land structure, GST regime, escrow bank).
  - Email confirmation, forgotten-password reset (signs out every other session) and resending the confirmation. Emails are kept in an outbox and sent over SMTP when one is set up; until then they are written to the log.
  - Settings: the firm's name, legal name and GSTIN (checked, with its state); the team and their roles; certifiers and their projects; invitations by email that also give the inviter a link to send on WhatsApp. Owner and finance invite; only an owner changes roles or removes people; the firm always keeps an owner.
  - Accepting an invitation creates the account (or signs in an existing one) and joins the firm, or the chosen projects for an architect, engineer or CA.
  - After the free month, an unpaid workspace becomes read-only: everything can still be seen and exported, nothing can be added or changed. Banners show the days left, the read-only state and an unconfirmed email.
  - A welcome on Today for a firm with no projects yet: add a project, explore the samples, invite the team.
  - Tested end to end: sign up, add a project, explore a sample, invite a colleague who accepts, confirm the email, reset a forgotten password.
- Import centre and the units register (the first records that come in three ways):
  - One definition per record type drives the add and edit forms, the template, the import and the export, so the four always agree.
  - Import from Excel (.xlsx) or CSV: title rows above the column names are skipped; columns are matched by name and common aliases (Flat No, Customer Name, Sale Value and so on) and can be corrected before anything is saved; the mapping is remembered for the next file with the same columns.
  - Cells are read the way builders write them: 1,20,00,000, 1.2 crore, 95 lakh, Rs. 95,00,000/-; dates day first in any common form.
  - A preview of every row before anything changes: new, changed (field by field), already the same, or left out with the reason in plain words (a missing carpet area, a sold unit without its booking date, a unit twice in the file).
  - Safe to repeat: units are matched on their number, the same file twice changes nothing, and blank cells never erase what is there. An applied import can be undone for 30 days, unless its units have changed since.
  - Templates (Excel with a sheet explaining each column, and CSV) and exports in the same layout, so data can go out and come back; tested as a round trip.
  - Units by hand: add, change, mark a cancelled booking unsold, delete one entered by mistake (refused once demands, payments, a handover record, a dispute or documents depend on it). Buyer phone and email are kept for reminders.
  - A history of every change to a unit: who, when, whether typed, imported or undone, and each field before and after.
  - The unit page works for every unit, sold or not; the handover steps appear once it is sold.
  - Tested end to end: a new firm imports its sales sheet, reviews the preview, applies it, edits a unit, exports, is refused an undo after the edit, adds and deletes a unit.

## In progress

- Payment plans and buyer payments: edit the plan from templates, import receipts and bank statements.

## Left

### v1: self-serve and pilot-ready (two founders)

In this order:

- Self-serve start, still to do: sign-in with Google and by phone code, limits on sign-ups and resets per network address, and row-level security in Postgres as a second wall between firms when production moves to Postgres.
- Add, edit, import and export for the remaining records that today come only from the demo data: payment plans, receipts, cost lines, budgets, commitments, bills, vendors, landowners and their payments, approvals, filings, and editing a project's own details; spreadsheet-style bulk editing; change history for each.
- Import centre, still to do: bank statements and known CRM export formats, templates in Kannada, AI column mapping for unfamiliar sheets, and the founder's existing Tally file import module (details to come).
- A full workspace export (Excel, JSON and every document) at any time.
- Onboarding: the firm from its GSTIN, projects from the K-RERA certificate, a completeness meter per project, engines that work with partial data and say what is missing, a sample workspace, first-run help.
- Billing: one Razorpay subscription per firm (UPI AutoPay, card, e-NACH), GST invoices, reminders before the trial ends and when a payment fails, a grace period, then read-only with export always open. Prices to be set.
- A forwarding address per workspace for bills, notices and statements; a background job queue; S3-compatible file storage.
- A review queue for anything imported or read by AI with doubt.
- Multi-provider AI gateway (Claude, OpenAI, Gemini, Sarvam, self-hosted) with an India-only mode; document reading; obligation extraction; history backfill; Ask.
- Collections, next steps: reminders through the team's own WhatsApp or email.
- Registration and handover, next steps: recording the occupancy certificate and the conveyance from the web, possession letters, the association handover checklist.
- Disputes, next steps: reading complaints and orders with AI, reply outlines for the lawyer, cancelling the unit when a refund is paid.
- Document vault, next steps: reading scans and filing documents by themselves, an optional name and email gate for data room visitors.
- Bank withdrawal pack (PDF); quarterly progress report and annual audit packs.
- Form errors shown without JavaScript too (today the browser's own checks catch most cases; the server's message appears once the page has loaded its scripts).

### v2

- Home-loan disbursements, guarantees and insurance, approval conditions and environmental reports, vendor check.
- Certifier practice workspace.
- Buyer portal, payables on WhatsApp, contractor billing, approvals tracker, notices.
- Mailbox connection (read-only) and documents sent on WhatsApp.
- Kannada voice, the Monday briefing, back-office agents.

### v3

- Plotted layouts, lender and independent-engineer workspace, landowner view, market intelligence, delay prediction.
- Sales and bookings, channel partners, agreements and e-execution, site progress verification, snags and defects, board packs.
- Other Karnataka cities.

### v4

- Feasibility and land-deal underwriting, procurement, title due diligence, estimation from drawings, Lekhara Lite, other states.

## Decisions taken

- The product is called Lekhara (renamed from Horus on 2026-10-17), in the code as well as the copy: the Python package, `LEKHARA_` settings, the session cookie and the demo accounts. The GitHub repository was renamed too: github.com/tfthushaar/lekhara.
- Plan v7.1 on 2026-10-17 ("continue building"): Lekhara is a self-serve monthly SaaS, and the self-serve foundation comes first in v1.
- Pricing: one subscription per builder firm, not per project; the amounts are to be decided.
- A one-month free trial on the firm's own data.
- Payments through Razorpay.
- Every record can be imported, exported, and added or edited in Lekhara; typing is a first-class path, not a fallback.
- Flagship: escrow withdrawal certification.
- Two layers: features only Lekhara has, plus standard modules done better, each able to coexist with the customer's own tools.
- Stack: Python and FastAPI for the API, Next.js for the web, Postgres in production (SQLite for local development).
- AI: several providers behind one gateway, chosen per task by measured accuracy, cost and residency; never a single provider.
- Tally data: through the founder's existing Tally file import module, not the Tally API.
- Team: two founders through v1; a seed raise after three paying customers funds the team for v2 onwards.
- Design: minimal, monochrome, no emojis, no symbols in the branding, text wordmark only.

## Working assumptions (change any time)

- India-only AI processing is the default for every customer.
- No payment details are asked for to start the free month.
- The second segment after developers is certifier firms.
- Land records and court data come from licensed partners, not our own collection.
