import { toSVG } from "bwip-js/node";
import Link from "next/link";

import { addOriginal } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { DateField } from "@/components/documents";
import { type OriginalRow, type ProjectOriginals, api } from "@/lib/api";
import { day } from "@/lib/format";

/** A Code 128 barcode of an original's number, which an ordinary barcode reader types back. */
export function Barcode({ number }: { number: string }) {
  const svg = toSVG({ bcid: "code128", text: number, height: 10, scale: 2, includetext: false });
  // The barcode is drawn from the original's own number (O- and digits) by the library, so the
  // markup holds nothing anyone typed.
  return <span className="barcode" dangerouslySetInnerHTML={{ __html: svg }} />;
}

export function where(o: Pick<OriginalRow, "held_at_label" | "held_by">): string {
  return o.held_by ? `${o.held_at_label}: ${o.held_by}` : o.held_at_label;
}

/** The register of originals for a project, on its Documents tab. */
export async function OriginalsSection({ projectId }: { projectId: string }) {
  const r: ProjectOriginals = await api.originals(projectId);
  return (
    <section className="section">
      <div className="section-head">
        <h2>Originals</h2>
        <p>Where each paper original is: in the office, with the bank, with the lawyer</p>
      </div>
      <form action="/originals" method="get" className="inline-form" style={{ marginTop: 12 }}>
        <div className="field">
          <label htmlFor="original-number">Scan a label, or type its number</label>
          <input id="original-number" name="n" placeholder="O-0001" autoComplete="off" />
        </div>
        <button type="submit" className="button button-secondary">
          Open
        </button>
      </form>
      {r.originals.length === 0 ? (
        <p className="empty">No originals in the register yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Number</th>
              <th>Original</th>
              <th>Where it is</th>
              <th>Since</th>
            </tr>
          </thead>
          <tbody>
            {r.originals.map((o) => (
              <tr key={o.id}>
                <td className="nowrap num">
                  <Link href={`/originals/${o.id}`}>{o.number}</Link>
                </td>
                <td>
                  {o.title} <span className="small muted">{o.kind_label}</span>
                </td>
                <td>
                  {where(o)}
                  {o.against ? <span className="small muted">{`, against ${o.against}`}</span> : null}
                </td>
                <td className="nowrap">
                  {day(o.since)}
                  {o.away_too_long ? <span className="tag tag-soon" style={{ marginLeft: 8 }}>{`Away ${o.days_there} days`}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12 }}>
        {r.originals.length ? (
          <Link href={`/projects/${projectId}/originals/labels`} className="link-action">
            Print labels
          </Link>
        ) : null}
      </div>
      {r.can_edit ? (
        <details className="disclosure">
          <summary>Add an original to the register</summary>
          <ActionForm action={addOriginal.bind(null, projectId)} label="Add it" pendingLabel="Adding">
            <div className="field-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label htmlFor="original-title">What it is</label>
                <input id="original-title" name="title" required placeholder="Title deed, survey 42" />
              </div>
              <div className="field">
                <label htmlFor="original-kind">Kind</label>
                <select id="original-kind" name="kind" defaultValue="title">
                  {r.kinds.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="original-at">Where it is now</label>
                <select id="original-at" name="held_at" defaultValue="office">
                  {r.held_at.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="original-by">Who has it</label>
                <input id="original-by" name="held_by" placeholder="HDFC Bank, MG Road branch" />
              </div>
              <DateField name="since" label="There since" id="original-since" />
              <div className="field">
                <label htmlFor="original-against">Held against (optional)</label>
                <input id="original-against" name="against" placeholder="Project loan 4471" />
              </div>
            </div>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}
