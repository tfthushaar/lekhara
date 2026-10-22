import Link from "next/link";
import { Suspense } from "react";

import {
  type ActionState,
  newConnectorCode,
  startImport,
  unlinkConnector,
  uploadGst,
  uploadStatement,
  uploadTally,
} from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { BankRulesSection, type RulePrefill } from "@/components/bank-rules";
import { InboundBox } from "@/components/inbound";
import { Steps, Way } from "@/components/ways";
import { type ConnectorList, PUBLIC_API_URL, api } from "@/lib/api";
import { moment } from "@/lib/format";

export default function ImportPage({ params, searchParams }: PageProps<"/projects/[id]/import">) {
  return (
    <Suspense fallback={<p className="loading">Opening the Import centre</p>}>
      <ImportView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

const STATE: Record<string, string> = {
  preview: "Not brought in yet",
  review: "Not brought in yet",
  applied: "Brought in",
  undone: "Undone",
};

type Entry = { id: string; at: string; what: string; file: string; state: string; href: string };

function when(iso: string): string {
  return moment(iso);
}

type Action = (previous: ActionState, form: FormData) => Promise<ActionState>;

function Upload({ id, label, accept, action }: { id: string; label: string; accept: string; action: Action }) {
  return (
    <ActionForm action={action} label={label} pendingLabel="Reading the file">
      <div className="field" style={{ maxWidth: 520 }}>
        <label htmlFor={id}>Your file</label>
        <input id={id} name="file" type="file" accept={accept} required />
      </div>
    </ActionForm>
  );
}

async function ImportView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const prefill: RulePrefill = {
    words: one(sp.rule_words),
    action: one(sp.rule_action),
    unit: one(sp.rule_unit),
    direction: one(sp.rule_direction),
  };
  const [list, tallyList, bankList, box, linked, gstList] = await Promise.all([
    api.imports(id),
    api.tallyImports(id),
    api.bankStatements(id),
    api.inbound(id),
    api.connectors(id),
    api.gstImports(id),
  ]);
  const can = list.can_import;
  const connected = linked.connectors.filter((c) => c.status === "active");

  const history: Entry[] = [
    ...list.imports.map((b) => ({ id: b.id, at: b.created_at, what: b.title, file: b.filename, state: STATE[b.status] ?? b.status, href: `/imports/${b.id}` })),
    ...tallyList.imports.map((t) => ({ id: t.id, at: t.created_at, what: "Tally", file: t.filename, state: STATE[t.status] ?? t.status, href: `/tally/${t.id}` })),
    ...bankList.statements.map((b) => ({ id: b.id, at: b.created_at, what: "Bank statement", file: b.filename, state: STATE[b.status] ?? b.status, href: `/bank/${b.id}` })),
    ...gstList.imports.map((g) => ({ id: g.id, at: g.created_at, what: g.form, file: g.filename, state: STATE[g.status] ?? g.status, href: `/gst/${g.id}` })),
  ].sort((a, b) => b.at.localeCompare(a.at));

  return (
    <>
      <p className="lead">
        Bring this project&apos;s records in from where they already are. Nothing is saved until you have seen it, the same
        file twice adds nothing, and every import can be undone for 30 days.
      </p>

      <InboundBox box={box} />

      <section className="section">
        <div className="section-head">
          <h2>Ways in</h2>
          <p>Open one to see what to do</p>
        </div>
        <ul className="ways">
          <Way
            title="Tally"
            what={
              connected.length
                ? `Connected: comes in by itself from ${connected.length === 1 ? "one computer" : `${connected.length} computers`}`
                : "Suppliers, bills, buyers' payments, costs and the RERA account, from Tally's export"
            }
            open={connected.some((c) => c.last_state)}
          >
            <Steps
              steps={[
                "In TallyPrime, open the company and press Alt+E (Export). Export Masters (All Masters) and Transactions (All Vouchers, for the period you want), as XML.",
                "Upload the file or files here. JSON from TallyPrime 7, or a Day Book in Excel, works too, with less detail.",
              ]}
            />
            {tallyList.can_import ? <Upload id="tally-file" label="Read the Tally file" accept=".xml,.json,.xlsx,.csv,.txt" action={uploadTally.bind(null, id)} /> : null}
            <Connector id={id} linked={linked} />
          </Way>

          <Way title="Bank statement" what="Buyers' payments and the RERA account, from the statement net banking gives you">
            <Steps
              steps={[
                "In net banking, open the statement of the account buyers pay into, or of the RERA designated account, and download it as Excel, CSV or PDF.",
                "Upload it here. Lekhara matches each buyer's payment to their unit and asks you about the rest, once.",
              ]}
            />
            {bankList.can_import ? <Upload id="bank-file" label="Read the statement" accept=".xls,.xlsx,.csv,.txt,.htm,.html,.pdf" action={uploadStatement.bind(null, id)} /> : null}
          </Way>

          <Way title="GST portal" what="GSTR-2B: your suppliers' invoices as the GST system has them, checked against your bills">
            <Steps
              steps={[
                "On the GST portal, open Returns, then the Returns Dashboard; choose the month and GSTR-2B, and download it as JSON or Excel.",
                "Upload it here. Lekhara shows bills your suppliers have not reported, amounts that differ, and invoices you have no bill for.",
              ]}
            />
            {gstList.can_import ? <Upload id="gst-file" label="Check the return" accept=".json,.xlsx" action={uploadGst.bind(null, id)} /> : null}
          </Way>

          <Way title="Units and buyers" what="From your sales sheet or CRM export">
            <p className="small muted">
              Exports from Sell.Do, LeadSquared, Zoho CRM, Salesforce and HubSpot are recognised as they come.{" "}
            </p>
            <p className="small muted">
              Any Excel or CSV file: columns are matched by name, such as Flat No or Customer Name, and you check the matching
              before anything is saved. Units are matched on their number; blank cells never erase what is there.{" "}
              <a href="/download/imports/templates/units.xlsx" className="link-action">
                Template
              </a>
            </p>
            {can ? <Upload id="file" label="Preview the import" accept=".xlsx,.xlsm,.csv" action={startImport.bind(null, id, "units")} /> : null}
          </Way>

          <Way title="Buyer payments" what="From your collections register: unit, date, amount, TDS and UTR">
            <p className="small muted">
              Payments already recorded are recognised, so the same file can be imported again.{" "}
              <a href="/download/imports/templates/receipts.xlsx" className="link-action">
                Template
              </a>
            </p>
            {can ? <Upload id="receipts-file" label="Preview the payments" accept=".xlsx,.xlsm,.csv" action={startImport.bind(null, id, "receipts")} /> : null}
          </Way>

          <Way title="Suppliers, bills and orders" what="For what you keep in a sheet rather than in Tally">
            <p className="small muted">
              A bill with a cost line counts as cost; leave the cost line blank when Tally already brings in your costs, so
              nothing counts twice.
            </p>
            <div id="purchases">
              {(
                [
                  ["suppliers", "Suppliers", "Preview the suppliers"],
                  ["bills", "Suppliers' bills", "Preview the bills"],
                  ["commitments", "Work and purchase orders", "Preview the orders"],
                ] as const
              ).map(([kind, title, label]) => (
                <div key={kind} className="way-part">
                  <p className="row-title">
                    {title}{" "}
                    <a href={`/download/imports/templates/${kind}.xlsx`} className="link-action small">
                      Template
                    </a>
                  </p>
                  {can ? <Upload id={`${kind}-file`} label={label} accept=".xlsx,.xlsm,.csv" action={startImport.bind(null, id, kind)} /> : null}
                </div>
              ))}
            </div>
          </Way>

          <Way title="Landowners, approvals and filings" what="Payments to landowners, your approvals list, K-RERA filings already made">
            <div>
              {(
                [
                  ["landowner_payments", "Landowner payments", "Preview the payments"],
                  ["approvals", "Approvals", "Preview the approvals"],
                  ["filings", "K-RERA filings", "Preview the filings"],
                ] as const
              ).map(([kind, title, label]) => (
                <div key={kind} className="way-part">
                  <p className="row-title">
                    {title}{" "}
                    <a href={`/download/imports/templates/${kind}.xlsx`} className="link-action small">
                      Template
                    </a>
                  </p>
                  {can ? <Upload id={`${kind}-file`} label={label} accept=".xlsx,.xlsm,.csv" action={startImport.bind(null, id, kind)} /> : null}
                </div>
              ))}
            </div>
          </Way>
        </ul>
        {!can ? <p className="empty">Your role cannot import into this project.</p> : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Brought in</h2>
          <p>Every file, newest first</p>
        </div>
        {history.length === 0 ? (
          <p className="empty">Nothing has been brought into this project yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>What</th>
                <th>File</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 25).map((e) => (
                <tr key={`${e.what}-${e.id}`}>
                  <td className="nowrap">{when(e.at)}</td>
                  <td>{e.what}</td>
                  <td>{e.file}</td>
                  <td>{e.state}</td>
                  <td className="right">
                    <Link href={e.href} className="link-action">
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {bankList.can_import || bankList.statements.length ? <BankRulesSection projectId={id} prefill={prefill} /> : null}
    </>
  );
}

function Connector({ id, linked }: { id: string; linked: ConnectorList }) {
  const active = linked.connectors.filter((c) => c.status === "active");
  return (
    <details className="disclosure" open={active.length > 0}>
      <summary>Or connect Tally, so it comes in by itself</summary>
      <p className="small muted" style={{ maxWidth: 760 }}>
        The Lekhara Connector runs on the computer with Tally and sends its masters and vouchers here every few minutes. It
        only reads Tally and opens nothing to the internet. In TallyPrime, turn on the HTTP server first (Help, Settings,
        Connectivity: act as a server on port 9000), then link the computer with a code.
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
      {active.length > 0 ? (
        <ul className="rows">
          {active.map((c) => (
            <li key={c.id} className="row">
              <div>
                <span className={c.last_state ? "tag tag-soon" : "tag tag-done"}>{c.last_state ? "Check" : "Connected"}</span>
              </div>
              <div>
                <p className="row-title">{`${c.name ?? "A computer"}${c.company ? `, reading ${c.company}` : ""}`}</p>
                <p className="row-detail">
                  {c.last_sync_at ? `Last brought in ${when(c.last_sync_at)}.` : "Linked; nothing sent yet."}
                  {c.last_seen_at ? ` Last heard from ${when(c.last_seen_at)}.` : ""}
                </p>
                {c.last_state ? <p className="row-meta">{c.last_state}</p> : null}
              </div>
              <div className="row-side">
                {c.last_import_id ? (
                  <Link href={`/tally/${c.last_import_id}`} className="link-action">
                    Latest sync
                  </Link>
                ) : null}
                {linked.can_edit ? <ActionForm action={unlinkConnector.bind(null, c.id)} label="Unlink" pendingLabel="Unlinking" secondary /> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}
