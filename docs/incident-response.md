# Incident response

What we do when Lekhara's security is breached or might have been: who acts, the deadlines the law sets, and the commands to run. Read it once now. In an incident, follow it from the top.

## The deadlines

The clock starts when any of us first notices the incident, or is told about it. Write that time down first.

| By | Who | What | Why |
|---|---|---|---|
| 6 hours | CERT-In | A report, even an incomplete one; details follow | CERT-In directions of 28 April 2022, under s.70B(6) of the IT Act |
| 24 hours | Each affected firm's owner and finance | What happened to the firm's data, and what they should do | Our data processing terms (section 5) |
| Without delay | Each person whose own account data was affected | A plain notice: what, how much, when, what to do | DPDP Rules 2025, rule 7(1), in force from 13 May 2027; follow it now |
| Without delay, then 72 hours | Data Protection Board of India | A first notice, then the full details | DPDP Rules 2025, rule 7(2), same date |

Two kinds of personal data are in Lekhara, and the duties differ:

- **Our users' accounts** (names, emails, phones, sign-ins, the access log). We are the data fiduciary: we tell the people and the Board.
- **What firms keep about others** (buyers, landowners, suppliers' contacts). The firm is the fiduciary and we are its processor: we tell the firm within 24 hours, and help it tell its buyers and the Board.

CERT-In is told in every case. Not reporting can cost up to a year in prison or a ₹1 lakh fine.

## What counts

Anything in CERT-In's list (Annexure I of the directions). For us, at least:

- Anyone seeing or changing a firm's records who should not: another firm, an outsider, a data room visitor beyond what was shared, or our own staff without the firm's consent.
- Unauthorised access to a server, the database, backups or file storage.
- A secret leaked: `LEKHARA_SECRET_KEY`, the database password, SMTP credentials, `LEKHARA_INBOUND_SECRET`, a connector's key, a session token.
- A staff account taken over, or a laptop or phone with access lost.
- Malware on our systems. A virus refused at upload is not an incident; one that got stored is.
- Ransomware, defacement of the website, a denial of service, phishing in Lekhara's name.

When unsure, treat it as an incident. A report that turns out unneeded costs nothing; a late one is a breach of the directions.

## Who does what

- **Incident lead:** whoever noticed it, until they hand it over in writing. Decides, and runs the steps below.
- **Scribe and messages:** the other founder. Keeps the log and writes and sends every notice.
- **CERT-In point of contact:** named to CERT-In in advance (decision 4). Sends the CERT-In report.

Before an incident, keep these in the shared drive, current: both founders' phones; the hosting provider's support line; our lawyer and CA; CERT-In's contact details.

## The first hour

1. **Start the log.** A shared document: every step, with the time in IST, who did it and what they saw. Times in Lekhara's database are UTC; add 5 hours 30 minutes.
2. **Keep the evidence.** Do not wipe or rebuild anything yet. Snapshot the affected servers' disks and the database. Copy the server, proxy and hosting logs somewhere safe.
3. **Stop it spreading.** Use the steps below that fit. Each is in the log with its time.

### Containment steps

Run SQL as the database owner, not as the app's role.

Sign people out:

```sql
DELETE FROM sessions;                                   -- everyone
DELETE FROM sessions WHERE user_id = '<user id>';       -- one person
DELETE FROM sessions WHERE support_org_id IS NOT NULL;  -- every support session
```

Take away access:

```bash
python -m lekhara.staff remove <email>     # a member of staff
python -m lekhara.staff list               # who is staff now
```

```sql
UPDATE users SET is_active = false WHERE email = '<email>';             -- block an account
UPDATE support_grants SET withdrawn_at = now() WHERE withdrawn_at IS NULL;  -- all support consent
UPDATE data_rooms SET revoked_on = CURRENT_DATE WHERE revoked_on IS NULL;   -- close every data room
UPDATE connectors SET status = 'unlinked' WHERE status = 'active';          -- every Tally connector
```

Rotate what may have leaked:

- **The database password.** Rotate it in the hosting provider, then update `LEKHARA_DATABASE_URL` and restart.
- **SMTP credentials.**
- **`LEKHARA_INBOUND_SECRET`.** Rotate it in both Lekhara and the email service.
- **`LEKHARA_SECRET_KEY`.** Rotate it only if it leaked. It seals statement passwords and two-step secrets, and there is no re-sealing tool yet. After a change, firms re-enter their statement passwords, and everyone with two-step sign-in sets it up again. Sign everyone out first.

Block the source:

- Block the attacking addresses at the hosting firewall or load balancer.
- If the leak continues, take the site down behind a maintenance page.

## Find out what happened

The access log (`access_events`) is kept a year and is the first place to look. Every sign-in, failed sign-in, export, document opened, change to who may do what, support visit and staff action is there, with the address and browser.

```sql
-- Everything from one address
SELECT at, who, action, detail, organization_id FROM access_events
WHERE ip = '<address>' ORDER BY at;

-- One firm, over a window (UTC)
SELECT at, who, action, detail, ip FROM access_events
WHERE organization_id = '<firm id>' AND at BETWEEN '<from>' AND '<to>' ORDER BY at;

-- Whole-workspace downloads and opened documents
SELECT at, who, organization_id, detail, ip FROM access_events
WHERE action IN ('workspace_exported', 'document_opened') AND at > '<from>' ORDER BY at;

-- Bursts of failed sign-ins
SELECT ip, count(*) FROM access_events
WHERE action = 'sign_in_failed' AND at > '<from>' GROUP BY ip ORDER BY 2 DESC;
```

Data room visits are in `data_room_visits` (with the visitor, if the room asks for one). Each record's history (`change_entries`) shows who changed what.

Write down:

- which firms, records and people were affected;
- when the incident started;
- how the attacker got in;
- whether it has stopped.

## CERT-In report (6 hours)

- **Email:** incident@cert-in.org.in.
- **Phone:** 1800-11-4949 (toll-free).
- **Fax:** 1800-11-6969.

Check these details, and the current reporting form, on cert-in.org.in each quarter, and before relying on them.

Send what is known by the deadline, and add the rest as it is learned. The report covers:

- the kind of incident, from Annexure I;
- when it happened, and when it was noticed;
- the systems affected;
- what was seen;
- what has been done;
- the point of contact.

CERT-In may ask for logs, so keep logs of every system for at least 180 days, in India:

- **The access log:** kept a year.
- **Server, proxy and hosting logs:** set retention in the hosting provider.

Server clocks must sync with the time servers of NIC (`samay1.nic.in`, `samay2.nic.in`) or NPL, so that times in logs line up.

## Telling firms (24 hours)

Email the owner and finance of each affected firm, then phone them. Write in plain words:

> **Subject: A security incident affecting [firm] in Lekhara**
>
> On [date, time IST] we found that [what happened, in one sentence]. It affected [which records: for example, the units and buyers of Kaveri Heights], from [time] to [time].
>
> We have [what we did: for example, signed everyone out and closed the way in], and reported it to CERT-In.
>
> What you should do:
> - [for example, sign in again and turn on two-step sign-in];
> - [any data room links to send again].
>
> If your buyers' or landowners' personal data was affected, you may need to tell them and the Data Protection Board. We will give you the list of affected records and a draft notice today.
>
> [Name], [phone], [email]

For buyers' data, export the affected records for the firm, and draft its notice to buyers along the lines of the next section.

## Telling people about their own accounts (without delay)

Email each affected person, and show the notice in Lekhara when they sign in. It says:

- what happened, how much of their data, and when;
- the likely consequences for them;
- what we have done;
- what they should do (for example, change their password elsewhere if they reused it);
- whom to contact: the grievance officer, `LEKHARA_GRIEVANCE_EMAIL`.

## Telling the Data Protection Board (without delay, then 72 hours)

Send a first notice at once, through the Board's online platform. Within 72 hours of becoming aware, send the full details:

- the nature, extent, timing and location of the breach;
- its likely impact;
- what caused it;
- what was done to stop it;
- what we found about who was responsible;
- what we did to prevent it happening again;
- how the people affected were told.

If 72 hours is not enough, ask the Board in writing for more time before it runs out.

## After

1. **Restore and check.** Recover from backups or rebuilt servers, then check that a firm sees only its own records (the Postgres isolation test in `tests/test_security.py`, run against production with care, or by hand).
2. **Review within a week.** Write down what happened, why, and what changes. Add the changes to status.md.
3. **Keep the record.** Keep the incident log, the notices sent and CERT-In's tracking number with the company's records.
4. **Update this runbook.** Change it wherever it was wrong or slow.

## Before an incident

- Name the CERT-In point of contact, and send CERT-In its details (decision 4).
- Keep backups, and test a restore every quarter.
- Keep logs for 180 days in India, and sync clocks with the NIC time servers.
- Run a short drill every year: one of us plays the attacker, the other follows this runbook against the clock.
