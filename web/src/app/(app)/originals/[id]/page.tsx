import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { moveOriginal } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { DateField } from "@/components/documents";
import { Barcode, where } from "@/components/originals";
import { api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Original" };

export default function OriginalPage({ params }: PageProps<"/originals/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Opening the original</p>}>
      <OriginalView params={params} />
    </Suspense>
  );
}

async function OriginalView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const o = await api.original(id);
  return (
    <>
      <p className="small">
        <Link href={`/projects/${o.project.id}/documents`}>{`${o.project.name}, documents`}</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>{`${o.number}: ${o.title}`}</h1>
          <p>
            {`${where(o)}, since ${day(o.since)}`}
            {o.against ? `, against ${o.against}` : ""}
          </p>
        </div>
      </div>
      {o.away_too_long ? (
        <p className="notice">{`It has been away ${o.days_there} days. Ask for it back, or record where it is now.`}</p>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>Where it has been</h2>
          <p>Newest first</p>
        </div>
        <ul className="rows">
          {o.moves.map((m, i) => (
            <li key={i} className="row">
              <div>
                <span className="small muted nowrap">{day(m.since)}</span>
              </div>
              <div>
                <p className="row-title">{m.held_by ? `${m.held_at_label}: ${m.held_by}` : m.held_at_label}</p>
                <p className="row-detail">
                  {[m.against ? `Against ${m.against}` : "", m.note ?? "", m.recorded_by ? `Recorded by ${m.recorded_by}` : ""]
                    .filter(Boolean)
                    .join(". ")}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {o.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>It has moved</h2>
            <p>Record where it went, and when</p>
          </div>
          <ActionForm action={moveOriginal.bind(null, o.id)} label="Record the move" pendingLabel="Saving">
            <div className="field-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label htmlFor="move-at">Where it is now</label>
                <select id="move-at" name="held_at" defaultValue={o.held_at}>
                  {o.held_at_choices.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="move-by">Who has it</label>
                <input id="move-by" name="held_by" placeholder="Rao & Co, advocates" />
              </div>
              <DateField name="since" label="Since" id="move-since" />
              <div className="field">
                <label htmlFor="move-against">Held against (optional)</label>
                <input id="move-against" name="against" />
              </div>
              <div className="field">
                <label htmlFor="move-note">Why (optional)</label>
                <input id="move-note" name="note" placeholder="For the buyer's bank's legal check" />
              </div>
            </div>
          </ActionForm>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>Its label</h2>
          <p>Stick it on the folder; a barcode reader opens this page from it</p>
        </div>
        <div className="label-sheet">
          <div className="label">
            <Barcode number={o.number} />
            <p className="label-number">{o.number}</p>
            <p className="label-title">{o.title}</p>
          </div>
        </div>
      </section>
    </>
  );
}
