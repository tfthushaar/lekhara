import type { Metadata } from "next";
import { Suspense } from "react";

import { api } from "@/lib/api";
import { SOURCE_QUALITY } from "@/lib/labels";

export const metadata: Metadata = { title: "Rules" };

export default function RulesPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Rules</h1>
          <p>
            Every rate, limit and deadline Horus uses, with its legal basis and how settled it is.
          </p>
        </div>
      </div>
      <div className="notice" style={{ marginBottom: 32 }}>
        Rules marked To confirm or Unsettled must be checked by your CA or lawyer before you rely
        on figures based on them. Horus settings are not law; they control when Horus warns you.
      </div>
      <Suspense fallback={<p className="loading">Loading the rules</p>}>
        <RulesTable />
      </Suspense>
    </>
  );
}

async function RulesTable() {
  const pack = await api.rules();
  return (
    <>
      <p className="muted small" style={{ marginBottom: 12 }}>
        Karnataka rules pack, version {pack.version}
      </p>
      <table className="table">
        <thead>
          <tr>
            <th>Rule</th>
            <th>Value</th>
            <th>Basis</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {pack.rules.map((r) => (
            <tr key={r.key}>
              <td>
                {r.title}
                {r.note ? <p className="row-detail">{r.note}</p> : null}
              </td>
              <td className="num nowrap">{r.display}</td>
              <td>
                {r.basis}
                <p className="row-detail">Confirm against: {r.confirm_against}</p>
              </td>
              <td>
                <span
                  className={
                    r.source_quality === "official"
                      ? "tag tag-pass"
                      : r.source_quality === "horus_default"
                        ? "tag tag-done"
                        : r.source_quality === "secondary"
                          ? "tag tag-upcoming"
                          : "tag tag-soon"
                  }
                >
                  {SOURCE_QUALITY[r.source_quality]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
