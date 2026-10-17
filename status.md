# Horus status

Last updated: 2026-10-17, with the commit "Add the Horus web app".

## What we are building

Horus is an owner-side system for a Karnataka real estate project's outside obligations: what the project owes K-RERA, the escrow bank and its certifiers, the tax department, landowners and lenders. It connects read-only to the systems a builder already uses, reads their documents, keeps the project's real numbers (cost incurred, estimated cost to complete), and prepares every filing, certificate and pack before it is due. People sign; Horus prepares.

Launch market: Bengaluru, then the rest of Karnataka, then other states.

## Done

- Repository set up: customer-facing README, developer guide, CI for API and web.
- API skeleton (Python, FastAPI) with a health check and tests.
- Web app shell (Next.js 16) with the Horus text wordmark and the monochrome design system.
- Karnataka rules pack v1: 37 rates, thresholds and deadlines as dated data, each with its legal basis, source quality and what to confirm it against. Horus settings are marked as settings, not law.
- Money truth engine: cost lines, ledger stages (committed, incurred, paid, retention, advances), anticipated final cost, cost to complete, contingency, land and development totals for RERA, point-in-time positions, and alerts for overruns, low contingency and spending ahead of certified progress.
- Escrow and certification engine: drawable amount (limited by cost incurred and paid, or by the account balance, whichever is lower), 70% deposit check, the ongoing-project deposit rule, next certificate cycle, drafts of the architect's, engineer's and CA's certificates prepared from the books, and the checks a bank or K-RERA auditor would run (amount, figures against the books, progress against cost, dates, CA independence, signatures).
- Real-estate tax engine: the 80% registered-supplier meter (with exclusions, unregistered cement and how much more can still be bought unregistered), GST on development rights for flats unbooked at completion (and the saving per flat sold before then), guidance-value check under s.43CA, TDS on landowner payments under s.194-IC, the MSME 45-day clock, BOCW labour cess and delay interest owed to buyers.
- Obligations engine: one dated list per project of what is owed, to whom, by when and what is at stake, covering withdrawals, deposits, quarterly progress reports, the annual audit, possession and delay interest, the 80% test, GST on development rights, guidance value, landowner TDS, MSME payments and labour cess. Most urgent first.
- Database models (SQLite locally, Postgres-ready) with money stored as exact paise, and an append-only ledger and escrow account that reject edits and deletes.
- HTTP API: Today, projects, money, escrow, tax, units and the rules pack; the full withdrawal workflow (create with drafted certificates, edit figures, sign, submit, release, reject) with the checks enforced.
- Every amount on the obligations list carries a plain label (for example "Can be drawn now", "Reverse charge", "Bill"), and only real exposures are added up as money at stake.
- Demo data: a fictional developer with three Bengaluru projects (a JDA area-share project, an own-land project and a nearly complete JDA revenue-share project), dated relative to today.
- JDA basics: every unit is marked as the developer's or the landowner's; landowners carry their share, deposit and payments, with the TDS check.
- Web app, minimal and monochrome:
  - Today: what needs you, grouped as Needs you now, Money waiting, At risk and Coming up, with the cash you can draw and the money at stake.
  - Projects: progress, final cost against budget, what can be drawn, what needs attention.
  - Project: Overview (key figures, cost signals, what the project owes, cost lines), Escrow (how much can be withdrawn today, worked out step by step, deposits, withdrawal history), Tax and statutory (80% meter, GST on development rights, delay interest, labour cess, guidance value, MSME bills, landowner TDS) and Units and landowners.
  - Withdrawal request: who it is waiting for, the six steps, the three certificates with each figure against the books, the checks, and the next step (send to the bank, record the release or a rejection).
  - Rules: every rate and deadline with its basis and how settled it is.
  - Every form works without JavaScript and explains errors in words. Tested end to end against the demo data.

## In progress

- Nothing in progress. Next up: sign-in, organisations and roles, so each certifier signs from their own seat.

## Left

### MVP

- K-RERA: the quarterly progress report pack and the annual audit pack (deadlines and delay interest are done).
- Downloadable withdrawal pack for the bank (PDF of the three certificates and supporting figures).
- Sign-in, organisations and roles, including certifier seats (today anyone can sign for a certifier, to try the flow).
- Connectors: accounts mailbox (read-only), Tally (read-only), Excel and CRM imports.
- AI document reading, obligation extraction and history backfill.
- Monday briefing and Ask on WhatsApp.
- Database migrations.

### After MVP

- Approval conditions and validity, environmental clearance compliance reports.
- Lender covenants and monitoring packs.
- Landowner statements and view, buyer TDS credit reconciliation, discount guard.
- Handover and closure.
- Other Karnataka cities, then other states.

## Decisions taken

- Flagship: escrow withdrawal certification.
- Stack: Python and FastAPI for the API, Next.js for the web, Postgres in production (SQLite for local development).
- AI: Claude Opus 5.5 by default; cheaper models only after cost and accuracy are measured.
- Design: minimal, monochrome, no emojis, no symbols in the branding, text wordmark only.
