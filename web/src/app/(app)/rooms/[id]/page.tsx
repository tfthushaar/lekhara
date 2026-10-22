import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";

import { newRoomLink, revokeRoom, updateRoom } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { DateField } from "@/components/documents";
import { type RoomDetail, api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Data room" };

export default function RoomPage({ params, searchParams }: PageProps<"/rooms/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Opening the data room</p>}>
      <RoomView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function origin(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

/** The room's protections, in a sentence. */
function protections(room: RoomDetail): string {
  const parts = [
    room.ask_visitor
      ? `Visitors give their name and email${room.terms ? " and accept the terms" : ""} before anything opens.`
      : "Anyone with the link can open it.",
    room.watermark ? "Every page of a PDF carries who opened it and when." : "PDFs are shared as they are.",
    room.notify
      ? room.ask_visitor
        ? "Whoever made the room is emailed when each visitor first opens it."
        : "Whoever made the room is emailed when it is first opened."
      : "",
  ];
  return parts.filter(Boolean).join(" ");
}

function when(iso: string): string {
  const [dayPart, time] = iso.split("T");
  return `${day(dayPart)}, ${time.slice(0, 5)}`;
}

async function RoomView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const token = typeof sp.link === "string" ? sp.link : null;
  const [room, site] = await Promise.all([api.room(id), origin()]);
  const base = `/projects/${room.project_id}`;
  const open = room.state === "open";
  const inRoom = new Set(room.documents_in_room.map((d) => d.id));

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{room.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/documents`}>Documents</Link>
          </p>
          <h1>{room.name}</h1>
          <p>
            {room.audience ? `For ${room.audience}. ` : ""}Made on {day(room.created_on)}.
          </p>
        </div>
      </div>

      <p className="status-line">
        {open
          ? `Open until ${day(room.expires_on)}`
          : room.state === "revoked"
            ? "Closed. The link no longer works."
            : `Expired on ${day(room.expires_on)}. The link no longer works.`}
      </p>

      <p className="small muted" style={{ marginTop: -8, marginBottom: 24, maxWidth: 720 }}>
        {protections(room)}
      </p>

      {token && open ? (
        <div className="notice" style={{ marginBottom: 32 }}>
          <p className="strong">The link to send</p>
          <input className="share-link" readOnly value={`${site}/shared/${token}`} aria-label="Link to the data room" />
          <p className="small">
            Copy it now. For safety Lekhara keeps only a fingerprint of the link, so it cannot be
            shown again. Making a new link stops this one working.
          </p>
        </div>
      ) : null}

      <div className="stats">
        <div className="stat">
          <p className="stat-label">Documents</p>
          <p className="stat-value">{room.documents}</p>
          <p className="stat-note">The latest version of each</p>
        </div>
        <div className="stat">
          <p className="stat-label">Opened</p>
          <p className="stat-value">{room.opens}</p>
          <p className="stat-note">{room.last_visit ? `Last on ${when(room.last_visit)}` : "Not yet"}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Downloads</p>
          <p className="stat-value">{room.downloads}</p>
          <p className="stat-note">Each one is recorded</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>What is shared</h2>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Kind</th>
              <th>Dated</th>
            </tr>
          </thead>
          <tbody>
            {room.documents_in_room.map((d) => (
              <tr key={d.id}>
                <td>
                  <Link href={`/documents/${d.id}`}>{d.title}</Link>
                </td>
                <td>{d.category_label}</td>
                <td className="nowrap">{day(d.document_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Visits</h2>
          <p>When the link was opened and what was downloaded</p>
        </div>
        {room.visits.length === 0 ? (
          <p className="empty">Nobody has opened the link yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>When (UTC)</th>
                <th>What</th>
                {room.visits.some((v) => v.visitor) ? <th>Who</th> : null}
              </tr>
            </thead>
            <tbody>
              {room.visits.map((v, i) => (
                <tr key={`${v.at}-${i}`}>
                  <td className="nowrap">{when(v.at)}</td>
                  <td>{v.action === "open" ? "Opened the room" : `Downloaded ${v.document ?? "a document"}`}</td>
                  {room.visits.some((x) => x.visitor) ? <td>{v.visitor ?? <span className="muted">Not asked</span>}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {room.can_share && open ? (
        <section className="section">
          <details className="disclosure">
            <summary>Change how the room is protected</summary>
            <ActionForm action={updateRoom.bind(null, room.id)} label="Save" pendingLabel="Saving" secondary>
              <input type="hidden" name="protections" value="change" />
              <label className="check-line">
                <input type="checkbox" name="ask_visitor" value="yes" defaultChecked={room.ask_visitor} /> Ask each visitor
                for their name and email before they see anything
              </label>
              <label className="check-line">
                <input type="checkbox" name="watermark" value="yes" defaultChecked={room.watermark} /> Mark every page of
                a PDF with who opened it and when
              </label>
              <label className="check-line">
                <input type="checkbox" name="notify" value="yes" defaultChecked={room.notify} /> Email whoever made the
                room the first time each visitor opens it
              </label>
              <div className="field">
                <label htmlFor="room-terms">Terms each visitor must accept</label>
                <textarea id="room-terms" name="terms" rows={4} defaultValue={room.terms ?? ""} />
                <p className="small muted">
                  Leave it empty for none. If you change the terms, visitors accept them again before anything more
                  opens.
                </p>
              </div>
            </ActionForm>
          </details>
          <details className="disclosure">
            <summary>Change what is shared</summary>
            <ActionForm action={updateRoom.bind(null, room.id)} label="Save" pendingLabel="Saving" secondary>
              <input type="hidden" name="documents" value="change" />
              <div className="checks">
                {[...room.documents_in_room, ...room.available].map((d) => (
                  <label key={d.id}>
                    <input type="checkbox" name="document_ids" value={d.id} defaultChecked={inRoom.has(d.id)} />{" "}
                    {d.title}
                    <span className="small muted">{d.category_label}</span>
                  </label>
                ))}
              </div>
            </ActionForm>
          </details>
          <details className="disclosure">
            <summary>Change the closing date</summary>
            <ActionForm action={updateRoom.bind(null, room.id)} label="Save" pendingLabel="Saving" secondary>
              <DateField name="expires_on" label="Link closes on" value={room.expires_on} id="room-expiry" />
            </ActionForm>
          </details>
          <details className="disclosure">
            <summary>Make a new link</summary>
            <p className="small muted" style={{ marginBottom: 12 }}>
              Use this if the link reached the wrong person. The old link stops working at once.
            </p>
            <ActionForm action={newRoomLink.bind(null, room.id)} label="Make a new link" pendingLabel="Making it" secondary />
          </details>
          <details className="disclosure">
            <summary>Close the data room now</summary>
            <ActionForm action={revokeRoom.bind(null, room.id)} label="Close it" pendingLabel="Closing" secondary />
          </details>
        </section>
      ) : null}
    </>
  );
}
