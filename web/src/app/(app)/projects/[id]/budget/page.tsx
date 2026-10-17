import { Suspense } from "react";

import Link from "next/link";

import {
  createCommitment,
  createCostLine,
  deleteCommitment,
  deleteCostLine,
  standardCostLines,
  updateCommitment,
  updateCostLine,
} from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { CommitmentFields } from "@/components/purchase-fields";
import { type CostLines, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export default function BudgetPage({ params }: PageProps<"/projects/[id]/budget">) {
  return (
    <Suspense fallback={<p className="loading">Loading the cost lines</p>}>
      <BudgetView params={params} />
    </Suspense>
  );
}

function LineFields({ c, line, prefix }: { c: CostLines; line?: CostLines["lines"][number]; prefix: string }) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-code`}>Code</label>
        <input id={`${prefix}-code`} name="code" defaultValue={line?.code ?? ""} required={!line} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-name`}>Name</label>
        <input id={`${prefix}-name`} name="name" defaultValue={line?.name ?? ""} required={!line} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-category`}>Kind of cost</label>
        <select id={`${prefix}-category`} name="category" defaultValue={line?.category ?? "construction"}>
          {c.categories.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-original`}>Original budget (rupees)</label>
        <input id={`${prefix}-original`} name="original_budget" defaultValue={line?.original_budget ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-revised`}>Revised budget (rupees)</label>
        <input id={`${prefix}-revised`} name="revised_budget" defaultValue={line?.revised_budget ?? ""} />
      </div>
    </div>
  );
}

async function BudgetView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [c, orders, purchases] = await Promise.all([api.costLines(id), api.commitments(id), api.purchases(id)]);

  return (
    <>
      <section>
        <div className="section-head">
          <h2>Cost lines and budget</h2>
          <p>
            What the project spends on, as the RERA certificates split it. Spending from Tally is
            counted against these lines.
          </p>
        </div>
        {c.lines.length === 0 ? (
          <div style={{ marginTop: 16 }}>
            <p style={{ marginBottom: 12, maxWidth: 720 }}>
              No cost lines yet. Start from the standard list for a Karnataka residential project:
              land, approvals, civil and structure, MEP, finishes, external works, consultants,
              finance, marketing, overheads and contingency. Budgets can be added afterwards.
            </p>
            {c.can_edit ? (
              <ActionForm action={standardCostLines.bind(null, id)} label="Set up the standard cost lines" pendingLabel="Setting them up" />
            ) : null}
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Cost line</th>
                <th>Kind</th>
                <th className="right">Original budget</th>
                <th className="right">Revised budget</th>
                <th className="right">Incurred</th>
                <th className="right">Paid</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {c.lines.map((line) => (
                <tr key={line.id}>
                  <td>{line.code}</td>
                  <td>
                    {line.name}
                    {c.can_edit ? (
                      <details className="disclosure">
                        <summary>Change</summary>
                        <ActionForm action={updateCostLine.bind(null, line.id)} label="Save" pendingLabel="Saving" secondary>
                          <LineFields c={c} line={line} prefix={`line-${line.id}`} />
                        </ActionForm>
                        {Number(line.incurred ?? 0) === 0 ? (
                          <ActionForm action={deleteCostLine.bind(null, line.id)} label="Delete this line" pendingLabel="Deleting" secondary />
                        ) : null}
                      </details>
                    ) : null}
                  </td>
                  <td>{line.category_label}</td>
                  <td className="right num">{inr(line.original_budget)}</td>
                  <td className="right num">{inr(line.revised_budget)}</td>
                  <td className="right num">{inr(line.incurred)}</td>
                  <td className="right num">{inr(line.paid)}</td>
                  <td />
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {c.can_edit && c.lines.length > 0 ? (
        <section className="section">
          <details className="disclosure">
            <summary>Add a cost line</summary>
            <ActionForm action={createCostLine.bind(null, id)} label="Add the cost line" pendingLabel="Adding">
              <LineFields c={c} prefix="new-line" />
            </ActionForm>
          </details>
          <details className="disclosure">
            <summary>Add any standard lines that are missing</summary>
            <ActionForm action={standardCostLines.bind(null, id)} label="Add them" pendingLabel="Adding" secondary />
          </details>
        </section>
      ) : null}

      {c.lines.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Commitments</h2>
            <p>Work orders, purchase orders and contracts: what each cost line is committed to</p>
          </div>
          <p className="small" style={{ marginTop: 12 }}>
            {`${plural(orders.commitments.length, "order")}, ${inr(orders.total)} in all. `}
            <a href={`/download/projects/${id}/exports/commitments.xlsx`} className="link-action">
              Export to Excel
            </a>
            {"  ·  "}
            <Link href={`/projects/${id}/import#purchases`} className="link-action">
              Import a sheet of orders
            </Link>
          </p>
          {orders.can_edit ? (
            <details className="disclosure">
              <summary>Add an order</summary>
              <ActionForm action={createCommitment.bind(null, id)} label="Add the order" pendingLabel="Adding">
                <CommitmentFields prefix="new-order" lines={orders.cost_lines} suppliers={purchases.suppliers} />
              </ActionForm>
            </details>
          ) : null}
          {orders.commitments.length === 0 ? (
            <p className="empty">No orders yet.</p>
          ) : (
            <table className="table" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Cost line</th>
                  <th>Supplier</th>
                  <th>Ordered on</th>
                  <th className="right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {orders.commitments.map((o) => (
                  <tr key={o.id}>
                    <td>
                      {o.reference}
                      {o.description ? <span className="small muted">{` ${o.description}`}</span> : null}
                      {orders.can_edit ? (
                        <details className="disclosure">
                          <summary>Change</summary>
                          <ActionForm action={updateCommitment.bind(null, o.id)} label="Save" pendingLabel="Saving" secondary>
                            <CommitmentFields prefix={`order-${o.id}`} lines={orders.cost_lines} suppliers={purchases.suppliers} c={o} />
                          </ActionForm>
                          <ActionForm action={deleteCommitment.bind(null, o.id)} label="Delete this order" pendingLabel="Deleting" secondary />
                        </details>
                      ) : null}
                    </td>
                    <td>{o.cost_line.code}</td>
                    <td>{o.supplier ?? ""}</td>
                    <td className="nowrap">{day(o.committed_on)}</td>
                    <td className="right num">{inr(o.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : null}
    </>
  );
}
