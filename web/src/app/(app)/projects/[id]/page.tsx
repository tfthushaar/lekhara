import Link from "next/link";
import { Suspense } from "react";

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
  const m = project.money;
  const over = Number(m.anticipated_final_cost) - Number(m.budget);
  const sum = (key: "budget" | "committed" | "incurred" | "paid" | "anticipated_final_cost") =>
    String(money.lines.reduce((total, line) => total + Number(line[key]), 0));

  return (
    <>
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Certified progress</p>
          <p className="stat-value">{pct(m.certified_progress_pct)}</p>
          <p className="stat-note">From the architect&apos;s latest certificate</p>
        </div>
        <div className="stat">
          <p className="stat-label">Anticipated final cost</p>
          <p className="stat-value">{inr(m.anticipated_final_cost)}</p>
          <p className="stat-note">
            {over > 0 ? `${inr(String(over))} over the budget of ${inr(m.budget)}` : `Budget ${inr(m.budget)}`}
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Cost incurred</p>
          <p className="stat-value">{inr(m.incurred)}</p>
          <p className="stat-note">
            {pct(m.development_incurred_pct)} of development cost.{" "}
            <Link href={`/projects/${id}/budget`}>Cost lines and budget</Link>
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Can draw now</p>
          <p className="stat-value">{inr(project.drawable_now)}</p>
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
        <ObligationRows
          items={project.obligations}
          today={m.as_of}
          showProject={false}
          empty="Nothing is owed right now."
        />
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Cost lines</h2>
          <p>
            Final cost is the larger of budget, committed and incurred. Contingency covers overruns
            first.
          </p>
        </div>
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
      </section>
    </>
  );
}
