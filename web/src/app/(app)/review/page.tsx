import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { type ReviewQueue, api } from "@/lib/api";
import { moment, plural } from "@/lib/format";

export const metadata: Metadata = { title: "Files waiting for you" };

export default function ReviewPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Files waiting for you</h1>
          <p>Each one needs a quick choice from you.</p>
        </div>
      </div>
      <Suspense fallback={<p className="loading">Gathering what waits</p>}>
        <ReviewView />
      </Suspense>
    </>
  );
}

const KIND: Record<ReviewQueue["items"][number]["kind"], string> = {
  bank: "Bank statement",
  tally: "Tally",
  sheet: "Sheet",
  mail: "Email",
  gst: "GST return",
};

async function ReviewView() {
  const q = await api.review();
  if (q.count === 0) {
    return <p className="empty">Nothing is waiting for you.</p>;
  }
  const projects = [...new Set(q.items.map((i) => i.project_name))];
  return (
    <>
      <p className="status-line">{`${plural(q.count, "thing")} to settle, in ${plural(projects.length, "project")}.`}</p>
      {projects.map((name) => (
        <section key={name} className="section">
          <div className="section-head">
            <h2>{name}</h2>
          </div>
          <ul className="rows">
            {q.items
              .filter((i) => i.project_name === name)
              .map((i, n) => (
                <li key={`${i.href}-${n}`} className="row">
                  <div>
                    <span className="tag">{KIND[i.kind]}</span>
                  </div>
                  <div>
                    <p className="row-title">{i.title}</p>
                    <p className="row-detail">{i.detail}</p>
                    <p className="row-meta">{`Since ${moment(i.since)}`}</p>
                  </div>
                  <div className="row-side">
                    <Link href={i.href} className="link-action">
                      Settle it
                    </Link>
                  </div>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </>
  );
}
