import Link from "next/link";
import { Suspense } from "react";

import { addRunningBill, addWorkOrder, releaseRetention } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Contractors, type RaBillRow, api } from "@/lib/api";
import { day, inr } from "@/lib/format";

export default function ContractorsPage({ params }: PageProps<"/projects/[id]/contractors">) {
  return (
    <Suspense fallback={<p className="loading">Loading contractors</p>}>
      <ContractorsView params={params} />
    </Suspense>
  );
}

const STATE: Record<RaBillRow["state"], { label: string; tag: string }> = {
  waiting: { label: "Waiting for approval", tag: "tag" },
  approved: { label: "Approved, to pay", tag: "tag tag-soon" },
  held: { label: "On hold", tag: "tag tag-overdue" },
  paid: { label: "Paid", tag: "tag tag-done" },
};

function OrderForm({ c }: { c: Contractors }) {
  return (
    <>
      <div className="field-grid">
        <div className="field">
          <label htmlFor="wo-contractor">Contractor</label>
          <input id="wo-contractor" name="contractor" required />
        </div>
        <div className="field">
          <label htmlFor="wo-amount">Value of the work order, in rupees</label>
          <input id="wo-amount" name="amount" inputMode="decimal" required />
        </div>
      </div>
      <label className="field-check">
        <input type="checkbox" name="deduct_cess" value="yes" defaultChecked /> Deduct 1% labour cess from this contractor&apos;s bills
      </label>
      <details className="disclosure">
        <summary>More details</summary>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="wo-retention">Retention, %</label>
            <input id="wo-retention" name="retention_pct" inputMode="decimal" placeholder={c.retention_default} />
          </div>
          <div className="field">
            <label htmlFor="wo-advance">Advance paid to them, in rupees</label>
            <input id="wo-advance" name="advance" inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="wo-line">Part of the budget</label>
            <select id="wo-line" name="cost_line" defaultValue="">
              <option value="">Civil and structure</option>
              {c.cost_lines.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="wo-desc">What the work is</label>
            <input id="wo-desc" name="description" placeholder="Civil work, Tower A" />
          </div>
        </div>
      </details>
    </>
  );
}

async function ContractorsView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await api.contractors(id);

  return (
    <>
      {c.orders.length === 0 ? (
        <p className="empty">No contractors yet. Add the first work order below.</p>
      ) : (
        <div className="rows">
          {c.orders.map((o) => (
            <section key={o.id} className="card">
              <div className="card-head">
                <h2>{o.contractor}</h2>
                <span className="muted small">{o.reference}</span>
              </div>
              <p className="muted">
                {`${inr(o.billed)} billed of ${inr(o.amount)}`}
                {o.over ? ", over the order" : ""}
              </p>
              <div className="tile-grid" style={{ marginTop: 14 }}>
                <div className="tile">
                  <p className="tile-label">{`Retention held (${Number(o.retention_pct)}%)`}</p>
                  <p className="tile-value">{inr(o.retention_held)}</p>
                </div>
                {Number(o.advance) > 0 ? (
                  <div className="tile">
                    <p className="tile-label">Advance still to recover</p>
                    <p className="tile-value">{inr(o.advance_left)}</p>
                  </div>
                ) : null}
              </div>
              {!o.has_pan ? (
                <p className="small" style={{ marginTop: 12 }}>
                  {"No PAN for this contractor yet, so TDS is 20%. "}
                  <Link href={`/projects/${id}/suppliers`}>Add it on Suppliers</Link>
                </p>
              ) : null}
              {c.can_edit ? (
                <details className="disclosure" style={{ marginTop: 14 }}>
                  <summary>Add a running bill</summary>
                  <ActionForm action={addRunningBill.bind(null, o.id)} label="Add the bill" pendingLabel="Working it out">
                    <div className="field-grid">
                      <div className="field">
                        <label htmlFor={`ra-${o.id}-value`}>Value of work in this bill, in rupees</label>
                        <input id={`ra-${o.id}-value`} name="work_value" inputMode="decimal" required />
                      </div>
                      <div className="field">
                        <label htmlFor={`ra-${o.id}-gst`}>GST on the bill</label>
                        <input id={`ra-${o.id}-gst`} name="gst" inputMode="decimal" />
                      </div>
                    </div>
                    <details className="disclosure">
                      <summary>More details</summary>
                      <div className="field-grid">
                        <div className="field">
                          <label htmlFor={`ra-${o.id}-date`}>Bill date (today if blank)</label>
                          <input id={`ra-${o.id}-date`} name="period_to" type="date" />
                        </div>
                        <div className="field">
                          <label htmlFor={`ra-${o.id}-no`}>Their bill number</label>
                          <input id={`ra-${o.id}-no`} name="bill_no" />
                        </div>
                        <div className="field">
                          <label htmlFor={`ra-${o.id}-adv`}>Advance to recover from this bill</label>
                          <input id={`ra-${o.id}-adv`} name="advance_recovery" inputMode="decimal" placeholder="Worked out for you" />
                        </div>
                      </div>
                    </details>
                    <p className="small muted" style={{ marginBottom: 12 }}>
                      Retention, the advance, TDS and labour cess are taken off for you, and the bill waits for approval.
                    </p>
                  </ActionForm>
                </details>
              ) : null}
              {o.bills.length > 0 ? (
                <ul className="rows" style={{ marginTop: 14 }}>
                  {o.bills.slice(0, 3).map((b) => (
                    <BillRow key={b.id} b={b} />
                  ))}
                </ul>
              ) : null}
              {o.bills.length > 3 ? (
                <details className="disclosure">
                  <summary>{`Earlier bills (${o.bills.length - 3})`}</summary>
                  <ul className="rows">
                    {o.bills.slice(3).map((b) => (
                      <BillRow key={b.id} b={b} />
                    ))}
                  </ul>
                </details>
              ) : null}
              {c.can_edit && Number(o.retention_held) > 0 && !o.retention_released_on ? (
                <details className="disclosure">
                  <summary>The work is done and accepted</summary>
                  <p className="small muted" style={{ margin: "8px 0 12px" }}>
                    {`Mark the ${inr(o.retention_held)} retention as released, so accounts can pay it.`}
                  </p>
                  <ActionForm action={releaseRetention.bind(null, o.id)} label="Release the retention" pendingLabel="Saving" secondary />
                </details>
              ) : null}
              {o.retention_released_on ? <p className="small muted">{`Retention released on ${day(o.retention_released_on)}.`}</p> : null}
            </section>
          ))}
        </div>
      )}

      {c.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>Add a work order</h2>
          </div>
          <ActionForm action={addWorkOrder.bind(null, id)} label="Add the work order" pendingLabel="Adding">
            <OrderForm c={c} />
          </ActionForm>
        </section>
      ) : null}
    </>
  );
}

