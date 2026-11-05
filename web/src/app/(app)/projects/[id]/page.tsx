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
          </div>
          <p style={{ margin: "12px 0", maxWidth: 720 }}>
            Your Tally export, bank statements and the Excel sheets you keep today. You see everything before it is saved.
          </p>
          <Link href={`/projects/${id}/import`} className="button">
            Add your files
          </Link>
        </section>
      ) : null}

      <div className="stats">
        <div className="stat">
          <p className="stat-label">You can draw now</p>
          <p className="stat-value">{known("costs") && known("escrow") ? inr(project.drawable_now) : "Not known yet"}</p>
          <p className="stat-note">
            <Link href={`/projects/${id}/escrow`}>From the RERA account</Link>
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Work done so far</p>
          <p className="stat-value">{pct(m.certified_progress_pct)}</p>
          <p className="stat-note">From the architect&apos;s latest certificate</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>What needs doing</h2>
        </div>
        <ObligationRows items={urgent} today={m.as_of} showProject={false} empty="Nothing is late or due soon." />
        {later.length > 0 ? (
          <details className="disclosure">
            <summary>{`Later (${later.length})`}</summary>
            <ObligationRows items={later} today={m.as_of} showProject={false} />
          </details>
        ) : null}
      </section>

      <section className="section">
        <details className="disclosure">
          <summary>How the money stands</summary>
          <p style={{ margin: "12px 0" }}>
            {!known("cost_lines") ? (
              <Link href={`/projects/${id}/budget`}>Set up the budget</Link>
            ) : over > 0 ? (
              `Expected final cost ${inr(m.anticipated_final_cost)}, which is ${inr(String(over))} over the budget of ${inr(m.budget)}. Spent so far: ${inr(m.incurred)}.`
            ) : (
              `Expected final cost ${inr(m.anticipated_final_cost)}, within the budget of ${inr(m.budget)}. Spent so far: ${inr(m.incurred)}.`
            )}
          </p>
          {m.alerts.length ? (
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
                  <div className="row-side">{a.amount ? <p className="row-amount">{inr(a.amount)}</p> : null}</div>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Line</th>
              <th className="right">Budget</th>
              <th className="right">Ordered</th>
              <th className="right">Billed</th>
              <th className="right">Paid</th>
              <th className="right">Expected final cost</th>
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
          </div>
        </details>
      </section>
    </>
  );
}
