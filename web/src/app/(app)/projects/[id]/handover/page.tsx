import Link from "next/link";
import { Suspense } from "react";

import { setAssociationItem } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Handover, type UnitReadiness, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export default function HandoverPage({ params }: PageProps<"/projects/[id]/handover">) {
  return (
    <Suspense fallback={<p className="loading">Checking every unit for registration</p>}>
      <HandoverView params={params} />
    </Suspense>
  );
}

function groups(h: Handover): { stage: string; text: string; units: UnitReadiness[] }[] {
  const order = [...h.stages.map((s) => s.stage), "done"];
  const by = new Map<string, UnitReadiness[]>();
  for (const u of h.units) by.set(u.blocker, [...(by.get(u.blocker) ?? []), u]);
  return order
    .filter((stage) => by.has(stage))
    .map((stage) => {
      const units = by.get(stage) ?? [];
      return { stage, text: units[0].blocker_text, units };
    });
}

async function HandoverView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const h = await api.handover(id);
  const s = h.summary;
  const ocIn = h.oc.received_on !== null;

  return (
    <>
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Registered</p>
          <p className="stat-value">
            {s.registered} of {s.units}
          </p>
          <p className="stat-note">Booked units with a registered sale deed</p>
        </div>
        <div className="stat">
          <p className="stat-label">Handed over</p>
          <p className="stat-value">{s.handed_over}</p>
          <p className="stat-note">Keys and possession letter given</p>
        </div>
        <div className="stat">
          <p className="stat-label">Waiting on registration</p>
          <p className="stat-value">{inr(s.money_waiting)}</p>
          <p className="stat-note">Still owed by buyers whose deed is not registered</p>
        </div>
        <div className="stat">
          <p className="stat-label">Occupancy certificate</p>
          <p className="stat-value">{h.oc.label}</p>
          <p className="stat-note">
            {ocIn ? `On ${day(h.oc.received_on)}${h.oc.reference ? `, ${h.oc.reference}` : ""}` : "Registration starts once it is in"}
          </p>
        </div>
      </div>

      {h.conveyance_due_on && !h.common_areas_conveyed_on ? (
        <p className="notice" style={{ marginTop: 32 }}>
          Convey the common areas to the association by {day(h.conveyance_due_on)}. RERA asks for
          this within three months of the occupancy certificate where no local law says otherwise;
          confirm the Karnataka position with your lawyer.
        </p>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>Where units are held up</h2>
          <p>Every unit moves through the same steps. Each one waits at the first step not done.</p>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Step</th>
              <th className="right">Units waiting here</th>
            </tr>
          </thead>
          <tbody>
            {h.stages.map((st) => (
              <tr key={st.stage}>
                <td>{st.label}</td>
                <td className="right num">{st.blocked > 0 ? st.blocked : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>What to do next</h2>
          <p>Units grouped by what they are waiting for. Open a unit to record the next step.</p>
        </div>
        {h.units.length === 0 ? (
          <p className="empty">No unit is booked yet.</p>
        ) : (
          groups(h).map((g, i) => (
            <details key={g.stage} className="disclosure" open={i === 0 && g.units.length <= 12}>
              <summary>
                {g.text} ({plural(g.units.length, "unit")})
              </summary>
              <table className="table">
                <thead>
                  <tr>
                    <th>Unit</th>
                    <th>Buyer</th>
                    <th>e-Khata</th>
                    <th className="right">Balance due</th>
                    <th className="right">Stamp duty and fees</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {g.units.map((u) => (
                    <tr key={u.unit_id}>
                      <td>{u.label}</td>
                      <td>{u.buyer}</td>
                      <td>{u.ekhata_label}</td>
                      <td className="right num">
                        {Number(u.balance_due) > 0 ? inr(u.balance_due) : ""}
                      </td>
                      <td className="right num">{inr(u.cost.total)}</td>
                      <td className="right">
                        <Link href={`/units/${u.unit_id}`} className="link-action">
                          Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))
        )}
        <p className="small muted" style={{ marginTop: 16 }}>
          Stamp duty and fees are estimates, worked out on the higher of the agreement value and
          the guidance value. The buyer pays them; confirm the rates before quoting.
        </p>
      </section>

      {ocIn ? <Association h={h} projectId={id} /> : null}
    </>
  );
}

function Association({ h, projectId }: { h: Handover; projectId: string }) {
  const done = h.association.filter((i) => i.done_on).length;
  return (
    <section className="section">
      <div className="section-head">
        <h2>Handing over to the residents&apos; association</h2>
        <p>{`${done} of ${h.association.length} done`}</p>
      </div>
      <ul className="rows">
        {h.association.map((item) => (
          <li key={item.key} className="row">
            <div>
              <span className={item.done_on ? "tag tag-done" : "tag tag-upcoming"}>{item.done_on ? "Done" : "To do"}</span>
            </div>
            <div>
              <p className="row-title">{item.label}</p>
              {item.done_on || item.note ? (
                <p className="row-detail">
                  {[item.done_on ? `Done ${day(item.done_on)}` : null, item.note].filter(Boolean).join("  ·  ")}
                </p>
              ) : null}
              {h.can_edit ? (
                <details className="disclosure">
                  <summary>{item.done_on ? "Change" : "Mark as done"}</summary>
                  <ActionForm action={setAssociationItem.bind(null, projectId, item.key)} label="Save" pendingLabel="Saving" secondary>
                    <div className="field-grid">
                      <div className="field">
                        <label htmlFor={`as-${item.key}-on`}>Done on</label>
                        <input id={`as-${item.key}-on`} name="done_on" type="date" defaultValue={item.done_on ?? ""} />
                      </div>
                      <div className="field">
                        <label htmlFor={`as-${item.key}-note`}>Note</label>
                        <input id={`as-${item.key}-note`} name="note" defaultValue={item.note ?? ""} />
                      </div>
                    </div>
                  </ActionForm>
                </details>
              ) : null}
            </div>
            <div />
          </li>
        ))}
      </ul>
    </section>
  );
}
