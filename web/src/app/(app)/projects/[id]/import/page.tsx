import Link from "next/link";
import { Suspense } from "react";

import { startImport, uploadStatement, uploadTally } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";
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
  const [list, tallyList, bankList] = await Promise.all([
    api.imports(id),
    api.tallyImports(id),
    api.bankStatements(id),
  ]);

  return (
    <>
      <section>
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
