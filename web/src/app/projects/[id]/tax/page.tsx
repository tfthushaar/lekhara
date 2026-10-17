import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";
import { day, inr, pct, relative } from "@/lib/format";

export default function TaxPage({ params }: PageProps<"/projects/[id]/tax">) {
  return (
    <Suspense fallback={<p className="loading">Working out tax and statutory exposure</p>}>
      <TaxView params={params} />
    </Suspense>
  );
}

const MSME_STATUS = { ok: "On time", due_soon: "Due soon", overdue: "Past the limit" } as const;

async function TaxView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await api.tax(id);
  const p = t.procurement;
  const dr = t.development_rights;
  const share = Math.min(Number(p.registered_share_pct), 100);

  return (
    <>
      <p className="muted small" style={{ marginBottom: 24 }}>
        GST regime: {t.regime}. Rates come from the Karnataka rules pack; some are marked for your
        CA to confirm. <Link href="/rules">See the rules</Link>
      </p>

      <div className="grid-2">
        {p.applies ? (
          <div className="card">
            <h2>Registered suppliers, FY {p.fy}</h2>
            <p className="hero-value">{pct(p.registered_share_pct)}</p>
            <div className="meter" aria-hidden="true">
              <div className="meter-fill" style={{ width: `${share}%` }} />
              <div className="meter-mark" style={{ left: `${Number(p.min_share_pct)}%` }} />
            </div>
            <p className="small muted">
              The line marks the {pct(p.min_share_pct)} minimum. {inr(p.qualifying)} of{" "}
              {inr(p.total)} bought this year counts as registered.
            </p>
            <p style={{ marginTop: 16 }}>
              {Number(p.shortfall) > 0 ? (
                <>
                  <strong>Reverse charge of {inr(p.rcm_on_shortfall)}</strong> will be due by{" "}
                  {day(p.payment_due_on)} unless more is bought from registered suppliers.
                </>
              ) : (
                <>
                  You can buy up to <strong>{inr(p.unregistered_headroom)}</strong> more from
                  unregistered suppliers this year before reverse charge applies.
                </>
              )}
            </p>
            {Number(p.cement_rcm) > 0 ? (
              <p className="small muted" style={{ marginTop: 8 }}>
                Reverse charge on cement from unregistered suppliers: {inr(p.cement_rcm)}.
              </p>
            ) : null}
          </div>
        ) : null}

        {dr.applies ? (
          <div className="card">
            <h2>GST on development rights</h2>
            <p className="stat-label" style={{ marginTop: 12 }}>
              Payable in cash if completion were today
            </p>
            <p className="hero-value">{inr(dr.liability)}</p>
            <p>
              {dr.unbooked_units} of your flats are unbooked.{" "}
              <strong>Each flat sold before completion lowers this by about {inr(dr.saving_per_unit_sold)}.</strong>
            </p>
            <ul className="calc" style={{ marginTop: 16 }}>
              <li>
                <span>GST on the unbooked share of development rights</span>
                <span className="num">{inr(dr.gst_on_unbooked_share)}</span>
              </li>
              <li>
                <span>Cap on the value of unbooked flats</span>
                <span className="num">{inr(dr.cap)}</span>
              </li>
              <li className="calc-total">
                <span>Payable, the lower of the two</span>
                <span className="num">{inr(dr.liability)}</span>
              </li>
            </ul>
          </div>
        ) : null}

        <div className="card">
          <h2>Delay interest owed to buyers</h2>
          {t.delay.days_late > 0 ? (
            <>
              <p className="stat-label" style={{ marginTop: 12 }}>
                Built up since {day(t.delay.possession_due_on)}
              </p>
              <p className="hero-value">{inr(t.delay.accrued)}</p>
              <p>
                Possession is {t.delay.days_late} days late. Each further month adds about{" "}
                <strong>{inr(t.delay.per_month)}</strong>.
              </p>
            </>
          ) : (
            <>
              <p className="stat-label" style={{ marginTop: 12 }}>
                If possession slips past {day(t.delay.possession_due_on)}
              </p>
              <p className="hero-value">{inr(t.delay.per_month)}</p>
              <p>a month in interest, on {inr(t.delay.buyer_money)} paid by buyers so far.</p>
            </>
          )}
          <p className="small muted" style={{ marginTop: 8 }}>
            At {pct(t.delay.annual_rate_pct)} a year, simple interest.
          </p>
        </div>

        <div className="card">
          <h2>Labour cess</h2>
          <p className="stat-label" style={{ marginTop: 12 }}>
            Still to pay on construction to date
          </p>
          <p className="hero-value">{inr(t.cess.balance_due) || "₹0"}</p>
          <p>
            1% of {inr(t.cess.construction_incurred)} of construction cost is{" "}
            {inr(t.cess.due_to_date)}; {inr(t.cess.paid)} is paid. The whole project will carry
            about {inr(t.cess.on_estimate)}.
          </p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Sales below guidance value</h2>
          <p>More than 10% below guidance value, the gap may be taxed as income</p>
        </div>
        {t.guidance.length === 0 ? (
          <p className="empty">No sales are priced below the limit.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Unit</th>
                <th>Booked</th>
                <th className="right">Price</th>
                <th className="right">Guidance value</th>
                <th className="right">Below by</th>
                <th className="right">Estimated tax</th>
              </tr>
            </thead>
            <tbody>
              {t.guidance.map((g) => (
                <tr key={g.unit}>
                  <td>{g.unit}</td>
                  <td>{day(g.booked_on)}</td>
                  <td className="right num">{inr(g.agreement_value)}</td>
                  <td className="right num">{inr(g.guidance_value)}</td>
                  <td className="right num">{pct(g.gap_pct)}</td>
                  <td className="right num">{inr(g.estimated_tax)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>MSME suppliers</h2>
          <p>Pay micro and small suppliers within 45 days, or 15 without an agreement, to keep the deduction</p>
        </div>
        {t.msme.length === 0 ? (
          <p className="empty">No open bills from MSME suppliers.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Bill</th>
                <th className="right">Amount</th>
                <th>Pay by</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {t.msme.map((b) => (
                <tr key={b.vendor + b.bill_no}>
                  <td>{b.vendor}</td>
                  <td>{b.bill_no}</td>
                  <td className="right num">{inr(b.amount)}</td>
                  <td>
                    {day(b.due_on)}
                    <p className="row-detail">{relative(b.due_on, t.as_of)}</p>
                  </td>
                  <td>
                    <span className={b.status === "overdue" ? "tag tag-overdue" : b.status === "due_soon" ? "tag tag-soon" : "tag tag-upcoming"}>
                      {MSME_STATUS[b.status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>TDS on payments to landowners</h2>
          <p>10% applies to money paid under a joint development agreement</p>
        </div>
        {t.landowner_tds.length === 0 ? (
          <p className="empty">TDS is in order on every landowner payment.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Landowner</th>
                <th>Paid</th>
                <th className="right">Amount</th>
                <th className="right">TDS due</th>
                <th className="right">Deducted</th>
                <th className="right">Short</th>
              </tr>
            </thead>
            <tbody>
              {t.landowner_tds.map((s) => (
                <tr key={s.landowner + s.paid_on}>
                  <td>{s.landowner}</td>
                  <td>{day(s.paid_on)}</td>
                  <td className="right num">{inr(s.amount)}</td>
                  <td className="right num">{inr(s.expected)}</td>
                  <td className="right num">{inr(s.deducted) || "₹0"}</td>
                  <td className="right num">{inr(s.short)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