function BillRow({ b }: { b: RaBillRow }) {
  const held = Number(b.retention) + Number(b.advance_recovery) + Number(b.tds) + Number(b.cess);
  return (
    <li className="row row-2 row-stack">
      <div>
        <p className="row-title">{`Bill ${b.number}: ${inr(b.net_payable)} to pay`}</p>
        <p className="row-detail">{`${inr(b.work_value)} of work, ${day(b.period_to)}. ${inr(String(held))} held back.`}</p>
        <details className="disclosure">
          <summary>What was held back</summary>
          <ul className="calc">
            <li>
              <span>Work done</span>
              <span className="num">{inr(b.work_value)}</span>
            </li>
            <li>
              <span>GST</span>
              <span className="num">{inr(b.gst)}</span>
            </li>
            <li>
              <span>Retention</span>
              <span className="num">{`- ${inr(b.retention)}`}</span>
            </li>
            <li>
              <span>Advance recovered</span>
              <span className="num">{`- ${inr(b.advance_recovery)}`}</span>
            </li>
            <li>
              <span>TDS</span>
              <span className="num">{`- ${inr(b.tds)}`}</span>
            </li>
            <li>
              <span>Labour cess</span>
              <span className="num">{`- ${inr(b.cess)}`}</span>
            </li>
            <li className="calc-total">
              <span>To pay</span>
              <span className="num">{inr(b.net_payable)}</span>
            </li>
          </ul>
        </details>
      </div>
      <div className="row-side">
        <span className={STATE[b.state].tag}>{b.state === "paid" && b.paid_on ? `Paid ${day(b.paid_on)}` : STATE[b.state].label}</span>
      </div>
    </li>
  );
}
