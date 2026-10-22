# Lekhara status

Last updated: 2026-10-23, with the commit "Keep files in S3 in production, encrypted and checked on upload".

## What we are building

Lekhara is an owner-side platform for Karnataka builders, in two layers:

1. **Only in Lekhara:** everything outside the ERP. What a project owes, and is owed by, K-RERA, the escrow bank and its certifiers, the tax department, landowners, buyers' home-loan banks, lenders, authorities, buyers in disputes, the sub-registrar and the residents' association. Escrow certification, K-RERA, real-estate tax, JDA landowners, registration and handover, disputes, home-loan disbursements, plotted layouts, guarantees and insurance, approval conditions, workspaces for certifiers, lenders and landowners, India-native feasibility, delay prediction.
2. **Also in Lekhara, done better:** the inside modules a builder needs if they have no ERP or CRM. Sales and bookings, collections, channel partners, agreements and e-stamping, a buyer portal, payables on WhatsApp, contractor billing, procurement, an approvals tracker, site progress from photos, snags and defects, title due diligence, notices, estimation, a document vault, board packs. Each can run in coexist mode, reading from the customer's own tool instead.

Lekhara connects read-only, reads documents with AI from several providers (with an India-only option), keeps two ledgers (obligations and money), and prepares every filing, certificate and pack before it is due. People sign; Lekhara prepares.

Lekhara is sold as a self-serve monthly SaaS: one subscription per builder firm, covering all its projects and people, after a one-month free trial, paid through Razorpay. A builder signs up and uses it on their own data the same day, without our help. Every record can be imported from a file, fed from a connected source, or typed and edited in Lekhara, and everything can be exported at any time.

Launch market: Bengaluru, then the rest of Karnataka, then other states. The plan, a description of what Lekhara is and does, and the list of decisions still to make, each with its options and sources, are kept outside the repository.

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
- Tally import, built from scratch (first part):
  - Reads every kind of Tally export: XML (masters and vouchers, UTF-16 or UTF-8, including the control characters Tally writes before reserved group names), JSON from TallyPrime 7, and Excel, CSV or ASCII reports (Day Book, Ledger Vouchers, Trial Balance, lists of ledgers, and sheets with one row per ledger line). PDF, HTML, pictures and old .xls files are refused with the steps to export XML or Excel instead.
  - Builds one book from any of them: groups, ledgers (classified by walking up to Tally's reserved groups, with builders' own groups such as Site Expenses or Work in Progress taken as project cost), cost centres, voucher types (custom ones traced to their base type), and vouchers with every ledger line as a debit or credit, bill-wise references, bank details (cheque, UTR), cost-centre splits, GST rates and stock lines, including invoice-mode purchases where the purchase ledger sits inside the stock line.
  - Fills in suppliers from Sundry Creditors (GSTIN, registration type, PAN, state, MSME category and Udyam number, from either the older or the newer TallyPrime layout); suppliers' bills from purchases and from journals that book contractors' bills (invoice number and date, taxable value, GST, cement, and the date paid from bill-wise payments); and buyers' payments from receipts, matched to units by unit number or buyer name, with the TDS the buyer deducted.
  - Alerts, each naming what it affects and how to fix it in Tally or Lekhara: ledger masters or vouchers missing from the file, a report with totals only, the period the vouchers cover, vouchers that do not add up, cancelled or optional vouchers left out, cost centres in use; suppliers without a GSTIN or MSME details, bills without the supplier's invoice number, bills that cannot be tied to payments because bill-wise details are off; buyers that cannot be matched to a unit (their payments wait until matched, and the choice is remembered).
  - A review page: what the file holds, what will come in, the alerts, the builder's choices (a cost centre for this project, a unit for each unmatched buyer), a look at the suppliers, bills and payments, then bring it in. Safe to repeat: vouchers are matched on their Tally identity, so the same export twice adds nothing. Undo within 30 days.
  - Built to Tally's documented structure and tested on sample exports in that structure; to be tested against real exports from design partners.
  - Tested end to end: a PDF refused with steps, an XML export reviewed with its alerts, a buyer matched by hand, everything brought in and shown in collections, the same file again adding nothing, a Day Book report read with its limits named, and an undo.
- Tally import, second part: cost, the RERA account and landowners.
  - Cost lines for any project: set up in one step from the standard list for a Karnataka residential project (land, approvals, civil and structure, MEP, finishes, external works, consultants, finance, marketing, overheads, contingency), then added to, renamed, budgeted (amounts like 45 crore are understood) or deleted while nothing is recorded against them. A Cost lines and budget page, linked from the Overview.
  - Landowners added and changed on the Units and landowners tab, with their share and PAN.
  - Each expense ledger in Tally is matched to a cost line, suggested from its name (cement and steel to civil works, lifts to MEP, sanction fees to approvals, architects to consultants) and confirmed or changed once; Lekhara remembers the choice. Ledgers can be set aside as not project cost.
  - Cost incurred: every debit to a matched expense ledger, plus the GST on the voucher when the project's GST scheme gives no input credit. Cost paid: what was paid straight from bank or cash, and payments to suppliers spread over the cost lines of their bills. Both feed the money engine and the withdrawable amount.
  - The RERA designated account: suggested from bank ledgers named RERA, escrow or designated, and confirmed once; its debits are deposits, its credits withdrawals, and interest credited by the bank is interest. Feeds the 70% check and escrow.
  - Landowner payments, matched to the project's landowners by name or chosen once, with the TDS cut on each (s.194-IC) and refundable deposits told apart from consideration.
  - New alerts: no cost lines yet, expense ledgers without a cost line (with the spending left out), which bank account is the RERA account, payments to suppliers that cannot be spread over cost lines, a joint development with no landowners, landowners without a PAN.
  - Undo adds reversing entries for cost and the RERA account (both are append-only) and removes landowner payments; importing the same file again afterwards brings them back.
  - Tested end to end: standard cost lines set up, a landowner added, an export reviewed with cost, RERA deposits and the landowner matched, brought in, and shown on the Overview, the budget, Escrow and the landowners; then undone.
