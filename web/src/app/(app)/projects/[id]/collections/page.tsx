import Link from "next/link";
import { Suspense } from "react";

import { applyPlanTemplate, raiseDemands, savePlan } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { Needs, has, missing } from "@/components/needs";
import { type Collections, type PaymentPlan, api } from "@/lib/api";
import { day, inr, pct } from "@/lib/format";

export default function CollectionsPage({ params }: PageProps<"/projects/[id]/collections">) {
  return (
    <Suspense fallback={<p className="loading">Working out what buyers owe</p>}>
      <CollectionsView params={params} />
    </Suspense>
  );
}

function when(m: Collections["milestones"][number]): string {
  if (m.trigger === "booking") return "On booking";
  if (m.trigger === "agreement") return "On the agreement";
  if (m.trigger === "possession") return "On possession";
  return `At ${pct(m.progress_pct)} certified progress`;
}

async function CollectionsView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [c, plan, setup] = await Promise.all([api.collections(id), api.paymentPlan(id), api.setup(id)]);
  const s = c.summary;
  const needs = missing(setup, ["units", "plan", "progress", "receipts"]);
  const canRaise = has(setup, "units") && has(setup, "plan") && has(setup, "progress");
  const paymentsIn = has(setup, "receipts");

  return (
    <>
      <Needs items={needs} purpose="To raise demands and follow up buyers' payments" />
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Billed to buyers</p>
          <p className="stat-value">{inr(s.billed)}</p>
          <p className="stat-note">Instalments raised so far, with GST</p>
        </div>
        <div className="stat">
          <p className="stat-label">Received</p>
          <p className="stat-value">{inr(s.received)}</p>
          <p className="stat-note">Cash received; buyers&apos; TDS counts as paid</p>
        </div>
        <div className="stat">
          <p className="stat-label">Overdue</p>
          <p className="stat-value">{inr(s.overdue)}</p>
          <p className="stat-note">From {s.overdue_buyers} buyers</p>
        </div>
        <div className="stat">
          <p className="stat-label">Interest on overdue</p>
          <p className="stat-value">{inr(s.interest)}</p>
          <p className="stat-note">At the rate in the agreement</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Ready to raise</h2>
          <p>Milestones the latest certified progress has reached</p>
        </div>
        {c.ready.length === 0 ? (
          <p className="empty">
            {canRaise
              ? "Every milestone reached so far has been demanded."
              : "Demands are ready to raise once the units, the payment plan and certified progress are in."}
          </p>
        ) : (
          <ul className="rows">
            {c.ready.map((r) => (
              <li key={r.milestone_id} className="row">
                <div>
                  <span className="tag tag-opportunity">Money waiting</span>
                </div>
                <div>
                  <p className="row-title">{r.name}</p>
                  <p className="row-detail">
                    {r.reason} {r.units} booked units, {inr(r.amount)} plus GST of {inr(r.gst)}.
                  </p>
                </div>
                <div className="row-side">
                  <p className="amount-label">Ready to bill</p>
                  <p className="row-amount">{inr(r.total)}</p>
                  {c.can_raise ? (
                    <div style={{ marginTop: 8 }}>
                      <ActionForm
                        action={raiseDemands.bind(null, id, r.milestone_id)}
                        label={`Raise demands for ${r.units} units`}
                        pendingLabel="Raising the demands"
                      />
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Overdue buyers</h2>
          <p>Past their due date, largest first. Your team sends the reminders.</p>
        </div>
        {c.overdue.length === 0 ? (
          <p className="empty">{paymentsIn || c.accounts.length === 0 ? "No buyer is overdue." : "No buyer is overdue on the demands raised so far."}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Unit</th>
                <th>Buyer</th>
                <th className="right">Overdue</th>
                <th className="right">Days late</th>
                <th className="right">Interest</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {c.overdue.map((o) => (
                <tr key={o.unit}>
                  <td>{o.unit}</td>
                  <td>{o.buyer}</td>
                  <td className="right num">{inr(o.overdue)}</td>
                  <td className="right num">{o.days_overdue}</td>
                  <td className="right num">{inr(o.interest)}</td>
                  <td className="right">
                    {o.demand_id ? (
                      <Link href={`/demands/${o.demand_id}`} className="link-action">
                        Demand letter
                      </Link>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Payment plan</h2>
          <p>Each milestone is a share of the agreement value</p>
        </div>
        <PlanEditor plan={plan} projectId={id} />
        <table className="table">
          <thead>
            <tr>
              <th>Milestone</th>
              <th>When</th>
              <th className="right">Share</th>
              <th>Status</th>
              <th className="right">Billed</th>
            </tr>
          </thead>
          <tbody>
            {c.milestones.map((m) => {
              const ready = c.ready.some((r) => r.milestone_id === m.id);
              return (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>{when(m)}</td>
                  <td className="right num">{pct(m.share_pct)}</td>
                  <td>
                    {ready ? (
                      <span className="tag tag-opportunity">Ready to raise</span>
                    ) : m.raised_units > 0 ? (
                      `Raised for ${m.raised_units} units`
                    ) : (
                      <span className="muted">Not reached</span>
                    )}
                  </td>
                  <td className="right num">{Number(m.billed) > 0 ? inr(m.billed) : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {paymentsIn ? (
      <section className="section">
        <div className="section-head">
          <h2>Deposits against the 70% rule</h2>
          <p>At each month end, was 70% of everything buyers paid in the RERA account?</p>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Month end</th>
              <th className="right">Paid by buyers so far</th>
              <th className="right">Must be deposited</th>
              <th className="right">Deposited</th>
              <th className="right">Short by</th>
            </tr>
          </thead>
          <tbody>
            {c.deposit_checks.map((d) => (
              <tr key={d.month_end}>
                <td>{day(d.month_end)}</td>
                <td className="right num">{inr(d.receipts)}</td>
                <td className="right num">{inr(d.required)}</td>
                <td className="right num">{inr(d.deposits)}</td>
                <td className="right num">
                  {Number(d.shortfall) > 0 ? <strong>{inr(d.shortfall)}</strong> : "In order"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      ) : null}

      <section className="section">
        <details className="disclosure">
          <summary>Every buyer&apos;s account ({c.accounts.length})</summary>
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Unit</th>
                <th>Buyer</th>
                <th className="right">Agreement value</th>
                <th className="right">Billed</th>
                <th className="right">Received</th>
                <th className="right">TDS</th>
                <th className="right">Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {c.accounts.map((a) => (
                <tr key={a.unit}>
                  <td>{a.unit}</td>
                  <td>{a.buyer}</td>
                  <td className="right num">{inr(a.agreement_value)}</td>
                  <td className="right num">{inr(a.billed)}</td>
                  <td className="right num">{inr(a.received)}</td>
                  <td className="right num">{inr(a.tds)}</td>
                  <td className="right num">
                    {Number(a.outstanding) > 0 ? inr(a.outstanding) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>
    </>
  );
}

function PlanEditor({ plan, projectId }: { plan: PaymentPlan; projectId: string }) {
  if (!plan.can_edit) return null;
  const rows = [...plan.stages, ...Array.from({ length: 3 }, () => null)];
  return (
    <>
      {plan.stages.length === 0 || !plan.any_raised ? (
        <details className="disclosure" open={plan.stages.length === 0}>
          <summary>{plan.stages.length === 0 ? "Choose a payment plan to start from" : "Start again from a standard plan"}</summary>
          <ActionForm action={applyPlanTemplate.bind(null, projectId)} label="Use this plan" pendingLabel="Setting it">
            <div className="checks">
              {plan.templates.map((t, i) => (
                <label key={t.key}>
                  <input type="radio" name="template" value={t.key} defaultChecked={i === 0} />{" "}
                  <span>
                    <strong>{t.label}</strong>
                    <span className="small muted">
                      {` ${t.stages.map((s) => `${s.share_pct}% ${s.trigger_label.toLowerCase()}${s.progress_pct ? ` (${s.progress_pct}%)` : ""}`).join(", ")}`}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <p className="small muted" style={{ marginBottom: 12 }}>
              A starting point: change the stages to match your agreement for sale.
            </p>
          </ActionForm>
        </details>
      ) : null}
      {plan.stages.length > 0 ? (
        <details className="disclosure">
          <summary>Change the payment plan</summary>
          <p className="small muted" style={{ margin: "8px 0 12px", maxWidth: 720 }}>
            The shares must add up to 100%. Stages with demands already raised keep their timing and
            share. Leave a row blank to drop it.
          </p>
          <ActionForm action={savePlan.bind(null, projectId)} label="Save the plan" pendingLabel="Saving">
            <table className="table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>When</th>
                  <th className="right">At progress (%)</th>
                  <th className="right">Share (%)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((stage, i) => (
                  <tr key={stage?.id ?? `new-${i}`}>
                    <td>
                      <input type="hidden" name={`stage_${i}_id`} value={stage?.id ?? ""} />
                      <input name={`stage_${i}_name`} defaultValue={stage?.name ?? ""} aria-label="Stage name" />
                      {stage?.demands ? <span className="small muted">{` ${stage.demands} demands raised`}</span> : null}
                    </td>
                    <td>
                      <select name={`stage_${i}_trigger`} defaultValue={stage?.trigger ?? "progress"} aria-label="When it falls due">
                        {plan.triggers.map((t) => (
                          <option key={t.value} value={t.value}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="right">
                      <input name={`stage_${i}_progress`} defaultValue={stage?.progress_pct ?? ""} inputMode="decimal" size={5} aria-label="Progress per cent" />
                    </td>
                    <td className="right">
                      <input name={`stage_${i}_share`} defaultValue={stage?.share_pct ?? ""} inputMode="decimal" size={5} aria-label="Share per cent" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ActionForm>
        </details>
      ) : null}
    </>
  );
}
