import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { extendTrial, openSupport, recordPayment, removePayment } from "@/app/actions";
import { standing } from "@/app/(app)/admin/standing";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";
import { day, inrFull, moment } from "@/lib/format";

export const metadata: Metadata = { title: "Firm" };

const DID: Record<string, string> = {
  staff_trial_extended: "Extended the free month",
  staff_payment_recorded: "Recorded a payment",
  staff_payment_removed: "Removed a payment",
  support_opened: "Opened their workspace as support",
};

export default function StaffFirmPage({ params }: PageProps<"/admin/firms/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the firm</p>}>
      <FirmView params={params} />
    </Suspense>
  );
}

async function FirmView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const f = await api.staffFirm(id);
  return (
    <>
      <p className="small">
        <Link href="/admin">All firms</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>{f.name}</h1>
          <p>{[standing(f), f.created_on ? `started ${day(f.created_on)}` : "", f.gstin ? `GSTIN ${f.gstin}` : ""].filter(Boolean).join(", ")}</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Support</h2>
          <p>Their workspace, read-only, only while they allow it</p>
        </div>
        {f.support_until ? (
          <>
            <p className="status-line" style={{ marginTop: 16 }}>
              {`They allow support until ${moment(f.support_until)}. Every page you open goes into their access log.`}
            </p>
            <ActionForm action={openSupport.bind(null, f.id)} label="See their workspace" pendingLabel="Opening" />
          </>
        ) : (
          <p className="small muted" style={{ marginTop: 16, maxWidth: 640 }}>
            They have not allowed support. Their owner or finance can allow it in Settings, for a few days at a time.
          </p>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>People</h2>
          <p>{`${f.members.length} in the firm`}</p>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Two-step</th>
              <th>Last sign-in</th>
            </tr>
          </thead>
          <tbody>
            {f.members.map((m) => (
              <tr key={m.email}>
                <td>{m.name}</td>
                <td>{m.email}</td>
                <td>{m.role}</td>
                <td>{m.two_step ? "On" : "Off"}</td>
                <td className="nowrap">{moment(m.last_sign_in)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Projects</h2>
          <p>{f.projects_list.length === 1 ? "1 project" : `${f.projects_list.length} projects`}</p>
        </div>
        {f.projects_list.length === 0 ? (
          <p className="empty">No projects yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Project</th>
                <th>K-RERA registration</th>
                <th className="right">Units</th>
              </tr>
            </thead>
            <tbody>
              {f.projects_list.map((p) => (
                <tr key={p.registration}>
                  <td>{p.name}</td>
                  <td>{p.registration}</td>
                  <td className="right num">{p.units}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {!f.is_sample ? (
        <section className="section">
          <div className="section-head">
            <h2>Payments</h2>
            <p>Recorded here until Razorpay brings them in by itself</p>
          </div>
          {f.payments.length === 0 ? (
            <p className="empty">Nothing paid yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Paid on</th>
                  <th className="right">Amount</th>
                  <th>How</th>
                  <th>Reference</th>
                  <th>Pays for</th>
                  <th>Recorded by</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {f.payments.map((p) => (
                  <tr key={p.id}>
                    <td className="nowrap">{day(p.paid_on)}</td>
                    <td className="right num">{inrFull(p.amount)}</td>
                    <td>{p.method}</td>
                    <td>{p.reference}</td>
                    <td className="nowrap">{`${day(p.covers_from)} to ${day(p.covers_to)}`}</td>
                    <td className="small">{p.recorded_by}</td>
                    <td className="right">
                      <ActionForm action={removePayment.bind(null, p.id)} label="Remove" pendingLabel="Removing" secondary />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <details className="disclosure">
            <summary>Record a payment</summary>
            <ActionForm action={recordPayment.bind(null, f.id)} label="Record the payment" pendingLabel="Recording">
              <div className="field-grid" style={{ marginTop: 12 }}>
                <div className="field">
                  <label htmlFor="amount">Amount received, GST included</label>
                  <input id="amount" name="amount" required placeholder="11,800" />
                </div>
                <div className="field">
                  <label htmlFor="paid_on">Paid on</label>
                  <input id="paid_on" name="paid_on" type="date" required />
                </div>
                <div className="field">
                  <label htmlFor="method">How</label>
                  <select id="method" name="method" required defaultValue="">
                    <option value="" disabled>
                      Choose
                    </option>
                    {f.methods.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="reference">UTR, UPI reference or cheque number</label>
                  <input id="reference" name="reference" required />
                </div>
                <div className="field">
                  <label htmlFor="covers_from">Pays for, from</label>
                  <input id="covers_from" name="covers_from" type="date" required />
                </div>
                <div className="field">
                  <label htmlFor="covers_to">to</label>
                  <input id="covers_to" name="covers_to" type="date" required />
                </div>
              </div>
              <div className="field">
                <label htmlFor="note">Note (optional)</label>
                <input id="note" name="note" />
              </div>
            </ActionForm>
          </details>
        </section>
      ) : null}

      {!f.is_sample && f.access !== "active" ? (
        <section className="section">
          <div className="section-head">
            <h2>Free month</h2>
            <p>{f.trial_ends_on ? `Runs to ${day(f.trial_ends_on)}` : "Not started"}</p>
          </div>
          <ActionForm action={extendTrial.bind(null, f.id)} label="Extend it" pendingLabel="Extending" secondary>
            <div className="field-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label htmlFor="ends_on">New last day</label>
                <input id="ends_on" name="ends_on" type="date" required />
              </div>
              <div className="field">
                <label htmlFor="reason">Why, for the record</label>
                <input id="reason" name="reason" required placeholder="Waiting for their Tally export" />
              </div>
            </div>
          </ActionForm>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>What we did</h2>
          <p>Also in the firm&apos;s own access log</p>
        </div>
        {f.staff_log.length === 0 ? (
          <p className="empty">Nothing yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
              </tr>
            </thead>
            <tbody>
              {f.staff_log.map((e, i) => (
                <tr key={`${e.at}-${i}`}>
                  <td className="nowrap">{moment(e.at)}</td>
                  <td>{e.who ?? ""}</td>
                  <td>
                    {DID[e.action] ?? e.action}
                    {e.detail ? <span className="small muted">{` ${e.detail}`}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
