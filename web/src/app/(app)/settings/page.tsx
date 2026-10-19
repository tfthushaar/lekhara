import type { Metadata } from "next";
import { Suspense } from "react";

import {
  addSender,
  closeFirm,
  deleteAccount,
  keepFirm,
  addStatementPassword,
  cancelInvitation,
  changeRole,
  inviteMember,
  removeMember,
  removeSender,
  removeStatementPassword,
  updateFirm,
} from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Firm, api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Settings" };

const TEAM_ROLES = ["owner", "finance", "accounts", "viewer"];

export default function SettingsPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p>Your firm, your team and your subscription.</p>
        </div>
      </div>
      <Suspense fallback={<p className="loading">Loading your firm</p>}>
        <SettingsView />
      </Suspense>
    </>
  );
}

function accessLine(f: Firm): string {
  if (f.is_sample) return "This is the sample firm. It never expires.";
  if (f.access === "trial")
    return `Free month: ${f.days_left === 1 ? "1 day" : `${f.days_left} days`} left, until ${day(f.trial_ends_on)}.`;
  if (f.access === "active") return "Subscribed.";
  return "Your free month has ended. You can still see and export everything.";
}

async function SettingsView() {
  const f = await api.firm();
  return (
    <>
      <section className="section">
        <div className="section-head">
          <h2>Subscription</h2>
          <p>One subscription for the whole firm: every project and everyone on your team</p>
        </div>
        <p className="status-line" style={{ marginTop: 16 }}>
          {accessLine(f)}
        </p>
        {!f.is_sample && f.access !== "active" ? (
          <p className="small muted" style={{ maxWidth: 640 }}>
            Subscriptions through Razorpay (UPI AutoPay, card or bank mandate, with a GST invoice)
            open shortly. Your data stays in place when you subscribe; nothing needs setting up
            again.
          </p>
        ) : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Your data</h2>
          <p>Everything your firm has in Lekhara, in one file, at any time</p>
        </div>
        <p className="small muted" style={{ maxWidth: 640, marginTop: 16 }}>
          A ZIP file with an Excel workbook (a sheet for every kind of record), the same records as
          JSON for another system, and every document in the vault, every version. It stays open
          even if the subscription lapses.
        </p>
        {f.can_manage ? (
          // A file from a route handler, not a page: a plain link, so the browser downloads it.
          // eslint-disable-next-line @next/next/no-html-link-for-pages
          <a href="/download/organization/export" className="button button-secondary">
            Download everything
          </a>
        ) : (
          <p className="small">The owner or finance can download it.</p>
        )}
      </section>

      <YourAccount f={f} />

      <Suspense fallback={<p className="loading">Loading email settings</p>}>
        <EmailIn />
      </Suspense>

      <section className="section">
        <div className="section-head">
          <h2>Your firm</h2>
          <p>Printed on demand letters, packs and invoices</p>
        </div>
        {f.is_owner ? (
          <ActionForm action={updateFirm} label="Save" pendingLabel="Saving" secondary>
            <div className="field-grid" style={{ marginTop: 16 }}>
              <div className="field">
                <label htmlFor="firm-name">Name</label>
                <input id="firm-name" name="name" defaultValue={f.name} required />
              </div>
              <div className="field">
                <label htmlFor="legal-name">Legal name</label>
                <input id="legal-name" name="legal_name" defaultValue={f.legal_name ?? ""} placeholder="As registered" />
              </div>
              <div className="field">
                <label htmlFor="gstin">GSTIN</label>
                <input id="gstin" name="gstin" defaultValue={f.gstin ?? ""} placeholder="29ABCDE1234F1Z5" />
              </div>
            </div>
          </ActionForm>
        ) : (
          <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
            <li>
              <span className="muted">Name</span>
              <span>{f.name}</span>
            </li>
            <li>
              <span className="muted">Legal name</span>
              <span>{f.legal_name ?? "Not entered"}</span>
            </li>
            <li>
              <span className="muted">GSTIN</span>
              <span>{f.gstin ?? "Not entered"}</span>
            </li>
          </ul>
        )}
        {f.gstin ? (
          <p className="small muted">
            {`From the GSTIN: ${[f.constitution, f.state ? `registered in ${f.state}` : null, f.pan ? `PAN ${f.pan}` : null]
              .filter(Boolean)
              .join(", ")}.`}
            {f.legal_name ? "" : " The legal name is on your GST certificate; enter it above."}
          </p>
        ) : (
          <p className="small muted">Your GSTIN goes on the packs and letters Lekhara prepares, and fills in your state and PAN.</p>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Your team</h2>
          <p>Owner and finance manage the team; only an owner changes roles</p>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {f.members.map((m) => (
              <tr key={m.user_id}>
                <td>
                  {m.name}
                  {m.you ? <span className="small muted"> (you)</span> : null}
                </td>
                <td>{m.email}</td>
                <td>
                  {f.is_owner ? (
                    <ActionForm action={changeRole.bind(null, m.user_id)} label="Change" pendingLabel="Saving" secondary className="inline-form">
                      <select name="role" defaultValue={m.role} aria-label={`Role for ${m.name}`}>
                        {f.roles
                          .filter((r) => TEAM_ROLES.includes(r.value))
                          .map((r) => (
                            <option key={r.value} value={r.value}>
                              {r.label}
                            </option>
                          ))}
                      </select>
                    </ActionForm>
                  ) : (
                    m.role_label
                  )}
                </td>
                <td className="right">
                  {f.is_owner && !m.you ? (
                    <ActionForm action={removeMember.bind(null, m.user_id)} label="Remove" pendingLabel="Removing" secondary />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Certifiers</h2>
          <p>Architects, engineers and CAs. They see only the projects they certify, and join free.</p>
        </div>
        {f.certifiers.length === 0 ? (
          <p className="empty">No certifier has joined yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Firm</th>
                <th>Projects</th>
              </tr>
            </thead>
            <tbody>
              {f.certifiers.map((c) => (
                <tr key={`${c.user_id}-${c.role_label}`}>
                  <td>
                    {c.name}
                    <br />
                    <span className="small muted">{c.email}</span>
                  </td>
                  <td>{c.role_label}</td>
                  <td>{c.firm}</td>
                  <td>{c.projects.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {f.can_manage ? (
        <section className="section">
          <div className="section-head">
            <h2>Invite someone</h2>
            <p>They get an email with a link; you also get the link to send on WhatsApp</p>
          </div>
          {f.invitations.length > 0 ? (
            <table className="table" style={{ marginBottom: 24 }}>
              <thead>
                <tr>
                  <th>Waiting to accept</th>
                  <th>Role</th>
                  <th>Link works until</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {f.invitations.map((i) => (
                  <tr key={i.id}>
                    <td>{i.email}</td>
                    <td>{i.role_label}</td>
                    <td className="nowrap">{day(i.expires_on)}</td>
                    <td className="right">
                      <ActionForm action={cancelInvitation.bind(null, i.id)} label="Cancel" pendingLabel="Cancelling" secondary />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <ActionForm action={inviteMember} label="Send the invitation" pendingLabel="Sending">
            <div className="field-grid">
              <div className="field">
                <label htmlFor="invite-email">Email</label>
                <input id="invite-email" name="email" type="email" required />
              </div>
              <div className="field">
                <label htmlFor="invite-role">Role</label>
                <select id="invite-role" name="role" defaultValue="accounts">
                  {f.roles
                    .filter((r) => f.is_owner || r.value !== "owner")
                    .map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                </select>
              </div>
            </div>
            {f.projects.length > 0 ? (
              <>
                <p className="small muted" style={{ marginBottom: 8 }}>
                  For an architect, engineer or CA, choose the projects they certify.
                </p>
                <div className="checks">
                  {f.projects.map((p) => (
                    <label key={p.id}>
                      <input type="checkbox" name="project_ids" value={p.id} /> {p.name}
                    </label>
                  ))}
                </div>
              </>
            ) : null}
          </ActionForm>
        </section>
      ) : null}
    </>
  );
}

async function EmailIn() {
  const e = await api.inboundSettings();
  return (
    <section className="section">
      <div className="section-head">
        <h2>Email in</h2>
        <p>Each project has its own address, shown on its Import page; these settings cover them all</p>
      </div>
      <div className="field-grid" style={{ marginTop: 12 }}>
        <div>
          <p className="row-title">Trusted senders</p>
          <p className="small muted" style={{ maxWidth: 420 }}>
            Mail from your team is read at once. So is mail from these: a bank&apos;s statement service, your accountant,
            a contractor. Anyone else&apos;s waits for you to allow it. A whole domain is written as @bank.example.
          </p>
          {e.senders.length === 0 ? (
            <p className="empty">None yet.</p>
          ) : (
            <ul className="calc" style={{ maxWidth: 420 }}>
              {e.senders.map((t) => (
                <li key={t.id}>
                  <span>{t.address}</span>
                  {e.can_edit ? <ActionForm action={removeSender.bind(null, t.id)} label="Remove" pendingLabel="Removing" secondary /> : null}
                </li>
              ))}
            </ul>
          )}
          {e.can_edit ? (
            <details className="disclosure">
              <summary>Add a trusted sender</summary>
              <ActionForm action={addSender} label="Trust this sender" pendingLabel="Adding" secondary>
                <div className="field">
                  <label htmlFor="sender-address">Email address or @domain</label>
                  <input id="sender-address" name="address" placeholder="statements@bank.example" required />
                </div>
              </ActionForm>
            </details>
          ) : null}
        </div>
        <div>
          <p className="row-title">Statement passwords</p>
          <p className="small muted" style={{ maxWidth: 420 }}>
            Banks lock emailed statements with a password, such as your customer ID or a date of birth. Give it once and
            Lekhara opens every statement locked with it. It is kept sealed and never shown again.
          </p>
          {e.passwords.length === 0 ? (
            <p className="empty">None yet.</p>
          ) : (
            <ul className="calc" style={{ maxWidth: 420 }}>
              {e.passwords.map((x) => (
                <li key={x.id}>
                  <span>{`${x.label}, added ${x.added_on}`}</span>
                  {e.can_edit ? (
                    <ActionForm action={removeStatementPassword.bind(null, x.id)} label="Remove" pendingLabel="Removing" secondary />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {e.can_edit ? (
            <details className="disclosure">
              <summary>Add a statement password</summary>
              <ActionForm action={addStatementPassword} label="Keep the password" pendingLabel="Keeping it" secondary>
                <div className="field">
                  <label htmlFor="password-label">For which account or bank</label>
                  <input id="password-label" name="label" placeholder="HDFC collection account" required />
                </div>
                <div className="field">
                  <label htmlFor="password-value">Password</label>
                  <input id="password-value" name="password" type="password" autoComplete="off" required />
                </div>
              </ActionForm>
            </details>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function YourAccount({ f }: { f: Firm }) {
  return (
    <section className="section">
      <div className="section-head">
        <h2>Your account and your firm&apos;s data</h2>
        <p>
          <a href="/legal/privacy" className="link-action">
            Privacy notice
          </a>
        </p>
      </div>
      {f.delete_after ? (
        <p className="notice" style={{ marginTop: 16 }}>
          {`The firm's account is closing: its data will be deleted after ${f.delete_after}. Download everything before then.`}
        </p>
      ) : null}
      {f.can_manage ? (
        <Suspense fallback={null}>
          <AccessLogView />
        </Suspense>
      ) : null}
      <details className="disclosure">
        <summary>Delete my account</summary>
        <p className="small muted" style={{ maxWidth: 640 }}>
          Your name and email are taken out of Lekhara and you are signed out. What you did stays in the records, under
          &quot;A former user&quot;. If you are the firm&apos;s only owner, make someone else an owner first.
        </p>
        <ActionForm action={deleteAccount} label="Delete my account" pendingLabel="Deleting" secondary>
          <div className="field" style={{ maxWidth: 360 }}>
            <label htmlFor="delete-password">Your password</label>
            <input id="delete-password" name="password" type="password" autoComplete="current-password" required />
          </div>
        </ActionForm>
      </details>
      {f.is_owner && !f.is_sample ? (
        f.delete_after ? (
          <div style={{ marginTop: 16 }}>
            <ActionForm action={keepFirm} label="Keep the firm's account open" pendingLabel="Saving" secondary />
          </div>
        ) : (
          <details className="disclosure">
            <summary>Close the firm&apos;s account</summary>
            <p className="small muted" style={{ maxWidth: 640 }}>
              Everything stays readable and downloadable for 30 days, and can be kept by changing your mind. After that, all
              of the firm&apos;s projects, records and documents are deleted, and the people who worked only for it are
              taken out.
            </p>
            <ActionForm action={closeFirm} label="Close the firm's account" pendingLabel="Closing" secondary>
              <div className="field" style={{ maxWidth: 360 }}>
                <label htmlFor="close-confirm">{`Type ${f.name} to confirm`}</label>
                <input id="close-confirm" name="confirm" autoComplete="off" required />
              </div>
            </ActionForm>
          </details>
        )
      ) : null}
    </section>
  );
}

const ACTION_LABEL: Record<string, string> = {
  sign_in: "Signed in",
  sign_in_failed: "Failed sign-in",
  signed_up: "Signed up",
  password_reset: "Reset the password",
  terms_accepted: "Accepted the terms",
  workspace_exported: "Downloaded everything",
  document_opened: "Opened a document",
  invitation_sent: "Invited someone",
  invitation_accepted: "Joined",
  role_changed: "Changed a role",
  member_removed: "Removed someone",
  account_deleted: "Deleted their account",
  firm_close_requested: "Asked to close the firm",
  firm_close_cancelled: "Kept the firm open",
};

async function AccessLogView() {
  const log = await api.accessLog();
  return (
    <details className="disclosure">
      <summary>{`Access log (${log.events.length} recent)`}</summary>
      <p className="small muted">{`Sign-ins, downloads and changes to who may do what, kept ${log.keep_days} days.`}</p>
      {log.events.length === 0 ? (
        <p className="empty">Nothing yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>What</th>
              <th>From</th>
            </tr>
          </thead>
          <tbody>
            {log.events.slice(0, 100).map((e, i) => (
              <tr key={`${e.at}-${i}`}>
                <td className="nowrap">{e.at.replace("T", ", ").slice(0, 17)}</td>
                <td>{e.who ?? ""}</td>
                <td>
                  {ACTION_LABEL[e.action] ?? e.action}
                  {e.detail ? <span className="small muted">{` ${e.detail}`}</span> : null}
                </td>
                <td className="small muted">{e.ip ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  );
}
