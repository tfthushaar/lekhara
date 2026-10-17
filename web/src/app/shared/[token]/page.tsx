import type { Metadata } from "next";
import { Suspense } from "react";

import { sharedRoom } from "@/lib/api";
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
        <span className="wordmark">Horus</span>
      </div>
      <Suspense fallback={<p className="loading">Opening the documents</p>}>
        <SharedView params={params} />
      </Suspense>
    </main>
  );
}

async function SharedView({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const room = await sharedRoom(token);
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
