# Horus status

Last updated: 2026-10-17, with the commit "Set up the Horus repository".

## What we are building

Horus is an owner-side system for a Karnataka real estate project's outside obligations: what the project owes K-RERA, the escrow bank and its certifiers, the tax department, landowners and lenders. It connects read-only to the systems a builder already uses, reads their documents, keeps the project's real numbers (cost incurred, estimated cost to complete), and prepares every filing, certificate and pack before it is due. People sign; Horus prepares.

Launch market: Bengaluru, then the rest of Karnataka, then other states.

## Done

- Repository set up: customer-facing README, developer guide, CI for API and web.
- API skeleton (Python, FastAPI) with a health check and tests.
- Web app shell (Next.js 16) with the Horus text wordmark and the monochrome design system.

## In progress

- Rules pack (Karnataka v1) and the money truth engine.

## Left

### MVP

- Rules pack: every rate, threshold and deadline as versioned data with legal basis and source quality.
- Money truth engine: cost lines, append-only ledger, cost incurred, estimated cost to complete, anticipated final cost, overrun and cost-ahead-of-progress alerts.
- Escrow and certification: drawable amount, deposit check, withdrawal requests, architect, engineer and CA certificates, consistency checks, sign-off, bank submission and release.
- K-RERA: quarterly progress report deadlines and pack, delay interest exposure.
- Real-estate tax: 80% registered-procurement meter, GST on development rights at completion, guidance-value check (s.43CA), TDS to landowners (s.194-IC), MSME 45-day clock, BOCW cess.
- JDA landowner register and the developer or landowner split on every unit.
- Obligations calendar and the Today screen.
- Database models, demo data and the HTTP API.
- Web screens: Today, Projects, Project (overview, escrow, tax, units), Withdrawal request.
- Sign-in, organisations and roles, including certifier seats.
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
