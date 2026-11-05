import { Suspense } from "react";

import { addQuote, askForMaterial, cancelMaterial, materialArrived, orderMaterial, receiveMaterial } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type MaterialRequestRow, type Materials, api } from "@/lib/api";
import { day, inr } from "@/lib/format";

export default function MaterialsPage({ params }: PageProps<"/projects/[id]/materials">) {
  return (
    <Suspense fallback={<p className="loading">Loading materials</p>}>
      <MaterialsView params={params} />
    </Suspense>
  );
}

function ItemFields({ m, prefix, needBy }: { m: Materials; prefix: string; needBy?: boolean }) {
  return (
    <>
      <datalist id={`${prefix}-items`}>
        {m.stock.map((s) => (
          <option key={s.id} value={s.name} />
        ))}
      </datalist>
      <div className="field-grid">
        <div className="field">
          <label htmlFor={`${prefix}-item`}>Material</label>
          <input id={`${prefix}-item`} name="item" list={`${prefix}-items`} required placeholder="Cement" />
        </div>
        <div className="pair">
          <div className="field">
            <label htmlFor={`${prefix}-qty`}>How much</label>
            <input id={`${prefix}-qty`} name="quantity" inputMode="decimal" required />
          </div>
          <div className="field">
            <label htmlFor={`${prefix}-unit`}>Unit</label>
            <input id={`${prefix}-unit`} name="unit" placeholder="bags" />
          </div>
        </div>
        {needBy ? (
          <div className="field">
            <label htmlFor={`${prefix}-by`}>Needed by</label>
            <input id={`${prefix}-by`} name="needed_by" type="date" />
          </div>
        ) : null}
      </div>
    </>
  );
}

function Request({ r, m }: { r: MaterialRequestRow; m: Materials }) {
  return (
    <li className="row row-2 row-stack">
      <div>
        <p className="row-title">{`${r.quantity} ${r.unit} ${r.item}`}</p>
        <p className="row-detail">
          {[r.status === "ordered" ? `Ordered, ${r.order}` : r.status_label, r.needed_by ? `needed by ${day(r.needed_by)}` : null, r.by].filter(Boolean).join(", ")}
          {r.late ? <span className="tag tag-overdue" style={{ marginLeft: 8 }}>Late</span> : null}
        </p>
        {r.note ? <p className="row-meta">{r.note}</p> : null}
        {r.status === "requested" && r.quotes.length > 0 ? (
          <ul className="calc" style={{ marginTop: 10 }}>
            {r.quotes.map((q) => (
              <li key={q.id}>
                <span>
                  {q.supplier}
                  <span className="muted small">{` ${inr(q.rate)} each${q.cheapest ? ", cheapest" : ""}`}</span>
                </span>
                <span className="nowrap" style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <span className="num">{inr(q.total)}</span>
                  {m.can_order ? <ActionForm action={orderMaterial.bind(null, r.id, q.id)} label="Order" pendingLabel="Ordering" secondary={!q.cheapest} /> : null}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {m.can_order && r.status === "requested" ? (
          <details className="disclosure">
            <summary>{r.quotes.length ? "Add another quote" : "Add a quote"}</summary>
            <ActionForm action={addQuote.bind(null, r.id)} label="Add the quote" pendingLabel="Adding" secondary>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor={`q-${r.id}-s`}>Supplier</label>
                  <input id={`q-${r.id}-s`} name="supplier" required />
                </div>
                <div className="field">
                  <label htmlFor={`q-${r.id}-r`}>{`Rate for each ${r.unit.replace(/s$/, "")}, in rupees`}</label>
                  <input id={`q-${r.id}-r`} name="rate" inputMode="decimal" required />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
      </div>
      <div className="row-side">
        {m.can_ask && r.status === "ordered" ? <ActionForm action={receiveMaterial.bind(null, r.id)} label="It arrived" pendingLabel="Saving" /> : null}
        {m.can_ask && r.status === "requested" ? <ActionForm action={cancelMaterial.bind(null, r.id)} label="Cancel" pendingLabel="Cancelling" secondary /> : null}
      </div>
    </li>
  );
}

async function MaterialsView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const m = await api.materials(id);
  const low = m.stock.filter((s) => s.low);

  return (
    <>
      {m.can_ask ? (
        <section>
          <div className="section-head">
            <h2>Need material?</h2>
          </div>
          <ActionForm action={askForMaterial.bind(null, id)} label="Ask the office" pendingLabel="Sending">
            <ItemFields m={m} prefix="ask" needBy />
          </ActionForm>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>{`Asked for (${m.open.length})`}</h2>
        </div>
        {m.open.length === 0 ? (
          <p className="empty">Nothing waiting.</p>
        ) : (
          <ul className="rows">
            {m.open.map((r) => (
              <Request key={r.id} r={r} m={m} />
            ))}
          </ul>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>On site now</h2>
          {low.length ? <p>{`${low.length} running low`}</p> : null}
        </div>
        {m.stock.length === 0 ? (
          <p className="empty">No material recorded yet.</p>
        ) : (
          <div className="tile-grid">
            {m.stock.map((s) => (
              <div key={s.id} className="tile">
                <p className="tile-label">{s.name}</p>
                <p className="tile-value">{`${s.in_stock} ${s.unit}`}</p>
                {s.low ? <span className="tag tag-overdue">Running low</span> : null}
              </div>
            ))}
          </div>
        )}
        {m.can_ask ? (
          <details className="disclosure" style={{ marginTop: 12 }}>
            <summary>Material arrived without a request</summary>
            <ActionForm action={materialArrived.bind(null, id)} label="Add to stock" pendingLabel="Adding" secondary>
              <ItemFields m={m} prefix="in" />
            </ActionForm>
          </details>
        ) : null}
      </section>

      {m.closed.length > 0 ? (
        <section className="section">
          <details className="disclosure">
            <summary>{`Received and cancelled (${m.closed.length})`}</summary>
            <ul className="rows">
              {m.closed.map((r) => (
                <li key={r.id} className="row row-1">
                  <div>
                    <p className="row-title">{`${r.quantity} ${r.unit} ${r.item}`}</p>
                    <p className="row-detail">{r.status === "received" && r.received_on ? `Received ${day(r.received_on)}${r.order ? `, ${r.order}` : ""}` : r.status_label}</p>
                  </div>
                </li>
              ))}
            </ul>
          </details>
        </section>
      ) : null}
    </>
  );
}
