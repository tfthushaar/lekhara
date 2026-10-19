import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { saveTable } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Edit as a table" };

const BACK: Record<string, string> = {
  units: "units",
  suppliers: "suppliers",
  bills: "suppliers",
  commitments: "budget",
  approvals: "approvals",
};

export default function TablePage({ params, searchParams }: PageProps<"/projects/[id]/table/[kind]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the table</p>}>
      <TableView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function TableView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; kind: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id, kind } = await params;
  const query = await searchParams;
  const page = Number(typeof query.page === "string" ? query.page : "1") || 1;
  const t = await api.table(id, kind, page);
  const back = `/projects/${id}/${BACK[kind] ?? ""}`;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href={back}>{t.project_name}</Link>
          </p>
          <h1>{`${t.title}, as a table`}</h1>
          <p>
            Change any cell, then review the changes before they are saved. Greyed columns identify each row and cannot be
            changed here. Clearing a cell leaves the value as it is; to remove a value, open the record.
          </p>
        </div>
      </div>

      {t.total === 0 ? (
        <p className="empty">Nothing to edit yet.</p>
      ) : (
        <ActionForm
          action={saveTable.bind(null, id, kind, { rows: t.rows.length, columns: t.fields.length })}
          label="Review the changes"
          pendingLabel="Checking"
        >
          <div className="table-scroll">
            <table className="table grid-edit">
              <thead>
                <tr>
                  {t.fields.map((f) => (
                    <th key={f.key}>{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.rows.map((row, r) => (
                  <tr key={`${page}-${r}-${row[0]}`}>
                    {t.fields.map((f, c) => {
                      const name = `c-${r}-${c}`;
                      const value = row[c];
                      if (f.locked) {
                        return (
                          <td key={f.key} className="grid-locked">
                            {value}
                            <input type="hidden" name={name} value={value} />
                          </td>
                        );
                      }
                      if (f.kind === "choice" || f.kind === "bool") {
                        const options = f.kind === "bool" ? ["Yes", "No"] : f.choices.map((x) => x.label);
                        return (
                          <td key={f.key}>
                            <select name={name} defaultValue={value} aria-label={`${f.label}, row ${r + 1}`}>
                              <option value="" />
                              {options.map((o) => (
                                <option key={o} value={o}>
                                  {o}
                                </option>
                              ))}
                            </select>
                          </td>
                        );
                      }
                      return (
                        <td key={f.key}>
                          <input name={name} defaultValue={value} aria-label={`${f.label}, row ${r + 1}`} />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ActionForm>
      )}

      {t.pages > 1 ? (
        <p className="chips" style={{ alignItems: "center" }}>
          <span className="small muted">{`Page ${t.page} of ${t.pages}, ${t.total} rows. Review each page's changes before moving on.`}</span>
          {t.page > 1 ? (
            <Link href={`/projects/${id}/table/${kind}?page=${t.page - 1}`} className="link-action">
              Previous page
            </Link>
          ) : null}
          {t.page < t.pages ? (
            <Link href={`/projects/${id}/table/${kind}?page=${t.page + 1}`} className="link-action">
              Next page
            </Link>
          ) : null}
        </p>
      ) : null}
    </>
  );
}
