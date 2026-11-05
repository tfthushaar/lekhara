import type { Metadata } from "next";
import { headers } from "next/headers";
import { Suspense } from "react";

import { api } from "@/lib/api";
import { moment } from "@/lib/format";

export const metadata: Metadata = { title: "Demo mailbox" };

export default function MailboxPage() {
  return (
    <Suspense fallback={<p className="loading">Opening the mailbox</p>}>
      <Mailbox />
    </Suspense>
  );
}

/** Text with this site's own links made clickable, and nothing else. */
function Body({ text, origin }: { text: string; origin: string }) {
  const parts = text.split(/(https?:\/\/\S+)/g);
  return (
    <p className="small" style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>
      {parts.map((part, i) =>
        part.startsWith(origin) ? (
          <a key={i} href={part.slice(origin.length) || "/"}>
            {part}
          </a>
        ) : (
          part
        ),
      )}
    </p>
  );
}

async function Mailbox() {
  const [box, h] = await Promise.all([api.mailbox(), headers()]);
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const origin = `${proto}://${host}`;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Demo mailbox</h1>
          <p>{`What Lekhara would have emailed to ${box.email}. The demo sends no real email.`}</p>
        </div>
      </div>
      {box.emails.length === 0 ? (
        <p className="empty">Nothing yet. Emails show up here as you use the demo: confirming an email, an invitation, a lender opening a data room.</p>
      ) : (
        <ul className="rows">
          {box.emails.map((m, i) => (
            <li key={`${m.at}-${i}`} className="row" style={{ display: "block" }}>
              <p className="row-title">{m.subject}</p>
              <p className="row-meta">{moment(m.at)}</p>
              <Body text={m.body} origin={origin} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
