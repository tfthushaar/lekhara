# Lekhara status

Last updated: 2026-10-19, with the commit "Add approvals, K-RERA filings, landowner payments and editing as a table".

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

## In progress

- The filing packs: the bank withdrawal pack, the quarterly progress report and the annual audit pack.
- Billing to the rules: one Razorpay subscription per firm; nothing charged without a mandate the builder sets up; the price with GST shown before paying; reminders before the free month ends; pre-debit notices; cancelling in one click, as easy as subscribing; a GST invoice for every payment. Built in test mode; going live waits on decisions about the company, prices, refunds and GST.

## Left

### v1: self-serve and pilot-ready (two founders)

In this order:

- Self-serve start, still to do: sign-in with Google and by phone code, limits on sign-ups and resets per network address, and row-level security in Postgres as a second wall between firms when production moves to Postgres.
- Import centre, still to do: known CRM export formats, templates in Kannada, AI column mapping for unfamiliar sheets.
- Tally import, after that: debit notes netted off bills, sales vouchers matched to demands, testing against real exports from design partners.
- Onboarding: the firm from its GSTIN, projects from the K-RERA certificate, engines that work with partial data and say what is missing, first-run help.
- Billing: one Razorpay subscription per firm (UPI AutoPay, card, e-NACH), GST invoices, reminders before the trial ends and when a payment fails, a grace period, then read-only with export always open. Prices to be set.
- S3-compatible file storage.
- Automatic feeds, decided on 2026-10-18 (everything except what needs a bank partnership), still to do: Sell.Do and other CRMs by API; GSTR-2B fetched through a GSP (an OTP about once a month), once there is a GSP account. Bank APIs and the Account Aggregator wait.
- Multi-provider AI gateway (Claude, OpenAI, Gemini, Sarvam, self-hosted) with an India-only mode; document reading; obligation extraction; history backfill; Ask.
- Collections, next steps: reminders through the team's own WhatsApp or email.
- Registration and handover, next steps: possession letters, the association handover checklist.
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
- Tally data: read from the files Tally exports, by Lekhara's own Tally import built from scratch (the founder's earlier module does not fit); no Tally API, nothing installed on the customer's machine.
- Team: two founders through v1; a seed raise after three paying customers funds the team for v2 onwards.
- Design: minimal, monochrome, no emojis, no symbols in the branding, text wordmark only.

## Working assumptions (change any time)

- India-only AI processing is the default for every customer.
- No payment details are asked for to start the free month.
- The second segment after developers is certifier firms.
- Land records and court data come from licensed partners, not our own collection.
