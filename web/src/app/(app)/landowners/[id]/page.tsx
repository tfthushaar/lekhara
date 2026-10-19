import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { addLandownerPayment, deleteLandownerPayment, updateLandowner, updateLandownerPayment } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { History } from "@/components/history";
import { LandownerFields, LandownerPaymentFields } from "@/components/landowner-fields";
import { api } from "@/lib/api";
import { day, inr, pct } from "@/lib/format";

export const metadata: Metadata = { title: "Landowner" };

export default function LandownerPage({ params }: PageProps<"/landowners/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the landowner</p>}>
      <LandownerView params={params} />
    </Suspense>
  );
}

const SOURCE = { typed: "Typed in", import: "Imported", tally: "From Tally" };

async function LandownerView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const o = await api.landowner(id);
  const t = o.totals;
  const short = Number(t.tds_short) > 0;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href={`/projects/${o.project_id}/units`}>{o.project_name}</Link>
          </p>
          <h1>{o.name}</h1>
          <p>
            {pct(o.share_pct)} of {o.share_type === "area" ? "the built area" : "revenue"}.{" "}
            {o.pan ? `PAN ${o.pan}.` : "PAN not recorded."}
          </p>
        </div>
      </div>

      <div className="stats">
        <div className="stat">
          <p className="stat-label">Consideration paid</p>
          <p className="stat-value">{inr(t.consideration)}</p>
          <p className="stat-note">Before TDS</p>
        </div>
        <div className="stat">
          <p className="stat-label">TDS deducted</p>
          <p className="stat-value">{inr(t.tds)}</p>
          <p className="stat-note">{short ? `${inr(t.tds_short)} short of s.194-IC` : "As s.194-IC asks"}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Refundable deposit</p>
          <p className="stat-value">{inr(t.deposits)}</p>
          <p className="stat-note">{`Paid, of ${inr(o.refundable_deposit)} agreed`}</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Payments</h2>
          <p>From Tally, imported or typed in. Correct Tally&apos;s in Tally.</p>
        </div>
        {o.can_edit ? (
          <details className="disclosure">
            <summary>Add a payment</summary>
            <ActionForm action={addLandownerPayment.bind(null, o.id)} label="Add the payment" pendingLabel="Adding">
              <LandownerPaymentFields prefix="new-pay" />
            </ActionForm>
          </details>
        ) : null}
        {o.payments.length === 0 ? (
          <p className="empty">No payments yet. Add them here, import a sheet, or bring in Tally.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Paid on</th>
                <th>What for</th>
                <th className="right">Amount</th>
                <th className="right">TDS</th>
                <th>Reference</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {o.payments.map((p) => (
                <tr key={p.id}>
                  <td className="nowrap">{day(p.paid_on)}</td>
                  <td>{p.deposit ? "Refundable deposit" : "Consideration"}</td>
                  <td className="right num">{inr(p.amount)}</td>
                  <td className="right num">
                    {inr(p.tds_deducted)}
                    {p.tds_short ? (
                      <>
                        <br />
                        <span className="tag tag-soon">{`${inr(p.tds_short)} short`}</span>
                      </>
                    ) : null}
                  </td>
                  <td>
                    {p.reference ?? <span className="muted">None</span>}
                    <br />
                    <span className="small muted">{SOURCE[p.source]}</span>
                  </td>
                  <td>
                    {o.can_edit && p.source !== "tally" ? (
                      <details className="disclosure">
                        <summary>Change</summary>
                        <ActionForm action={updateLandownerPayment.bind(null, p.id)} label="Save" pendingLabel="Saving" secondary>
                          <LandownerPaymentFields prefix={`pay-${p.id}`} payment={p} />
                        </ActionForm>
                        <ActionForm action={deleteLandownerPayment.bind(null, p.id)} label="Delete the payment" pendingLabel="Deleting" secondary />
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {o.can_edit ? (
        <section className="section">
          <details className="disclosure">
            <summary>Change the landowner&apos;s details</summary>
            <ActionForm action={updateLandowner.bind(null, o.id)} label="Save" pendingLabel="Saving">
              <LandownerFields prefix="owner" owner={o} />
            </ActionForm>
          </details>
        </section>
      ) : null}

      <section className="section">
        <History entries={o.history} />
      </section>
    </>
  );
}
