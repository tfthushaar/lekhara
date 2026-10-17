import Link from "next/link";
import { Suspense } from "react";

import { startWithdrawal } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";
import { day, inr, pct } from "@/lib/format";
import { REQUEST_STATUS } from "@/lib/labels";

export default function EscrowPage({ params }: PageProps<"/projects/[id]/escrow">) {
  return (
    <Suspense fallback={<p className="loading">Working out what can be drawn</p>}>
      <EscrowView params={params} />
    </Suspense>
  );
}

async function EscrowView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const e = await api.escrow(id);
  const open = e.requests.find((r) => r.id === e.open_request_id);
  const drawable = Number(e.drawable_now);

  return (
    <>
      {open ? (
        <div className="notice" style={{ marginBottom: 32 }}>
          A withdrawal of {inr(open.amount)} is under way and waiting for {open.waiting_on}.{" "}
          <Link href={`/withdrawals/${open.id}`} className="link-action">
            Open the request
          </Link>
        </div>
      ) : null}

      <div className="grid-2">
        <div>
          <p className="stat-label">You can withdraw today</p>
          <p className="hero-value">{inr(e.drawable_now)}</p>
          <p className="stat-note">{e.limited_by_text}</p>

          {e.can_start ? (
            <div style={{ marginTop: 24 }}>
              <ActionForm
                action={startWithdrawal.bind(null, id)}
                label={`Start a withdrawal of ${inr(e.drawable_now)}`}
                pendingLabel="Preparing the certificates"
              />
              <p className="muted small" style={{ marginTop: 10 }}>
                Lekhara prepares the architect&apos;s, engineer&apos;s and CA&apos;s certificates from
                your books. Each of them reviews and signs before anything goes to the bank.
              </p>
            </div>
          ) : null}
          {!open && drawable <= 0 && e.can_start ? (
            <p className="muted" style={{ marginTop: 24 }}>
              Nothing can be drawn until more cost is incurred or more is deposited.
            </p>
          ) : null}
        </div>

        <div>
          <h2 style={{ marginBottom: 8 }}>How Lekhara worked this out</h2>
          <ul className="calc">
            {e.steps.map((s) => (
              <li key={s.label}>
                <span>{s.label}</span>
                <span className="num">{s.kind === "percent" ? pct(s.value) : inr(s.value)}</span>
              </li>
            ))}
            <li className="calc-total">
              <span>You can withdraw now, the lower of the last two</span>
              <span className="num">{inr(e.drawable_now)}</span>
            </li>
          </ul>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Deposits</h2>
          <p>{e.deposits.deposit_share_pct}% of what buyers pay must go into the RERA account</p>
        </div>
        <ul className="calc">
          <li>
            <span>Received from buyers so far</span>
            <span className="num">{inr(e.deposits.receipts_from_buyers)}</span>
          </li>
          <li>
            <span>Must be in the RERA account</span>
            <span className="num">{inr(e.deposits.required)}</span>
          </li>
          <li>
            <span>Deposited</span>
            <span className="num">{inr(e.deposits.deposited)}</span>
          </li>
          <li className="calc-total">
            <span>{Number(e.deposits.shortfall) > 0 ? "Still to deposit" : "Deposits are complete"}</span>
            <span className="num">
              {Number(e.deposits.shortfall) > 0 ? inr(e.deposits.shortfall) : ""}
            </span>
          </li>
        </ul>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Withdrawals</h2>
          <p>
            {e.last_withdrawal_on ? `Last withdrawal ${day(e.last_withdrawal_on)}. ` : ""}
            {e.next_cycle_due_on
              ? `Certificates are usually renewed by ${day(e.next_cycle_due_on)}.`
              : ""}
          </p>
        </div>
        {e.requests.length === 0 ? (
          <p className="empty">No withdrawals yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Started</th>
                <th className="right">Amount</th>
                <th>Status</th>
                <th>Released</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {e.requests.map((r) => (
                <tr key={r.id}>
                  <td>{day(r.created_on)}</td>
                  <td className="right num">{inr(r.amount)}</td>
                  <td>
                    {REQUEST_STATUS[r.status]}
                    {r.waiting_on ? <p className="row-detail">Waiting for {r.waiting_on}</p> : null}
                  </td>
                  <td>{r.released_on ? `${day(r.released_on)}, ${inr(r.released_amount)}` : ""}</td>
                  <td className="right">
                    <Link href={`/withdrawals/${r.id}`} className="link-action">
                      Open
                    </Link>
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
