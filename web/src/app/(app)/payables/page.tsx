import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { approveBill, holdBill, payBill } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type PayableRow, type Payables, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export const metadata: Metadata = { title: "Bills to pay" };

export default function PayablesPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bills to pay</h1>
          <p>Every bill not yet paid, on every project.</p>
        </div>
      </div>
      <Suspense fallback={<p className="loading">Loading bills</p>}>
        <PayablesView />
      </Suspense>
    </>
  );
}

function Detail({ b }: { b: PayableRow }) {
  return (
    <>
      <p className="row-title">{`${inr(b.amount)} to ${b.supplier}`}</p>
      <p className="row-detail">
        {[
          b.project,
          b.running_bill ? `running bill ${b.running_bill}, after ${inr(b.held_back)} held back` : `bill ${b.bill_no}`,
        ].join(", ")}
      </p>
      <p className="row-meta">
        {b.late ? <span className="tag tag-overdue">{`Was due ${day(b.pay_by)}`}</span> : `Pay by ${day(b.pay_by)}`}
        {b.msme ? "  Small supplier: the 45-day limit applies." : ""}
      </p>
      {b.note ? <p className="row-meta">{`On hold: ${b.note}${b.decided_by ? ` (${b.decided_by})` : ""}`}</p> : null}
    </>
  );
}

function PayForm({ b }: { b: PayableRow }) {
  return (
    <ActionForm action={payBill.bind(null, b.id)} label="Mark paid" pendingLabel="Saving">
      <div className="field">
        <label htmlFor={`pay-${b.id}`}>UTR or cheque number</label>
        <input id={`pay-${b.id}`} name="reference" />
      </div>
    </ActionForm>
  );
}

function Rows({ rows, children }: { rows: PayableRow[]; children: (b: PayableRow) => React.ReactNode }) {
  return (
    <ul className="rows">
      {rows.map((b) => (
        <li key={b.id} className="row row-2 row-stack">
          <div>
            <Detail b={b} />
          </div>
          <div className="row-side">{children(b)}</div>
        </li>
      ))}
    </ul>
  );
}

async function PayablesView() {
  const p: Payables = await api.payables();
  const none = !p.waiting.length && !p.approved.length && !p.held.length;
  if (none) return <p className="empty">Every bill is paid.</p>;

  const approvals = (
    <section className="section">
      <div className="section-head">
        <h2>{p.can_approve ? `Waiting for your approval (${p.waiting.length})` : `Waiting for approval (${p.waiting.length})`}</h2>
        <p>{inr(p.totals.waiting)}</p>
      </div>
      {p.waiting.length === 0 ? (
        <p className="empty">Nothing waiting.</p>
      ) : (
        <Rows rows={p.waiting}>
          {(b) =>
            p.can_approve ? (
              <>
                <ActionForm action={approveBill.bind(null, b.id)} label="Approve" pendingLabel="Approving" />
                <details className="disclosure">
                  <summary>Hold</summary>
                  <ActionForm action={holdBill.bind(null, b.id)} label="Put on hold" pendingLabel="Saving" secondary>
                    <div className="field">
                      <label htmlFor={`hold-${b.id}`}>Why?</label>
                      <input id={`hold-${b.id}`} name="note" required placeholder="Quantity doesn't match the challan" />
                    </div>
                  </ActionForm>
                </details>
              </>
            ) : null
          }
        </Rows>
      )}
    </section>
  );

  const payments = (
    <section className="section">
      <div className="section-head">
        <h2>{`Approved, to pay (${p.approved.length})`}</h2>
        <p>{inr(p.totals.approved)}</p>
      </div>
      {p.approved.length === 0 ? <p className="empty">Nothing approved and waiting to be paid.</p> : <Rows rows={p.approved}>{(b) => (p.can_pay ? <PayForm b={b} /> : null)}</Rows>}
    </section>
  );

  return (
    <>
      <p className="status-line">
        {p.can_approve
          ? p.waiting.length
            ? `${plural(p.waiting.length, "bill")} for you to approve.`
            : "Nothing to approve."
          : p.approved.length
            ? `${plural(p.approved.length, "approved bill")} to pay.`
            : "Nothing approved to pay yet."}
      </p>
      {p.can_approve ? (
        <>
          {approvals}
          {payments}
        </>
      ) : (
        <>
          {payments}
          {approvals}
        </>
      )}
      {p.held.length > 0 ? (
        <section className="section">
          <details className="disclosure">
            <summary>{`On hold (${p.held.length}), ${inr(p.totals.held)}`}</summary>
            <Rows rows={p.held}>{(b) => (p.can_approve ? <ActionForm action={approveBill.bind(null, b.id)} label="Approve" pendingLabel="Approving" secondary /> : null)}</Rows>
          </details>
        </section>
      ) : null}
      <p className="small muted" style={{ marginTop: 24 }}>
        {"Accounts adds bills and records payments; the owner or finance approves each one first. "}
        <Link href="/projects">Bills come in from each project&apos;s Suppliers and Contractors pages.</Link>
      </p>
    </>
  );
}
