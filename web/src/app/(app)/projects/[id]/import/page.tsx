import Link from "next/link";
import { Suspense } from "react";

import { addFile, addSheet, newConnectorCode, unlinkConnector } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { BankRulesSection, type RulePrefill } from "@/components/bank-rules";
import { InboundBox, needsYou } from "@/components/inbound";
import { Steps } from "@/components/ways";
import { type ConnectorList, type DemoSample, PUBLIC_API_URL, api, demoSamples } from "@/lib/api";
import { moment } from "@/lib/format";

export default function ImportPage({ params, searchParams }: PageProps<"/projects/[id]/import">) {
  return (
    <Suspense fallback={<p className="loading">Opening your files</p>}>
      <ImportView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

function one(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

const STATE: Record<string, string> = {
  preview: "Waiting for you",
  review: "Waiting for you",
  applied: "Saved",
  undone: "Undone",
};

type Entry = { id: string; at: string; what: string; file: string; state: string; href: string };

function when(iso: string): string {
  return moment(iso);
}

const SHEETS = [
  ["units", "Units and buyers"],
  ["receipts", "Buyers' payments"],
  ["leads", "Leads"],
  ["suppliers", "Suppliers"],
  ["bills", "Suppliers' bills"],
  ["commitments", "Work and purchase orders"],
  ["landowner_payments", "Landowner payments"],
  ["approvals", "Approvals"],
  ["filings", "K-RERA filings"],
] as const;

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
  const samples = await demoSamples(id);
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
      <section>
        <div className="section-head">
          <h2>Add a file</h2>
        </div>
        <p style={{ margin: "12px 0", maxWidth: 760 }}>
          Your Tally export, a bank statement, a GST return, any Excel sheet or PDF. We work out what it is and show you what
          is in it. Nothing is saved until you say so.
        </p>
        {can ? (
          <ActionForm action={addFile.bind(null, id)} label="Add the file" pendingLabel="Reading the file">
            <div className="field" style={{ maxWidth: 520 }}>
              <label htmlFor="any-file">Your file</label>
              <input id="any-file" name="file" type="file" required />
            </div>
          </ActionForm>
        ) : (
          <p className="empty">Your role cannot add files to this project.</p>
        )}
      </section>

      {samples ? <Samples projectId={id} samples={samples} /> : null}

      <section className="section">
        <details className="disclosure" open={history.some((e) => e.state === "Waiting for you")}>
          <summary>{`Files added (${history.length})`}</summary>
          {history.length === 0 ? (
            <p className="empty">Nothing added yet.</p>
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>File</th>
                    <th>State</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {history.slice(0, 25).map((e) => (
                    <tr key={`${e.what}-${e.id}`}>
                      <td className="nowrap">{when(e.at)}</td>
                      <td>
                        {e.file}
                        <span className="small muted">{` ${e.what}`}</span>
                      </td>
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
            </div>
          )}
          <p className="small muted" style={{ marginTop: 12 }}>
            A file you added by mistake can be undone for 30 days from its own page.
          </p>
        </details>

        <details className="disclosure">
          <summary>Where do I get these files?</summary>
          <p className="row-title" style={{ marginTop: 12 }}>From Tally</p>
          <Steps
            steps={[
              "In TallyPrime, open the company and press Alt+E (Export).",
              "Export Masters (All Masters) and Transactions (All Vouchers) as XML, and add both files here.",
            ]}
          />
          <p className="row-title">From your bank</p>
          <Steps steps={["In net banking, open the statement of the account buyers pay into, or the RERA account.", "Download it as Excel or PDF and add it here."]} />
          <p className="row-title">From the GST portal</p>
          <Steps steps={["Open Returns, then the Returns Dashboard, choose the month and GSTR-2B.", "Download it and add it here."]} />
          <p className="row-title">From 99acres, MagicBricks or your ads</p>
          <Steps steps={["Download your leads from the portal or ad manager.", "Add the file here as it is."]} />
        </details>

        {box.can_edit || box.messages.length > 0 ? (
          <details className="disclosure" open={box.messages.some(needsYou)}>
            <summary>Send files by email instead</summary>
            <InboundBox box={box} demo={samples !== null} />
          </details>
        ) : null}

        <details className="disclosure" open={connected.some((c) => c.last_state)}>
          <summary>Have Tally send its data by itself</summary>
          <Connector id={id} linked={linked} />
        </details>

        {can ? (
          <details className="disclosure">
            <summary>We could not tell what your Excel sheet is?</summary>
            <ActionForm action={addSheet.bind(null, id)} label="Add the sheet" pendingLabel="Reading the file" secondary>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="sheet-kind">What is in it?</label>
                  <select id="sheet-kind" name="kind" defaultValue="units">
                    {SHEETS.map(([kind, title]) => (
                      <option key={kind} value={kind}>
                        {title}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="sheet-file">Your sheet</label>
                  <input id="sheet-file" name="file" type="file" accept=".xlsx,.xlsm,.csv" required />
                </div>
              </div>
            </ActionForm>
            <p className="small muted">
              {"Or start from our blank sheets: "}
              {SHEETS.map(([kind, title], i) => (
                <span key={kind}>
                  {i ? ", " : ""}
                  <a href={`/download/imports/templates/${kind}.xlsx`}>{title.toLowerCase()}</a>
                </span>
              ))}
              .
            </p>
          </details>
        ) : null}
      </section>

      {bankList.can_import || bankList.statements.length ? (
        <section className="section">
          <details className="disclosure" open={Boolean(prefill.words)}>
            <summary>Teach us your regular bank entries</summary>
            <BankRulesSection projectId={id} prefill={prefill} />
          </details>
        </section>
      ) : null}
    </>
  );
}

/** The demo's sample files for this project, to bring in the way you would your own. */
function Samples({ projectId, samples }: { projectId: string; samples: DemoSample[] }) {
  return (
    <section className="section">
      <div className="section-head">
        <h2>Sample files to try</h2>
        <p>Made from this project&apos;s own units, suppliers and bills</p>
      </div>
      <p className="small muted" style={{ maxWidth: 760, marginTop: 12 }}>
        Download one, then add it above the way you would your own file.
      </p>
      <table className="table">
        <thead>
          <tr>
            <th>File</th>
            <th>What&apos;s in it</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {samples.map((s) => (
            <tr key={s.name}>
              <td className="nowrap">{s.label}</td>
              <td className="small">{s.detail}</td>
              <td className="right">
                <a href={`/download/projects/${projectId}/demo/samples/${s.name}`} className="link-action">
                  Download
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
