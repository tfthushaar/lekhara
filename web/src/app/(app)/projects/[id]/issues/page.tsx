import { Suspense } from "react";

import { addIssue, closeIssue } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type IssueRow, api } from "@/lib/api";
import { day, plural } from "@/lib/format";

export default function IssuesPage({ params }: PageProps<"/projects/[id]/issues">) {
  return (
    <Suspense fallback={<p className="loading">Loading</p>}>
      <IssuesView params={params} />
    </Suspense>
  );
}

function When({ i }: { i: IssueRow }) {
  if (i.status === "done") return <>{`Done ${day(i.done_on)}${i.reply ? `: ${i.reply}` : ""}`}</>;
  if (i.kind !== "defect" || !i.due_on) return <>{`Reported ${day(i.reported_on)}`}</>;
  if (i.late) return <span className="tag tag-overdue">{`Was due ${day(i.due_on)}`}</span>;
  return <>{`Put right by ${day(i.due_on)}, ${plural(i.days_left ?? 0, "day")} left`}</>;
}

function Issue({ i, canEdit }: { i: IssueRow; canEdit: boolean }) {
  return (
    <li className="row row-2 row-stack">
      <div>
        <p className="row-title">{i.title}</p>
        <p className="row-detail">{[`${i.kind_label}, unit ${i.unit}`, i.buyer].filter(Boolean).join(", ")}</p>
        <p className="row-meta">
          <When i={i} />
        </p>
        {i.detail ? <p className="row-meta">{i.detail}</p> : null}
        {i.note ? <p className="row-meta">{i.note}</p> : null}
      </div>
      <div className="row-side">
        {canEdit && i.status === "open" ? <ActionForm action={closeIssue.bind(null, i.id)} label="Done" pendingLabel="Saving" /> : null}
      </div>
    </li>
  );
}

async function IssuesView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const v = await api.issues(id);

  return (
    <>
      {v.can_edit ? (
        <section>
          <div className="section-head">
            <h2>Something to put right?</h2>
          </div>
          <ActionForm action={addIssue.bind(null, id)} label="Add it" pendingLabel="Adding">
            <fieldset className="choice-pills">
              <legend className="small muted" style={{ marginBottom: 8 }}>
                What is it?
              </legend>
              {v.kinds.map((k, n) => (
                <label key={k.value}>
                  <input type="radio" name="kind" value={k.value} defaultChecked={n === 0} />
                  <span>{k.label}</span>
                </label>
              ))}
            </fieldset>
            <div className="field-grid">
              <div className="field">
                <label htmlFor="is-unit">Unit</label>
                <select id="is-unit" name="unit_id" required defaultValue="">
                  <option value="" disabled>
                    Choose the unit
                  </option>
                  {v.units.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.buyer ? `${u.label}, ${u.buyer}` : u.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="is-title">In a few words</label>
                <input id="is-title" name="title" required placeholder="Seepage under the kitchen sink" />
              </div>
            </div>
            <details className="disclosure">
              <summary>More details</summary>
              <div className="field">
                <label htmlFor="is-detail">Details</label>
                <textarea id="is-detail" name="detail" rows={2} />
              </div>
              <div className="field" style={{ maxWidth: 260 }}>
                <label htmlFor="is-on">Reported on (today if blank)</label>
                <input id="is-on" name="reported_on" type="date" />
              </div>
            </details>
            <p className="small muted" style={{ marginBottom: 12 }}>
              {`A defect after possession has to be put right within ${v.defect_days} days. We count them for you.`}
            </p>
          </ActionForm>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>{`Open (${v.open.length})`}</h2>
          {v.late ? <p>{`${v.late} late`}</p> : null}
        </div>
        {v.open.length === 0 ? (
          <p className="empty">Nothing open.</p>
        ) : (
          <ul className="rows">
            {v.open.map((i) => (
              <Issue key={i.id} i={i} canEdit={v.can_edit} />
            ))}
          </ul>
        )}
      </section>

      {v.done.length > 0 ? (
        <section className="section">
          <details className="disclosure">
            <summary>{`Done (${v.done.length})`}</summary>
            <ul className="rows">
              {v.done.map((i) => (
                <Issue key={i.id} i={i} canEdit={false} />
              ))}
            </ul>
          </details>
        </section>
      ) : null}
    </>
  );
}