- Payment plans and buyer payments:
  - A payment plan for any project, started from a standard plan (construction-linked in ten stages, construction-linked front-loaded, or 20:80) and changed stage by stage on the Collections tab: name, when it falls due (booking, agreement, a certified-progress percentage, possession) and share. The shares must add up to 100%; stages with demands already raised keep their timing and share.
  - Buyer payments typed in on the unit page (date, amount, TDS the buyer deducted, UTR or cheque number), listed with where each came from (typed, imported or Tally), and deleted if entered by mistake (Tally's are corrected in Tally).
  - Buyer payments imported from a collections register or a bank export through the Import centre, with a template; each row checked (the unit exists and is sold, the date and amount are there), payments already recorded recognised so the file can be imported again, exported in the same layout, and undone.
  - The Import centre now takes any record type through one handler per type, so new types plug in with their own checks.
  - Tested end to end: a 20:80 plan chosen and changed, a plan that does not add up refused, a payment typed in, two imported, and collections showing them.
- Project details and the set-up checklist:
  - A Set-up tab on every project: each kind of data Lekhara works from (project details, units and buyers, the payment plan, certified progress, cost lines and budgets, costs, suppliers' bills, buyer payments, RERA account movements, landowners for a joint development, documents, and the architect, engineer and CA), whether it is in, partly in or out of date (accounts older than 45 days, a progress certificate older than 100), what each one switches on, and a link straight to where it comes in.
  - The Overview shows how many are done and the next one to bring in, until all are.
  - A project's details can be changed after it is added: name, K-RERA number (checked against the firm's other projects), dates, locality, land structure, GST scheme, escrow bank, auditor, development rights value, labour cess paid. Clearing a field in the form clears it.
  - The occupancy certificate (applied for, partial or received, with its date and number), the date the association was formed and the date the common areas were conveyed, recorded from the web; the handover desk and Today follow them.
  - Certified progress recorded from the architect's or engineer's certificate, by the team or by the project's architect or engineer: not in the future, and never lower than an earlier certificate. Demands ready to raise follow at once.
  - Every change goes into the project's change history.
  - Tested end to end: a new project's checklist, details saved, an occupancy certificate refused without its date, a field cleared, progress recorded and refused when lower, the sample project complete and read-only to another firm.
- The full workspace export:
  - "Download everything" in Settings: one ZIP file with everything the firm has in Lekhara, at any time, including when the workspace is read-only after the trial.
  - An Excel workbook with a sheet for every kind of record (30 of them: projects, units, handover, the payment plan, demands, buyer payments, progress certificates, cost lines and the cost ledger, the RERA account, suppliers and their bills, landowners and their payments, withdrawals and their certificates, filings, cases with hearings, orders and payments, documents, data rooms and their visits, Tally choices, the team, certifiers and the change history), with names of projects, units, suppliers, cost lines and people in place of ids.
  - The same records as JSON, with the ids that tie them together, for another system to read.
  - Every document in the vault, every version, in a folder per project (archived ones apart), named by title; the Documents sheet says where each file is. A file missing from storage is named in the read-me instead of stopping the export.
  - Only the owner and finance can download it; each download is recorded in the change history. Secrets such as data room link fingerprints are never included.
  - Tested end to end: the owner downloads the sample firm's 520 units and 75 files; accounts is refused; a new firm's file holds only its own data.

- Bank statements:
  - Upload the statement net banking gives you, as Excel (XLSX, or the older XLS most Indian banks still give), CSV, text, or the web page some banks save as "Excel". Lekhara finds the table of transactions under the title rows whichever bank it came from (HDFC, SBI, ICICI, Axis, Kotak, Canara, Bank of Baroda, Union Bank, Karnataka Bank, Federal and others), with withdrawal and deposit columns or one amount column marked Dr or Cr, dates in any common form, amounts as 1,23,456.00 or 5,000.00 Cr, narrations that run onto a second row, and statements listed newest first. PDFs are refused with the steps to download Excel instead.
  - Reads the bank, the account number, the period and the opening balance from above the table, and checks that each line's running balance follows from the one before (a jump means transactions are missing from the download).
  - Asks once which account it is: the account buyers pay into, or the RERA designated account (optionally one that buyers pay straight into). Lekhara remembers it by the account number for the next statements.
  - Collection account: each credit is matched to a sold unit from the narration (the unit number, or the buyer's name, including on home-loan disbursements that name the borrower), from the builder's earlier choice for the same payer, or from the buyer's ledger in Tally. The payer's name is read from NEFT, RTGS, IMPS, UPI and transfer narrations, passing over the firm's own name. Payments that cannot be matched wait for a choice (a unit, not a buyer's payment, or leave out), which is remembered for the payer. Interest and money going out are left out.
  - RERA account: deposits, withdrawals, interest and bank charges (charges lower the balance but are not counted as withdrawals). Feeds the 70% deposit check and the withdrawable amount. Lekhara compares the statement's opening balance with its own balance for the account the day before and says if earlier movements are missing.
  - A bounced cheque or returned transfer is paired with the original and both are left out.
  - Never twice: each line has a fingerprint that is the same in any download covering it, so overlapping statements, or the same statement in another layout, add nothing again; money already brought in from Tally or typed in (the same amount within three days) is recognised too.
  - A review page with what needs attention, every buyer payment and how it was matched, and every transaction with what Lekhara does with it; then bring it in, and undo within 30 days (buyer payments removed, RERA account movements reversed).
  - Built to the layouts banks print and tested on sample statements in those layouts; to be tested against real statements from design partners.
  - Tested end to end: a PDF refused with steps, an HDFC collection account statement read and matched (by name, by unit number, a home-loan disbursement, a bounced cheque), a payer placed by hand, payments on the unit, the same account in ICICI's layout adding nothing, an SBI RERA account statement shown in escrow and the set-up checklist, and an undo.

- Suppliers, their bills and commitments, for builders who keep them outside Tally (or alongside it):
  - Suppliers belong to the firm and serve every project: name, GSTIN (checked, with the PAN and state filled in from it), MSME category, Udyam number and whether a written agreement fixes payment terms. Added, changed, cleared and deleted (only while they have no bills or orders) on a page of their own, with every bill they sent across projects.
  - A "Suppliers and bills" tab on each project: every bill with its supplier, date, taxable value, GST, cost line and payment, where it came from (Lekhara or Tally), and forms to add bills and suppliers.
  - A bill can name a cost line: it then counts as cost incurred on that line (with the GST when the project's GST scheme gives no input credit) and as cost paid once paid. Changing the amount, the line or the payment, clearing it or deleting the bill moves the cost with it, through new entries in the append-only ledger. A bill from Tally carries no cost line here, so nothing counts twice; it can be corrected but not deleted.
  - Commitments: work orders, purchase orders and contracts on the Budget page, each committing a cost line to an amount; a variation changes the amount, and the committed figures and anticipated final cost follow.
  - The 80% registered-supplier test and the MSME clock use every bill at once, whichever way it came in.
  - All three import from a sheet through the Import centre, with templates: suppliers matched on GSTIN or name, bills on the supplier and the bill number (a new supplier is added), orders on their number; the preview, re-import that changes nothing, undo (the cost goes back too) and export in the same layout, as for units.
  - Every change is in each record's history; the demo's commitments are now real work orders.
  - Tested end to end: a supplier added and a wrong GSTIN refused, a bill added and paid with its cost on the budget, an order added, a sheet of bills imported with a new supplier, the supplier's page, the export, and the tax tab.

- The forwarding address (the first automatic feed):
  - Each project has its own email address, shown on its Import page. Whatever is sent or forwarded to it is kept, and each file is brought in the way it would be if uploaded: a Tally export through the Tally import (applied by itself unless it needs choices), a bank statement through the bank statement import (applied by itself once the account is known), a sheet of units, payments, suppliers, bills or orders into an Import centre preview, and anything else into the document vault, filed by what its name says (bills, approvals, insurance, deeds and so on).
  - Mail from the firm's team and from senders it trusts (an address, or a whole domain such as a bank's) is read at once; anyone else's waits until a team member allows it or turns it away, and allowing can trust the sender from then on. A sender whose domain fails the mail service's checks is not taken at its word.
  - Banks can email statements on a schedule straight to the address. Statements emailed as PDF are read too, including those locked with a password: the firm gives each password once in Settings, where it is kept sealed with the server's key and never shown again, and a statement that was waiting for its password can be tried again.
  - Mail reaches Lekhara either from an email service that posts each message to Lekhara with a shared secret (SendGrid, Mailgun, Cloudflare Email Routing and others), or by Lekhara checking a catch-all mailbox every two minutes.
  - A background job queue in the database runs the work, retries failures with a growing wait, and runs inside the API (or on its own).
- Bank statements as PDF: the transactions are read line by line from the text of each page, whatever the bank, with whether money went in or out read from the running balance; narrations over two lines are joined, the value date taken out, statements listed newest first put in order. A line has the same fingerprint in the PDF and the Excel download of the same statement, so nothing is counted twice across formats.
  - Tested end to end: a statement emailed by the team and read by the background worker, a document from an outsider held, allowed and its sender trusted, a locked PDF statement waiting for its password and read once the password is given.

- The review queue:
  - A "To review" page with everything brought in that waits for a choice, across every project the person can import into, oldest first, each opening where it is settled: a statement whose account is not known yet, buyers' payments to place, a statement, Tally export or sheet not brought in yet, an email from outside the team to allow, a file that could not be read (such as a statement waiting for its password).
  - Today says how many things wait, with a link to the queue.
  - A bank statement already brought in can still have its waiting payments placed, and then brings in just those ("Bring in the rest"); nothing else in it is added twice.
  - Tested end to end: a statement waiting for its account, then for one payment after it was brought in, the payment placed and brought in, and the queue empty again.

- The Lekhara Connector for Tally (the second automatic feed, optional):
  - A small program for the computer with Tally (`connector/` in the repository; Python's standard library only, packaged as one Windows program with `build.ps1`). Every five minutes it reads Tally's masters and the Day Book for the last seven days, and once a day the whole financial year, over TallyPrime's own XML interface on that computer, and sends them to Lekhara. It only reads Tally and only makes outgoing connections; when nothing changed, nothing is sent.
  - A computer is linked to a project with a one-time code from the Import page (it works once, for 30 minutes), which the connector exchanges for its own key; the key can only send data to that project, and unlinking the computer on the Import page withdraws it at once. The Import page shows each linked computer, the company it reads, when it was last heard from and last brought anything in, and anything wrong (Tally not open, its HTTP server off).
  - Each sync goes through the Tally import and is applied by itself, matched on Tally's own voucher identities so nothing comes in twice; masters are kept to read later vouchers against. What needs a choice shows in the review queue as "Choices for the connected Tally", and comes in on the next sync once chosen.
  - Tally imports, like bank statements, now take choices after they are applied, and "Bring in the rest" brings in only what the choices freed.
  - A firm whose free month has ended unpaid takes no new data from its connectors.
  - Tested with a stand-in Tally on the real program: linking with a code from the Import page, a sync brought in, the next one sending nothing, the computer shown as connected, choices in the review queue, and the connector stopped once unlinked. To be tested against TallyPrime itself at a design partner.

- GSTR-2B from the GST portal:
  - Upload or forward the GSTR-2B downloaded from the portal (JSON or Excel), or a GSTR-2A (JSON). Lekhara reads the suppliers' invoices and notes in it, whichever layout, and checks them against the project's bills, matching on the supplier's GSTIN (or name, for a supplier without one in Lekhara) and the invoice number however it is written.
  - It shows the invoices that agree, those whose amounts differ, bills in Lekhara for the month that the supplier has not reported (their credit, and their standing as from a registered supplier for the 80% test, are at risk until the supplier files), invoices the GST system has with no bill in Lekhara, suppliers whose GSTIN Lekhara lacks, credit and debit notes, and invoices on which credit is not available. A return for another GSTIN than the firm's is flagged.
  - Bringing it in fills in suppliers' GSTINs, adds suppliers who are not in Lekhara, and, if chosen, adds the missing invoices as bills (off by default for firms whose bills come from Tally, so nothing is counted twice or looks unpaid). Undo takes it out again within 30 days.
  - A return waiting to be checked is in the review queue; one forwarded to the project's email address comes in for checking.
  - Built to the layouts the portal gives and tested on sample returns in them; to be tested against real downloads from design partners. Fetching GSTR-2B by itself through a GST Suvidha Provider needs a GSP account and is still to do.
  - Tested end to end: a GSTR-2B checked against bills with an unreported bill, a supplier's GSTIN and missing invoices found, shown in the review queue, and brought in.

- A tidier frontend, so pages stay clean as features are added:
  - The Import page is a short list of ways in (Tally, bank statement, GST portal, units, buyer payments, suppliers and bills), one line each until opened for its steps and upload, with the project's email address above and one list of everything brought in below, newest first.
  - Project tabs: the work (Overview, Escrow, Collections, Handover, Disputes, Tax, Documents) as tabs, and the records (Units, Suppliers, Budget, Import, Set-up) as a quieter group on the right, so Import is always one click away.
  - Today shows everything that needs you now in full and the first three of each other group, with the rest a click away; a project's Overview shows what is late, due soon or at risk, with money waiting, what is coming up and the cost lines folded away.
  - The units list has filters (tower, sold or not, the landowner's, priced below guidance) and a search by unit or buyer, and shows fifty at a time.
  - Long tables on review pages (every transaction in a statement, every invoice in a GST return, what a Tally file holds) and forms in Settings open on request; columns with nothing in them are left out.

- Legal foundations, from the research into Indian law for a SaaS (the DPDP Act and Rules 2025, the IT Act and SPDI Rules, the CERT-In Directions, consumer law on dark patterns; the full research is outside the repository):
  - Terms of service, a privacy notice and data processing terms (Lekhara as the builder's data processor for buyers', landowners' and suppliers' personal data), in plain words, open without signing in and linked from every page. The company's name, address and grievance officer come from settings. They need a lawyer's review before launch.
  - Signing up, and joining by invitation, mean ticking that you agree (never pre-ticked); the version and time are recorded for each person, and the owner or finance accept the data processing terms for the firm. When the documents change, everyone is asked to read and accept them again.
  - An access log of sign-ins (and failed ones), exports, documents opened, invitations, role changes and people removed, with the address and browser they came from, kept a year (CERT-In asks for 180 days in India); the owner and finance see it in Settings, and it is part of the firm's export.
  - Anyone can delete their own account (their name and email are taken out; what they did stays under "A former user"), except a firm's only owner. An owner can close the firm's account: everything stays readable and downloadable for 30 days and the closing can be undone; then a daily job deletes all of the firm's projects, records, documents and files and takes out the people who worked only for it, keeping the access log.
  - Tested end to end: the three documents open without signing in, sign-up refused without agreeing, the access log in Settings, a firm closed and kept open, and the only owner unable to delete their account.
- The last records that came only from the demo data or Tally, each now added, changed, imported, exported and with a history:
  - Landowner payments: a page for each landowner with every payment (from Tally, imported or typed in), the TDS each one should have had under s.194-IC and any shortfall, refundable deposits told apart from consideration, and the landowner's details. Tally's payments are corrected in Tally. The history keeps every payment added, changed or deleted.
  - Approvals: a new Approvals tab with each approval, consent and NOC, its authority and number, when it was applied for, granted and until when it holds. The usual twelve for a Karnataka residential project (land conversion to occupancy certificate) are set up in one step and trimmed to what applies. An approval lapsing within 90 days, or already lapsed, is on Today.
  - K-RERA filings: a new K-RERA tab with every quarter's progress report and every year's annual audit since registration, each due, late, current or filed, and recorded as filed with its acknowledgement in one step. Today now checks the audit for every year since registration, not only the last one.
- Editing as a table: units, suppliers, bills, orders and approvals can be edited fifty rows at a time like a spreadsheet; the changes go through the same preview as an import before they are saved, can be undone for 30 days, and show in each record's history as edited as a table.
- On a phone, the project's tabs and the top menu stay on one line that scrolls sideways.
- Tested end to end: a landowner's payment with short TDS flagged and corrected, the usual approvals set up and one about to lapse shown on Today, a late quarter recorded as filed, payments, approvals and filings imported, and a unit's price changed as a table and saved with its history.
- The packs Lekhara prepares, each as a PDF to read, print and sign, from the project's own records:
  - For the escrow bank, on every withdrawal: a covering letter for the promoter to sign, how the amount is worked out (estimated cost, cost incurred and paid, withdrawn so far, the balance), the 70% deposits, cost by head, the architect's, engineer's and CA's certificates with their statements (or a place to sign, with a note that the professional checks and signs under their own name), and the checks Lekhara ran.
  - For each quarter's progress report on the K-RERA portal: units booked in the quarter and to date, the last certified completion, money from buyers and the designated account in the quarter and to date, cost, the approvals and open cases at the quarter's end. Also as Excel, to copy figures from.
  - For each year's audit: money from buyers, the 70% deposits for the year, withdrawals released with who signed the certificates behind each, cost incurred in the year and to date, and a draft statement for the CA to examine, change and sign with a UDIN. Also as Excel.
  - Downloaded from the withdrawal page and from each period on the K-RERA tab. Each bank's own format, and K-RERA's form layout, will follow from design partners' samples.
- The sample projects' designated accounts now draw down quarter by quarter and never run below zero, and the released withdrawal carries the figures its certificates were signed with.
- Tested end to end: the bank pack from a withdrawal, the quarterly report and the audit pack from the K-RERA tab as PDF and Excel, and a wrong quarter refused.
- Handing homes and the project over:
  - A possession letter for each buyer once the occupancy certificate is in, from the unit page: the certificate, the date to take possession by (two months, RERA s.19(10)), any balance due, the estimated stamp duty and fees, the inspection before handover, and the five-year defect liability (s.14(3)). Printable, sent from the builder's own address.
  - Handing over to the residents' association: a checklist on the Handover tab once the certificate is in, from forming the association to conveying the common areas, with the corpus, maintenance deposits, drawings, fire systems, lifts, plant, warranties, utilities, insurance, keys and contractors in between; each marked done with a date and a note, with its history. Forming the association and conveying the common areas keep the project's own dates in step.
  - Grouped units on the Handover tab open on their own only when the group is short.
- Cancelling a booking: from the unit page (the date, any refund and why), or from a case once the refund under an order or a settlement is paid. The unit is free to sell again; the buyer's demands and payments stay on record under the cancelled booking, still count in the 70% check and in the case, and the unit page lists earlier bookings. A unit registered in the buyer's name is refused, since that needs a cancellation deed. Marking a unit unsold is kept for bookings entered by mistake.
- Tested end to end: the possession letter, an association item marked done, and a refund case paid in full cancelling the booking, with the unit free and its earlier booking kept.
- Data rooms can ask each visitor for their name and email before showing anything, telling them it is shared with the builder and recorded with what they open; every opening and download is then recorded against that person, and the room's page shows who. On by default for new rooms, and switched on or off on the room's page. The visitor's browser keeps a token for that room's link only.
- Tested end to end: a gated room shown only after a name and email, a wrong email refused, a file refused before the gate and downloaded after it, and the room showing who visited.
- Tally, debit notes and sales:
  - A debit note to a supplier (goods returned, a rate cut) comes off the bill it was raised against, found by its bill-wise reference or the supplier's invoice number: the bill's taxable value and GST come down, so the 80% test and the MSME clock see the net bill, and a note arriving in a later file changes a bill already brought in (undone with the import). When GST is cost, the note's GST comes off cost too. A debit note is no longer counted as a payment of the bill. Notes that cannot be tied to a bill are named, with how to fix them in Tally.
  - Sales vouchers raised on buyers are matched to the demands raised in Lekhara on the same unit, for the same amount, within two months. When a firm books its demands as sales, demands with no sales voucher are named, since GST on a home under construction is due on the invoice or the payment, whichever comes first; sales vouchers that match no demand are named too.
- Tested end to end with the full suites; the Tally review shows the notes netted and how the sales match.
- Onboarding:
  - A project is added by dropping in its K-RERA registration certificate: its number, name, locality, promoter, registration date and declared completion date are read from the PDF and the form opens filled in, to check. A scanned certificate, with no text in it yet, is named as such and the details are typed.
  - The firm's GSTIN fills in its state, its PAN and the kind of business (company, firm or LLP, proprietor and so on); the legal name, which is not in the number, is asked for. Today's welcome asks for the GSTIN first.
  - Pages say what they cannot work out yet, and where each missing piece comes in, instead of showing zeros or "in order": the Overview's figures, what can be withdrawn, the 70% deposits, demands ready to raise, the 80% test, delay interest and labour cess. A new project's Overview starts with the three ways to bring data in (Tally, bank statements, units).
  - K-RERA filings due before the firm started using Lekhara are not counted as late: Today asks once to record them, and the K-RERA tab marks them "Not recorded", with one step to record them all as filed on time.
  - A project with no locality no longer shows a stray comma in its heading.
- Tested end to end: the GSTIN step, a project read from its certificate and added, the new project's start block and honest figures, the escrow tab saying what it needs, and earlier filings recorded at once.
- Security:
  - Two-step sign-in with an authenticator app (Google Authenticator, Microsoft Authenticator and the like): turned on in Settings with a key the app takes, then a six-digit code after the password at every sign-in, and on joining another firm by invitation. Eight recovery codes, each good once, for a lost phone. A code once used cannot be used again; the secret is sealed with the server's key. Recommended in Settings for owners and finance; turning it on and off is in the access log.
  - Limits per network address, on top of the limits per email: sign-ups, password reset emails, failed sign-ins across all emails, and data room visitors. The numbers are settings.
  - Every file uploaded, emailed to a project's address or sent by the Tally connector is checked for viruses by ClamAV when a scanner is set up (`LEKHARA_CLAMAV_URL`); a file carrying one is refused by name, and if the scanner cannot be reached, files are refused rather than let through.
  - Row-level security in Postgres, as a second wall between firms beneath the checks in the code: every table holding a firm's data has a policy, and while a signed-in person's request runs, Postgres shows and accepts only rows of their firms, the sample firm and the projects they certify. The policies are put on after every migration. The whole test suite runs on Postgres with them in force (a new CI job), and a test shows another firm's rows hidden and writes refused with the code's own checks out of the way.
  - A wrong password or code now shows its own message instead of "Your session has ended".
- Tested end to end: two-step sign-in turned on, a sign-in asking for the code, a wrong code refused, the right code and a recovery code accepted, and turned off.
- CRM exports read as they come:
  - Unit and payment exports from Sell.Do, LeadSquared, Zoho CRM, Salesforce and HubSpot are matched by their own column names (Unit Name, Primary Lead Name, mx_Unit_Number, Deal Name, Closing Date, Amount and the like); the preview says which CRM it recognised.
  - A first and a last name in separate columns are joined into the buyer's name.
  - A unit whose status says it is blocked, on hold, available or lost is brought in unsold, even with a name against it.
  - Built from the CRMs' published field names; to be checked against real exports from design partners.
- Tested end to end: a Sell.Do inventory export recognised on the preview and imported, with the blocked unit left unsold.
- Forms on a slow connection: a form sent before the page's scripts have arrived now comes back to the same page with its error or confirmation on that form straight away, instead of the message appearing only once the scripts load. Reloading the page afterwards does not send the form again. With the scripts loaded, nothing changes.
- Tested end to end: sign-in and adding a unit sent as plain posts, the message shown on the right form only and only once, and in a browser with its scripts held back; with scripts, errors still show in place.
- Public website, in the same monochrome design:
  - Home, at `/` for anyone not signed in (signed in, `/` is still Today): what only Lekhara does, what it brings in, how it works, your data, and what it does not do.
  - Pricing: one subscription per firm, everything included, and how paying works. The amount shows once it is set (`LEKHARA_PRICE_PER_MONTH`); until then the page says the price is being set with the first builders.
  - Contact: email, phone if set, office, and the grievance officer.
  - Cancellation and refunds, and shipping and delivery, next to the terms, privacy notice and data processing terms, as Razorpay asks for. The refund rules follow decision 11's recommendation: monthly runs to the end of the month paid; yearly is 12 months for the price of 10 with unused whole months refunded; refunds within 7 working days.
  - The sign-in pages' wordmark leads back to the website.
- Tested end to end: the website signed out, the price not yet set, the policy pages, private pages still asking to sign in, and `/` as Today once signed in; screenshots on a computer and a phone.
- Our admin console, at `/admin` for Lekhara's own staff:
  - Staff are marked from the command line (`python -m lekhara.staff add someone@lekhara.in`), and the console opens only once they have two-step sign-in on. To everyone else it does not exist.
  - Every firm, found by its name or a member's email: where it stands (free month to a date, paid to a date, read-only, closing), people, projects, last sign-in, and whether support is allowed. A firm's page lists its people (with their two-step), projects with unit counts, payments, and what we did.
  - Extending a free month, with the reason recorded. Recording a payment received by bank transfer, UPI or cheque, with its reference and the period it pays for: the firm is then paid to that day, and becomes read-only after it (no grace period yet; decision 12). A payment recorded by mistake can be removed. Payments are kept when a closed firm's data is deleted, as our record of what was paid.
  - Support access only with the firm's consent: the owner or finance allows it in Settings for 1, 3, 7 or 14 days, and can withdraw it at any time, which ends any support session at once. Staff then see the workspace as a viewer, read-only, for two hours at a time, with a banner saying so and a way back to the console. Every page support opens, and everything we do to the firm's account, is in the firm's own access log.
  - The workspace is read-only once the period paid for runs out, and says so in those words.
- Times in the access log, history, imports, the review queue and emails received are now shown in India time; they were shown in UTC.
- Two-step sign-in: the recovery codes stay on screen after turning it on; before, the page redrew and they were gone before they could be copied.
- Tested end to end: the console closed to a builder and to staff without two-step, a firm found by email, its free month extended and a payment recorded (and seen in the builder's Settings), support refused before consent, then allowed, opened read-only, ended, and seen in the builder's access log, and withdrawn.

- Incident response: a written runbook (`docs/incident-response.md`) for when security is breached or might have been. It covers who acts, the deadlines (CERT-In within 6 hours, affected firms within 24 as our data processing terms promise, affected people and the Data Protection Board as the DPDP Rules require from May 2027, followed now), the commands to sign people out, withdraw access, close data rooms, unlink connectors and rotate secrets, the access-log queries to find out what happened, and the notices to send.

- Security hardening, first round (from the review in October 2026):
  - Emails that only claim to come from a team member or trusted sender are held: the receiving mail service's own verdict must show the sender's domain vouched for the message (DMARC, or DKIM or SPF for that domain). A verdict a sender writes into the email is ignored.
  - Excel and CSV downloads keep imported text as text, so a buyer named `=HYPERLINK(...)` in a CRM file can never become a working formula in someone's spreadsheet.
  - Excel files that would unpack to far more than they weigh (decompression bombs) are refused before they are opened.
  - The web app sends security headers: a Content Security Policy, frames from Lekhara only, no referrer to other sites (data room links carry their key), and HTTPS enforced in production.
  - The API no longer publishes a map of its own routes.
  - Every Python package is pinned with its hash; CI now checks for committed secrets, known vulnerabilities and risky code; Dependabot proposes updates.
- Tested: forged and missing sender verdicts held, formulas kept as text in Excel and escaped in CSV (and read back), a 30 MB zip bomb refused, headers present and nothing blocked in the browser, the API's docs hidden; all end-to-end suites.

- Security hardening, second round:
  - Sensitive steps ask for the password again (and the two-step code, if on) unless the person signed in or confirmed in the last 15 minutes: downloading everything, inviting, changing roles, removing someone, adding a trusted mail sender, creating a data room or a new room link, closing the firm, allowing support, and every staff console action. The page comes back to where it was after confirming.
  - Sessions unused for 12 hours end by themselves. Settings lists every browser you are signed in on, with when and from where, and ends any of them, or all but this one.
  - Emails at once: to you, when you sign in from a browser not seen before; to the owner and finance, when someone downloads everything or support opens the workspace.
  - An owner can require two-step sign-in for the whole team; anyone without it is sent to set it up before going on.
  - Data room visitors confirm their email with a code sent to it before anything opens, so the name and email in the visit log are real.
  - Passwords already leaked in data breaches elsewhere are refused at sign-up, reset and invitation, checked without the password leaving Lekhara (only five characters of its hash are sent); if the checking service is down, the password is accepted.
- Tested: each sensitive step asking after a while and passing once confirmed, with the code when two-step is on; an idle session ending; two sessions listed and one ended; the new-browser and full-download emails; the firm's two-step rule sending a team member to set it up; a visitor's wrong code refused and the right one opening the room; leaked passwords refused and the check sending only a hash prefix. All end-to-end suites, and a new one for confirming, the two-step rule and sessions.

- Passkeys: sign in with the phone's or computer's own lock (fingerprint, face or PIN) instead of a password. Added in Settings after confirming it is you, named to tell them apart, and removable. A passkey only works on Lekhara's own address, so a fake sign-in page cannot use it; it counts as two-step sign-in for the firm's rule and the admin console. Sign-in needs no email: the browser offers the passkeys it holds.
- Tested: passkeys added, used to sign in, refused for a look-alike site or when unknown, the same answer refused twice, removal asking to confirm first, and a passkey counting as two-step (with a software authenticator in the tests); in Chrome with its virtual authenticator, a passkey added in Settings and used to sign back in without a password.

- Security hardening, last round:
  - The secret key can be changed without losing anything: the old key stays readable while every sealed secret is sealed again with the new one (`python -m lekhara.secretbox reseal`).
  - The access log is tamper-evident: each entry carries a hash of itself and of the one before, so an entry changed or removed later shows (`python -m lekhara.legal verify-log`, also run daily). Requests arriving together queue on the chain's end instead of forking it.
  - Sign-in and sign-up limits are counted in the database, so they hold across any number of servers; emails and addresses are kept only as hashes.
  - Encrypted backups of the database and every document (`python -m lekhara.backup create`, `check`, `restore`): AES-256 in sealed pieces, so a backup cut short, altered or opened with the wrong key is refused; each document is checked against its fingerprint.
  - A public Security page, and a `security.txt` saying where to report a weakness.
  - The CI's actions are pinned to exact commits.
- Tested: a secret sealed with the old key read with both, resealed, then read with the new key alone; an access log entry altered and the newest removed, both caught; twenty events written at once keeping one chain; failed sign-ins on two servers counting together; a backup checked and restored, and an altered, a cut-short and a wrongly keyed one refused; all on SQLite and the security tests on Postgres with row-level security; every end-to-end suite, with the live access log intact afterwards.

- Borrowed from other software, first two:
  - The Tally connector asks Tally for two numbers before anything else (the last change numbers of the company's masters and vouchers, from the idea in tally-database-loader) and exports only what has changed: when nothing has, Tally is not asked for an export at all, so it is not slowed every few minutes. Older Tally versions that cannot answer are handled as before.
  - Every night, every stored file (documents, imports, statements, emails) is read and checked against its fingerprint, as Paperless-ngx does; files missing or changed are logged as errors and shown in the admin console (`python -m lekhara.integrity` runs it by hand).
- Tested: the connector asking only for the numbers when nothing changed, exporting the day book alone when a voucher changed and the masters too when a master did, and falling back for an older Tally; the file check passing, then finding one document altered and one missing.

- Filing documents by rules (borrowed from Paperless-ngx's matching): a firm writes rules (words, and whether any, all, the exact phrase, or all allowing small spelling differences must appear) saying what kind of document, and which checklist item, a document containing them is. A document uploaded or emailed in without a kind chosen is filed by the rule whose words come earliest in it, and says which rule did; it can always be changed. Seventeen rules for common Karnataka documents (occupancy and commencement certificates, fire NOC, encumbrance certificate, mother deed, sale deeds, khata and others) are added in one step; a new rule shows how many documents already in the vault it fits, and what is still under Other can be filed by the rules at once. Patterns (regular expressions) are left out, since one written carelessly can stall the server.
- A register of paper originals (borrowed from Paperless-ngx's archive serial numbers): each title deed, plan, certificate or sale deed gets a number for the firm (O-0001 and on) on a printed barcode label for its folder, and Lekhara keeps where it is (in the office, with a bank as security and against which loan, with the lawyer, at the sub-registrar, with an authority, handed to the buyer) and every move, with who recorded it. An ordinary barcode reader scanning a label opens its record; one away with the lawyer, registrar or an authority for more than 30 days is flagged.
- Tested: the four ways of matching (a scanned "OCCUPANCV CERTIFlCATE" found), an upload filed by a standard rule and one with its kind chosen left alone, a rule tried, added and used on documents already in, the rule nearest the top winning over a passing mention, and who may change rules; originals numbered across the firm, moved with history, found by a scanned or typed number, flagged when away too long, and hidden from other firms and certifiers; both end to end, with the label sheet's barcodes.

- Stronger data rooms (borrowed from Papermark and other data room software):
  - Every page of a PDF opened from a room carries, faintly across it, the visitor's email and the date (or, in a room that does not ask who visitors are, who it was shared with), and along its foot who opened it, from which firm's room, marked confidential. The document underneath is unchanged and still searchable; the team's own copy is never marked. On by default, and a room can turn it off. Photos are shown as they are, and a damaged PDF that cannot be marked is served unmarked rather than not at all.
  - Terms (a confidentiality note, or an NDA) each visitor accepts before anything opens, recorded with their name, email, the time and the words they accepted. If the terms change, visitors accept them again before anything more opens. Terms need the room to ask who visitors are, so each acceptance has a name on it.
  - Whoever made the room is emailed the first time each visitor opens it (or, for a room that does not ask who visitors are, the first time anyone does), with a link to every open and download. It can be turned off for a room.
  - A switch to stop downloads is left out: anything on a visitor's screen can be saved or photographed, so it would promise more than it does. The watermark makes a copy traceable instead.
- Tested: a PDF opened by a visitor carrying their email, the date and the footer while its own text is still found, the team's copy unmarked, a room without names marked with who it was shared with, and the mark turned off; terms refused without names, required at the gate, accepted again after a change, and the accepted words kept; the room's maker emailed once per visitor, not when turned off, and once only for a room without names; all end to end, with the watermark read back from the PDF a visitor downloaded.

- Bank rules (borrowed from Firefly III): a firm writes rules for what repeats in its statements every month.
  - A rule looks for words in a line's narration (the same four ways as filing rules), for money in, out or either, and optionally within an amount range.
  - It says what such a line is: a payment from the buyer of a unit, not a buyer's payment, a line to leave out (sweeps to a fixed deposit, transfers between the firm's own accounts), or, in the RERA account, a deposit, interest, a withdrawal or bank charges.
  - A rule is for one project, or for every project unless it names a unit. Rules are tried in their order, which can be changed, and the first that fits decides; a choice made for the line itself still comes first, and the payers Lekhara remembers come after. Every line a rule decided says which rule did.
  - Each line of a statement has a link that opens the rule form filled in from it (its payer, or the telling words of the narration, and what Lekhara made of it). A rule can be tried on the project's statements before it is saved, and on saving says how many lines it fits; statements not yet brought in follow it at once.
  - A unit a rule names, or a payer remembered from bank statements points at, can no longer be deleted out from under them.
- Tested: a rule placing a line as not a buyer's, two rules for one line with the first deciding and the order changed, a choice for the line coming first, a rule coming before a remembered payer, a bounced cheque staying paired whatever the rules say; rules for the RERA account (sweeps left out both ways, a card fee as charges within an amount range, a line kept a deposit); trying a rule; every check on what a rule may say, rules for every project shown on each, and certifiers kept out; all end to end, from a statement line to the rule and back.

- Help with the GST Invoice Management System (borrowed from india-compliance's purchase reconciliation):
  - Every invoice and note in a GSTR-2A or GSTR-2B brought in gets what to do with it in IMS, and why: accept when the bill is in Lekhara with the same amounts; keep pending when the amounts differ (correct the bill and accept, or reject so the supplier corrects it) or when there is no bill yet (credit needs the goods or service received); reject a copy of an invoice already in an earlier month's return, so the credit is not taken twice; check a credit or debit note, which only the person who agreed to it can judge.
  - A return covers the firm's GSTIN, so a bill is looked for in the firm's other projects too.
  - The return's page explains when GSTR-2B is drawn up (the 14th, from what was accepted and what was left untouched) and that choices can change until GSTR-3B is filed, lists what is not simply to accept, and the whole list downloads as a spreadsheet to work through on the portal.
  - Lekhara does not act in IMS itself: that needs a GST Suvidha Provider (decision 20). Which records may be kept pending has changed since IMS began, so the page says the portal's own choices for each record are the final word.
- Tested: each suggestion and its reason (a bill that agrees, amounts that differ, no bill, the bill in another project, an invoice in August's return again in September's, a credit note), the counts, and the downloaded list; end to end with the GST import.

- A signing record on certificates (borrowed from DocuSeal and Documenso's audit pages):
  - When the architect, engineer or CA signs a withdrawal certificate, Lekhara keeps who signed (their account and its email), when, from which address and browser, whether they use two-step sign-in, and a SHA-256 fingerprint of exactly what they signed (the project, the request, the statement with its figures, the signer). Entering the figures is recorded the same way.
  - Signing needs the person to have signed in or confirmed their password in the last 15 minutes, so a session left open cannot sign.
  - Each certificate downloads as a PDF that ends with its signing record page and a check code; the withdrawal pack carries the same page after each signed certificate. Anyone holding the PDF, a bank first, can enter the code on the public check page (no sign-in, limited per network) and see what was signed, by whom and when, and whether it still says that.
  - The demo's signed certificates come with records.
  - A digital seal a PDF reader checks by itself needs a document-signing certificate from a certifying authority, and Aadhaar eSign needs a provider: decision 36.
- Tested: the record kept at signing (address, browser, fingerprint, code), the check page found by the code typed any way and refusing unknown codes, the certificate PDF and the pack carrying the record, a figure changed after signing caught, and signing refused until the person confirms it is them; end to end, from the CA signing to a bank checking the code.
- With these, every feature borrowed from other software in `research-borrow-and-secure.md` is built.

- Files in S3 for production: `LEKHARA_STORAGE_URL=s3://bucket/prefix` keeps the document vault, imports, statements and emails in an S3 bucket (or any S3-compatible store, such as SeaweedFS or RustFS in development) instead of on the server's disk.
  - Files keep their SHA-256 names, so the same file is stored once. S3 checks each upload against its SHA-256 before keeping it, and every file is encrypted at rest with S3's keys or a KMS key.
  - Credentials come the usual AWS way, the server's role first.
  - The nightly file check, backups and the demo seed work the same with either store; a backup now reads files through the store, so it includes the bucket's files too.
  - boto3 comes in as an optional extra, `s3`.
- Tested: local disk keeping, listing and removing files and refusing a path outside it; S3 uploads carrying the SHA-256 and the encryption asked for (AES256, or a KMS key), a file already there not sent again, reading, listing past other objects, a missing file reported as missing, and the settings choosing the store; backups and the file check as before.

## In progress

- Nothing at the moment; the next work is under Left.

## Left

### v1: self-serve and pilot-ready (two founders)

In this order:

- Self-serve start, still to do: sign-in with Google and by phone code (decision 18).
- Import centre, still to do: templates in Kannada, AI column mapping for unfamiliar sheets.
- Tally import, after that: testing against real exports from design partners.
- Billing: one Razorpay subscription per firm (UPI AutoPay, card, e-NACH), GST invoices, reminders before the trial ends and when a payment fails, a grace period, then read-only with export always open. Prices to be set.
- Automatic feeds, decided on 2026-10-18 (everything except what needs a bank partnership), still to do: Sell.Do and other CRMs by API; GSTR-2B fetched through a GSP (an OTP about once a month), once there is a GSP account. Bank APIs and the Account Aggregator wait.
- Multi-provider AI gateway (Claude, OpenAI, Gemini, Sarvam, self-hosted) with an India-only mode; document reading; obligation extraction; history backfill; Ask.
- Collections, next steps: reminders through the team's own WhatsApp or email.
- Disputes, next steps: reading complaints and orders with AI, reply outlines for the lawyer.
- Document vault, next steps: reading scans and filing documents by themselves.

### v2

- Home-loan disbursements, guarantees and insurance, approval conditions and environmental reports, vendor check.
- Certifier practice workspace.
- Buyer portal, payables on WhatsApp, contractor billing, notices.
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
- Tally data: read from the files Tally exports, by Lekhara's own Tally import built from scratch (the founder's earlier module does not fit); no Tally API, nothing installed on the customer's machine.
- Team: two founders through v1; a seed raise after three paying customers funds the team for v2 onwards.
- Design: minimal, monochrome, no emojis, no symbols in the branding, text wordmark only.

## Working assumptions (change any time)

- India-only AI processing is the default for every customer.
- No payment details are asked for to start the free month.
- The second segment after developers is certifier firms.
- Land records and court data come from licensed partners, not our own collection.
