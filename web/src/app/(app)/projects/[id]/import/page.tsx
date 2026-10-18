import Link from "next/link";
import { Suspense } from "react";

import { newConnectorCode, startImport, unlinkConnector, uploadStatement, uploadTally } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { InboundBox } from "@/components/inbound";
import { PUBLIC_API_URL, api } from "@/lib/api";
import { day } from "@/lib/format";

export default function ImportPage({ params }: PageProps<"/projects/[id]/import">) {
  return (
    <Suspense fallback={<p className="loading">Opening the Import centre</p>}>
      <ImportView params={params} />
    </Suspense>
  );
}

const STATUS: Record<string, string> = {
  preview: "Not applied yet",
  applied: "Applied",
  undone: "Undone",
};

async function ImportView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [list, tallyList, bankList, box, linked] = await Promise.all([
    api.imports(id),
    api.tallyImports(id),
    api.bankStatements(id),
    api.inbound(id),
    api.connectors(id),
  ]);

  return (
    <>
      <InboundBox box={box} />

      <section className="section">
        <div className="section-head">
          <h2>From Tally</h2>
          <p>Suppliers, their bills and your buyers&apos; payments, straight from Tally&apos;s own export</p>
        </div>
        <ol className="calc" style={{ marginTop: 12, maxWidth: 760, paddingLeft: 0 }}>
          <li>
            <span>
              1. In TallyPrime, open the company and press Alt+E (Export). Choose Masters, then All
              Masters, with dependent masters, and export as XML.
            </span>
          </li>
          <li>
            <span>
              2. Export again: Transactions, All Vouchers, for the period you want, also as XML. Both
              can go in one file or two.
            </span>
          </li>
          <li>
            <span>
              3. Upload the files here. JSON from TallyPrime 7 works too, and so does a Day Book exported
              to Excel, with less detail. Lekhara tells you what each file is missing.
            </span>
          </li>
        </ol>
        {tallyList.can_import ? (
          <div style={{ maxWidth: 560, marginTop: 20 }}>
            <ActionForm action={uploadTally.bind(null, id)} label="Read the Tally file" pendingLabel="Reading the file">
              <div className="field">
                <label htmlFor="tally-file">File exported from Tally</label>
                <input id="tally-file" name="file" type="file" accept=".xml,.json,.xlsx,.csv,.txt" required />
              </div>
            </ActionForm>
          </div>
        ) : null}
        <details className="disclosure" open={linked.connectors.some((c) => c.status === "active")}>
          <summary>Or connect Tally, so it comes in by itself</summary>
          <p className="small muted" style={{ maxWidth: 760, margin: "8px 0 12px" }}>
            The Lekhara Connector runs on the computer with Tally. Every few minutes it reads Tally&apos;s masters and
            vouchers, over Tally&apos;s own connection on that computer, and sends them here; nothing in Tally is changed
            and nothing is opened to the internet. In TallyPrime, turn on its HTTP server first (Help, Settings,
            Connectivity: act as a server on port 9000). Then link the computer with a code, which works once:
          </p>
          {linked.can_edit ? (
            <>
              <ActionForm action={newConnectorCode.bind(null, id)} label="Get a code" pendingLabel="Making a code" secondary />
              <p className="small" style={{ maxWidth: 760 }}>
                On the Tally computer, run <code>{`lekhara-connector link CODE --server ${PUBLIC_API_URL}`}</code>, then{" "}
                <code>lekhara-connector run</code>.
              </p>
            </>
          ) : null}
          {linked.connectors.filter((c) => c.status === "active").length > 0 ? (
            <ul className="rows" style={{ marginTop: 12 }}>
              {linked.connectors
                .filter((c) => c.status === "active")
                .map((c) => (
                  <li key={c.id} className="row">
                    <div>
                      <span className={c.last_state ? "tag tag-soon" : "tag tag-done"}>{c.last_state ? "Check" : "Connected"}</span>
                    </div>
                    <div>
                      <p className="row-title">{`${c.name ?? "A computer"}${c.company ? `, reading ${c.company}` : ""}`}</p>
                      <p className="row-detail">
                        {c.last_sync_at
                          ? `Last brought in ${c.last_sync_at.replace("T", ", ").slice(0, 17)}.`
                          : "Linked; nothing sent yet."}
                        {c.last_seen_at ? ` Last heard from ${c.last_seen_at.replace("T", ", ").slice(0, 17)}.` : ""}
                      </p>
                      {c.last_state ? <p className="row-meta">{c.last_state}</p> : null}
                    </div>
                    <div className="row-side">
                      {c.last_import_id ? (
                        <Link href={`/tally/${c.last_import_id}`} className="link-action">
                          Latest sync
                        </Link>
                      ) : null}
                      {linked.can_edit ? (
                        <ActionForm action={unlinkConnector.bind(null, c.id)} label="Unlink" pendingLabel="Unlinking" secondary />
                      ) : null}
                    </div>
                  </li>
                ))}
            </ul>
          ) : null}
        </details>
        {tallyList.imports.length > 0 ? (
          <table className="table" style={{ marginTop: 20 }}>
            <thead>
              <tr>
                <th>Tally file</th>
                <th>Company</th>
                <th>When</th>
                <th>State</th>
                <th className="right">Bills</th>
                <th className="right">Payments</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tallyList.imports.map((t) => (
                <tr key={t.id}>
                  <td>{t.filename}</td>
                  <td>{t.company}</td>
                  <td className="nowrap">{t.created_at.replace("T", ", ").slice(0, 17)}</td>
                  <td>{STATUS[t.status === "review" ? "preview" : t.status] ?? t.status}</td>
                  <td className="right num">{t.bills ?? ""}</td>
                  <td className="right num">{t.receipts ?? ""}</td>
                  <td className="right">
                    <Link href={`/tally/${t.id}`} className="link-action">
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>From your bank</h2>
          <p>Buyers&apos; payments and the RERA account, from the statement your net banking gives you</p>
        </div>
        <ol className="calc" style={{ marginTop: 12, maxWidth: 760, paddingLeft: 0 }}>
          <li>
            <span>
              1. In net banking, open the statement of the account buyers pay into, or of the RERA designated
              account.
            </span>
          </li>
          <li>
            <span>2. Choose the dates and download it as Excel or CSV, not PDF. Any bank&apos;s layout works.</span>
          </li>
          <li>
            <span>
              3. Upload it here. Lekhara matches each buyer&apos;s payment to their unit, asks about the rest once,
              and leaves out anything already brought in from Tally or an earlier statement.
            </span>
          </li>
        </ol>
        {bankList.can_import ? (
          <div style={{ maxWidth: 560, marginTop: 20 }}>
            <ActionForm action={uploadStatement.bind(null, id)} label="Read the statement" pendingLabel="Reading the statement">
              <div className="field">
                <label htmlFor="bank-file">Statement from net banking</label>
                <input id="bank-file" name="file" type="file" accept=".xls,.xlsx,.csv,.txt,.htm,.html" required />
              </div>
            </ActionForm>
          </div>
        ) : null}
        {bankList.statements.length > 0 ? (
          <table className="table" style={{ marginTop: 20 }}>
            <thead>
              <tr>
                <th>Statement</th>
                <th>Account</th>
                <th>Period</th>
                <th>State</th>
                <th className="right">Transactions</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {bankList.statements.map((b) => (
                <tr key={b.id}>
                  <td>{b.filename}</td>
                  <td>{[b.bank, b.account].filter(Boolean).join(", ")}</td>
                  <td className="nowrap">{b.period_from ? `${day(b.period_from)} to ${day(b.period_to ?? b.period_from)}` : ""}</td>
                  <td>{STATUS[b.status === "review" ? "preview" : b.status] ?? b.status}</td>
                  <td className="right num">{b.lines}</td>
                  <td className="right">
                    <Link href={`/bank/${b.id}`} className="link-action">
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Import units and buyers</h2>
          <p>From your sales sheet, your CRM export or the Lekhara template</p>
        </div>
        <ul className="calc" style={{ marginTop: 12, maxWidth: 760 }}>
          <li>
            <span>Any Excel (.xlsx) or CSV file works; title rows above the column names are skipped.</span>
          </li>
          <li>
            <span>
              Columns are matched by name, such as Flat No, Customer Name or Sale Value. You can
              correct the matching before anything is saved.
            </span>
          </li>
          <li>
            <span>
              You see every change first. Units are matched on their number, so importing the same
              file again changes nothing, and blank cells never erase what is there.
            </span>
          </li>
          <li>
            <span>An import can be undone for 30 days.</span>
          </li>
        </ul>
        <p className="small" style={{ marginTop: 12 }}>
          Starting from scratch?{" "}
          <a href="/download/imports/templates/units.xlsx" className="link-action">
            Download the Excel template
          </a>{" "}
          or the{" "}
          <a href="/download/imports/templates/units.csv" className="link-action">
            CSV version
          </a>
          .
        </p>
        {list.can_import ? (
          <div style={{ maxWidth: 560, marginTop: 20 }}>
            <ActionForm action={startImport.bind(null, id, "units")} label="Preview the import" pendingLabel="Reading the file">
              <div className="field">
                <label htmlFor="file">Your file</label>
                <input id="file" name="file" type="file" accept=".xlsx,.xlsm,.csv" required />
              </div>
            </ActionForm>
          </div>
        ) : (
          <p className="empty">Your role cannot import into this project.</p>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Import buyer payments</h2>
          <p>From your collections register or a bank export: unit, date, amount, TDS and UTR</p>
        </div>
        <p className="small" style={{ marginTop: 12 }}>
          <a href="/download/imports/templates/receipts.xlsx" className="link-action">
            Download the payments template
          </a>
          . Payments already recorded are recognised, so the same file can be imported again.
        </p>
        {list.can_import ? (
          <div style={{ maxWidth: 560, marginTop: 16 }}>
            <ActionForm action={startImport.bind(null, id, "receipts")} label="Preview the payments" pendingLabel="Reading the file">
              <div className="field">
                <label htmlFor="receipts-file">Your file</label>
                <input id="receipts-file" name="file" type="file" accept=".xlsx,.xlsm,.csv" required />
              </div>
            </ActionForm>
          </div>
        ) : null}
      </section>

      <section className="section" id="purchases">
        <div className="section-head">
          <h2>Import suppliers, bills and orders</h2>
          <p>For bills and orders you keep in a sheet rather than in Tally</p>
        </div>
        <div className="field-grid" style={{ marginTop: 12 }}>
          {(
            [
              ["suppliers", "Suppliers", "Name, GSTIN, MSME category, Udyam number", "Preview the suppliers"],
              ["bills", "Suppliers' bills", "Supplier, bill number and date, taxable value, GST, paid on, cost line", "Preview the bills"],
              ["commitments", "Work and purchase orders", "Order number, cost line, amount, date, supplier", "Preview the orders"],
            ] as const
          ).map(([kind, title, what, label]) => (
            <div key={kind}>
              <p className="row-title">{title}</p>
              <p className="small muted">{what}</p>
              <p className="small" style={{ margin: "6px 0 10px" }}>
                <a href={`/download/imports/templates/${kind}.xlsx`} className="link-action">
                  Template
                </a>
              </p>
              {list.can_import ? (
                <ActionForm action={startImport.bind(null, id, kind)} label={label} pendingLabel="Reading the file" secondary>
                  <div className="field">
                    <label htmlFor={`${kind}-file`}>Your file</label>
                    <input id={`${kind}-file`} name="file" type="file" accept=".xlsx,.xlsm,.csv" required />
                  </div>
                </ActionForm>
              ) : null}
            </div>
          ))}
        </div>
        <p className="small muted" style={{ maxWidth: 760 }}>
          Suppliers are matched on GSTIN or name, bills on the supplier and bill number, orders on their number, so the
          same sheet imported again changes nothing. A bill with a cost line counts as cost; leave the cost line blank
          when Tally already brings in your costs.
        </p>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Earlier imports</h2>
        </div>
        {list.imports.length === 0 ? (
          <p className="empty">Nothing has been imported into this project yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>File</th>
                <th>What</th>
                <th>When</th>
                <th>State</th>
                <th className="right">Added</th>
                <th className="right">Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.imports.map((b) => (
                <tr key={b.id}>
                  <td>{b.filename}</td>
                  <td>{b.title}</td>
                  <td className="nowrap">{b.created_at.replace("T", ", ").slice(0, 17)}</td>
                  <td>{STATUS[b.status] ?? b.status}</td>
                  <td className="right num">{b.added ?? ""}</td>
                  <td className="right num">{b.updated ?? ""}</td>
                  <td className="right">
                    <Link href={`/imports/${b.id}`} className="link-action">
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
