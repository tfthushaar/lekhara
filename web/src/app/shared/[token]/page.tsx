import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Suspense } from "react";

import { confirmRoomCode, enterRoom, forgetRoomVisitor } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { VISITOR_COOKIE, sharedRoom } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = {
  title: "Shared documents",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function SharedPage({ params }: PageProps<"/shared/[token]">) {
  return (
    <main className="main">
      <div className="shared-head">
        <span className="wordmark">Lekhara</span>
      </div>
      <Suspense fallback={<p className="loading">Opening the documents</p>}>
        <SharedView params={params} />
      </Suspense>
    </main>
  );
}

async function SharedView({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const visitor = (await cookies()).get(VISITOR_COOKIE)?.value;
  const room = await sharedRoom(token, visitor);
  if (room === null) {
    return (
      <>
        <h1>This link has closed</h1>
        <p style={{ marginTop: 12, maxWidth: 560 }}>
          It has expired or been withdrawn. Ask the person who shared it for a new link.
        </p>
      </>
    );
  }
  if (room.gate && room.pending_email) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1>{room.name}</h1>
            <p>
              Shared by {room.organization}. {room.project}.
            </p>
          </div>
        </div>
        <p style={{ maxWidth: 560, marginBottom: 16 }}>
          {`We have sent a six-digit code to ${room.pending_email}. Enter it to open the documents; it works for 15 minutes.`}
        </p>
        <div style={{ maxWidth: 560 }}>
          <ActionForm action={confirmRoomCode.bind(null, token)} label="Open the documents" pendingLabel="Checking">
            <div className="field" style={{ maxWidth: 240 }}>
              <label htmlFor="visitor-code">The code</label>
              <input id="visitor-code" name="code" inputMode="numeric" autoComplete="one-time-code" required />
            </div>
          </ActionForm>
          <div style={{ marginTop: 16 }}>
            <ActionForm action={forgetRoomVisitor.bind(null, token)} label="Use another email" pendingLabel="Starting again" secondary />
          </div>
        </div>
      </>
    );
  }
  if (room.gate) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1>{room.name}</h1>
            <p>
              Shared by {room.organization}. {room.project}.
            </p>
          </div>
        </div>
        <p style={{ maxWidth: 560, marginBottom: 16 }}>
          {room.organization} asks for your name and email before you open these documents, and we send a code to
          the email to confirm it is yours. Your name and email are shared with {room.organization} and recorded with
          each document you open or download, until this link closes on {day(room.expires_on)}.
        </p>
        <div style={{ maxWidth: 560 }}>
          <ActionForm action={enterRoom.bind(null, token)} label="Send me a code" pendingLabel="Sending">
            <div className="field">
              <label htmlFor="visitor-name">Your name</label>
              <input id="visitor-name" name="name" autoComplete="name" required />
            </div>
            <div className="field">
              <label htmlFor="visitor-email">Your email</label>
              <input id="visitor-email" name="email" type="email" autoComplete="email" required />
            </div>
          </ActionForm>
        </div>
      </>
    );
  }
  const files = `/shared/${encodeURIComponent(token)}/files`;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>{room.name}</h1>
          <p>
            Shared by {room.organization}
            {room.audience ? ` for ${room.audience}` : ""}. {room.project}, K-RERA registration{" "}
            {room.krera_registration}.
          </p>
        </div>
      </div>
      <p className="small muted" style={{ marginBottom: 24 }}>
        This link closes on {day(room.expires_on)}. {room.organization} can see when it is opened
        and what is downloaded.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Kind</th>
            <th>Dated</th>
            <th>Number</th>
            <th className="right">Size</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {room.documents.map((d) => {
            const viewable = d.content_type === "application/pdf" || d.content_type.startsWith("image/");
            return (
              <tr key={d.id}>
                <td>{d.title}</td>
                <td>{d.category_label}</td>
                <td className="nowrap">{day(d.document_date)}</td>
                <td>{d.reference}</td>
                <td className="right num">{d.size}</td>
                <td className="right nowrap">
                  {viewable ? (
                    <a href={`${files}/${d.id}?inline=1`} target="_blank" rel="noreferrer" className="link-action">
                      View
                    </a>
                  ) : null}
                  {"  "}
                  <a href={`${files}/${d.id}`} className="link-action">
                    Download
                  </a>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
