import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { addHearing, addOrder, addPayment, cancelCaseBooking, updateCase } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { LinkedDocuments } from "@/components/documents";
import { type CaseDetail, type CaseOrder, api } from "@/lib/api";
import { day, inr, inrFull } from "@/lib/format";

export const metadata: Metadata = { title: "Case" };

export default function CasePage({ params }: PageProps<"/cases/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the case</p>}>
      <CaseView params={params} />
    </Suspense>
  );
}

function positive(value: string | null | undefined): boolean {
  return value !== null && value !== undefined && Number(value) > 0;
}

async function CaseView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await api.case(id);
  const base = `/projects/${c.project_id}`;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{c.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/disputes`}>Disputes</Link>
          </p>
          <h1>
            {c.forum_label} {c.case_number}
          </h1>
          <p>
            Brought by {c.complainant}
            {c.unit ? `, unit ${c.unit}` : ""}. Seeks: {c.relief_label.toLowerCase()}.
          </p>
        </div>
      </div>

      <p className="status-line">
        {c.status_label}
        {c.next ? `. Next: ${c.next.text.replace(` in the case by ${c.complainant}`, "")}, ${day(c.next.on)}` : ""}
      </p>

      <div className="stats">
        <div className="stat">
          <p className="stat-label">Could still cost</p>
          <p className="stat-value">{c.open ? inr(c.at_stake) : "Nothing"}</p>
          <p className="stat-note">
            {!c.open
              ? `Closed${c.closed_on ? ` on ${day(c.closed_on)}` : ""}`
              : c.settlement.agreed
                ? "What is left of the agreed settlement"
                : c.ordered
                  ? "What the orders direct, less what is paid"
                  : "If it goes against you, at today's figures"}
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Ordered</p>
          <p className="stat-value">{c.orders.length ? inr(c.ordered_total) : "No order yet"}</p>
          <p className="stat-note">{positive(c.paid) ? `${inr(c.paid)} paid so far` : "Nothing paid yet"}</p>
        </div>
        <div className="stat">
          <p className="stat-label">The buyer has paid</p>
          <p className="stat-value">{c.unit ? inr(c.buyer_paid) : "Not a buyer"}</p>
          <p className="stat-note">
            {c.possession_due_on ? `Possession was promised for ${day(c.possession_due_on)}` : ""}
          </p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>What it could cost</h2>
          <p>Worked out from what the buyer paid, before any order</p>
        </div>
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          {positive(c.estimate.principal) ? (
            <li>
              <span>The buyer&apos;s money returned (the unit comes back to sell again)</span>
              <span className="num">{inrFull(c.estimate.principal)}</span>
            </li>
          ) : null}
          {positive(c.estimate.interest) ? (
            <li>
              <span>Interest at {c.rate_pct}% a year</span>
              <span className="num">{inrFull(c.estimate.interest)}</span>
            </li>
          ) : null}
          {positive(c.estimate.other) ? (
            <li>
              <span>Amount claimed</span>
              <span className="num">{inrFull(c.estimate.other)}</span>
            </li>
          ) : null}
          <li className="calc-total">
            <span>Total</span>
            <span className="num">{inrFull(c.estimate.total)}</span>
          </li>
        </ul>
        <p className="small muted" style={{ marginTop: 12 }}>
          {c.estimate.basis} The rate is SBI MCLR plus 2%; confirm it on the Rules page.
        </p>
      </section>

      <SettlementSection c={c} />

      <section className="section">
        <div className="section-head">
          <h2>Orders</h2>
          <p>What each order directs, when to comply and the last day to appeal</p>
        </div>
        {c.orders.length === 0 ? (
          <p className="empty">No order has been passed.</p>
        ) : (
          <ul className="rows">
            {c.orders.map((o) => (
              <OrderRow key={o.id} o={o} appealed={c.appealed_on} />
            ))}
          </ul>
        )}
        {c.can_edit && c.open ? (
          <details className="disclosure">
            <summary>Record an order</summary>
            <ActionForm action={addOrder.bind(null, c.id)} label="Record the order" pendingLabel="Saving">
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="kind">What it directs</label>
                  <select id="kind" name="kind" defaultValue={c.relief === "refund" ? "refund" : "delay_interest"}>
                    {c.choices.order_kinds.map((k) => (
                      <option key={k.value} value={k.value}>
                        {k.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="amount">Amount (leave empty for a refund or interest)</label>
                  <input id="amount" name="amount" inputMode="decimal" />
                </div>
                <div className="field">
                  <label htmlFor="ordered_on">Order dated</label>
                  <input id="ordered_on" name="ordered_on" type="date" required />
                </div>
                <div className="field">
                  <label htmlFor="received_on">Copy received on</label>
                  <input id="received_on" name="received_on" type="date" />
                </div>
                <div className="field">
                  <label htmlFor="comply_by">Comply by</label>
                  <input id="comply_by" name="comply_by" type="date" />
                </div>
                <div className="field field-wide">
                  <label htmlFor="order-summary">What the order says</label>
                  <textarea id="order-summary" name="summary" rows={2} />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Hearings</h2>
          <p>{c.next_hearing_on ? `Next hearing on ${day(c.next_hearing_on)}` : "No hearing is fixed"}</p>
        </div>
        {c.hearings.length === 0 ? (
          <p className="empty">No hearing has been recorded.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Hearing</th>
                <th>What happened</th>
              </tr>
            </thead>
            <tbody>
              {c.hearings.map((h) => (
                <tr key={`${h.held_on}-${h.purpose}`}>
                  <td className="nowrap">{day(h.held_on)}</td>
                  <td>{h.purpose}</td>
                  <td>{h.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {c.can_edit && c.open ? (
          <details className="disclosure">
            <summary>Record a hearing</summary>
            <ActionForm action={addHearing.bind(null, c.id)} label="Record the hearing" pendingLabel="Saving">
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="held_on">Held on</label>
                  <input id="held_on" name="held_on" type="date" required />
                </div>
                <div className="field">
                  <label htmlFor="purpose">Hearing</label>
                  <input id="purpose" name="purpose" placeholder="Arguments" />
                </div>
                <div className="field">
                  <label htmlFor="hearing-next">Next hearing</label>
                  <input id="hearing-next" name="next_hearing_on" type="date" />
                </div>
                <div className="field field-wide">
                  <label htmlFor="outcome">What happened</label>
                  <textarea id="outcome" name="outcome" rows={2} />
                </div>
              </div>
              <label className="field-check">
                <input type="checkbox" name="order_reserved" /> The order is reserved
              </label>
            </ActionForm>
          </details>
        ) : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Payments</h2>
          <p>What you have paid under the orders or a settlement</p>
        </div>
        {c.payments.length === 0 ? (
          <p className="empty">Nothing has been paid.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Reference</th>
                <th className="right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {c.payments.map((p) => (
                <tr key={`${p.paid_on}-${p.amount}-${p.reference}`}>
                  <td className="nowrap">{day(p.paid_on)}</td>
                  <td>{p.reference}</td>
                  <td className="right num">{inrFull(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {c.can_edit && c.open && (c.orders.length > 0 || c.settlement.agreed) ? (
          <details className="disclosure">
            <summary>Record a payment</summary>
            <ActionForm action={addPayment.bind(null, c.id)} label="Record the payment" pendingLabel="Saving">
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="paid_on">Paid on</label>
                  <input id="paid_on" name="paid_on" type="date" required />
                </div>
                <div className="field">
                  <label htmlFor="pay-amount">Amount (rupees)</label>
                  <input
                    id="pay-amount"
                    name="amount"
                    inputMode="decimal"
                    required
                    defaultValue={c.settlement.agreed ? c.at_stake : c.owed}
                  />
                </div>
                <div className="field">
                  <label htmlFor="reference">Bank reference</label>
                  <input id="reference" name="reference" />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
        {c.booking?.cancelled_on ? (
          <p className="status-line" style={{ marginTop: 16 }}>
            {`The booking of unit ${c.booking.unit} was cancelled on ${day(c.booking.cancelled_on)}; the unit can be sold again.`}
          </p>
        ) : null}
        {c.booking?.refund_paid && c.booking.registered && !c.booking.cancelled_on ? (
          <p className="notice" style={{ marginTop: 16 }}>
            {`The refund is paid, but unit ${c.booking.unit} is registered in the buyer's name. Taking it back needs a cancellation deed; ask your lawyer.`}
          </p>
        ) : null}
        {c.booking?.can_cancel && c.can_edit ? (
          <div className="notice" style={{ marginTop: 16 }}>
            <p>{`The refund is paid. Cancel the booking of unit ${c.booking.unit} so it can be sold again; what the buyer paid stays on record under this case.`}</p>
            <div style={{ marginTop: 12 }}>
              <ActionForm action={cancelCaseBooking.bind(null, c.id)} label={`Cancel the booking of unit ${c.booking.unit}`} pendingLabel="Cancelling" secondary />
            </div>
          </div>
        ) : null}
      </section>

      <Suspense fallback={null}>
        <LinkedDocuments
          linkType="case"
          linkId={c.id}
          category="order"
          hint="The complaint, your reply, orders and settlement terms"
        />
      </Suspense>

      <section className="section">
        <div className="section-head">
          <h2>The case</h2>
        </div>
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          <Fact label="Filed on" value={day(c.filed_on)} />
          <Fact label="Notice received on" value={day(c.notice_received_on)} />
          <Fact label="Reply due by" value={day(c.reply_due_on)} />
          <Fact label="Reply filed on" value={c.reply_filed_on ? day(c.reply_filed_on) : "Not filed"} />
          <Fact label="Amount claimed" value={c.claim_amount ? inrFull(c.claim_amount) : "None stated"} />
          <Fact label="Your lawyer" value={c.lawyer ?? "Not recorded"} />
          {c.appealed_on ? <Fact label="Appealed on" value={day(c.appealed_on)} /> : null}
        </ul>
        {c.summary ? <p style={{ marginTop: 16, maxWidth: 640 }}>{c.summary}</p> : null}
        {c.can_edit ? (
          <details className="disclosure">
            <summary>Change the details</summary>
            <ActionForm action={updateCase.bind(null, c.id)} label="Save the changes" pendingLabel="Saving" secondary>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="status">Status</label>
                  <select id="status" name="status" defaultValue={c.status}>
                    {c.choices.statuses.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
                <DateInput name="reply_due_on" label="Reply due by" value={c.reply_due_on} />
                <DateInput name="reply_filed_on" label="Reply filed on" value={c.reply_filed_on} />
                <DateInput name="next_hearing_on" label="Next hearing" value={c.next_hearing_on} />
                <DateInput name="appealed_on" label="Appealed on" value={c.appealed_on} />
                <div className="field">
                  <label htmlFor="edit-claim">Amount claimed (rupees)</label>
                  <input id="edit-claim" name="claim_amount" inputMode="decimal" defaultValue={c.claim_amount ?? ""} />
                </div>
                <div className="field">
                  <label htmlFor="edit-lawyer">Your lawyer</label>
                  <input id="edit-lawyer" name="lawyer" defaultValue={c.lawyer ?? ""} />
                </div>
                <div className="field field-wide">
                  <label htmlFor="edit-summary">What the complaint says</label>
                  <textarea id="edit-summary" name="summary" rows={3} defaultValue={c.summary ?? ""} />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
      </section>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <li>
      <span className="muted">{label}</span>
      <span>{value}</span>
    </li>
  );
}

function DateInput({ name, label, value }: { name: string; label: string; value: string | null }) {
  return (
    <div className="field">
      <label htmlFor={`edit-${name}`}>{label}</label>
      <input id={`edit-${name}`} name={name} type="date" defaultValue={value ?? ""} />
    </div>
  );
}

function OrderRow({ o, appealed }: { o: CaseOrder; appealed: string | null }) {
  const settled = Number(o.outstanding) <= 0;
  return (
    <li className="row">
      <div>
        <span className={settled ? "tag tag-done" : o.overdue ? "tag tag-overdue" : "tag tag-soon"}>
          {settled ? "Paid" : o.overdue ? "Past its date" : appealed ? "Under appeal" : "To pay"}
        </span>
      </div>
      <div>
        <p className="row-title">{o.label}</p>
        <p className="row-detail">
          Dated {day(o.ordered_on)}
          {o.comply_by ? `. Comply by ${day(o.comply_by)}` : ""}.
          {o.worked_out ? " Lekhara works out the amount from the buyer's payments, to today; interest runs until it is paid." : ""}
        </p>
        {o.summary ? <p className="row-detail">{o.summary}</p> : null}
        {o.appeal_by && !settled && !appealed ? (
          <p className="row-meta">
            An appeal to the {o.appeal_to} must be filed by {day(o.appeal_by)}
            {o.appeal_deposit ? `, with ${inr(o.appeal_deposit)} deposited first` : ""}. Confirm
            the time limit with your lawyer.
          </p>
        ) : null}
      </div>
      <div className="row-side">
        <p className="amount-label">{settled ? "Paid" : "Still to pay"}</p>
        <p className="row-amount">{inr(settled ? o.paid : o.outstanding)}</p>
        {positive(o.paid) && !settled ? <p className="row-meta">{inr(o.paid)} paid</p> : null}
      </div>
    </li>
  );
}

function SettlementSection({ c }: { c: CaseDetail }) {
  const s = c.settlement;
  const amount = s.agreed ?? s.offered;
  return (
    <section className="section">
      <div className="section-head">
        <h2>Settlement</h2>
        <p>Settling can cost less than fighting; Lekhara shows the difference</p>
      </div>
      {amount ? (
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          {s.offered ? (
            <li>
              <span>Offered</span>
              <span className="num">{inrFull(s.offered)}</span>
            </li>
          ) : null}
          {s.agreed ? (
            <li>
              <span>Agreed</span>
              <span className="num">{inrFull(s.agreed)}</span>
            </li>
          ) : null}
          {s.saving ? (
            <li className="calc-total">
              <span>{Number(s.saving) >= 0 ? "Less than the order or the estimate by" : "More than the order or the estimate by"}</span>
              <span className="num">{inrFull(String(Math.abs(Number(s.saving))))}</span>
            </li>
          ) : null}
        </ul>
      ) : (
        <p className="empty">No settlement has been offered.</p>
      )}
      {c.can_edit && c.open ? (
        <details className="disclosure">
          <summary>{amount ? "Change the settlement" : "Record a settlement offer"}</summary>
          <ActionForm action={updateCase.bind(null, c.id)} label="Save the settlement" pendingLabel="Saving" secondary>
            <div className="field-grid">
              <div className="field">
                <label htmlFor="settlement_offered">Offered (rupees)</label>
                <input id="settlement_offered" name="settlement_offered" inputMode="decimal" defaultValue={s.offered ?? ""} />
              </div>
              <div className="field">
                <label htmlFor="settlement_agreed">Agreed (rupees)</label>
                <input id="settlement_agreed" name="settlement_agreed" inputMode="decimal" defaultValue={s.agreed ?? ""} />
              </div>
            </div>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}
