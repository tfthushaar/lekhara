import Link from "next/link";
import { Suspense } from "react";

import { has } from "@/components/needs";
import { ObligationRows } from "@/components/obligations";
import { api } from "@/lib/api";
import { inr, pct } from "@/lib/format";

export default function ProjectOverviewPage({ params }: PageProps<"/projects/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the project</p>}>
      <Overview params={params} />
    </Suspense>
  );
}

async function Overview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [project, money] = await Promise.all([api.project(id), api.money(id)]);
  const setup = project.access.team ? await api.setup(id) : null;
  const next = setup?.items.find((i) => i.key === setup.summary.next);
  const m = project.money;
  const urgent = project.obligations.filter((o) => ["overdue", "due_soon", "at_risk"].includes(o.status));
  const later = project.obligations.filter((o) => !urgent.includes(o));
  const over = Number(m.anticipated_final_cost) - Number(m.budget);
  const sum = (key: "budget" | "committed" | "incurred" | "paid" | "anticipated_final_cost") =>
    String(money.lines.reduce((total, line) => total + Number(line[key]), 0));
  const known = (key: string) => !setup || has(setup, key);
  const fresh = setup !== null && ["units", "costs", "receipts", "escrow"].every((key) => !known(key));

  return (
    <>
      {setup && setup.summary.done < setup.summary.total ? (
        <p className="notice" style={{ marginBottom: 24 }}>
          {`Set-up: ${setup.summary.done} of ${setup.summary.total} done.`}
          {next ? ` Next: ${next.title.toLowerCase()}, for ${next.unlocks.charAt(0).toLowerCase()}${next.unlocks.slice(1)} ` : " "}
          <a href={`/projects/${id}/setup`} className="link-action">
            See what is left
          </a>
        </p>
      ) : null}
      {fresh ? (
        <section style={{ marginBottom: 32 }}>
          <div className="section-head">
            <h2>Start with what you already have</h2>
            <p>Each file comes in with a preview first; nothing changes until you say so</p>
          </div>
          <ul className="steps-list">
            <li>
              <div>
                <p className="row-title">Your Tally books</p>
                <p className="row-detail">Suppliers, bills, costs, buyer payments, the RERA account and landowners, from one export.</p>
              </div>
              <Link href={`/projects/${id}/import`} className="button">
                Bring in Tally
              </Link>
            </li>
            <li>
              <div>
                <p className="row-title">Bank statements</p>
                <p className="row-detail">The collection account and the RERA account, as Excel or PDF from net banking.</p>
              </div>
              <Link href={`/projects/${id}/import`} className="button button-secondary">
                Bring in a statement
              </Link>
            </li>
            <li>
              <div>
                <p className="row-title">Your units and buyers</p>
                <p className="row-detail">From your sales sheet or CRM export; columns are matched for you.</p>
              </div>
              <Link href={`/projects/${id}/import`} className="button button-secondary">
                Import units
              </Link>
            </li>
          </ul>
        </section>
      ) : null}
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Certified progress</p>
          <p className="stat-value">{pct(m.certified_progress_pct)}</p>
          <p className="stat-note">From the architect&apos;s latest certificate</p>
        </div>
        <div className="stat">
          <p className="stat-label">Anticipated final cost</p>
          <p className="stat-value">{known("cost_lines") ? inr(m.anticipated_final_cost) : "No budget yet"}</p>
          <p className="stat-note">
            {!known("cost_lines") ? (
              <Link href={`/projects/${id}/budget`}>Set up the cost lines</Link>
            ) : over > 0 ? (
              `${inr(String(over))} over the budget of ${inr(m.budget)}`
            ) : (
              `Budget ${inr(m.budget)}`
            )}
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Cost incurred</p>
          <p className="stat-value">{known("costs") || Number(m.incurred) > 0 ? inr(m.incurred) : "No costs yet"}</p>
          <p className="stat-note">
            {known("costs") || Number(m.incurred) > 0 ? (
              <>
                {pct(m.development_incurred_pct)} of development cost.{" "}
                <Link href={`/projects/${id}/budget`}>Cost lines and budget</Link>
              </>
            ) : (
              <Link href={`/projects/${id}/import`}>Bring in your costs from Tally</Link>
            )}
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Can draw now</p>
          <p className="stat-value">{known("costs") && known("escrow") ? inr(project.drawable_now) : "Not known yet"}</p>
          <p className="stat-note">
            <Link href={`/projects/${id}/escrow`}>See how this is worked out</Link>
          </p>
        </div>
      </div>

      {m.alerts.length ? (
        <section className="section">
          <div className="section-head">
            <h2>Cost signals</h2>
            <p>Worth a look before they grow</p>
          </div>
          <ul className="rows">
            {m.alerts.map((a) => (
              <li key={a.code + a.title} className="row">
                <div>
                  <span className="tag tag-warn">Check</span>
                </div>
                <div>
                  <p className="row-title">{a.title}</p>
                  <p className="row-detail">{a.detail}</p>
                </div>
                <div className="row-side">
                  {a.amount ? <p className="row-amount">{inr(a.amount)}</p> : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>What this project owes</h2>
          <p>To K-RERA, the escrow bank, tax authorities, buyers and landowners</p>
        </div>
        <ObligationRows items={urgent} today={m.as_of} showProject={false} empty="Nothing is late or due soon." />
        {later.length > 0 ? (
          <details className="disclosure">
            <summary>{`Money waiting and coming up (${later.length})`}</summary>
            <ObligationRows items={later} today={m.as_of} showProject={false} />
          </details>
        ) : null}
      </section>

      <section className="section">
        <details className="disclosure">
          <summary>{`Cost lines (${money.lines.length}): budget, committed, incurred, paid and final cost`}</summary>
          <p className="small muted">Final cost is the larger of budget, committed and incurred. Contingency covers overruns first.</p>
        <table className="table">
          <thead>
            <tr>
              <th>Line</th>
              <th className="right">Budget</th>
              <th className="right">Committed</th>
              <th className="right">Incurred</th>
              <th className="right">Paid</th>
              <th className="right">Final cost</th>
              <th className="right">Over budget</th>
            </tr>
          </thead>
          <tbody>
            {money.lines.map((line) => (
              <tr key={line.id}>
                <td>{line.name}</td>
                <td className="right num">{inr(line.budget)}</td>
                <td className="right num">{inr(line.committed)}</td>
                <td className="right num">{inr(line.incurred)}</td>
                <td className="right num">{inr(line.paid)}</td>
                <td className="right num">{inr(line.anticipated_final_cost)}</td>
                <td className="right num">{Number(line.overrun) > 0 ? inr(line.overrun) : ""}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total</td>
              <td className="right num">{inr(sum("budget"))}</td>
              <td className="right num">{inr(sum("committed"))}</td>
              <td className="right num">{inr(sum("incurred"))}</td>
              <td className="right num">{inr(sum("paid"))}</td>
              <td className="right num">{inr(sum("anticipated_final_cost"))}</td>
              <td className="right num">{over > 0 ? inr(String(over)) : ""}</td>
            </tr>
          </tfoot>
        </table>
        </details>
      </section>
    </>
  );
}
