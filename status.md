# Horus status

Last updated: 2026-10-17, with the commit "Add database migrations".

## What we are building

Horus is an owner-side platform for Karnataka builders, in two layers:

1. **Only in Horus:** everything outside the ERP. What a project owes, and is owed by, K-RERA, the escrow bank and its certifiers, the tax department, landowners, buyers' home-loan banks, lenders, authorities, buyers in disputes, the sub-registrar and the residents' association. Escrow certification, K-RERA, real-estate tax, JDA landowners, registration and handover, disputes, home-loan disbursements, plotted layouts, guarantees and insurance, approval conditions, workspaces for certifiers, lenders and landowners, India-native feasibility, delay prediction.
2. **Also in Horus, done better:** the inside modules a builder needs if they have no ERP or CRM. Sales and bookings, collections, channel partners, agreements and e-stamping, a buyer portal, payables on WhatsApp, contractor billing, procurement, an approvals tracker, site progress from photos, snags and defects, title due diligence, notices, estimation, a document vault, board packs. Each can run in coexist mode, reading from the customer's own tool instead.

Horus connects read-only, reads documents with AI from several providers (with an India-only option), keeps two ledgers (obligations and money), and prepares every filing, certificate and pack before it is due. People sign; Horus prepares.

Launch market: Bengaluru, then the rest of Karnataka, then other states. The full plan is v6 (kept outside the repository).

## Done

- Repository set up: customer-facing README, developer guide, CI for API and web.
- API skeleton (Python, FastAPI) with a health check and tests.
- Web app shell (Next.js 16) with the Horus text wordmark and the monochrome design system.
- Karnataka rules pack v1: 37 rates, thresholds and deadlines as dated data, each with its legal basis, source quality and what to confirm it against. Horus settings are marked as settings, not law.
- Money truth engine: cost lines, ledger stages (committed, incurred, paid, retention, advances), anticipated final cost, cost to complete, contingency, land and development totals for RERA, point-in-time positions, and alerts for overruns, low contingency and spending ahead of certified progress.
- Escrow and certification engine: drawable amount (limited by cost incurred and paid, or by the account balance, whichever is lower), 70% deposit check, the ongoing-project deposit rule, next certificate cycle, drafts of the architect's, engineer's and CA's certificates prepared from the books, and the checks a bank or K-RERA auditor would run.
- Real-estate tax engine: the 80% registered-supplier meter, GST on development rights at completion, the s.43CA guidance-value check, s.194-IC landowner TDS, the MSME 45-day clock, BOCW labour cess and delay interest owed to buyers.
- Obligations engine: one dated, plain-language list per project of what is owed, to whom, by when and what is at stake, most urgent first. Every amount carries a label, and only real exposures count as money at stake.
- Database models (SQLite locally, Postgres-ready) with money stored as exact paise, and an append-only ledger and escrow account.
- HTTP API: Today, projects, money, escrow, tax, units and the rules pack; the full withdrawal workflow with its checks enforced.
- Demo data: a fictional developer with three Bengaluru projects, dated relative to today.
- JDA basics: every unit is marked as the developer's or the landowner's; landowners carry their share, deposit and payments, with the TDS check.
- Web app: Today, Projects, a project's Overview, Escrow, Tax and statutory, and Units and landowners tabs, the Withdrawal request and Rules. Every form works without JavaScript.
- Database migrations (Alembic, inside the package). The API brings the schema up to date on start; the demo seed builds the schema through migrations; a test fails if the migrated schema and the models ever disagree.

## In progress

- Sign-in, organisations, roles and certifier seats.

## Left

### v1: pilot-ready (two founders)

- Sign-in, organisations, roles and certifier seats, so each certifier signs from their own access.
- Integration of the founder's existing Tally file import module (details to come).
- Mailbox connector (read-only), Excel and CRM imports.
- Multi-provider AI gateway (Claude, OpenAI, Gemini, Sarvam, self-hosted) with an India-only mode; document reading; obligation extraction; history backfill; Ask.
- Collections: payment plans, demand letters raised when a stage is certified, receipt matching, the 70/30 split check.
- Registration and handover desk.
- Disputes and orders desk.
- Document vault.
- Bank withdrawal pack (PDF); quarterly progress report and annual audit packs.

### v2

- Home-loan disbursements, guarantees and insurance, approval conditions and environmental reports, vendor check.
- Certifier practice workspace.
- Buyer portal, payables on WhatsApp, contractor billing, approvals tracker, notices.
- Kannada voice, the Monday briefing, back-office agents.

### v3

- Plotted layouts, lender and independent-engineer workspace, landowner view, market intelligence, delay prediction.
- Sales and bookings, channel partners, agreements and e-execution, site progress verification, snags and defects, board packs.
- Other Karnataka cities.

### v4

- Feasibility and land-deal underwriting, procurement, title due diligence, estimation from drawings, Horus Lite, other states.

## Decisions taken

- Plan v6 approved on 2026-10-17 ("continue building").
- Flagship: escrow withdrawal certification.
- Two layers: features only Horus has, plus standard modules done better, each able to coexist with the customer's own tools.
- Stack: Python and FastAPI for the API, Next.js for the web, Postgres in production (SQLite for local development).
- AI: several providers behind one gateway, chosen per task by measured accuracy, cost and residency; never a single provider.
- Tally data: through the founder's existing Tally file import module, not the Tally API.
- Team: two founders through v1; a seed raise after three paying customers funds the team for v2 onwards.
- Design: minimal, monochrome, no emojis, no symbols in the branding, text wordmark only.

## Working assumptions (change any time)

- India-only AI processing is the default for every customer.
- The second segment after developers is certifier firms.
- Land records and court data come from licensed partners, not our own collection.
