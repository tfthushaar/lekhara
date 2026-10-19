import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { standing } from "@/app/(app)/admin/standing";
import { staffFirms } from "@/lib/api";
import { day, moment } from "@/lib/format";

export const metadata: Metadata = { title: "Admin" };

export default function AdminPage({ searchParams }: PageProps<"/admin">) {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Firms</h1>
          <p>Everyone using Lekhara, their free months and payments. A firm&apos;s records open only if it allows support.</p>
        </div>
      </div>
      <Suspense fallback={<p className="loading">Loading the firms</p>}>
        <Firms searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Firms({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : "";
  const result = await staffFirms(q);
  if ("closed" in result) {
    return (
      <p className="empty">
        {result.closed} <Link href="/settings">Settings</Link>
      </p>
    );
  }
  return (
    <>
      <form method="get" className="filters">
        <div className="field">
          <label htmlFor="q">Firm, or someone&apos;s email</label>
          <input id="q" name="q" defaultValue={q} />
        </div>
        <button type="submit" className="button button-secondary">
          Find
        </button>
      </form>
      {result.firms.length === 0 ? (
        <p className="empty">No firm matches.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Firm</th>
              <th>Started</th>
              <th>Where it stands</th>
              <th className="right">People</th>
              <th className="right">Projects</th>
              <th>Last sign-in</th>
              <th>Support</th>
            </tr>
          </thead>
          <tbody>
            {result.firms.map((f) => (
              <tr key={f.id}>
                <td>
                  <Link href={`/admin/firms/${f.id}`}>{f.name}</Link>
                </td>
                <td className="nowrap">{day(f.created_on)}</td>
                <td>{standing(f)}</td>
                <td className="right num">{f.people}</td>
                <td className="right num">{f.projects}</td>
                <td className="nowrap">{moment(f.last_sign_in)}</td>
                <td className="nowrap">{f.support_until ? `Allowed to ${moment(f.support_until)}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
