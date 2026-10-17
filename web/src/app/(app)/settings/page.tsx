import type { Metadata } from "next";
import { Suspense } from "react";

import { cancelInvitation, changeRole, inviteMember, removeMember, updateFirm } from "@/app/actions";
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
        {f.state ? <p className="small muted">Registered in {f.state}.</p> : null}
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
