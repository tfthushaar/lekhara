import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { applyImport, mapImport, undoImport } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type ImportBatch, api } from "@/lib/api";
import { plural } from "@/lib/format";

export const metadata: Metadata = { title: "Import" };

export default function ImportBatchPage({ params }: PageProps<"/imports/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Checking every row</p>}>
      <BatchView params={params} />
    </Suspense>
  );
}

const ACTION: Record<string, { label: string; className: string }> = {
  error: { label: "Will be left out", className: "tag tag-fail" },
  add: { label: "New", className: "tag tag-done" },
  update: { label: "Changes", className: "tag tag-soon" },
};

function value(v: string | number | null): string {
  return v === null || v === "" ? "blank" : String(v);
}

async function BatchView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const b = await api.importBatch(id);
  const base = `/projects/${b.project_id}`;
  const ready = b.counts.add + b.counts.update;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{b.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/import`}>Import</Link>
          </p>
          <h1>{b.filename}</h1>
          <p>
            {b.title}. {plural(b.total_rows, "row")} below the column names on row {b.header_row}.
          </p>
        </div>
      </div>

      {b.status === "preview" ? <Preview b={b} ready={ready} /> : <Result b={b} base={base} />}
    </>
  );
}

function Preview({ b, ready }: { b: ImportBatch; ready: number }) {
  return (
    <>
      <p className="status-line">
        Nothing is saved yet. Check the columns and the rows, then import.
      </p>
      <div className="stats">
        <div className="stat">
          <p className="stat-label">New</p>
          <p className="stat-value">{b.counts.add}</p>
          <p className="stat-note">{b.kind === "receipts" ? "Payments not recorded yet" : "Units not in Lekhara yet"}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Changes</p>
          <p className="stat-value">{b.counts.update}</p>
          <p className="stat-note">{b.kind === "receipts" ? "Payments are only added" : "Units whose details differ"}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Already the same</p>
          <p className="stat-value">{b.counts.unchanged}</p>
          <p className="stat-note">Left as they are</p>
        </div>
        <div className="stat">
          <p className="stat-label">Will be left out</p>
          <p className="stat-value">{b.counts.error}</p>
          <p className="stat-note">Rows with something to fix</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Columns</h2>
          <p>How each column in your file is read. Columns set to &ldquo;Not used&rdquo; are ignored.</p>
        </div>
        {b.missing_required.length > 0 ? (
          <p className="notice" style={{ margin: "12px 0" }}>
            {`No column is set to ${b.missing_required.join(" or ")} yet. Choose which column holds it.`}
          </p>
        ) : null}
        <ActionForm action={mapImport.bind(null, b.id)} label="Use these columns" pendingLabel="Checking again" secondary>
          <table className="table">
            <thead>
              <tr>
                <th>Your column</th>
                <th>First value</th>
                <th>Read as</th>
              </tr>
            </thead>
            <tbody>
              {b.columns.map((c) => (
                <tr key={c.index}>
                  <td>{c.header || <span className="muted">No name</span>}</td>
                  <td className="muted">{c.sample}</td>
                  <td>
                    <select name={`column_${c.index}`} defaultValue={c.field ?? ""} aria-label={`Read ${c.header} as`} disabled={!b.can_edit}>
                      <option value="">Not used</option>
                      {b.fields.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                          {f.required ? " (needed)" : ""}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ActionForm>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Rows</h2>
          <p>Rows to fix first, then new units, then changes</p>
        </div>
        {b.rows.length === 0 ? (
          <p className="empty">Every row matches what Lekhara already has.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Row</th>
                <th>Unit</th>
                <th>What happens</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {b.rows.map((r) => (
                <tr key={r.row}>
                  <td className="num">{r.row}</td>
                  <td>{r.key ?? <span className="muted">No number</span>}</td>
                  <td>
                    <span className={ACTION[r.action].className}>{ACTION[r.action].label}</span>
                  </td>
                  <td>
                    {r.messages.join(" ")}
                    {r.changes.map((c) => (
                      <span key={c.field} className="small" style={{ display: "block" }}>
                        {`${c.field}: ${value(c.before)} to ${value(c.after)}`}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {b.can_edit ? (
        <section className="section">
          {ready > 0 ? (
            <ActionForm
              action={applyImport.bind(null, b.id)}
              label={`Import ${plural(ready, b.kind === "receipts" ? "payment" : "unit")}`}
              pendingLabel="Importing"
            >
              <p style={{ marginBottom: 12 }}>
                {b.counts.error > 0
                  ? `${plural(b.counts.error, "row")} with something to fix will be left out; fix them in your file and import it again later.`
                  : "Every row is ready."}
              </p>
            </ActionForm>
          ) : (
            <p className="empty">Nothing to import. Fix the rows above, or check the columns.</p>
          )}
        </section>
      ) : null}
    </>
  );
}

function Result({ b, base }: { b: ImportBatch; base: string }) {
  const r = b.result;
  return (
    <>
      <p className="status-line">
        {b.status === "undone"
          ? "This import was undone. The units are as they were before it."
          : b.kind === "receipts"
            ? `Imported: ${r ? plural(r.added, "payment") : ""} recorded.`
            : `Imported: ${r ? `${plural(r.added, "unit")} added, ${plural(r.updated, "unit")} changed` : ""}.`}
      </p>
      {r && b.status === "applied" ? (
        <p className="muted">
          {r.unchanged ? `${plural(r.unchanged, "row")} already matched. ` : ""}
          {r.errors ? `${plural(r.errors, "row")} were left out.` : ""}
        </p>
      ) : null}
      <p style={{ marginTop: 16 }}>
        <Link href={b.kind === "receipts" ? `${base}/collections` : `${base}/units`} className="link-action">
          {b.kind === "receipts" ? "See collections" : "See the units"}
        </Link>
      </p>
      {b.can_undo ? (
        <details className="disclosure" style={{ marginTop: 24 }}>
          <summary>Undo this import</summary>
          <p className="small muted" style={{ margin: "8px 0 12px", maxWidth: 640 }}>
            New units are removed and changed ones go back to what they were. This works only
            while nothing has happened to them since.
          </p>
          <ActionForm action={undoImport.bind(null, b.id)} label="Undo the import" pendingLabel="Undoing" secondary />
        </details>
      ) : null}
    </>
  );
}
