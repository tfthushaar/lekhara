import Link from "next/link";
import { Suspense } from "react";

import {
  addFilingRule,
  addStandardFilingRules,
  createRoom,
  deleteFilingRule,
  refileDocuments,
  restoreRequirement,
  uploadDocument,
  waiveRequirement,
} from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { CategoryField, DateField, ExpiryTag, FileField } from "@/components/documents";
import { OriginalsSection } from "@/components/originals";
import { type ChecklistRow, type DocumentsView, type SearchResults, api } from "@/lib/api";
import { day, plural } from "@/lib/format";

export default function DocumentsPage({ params, searchParams }: PageProps<"/projects/[id]/documents">) {
  return (
    <Suspense fallback={<p className="loading">Opening the vault</p>}>
      <VaultView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

const STATUS: Record<ChecklistRow["status"], { label: string; className: string }> = {
  held: { label: "In the vault", className: "tag tag-done" },
  missing: { label: "Missing", className: "tag tag-fail" },
  expiring: { label: "Expires soon", className: "tag tag-soon" },
  expired: { label: "Lapsed", className: "tag tag-overdue" },
  waived: { label: "Not needed", className: "tag tag-upcoming" },
};

const RECORD_HREF: Record<string, string> = {
  unit: "/units/",
  case: "/cases/",
  withdrawal: "/withdrawals/",
};

function one(value: string | string[] | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

async function VaultView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const q = one(sp.q);
  const category = one(sp.category);
  const [r, found] = await Promise.all([
    api.documents(id),
    q.length >= 2 ? api.searchDocuments(id, q) : Promise.resolve(null),
  ]);
  const s = r.summary;
  const base = `/projects/${id}/documents`;
  const shown = category ? r.documents.filter((d) => d.category === category) : r.documents;
  const counts = new Map<string, number>();
  for (const d of r.documents) counts.set(d.category, (counts.get(d.category) ?? 0) + 1);

  return (
    <>
      <div className="stats">
        <div className="stat">
          <p className="stat-label">In the vault</p>
          <p className="stat-value">{s.documents}</p>
          <p className="stat-note">Latest versions; older ones are kept</p>
        </div>
        <div className="stat">
          <p className="stat-label">Missing</p>
          <p className="stat-value">{s.missing}</p>
          <p className="stat-note">From the checklist below</p>
        </div>
        <div className="stat">
          <p className="stat-label">About to lapse</p>
          <p className="stat-value">{s.expiring}</p>
          <p className="stat-note">Expired, or expiring within {r.notice_days} days</p>
        </div>
        <div className="stat">
          <p className="stat-label">Data rooms open</p>
          <p className="stat-value">{s.rooms_open}</p>
          <p className="stat-note">Shared with lenders or investors</p>
        </div>
      </div>

      <section className="section">
        <form action={base} method="get" role="search" className="inline-form">
          <div className="field">
            <label htmlFor="q">Search every page of every document</label>
            <input id="q" name="q" defaultValue={q} placeholder="A survey number, a name, a clause" />
          </div>
          <button type="submit" className="button button-secondary">
            Search
          </button>
        </form>
        {found ? <Results found={found} base={base} /> : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Checklist</h2>
          <p>What banks, K-RERA and buyers ask to see for this project</p>
        </div>
        <ul className="rows">
          {r.checklist.map((item) => (
            <ChecklistItem key={item.key} item={item} r={r} projectId={id} />
          ))}
        </ul>
      </section>

      {r.records.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>For each unit, case and withdrawal</h2>
            <p>File these from the unit, case or withdrawal they belong to</p>
          </div>
          <ul className="calc" style={{ marginTop: 12, maxWidth: 720 }}>
            {r.records.map((rec) => (
              <li key={rec.key} style={{ display: "block" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 24 }}>
                  <span>{rec.title}</span>
                  <span className="num">
                    {rec.held} of {rec.needed}
                  </span>
                </div>
                {rec.missing.length > 0 ? (
                  <details className="disclosure" style={{ marginTop: 6 }}>
                    <summary>{plural(rec.missing.length, "missing")}</summary>
                    <p className="small">
                      {rec.missing.map((m, i) => (
                        <span key={m.id}>
                          {i > 0 ? ", " : ""}
                          <Link href={`${RECORD_HREF[rec.link_type]}${m.id}`}>{m.label}</Link>
                        </span>
                      ))}
                    </p>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>All documents</h2>
          <p>The latest version of each</p>
        </div>
        <nav className="chips" aria-label="Kind of document">
          <Link href={base} className={category ? "chip" : "chip chip-on"}>
            All ({r.documents.length})
          </Link>
          {r.categories
            .filter((c) => counts.has(c.value))
            .map((c) => (
              <Link
                key={c.value}
                href={`${base}?category=${c.value}`}
                className={category === c.value ? "chip chip-on" : "chip"}
              >
                {c.label} ({counts.get(c.value)})
              </Link>
            ))}
        </nav>
        {shown.length === 0 ? (
          <p className="empty">Nothing is filed yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Kind</th>
                <th>Dated</th>
                <th>Expiry</th>
                <th className="right">Size</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link href={`/documents/${d.id}`}>{d.title}</Link>
                    {d.version > 1 ? <span className="small muted">{` (version ${d.version})`}</span> : null}
                  </td>
                  <td>{d.category_label}</td>
                  <td className="nowrap">{day(d.document_date)}</td>
                  <td className="nowrap">
                    <ExpiryTag doc={d} />
                  </td>
                  <td className="right num">{d.size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {r.can_edit ? (
          <details className="disclosure">
            <summary>Add a document</summary>
            <ActionForm action={uploadDocument.bind(null, id)} label="Add to the vault" pendingLabel="Uploading">
              <input type="hidden" name="then" value="open" />
              <div className="field-grid">
                <FileField id="general-file" />
                <CategoryField categories={r.categories} id="general-category" auto />
                <div className="field">
                  <label htmlFor="general-title">Title (optional)</label>
                  <input id="general-title" name="title" />
                </div>
                <DateField name="document_date" label="Dated" id="general-date" />
                <DateField name="expires_on" label="Expires on, if it does" id="general-expiry" />
                <div className="field">
                  <label htmlFor="general-reference">Number on the document</label>
                  <input id="general-reference" name="reference" />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
      </section>

      <Suspense fallback={null}>
        <OriginalsSection projectId={id} />
      </Suspense>

      {r.can_edit ? (
        <Suspense fallback={null}>
          <FilingRules />
        </Suspense>
      ) : null}

      <RoomsSection r={r} projectId={id} />
    </>
  );
}

/** The firm's rules for filing documents no one chose a kind for. */
async function FilingRules() {
  const f = await api.filingRules();
  return (
    <section className="section">
      <div className="section-head">
        <h2>Filing rules</h2>
        <p>For every project: words that say what kind of document something is</p>
      </div>
      <p className="small muted" style={{ maxWidth: 760, marginTop: 12 }}>
        When a document is uploaded or emailed in without a kind chosen, Lekhara reads it and files it by the first rule
        that fits, and says which rule did. You can always change it.
      </p>
      {f.rules.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Looks for</th>
              <th>Files it as</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {f.rules.map((rule) => (
              <tr key={rule.id}>
                <td>{rule.name}</td>
                <td>
                  {`"${rule.words}"`} <span className="small muted">{rule.how_label.toLowerCase()}</span>
                </td>
                <td>
                  {rule.category_label}
                  {rule.requirement_label ? <span className="small muted">{`, ${rule.requirement_label}`}</span> : null}
                </td>
                <td className="right">
                  {f.can_edit ? (
                    <ActionForm action={deleteFilingRule.bind(null, rule.id)} label="Remove" pendingLabel="Removing" secondary />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">No rules yet.</p>
      )}
      {f.can_edit ? (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 16 }}>
          {f.standard_missing ? (
            <ActionForm action={addStandardFilingRules} label="Add the rules for common Karnataka documents" pendingLabel="Adding" secondary />
          ) : null}
          {f.rules.length ? (
            <ActionForm action={refileDocuments} label="File what is still under Other" pendingLabel="Filing" secondary />
          ) : null}
        </div>
      ) : null}
      {f.can_edit ? (
        <details className="disclosure">
          <summary>Add a rule</summary>
          <ActionForm action={addFilingRule} label="Add the rule" pendingLabel="Adding">
            <div className="field-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label htmlFor="rule-name">Name</label>
                <input id="rule-name" name="name" required placeholder="Lift licence" />
              </div>
              <div className="field">
                <label htmlFor="rule-words">Words to look for</label>
                <input id="rule-words" name="words" required placeholder="lift licence" />
              </div>
              <div className="field">
                <label htmlFor="rule-how">How</label>
                <select id="rule-how" name="how" defaultValue="phrase">
                  {f.hows.map((h) => (
                    <option key={h.value} value={h.value}>
                      {h.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="rule-category">Files it as</label>
                <select id="rule-category" name="category" defaultValue="approval">
                  {f.categories.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="rule-requirement">Checklist item, if it is one</label>
                <select id="rule-requirement" name="requirement" defaultValue="">
                  <option value="">None</option>
                  {f.requirements.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}

function Results({ found, base }: { found: SearchResults; base: string }) {
  if (found.results.length === 0) {
    return (
      <p className="empty">
        Nothing found for &ldquo;{found.query}&rdquo;. Scanned papers become searchable once AI
        document reading is switched on. <Link href={base}>Clear the search</Link>
      </p>
    );
  }
  return (
    <>
      <p className="small muted" style={{ margin: "12px 0" }}>
        {plural(found.results.length, "match", "matches")} for &ldquo;{found.query}&rdquo;.{" "}
        <Link href={base}>Clear the search</Link>
      </p>
      <ul className="rows">
        {found.results.map((hit) => (
          <li key={`${hit.document.id}-${hit.page ?? "title"}`} className="row">
            <div>
              <span className="tag tag-upcoming">{hit.page ? `Page ${hit.page}` : "Title"}</span>
            </div>
            <div>
              <p className="row-title">
                <Link href={`/documents/${hit.document.id}`}>{hit.document.title}</Link>
              </p>
              {hit.snippets.map((sn, i) => (
                <p key={i} className="row-detail">
                  {sn.before}
                  <span className="hit-match">{sn.match}</span>
                  {sn.after}
                </p>
              ))}
            </div>
            <div className="row-side">
              <p className="amount-label">{hit.document.category_label}</p>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function ChecklistItem({ item, r, projectId }: { item: ChecklistRow; r: DocumentsView; projectId: string }) {
  const tag = STATUS[item.status];
  return (
    <li className="row">
      <div>
        <span className={tag.className}>{tag.label}</span>
      </div>
      <div>
        <p className="row-title">{item.title}</p>
        <p className="row-detail">
          {item.status === "waived" ? `Not needed: ${item.waiver_reason}` : item.why}
        </p>
        {item.expires_on && item.status !== "missing" ? (
          <p className="row-meta">
            {item.status === "expired" ? "Lapsed on" : "Valid to"} {day(item.expires_on)}
          </p>
        ) : null}
        {r.can_edit && item.status === "missing" ? (
          <>
            <details className="disclosure">
              <summary>Add it</summary>
              <ActionForm action={uploadDocument.bind(null, projectId)} label="Add to the vault" pendingLabel="Uploading">
                <input type="hidden" name="requirement" value={item.key} />
                <input type="hidden" name="category" value={item.category} />
                <div className="field-grid">
                  <FileField id={`${item.key}-file`} />
                  <DateField name="document_date" label="Dated" id={`${item.key}-date`} />
                  {item.tracks_expiry ? (
                    <DateField name="expires_on" label="Valid to" id={`${item.key}-expiry`} />
                  ) : null}
                  <div className="field">
                    <label htmlFor={`${item.key}-reference`}>Number on the document</label>
                    <input id={`${item.key}-reference`} name="reference" />
                  </div>
                </div>
              </ActionForm>
            </details>
            <details className="disclosure">
              <summary>This project does not need it</summary>
              <ActionForm
                action={waiveRequirement.bind(null, projectId, item.key)}
                label="Mark as not needed"
                pendingLabel="Saving"
                secondary
              >
                <div className="field">
                  <label htmlFor={`${item.key}-reason`}>Why not</label>
                  <input id={`${item.key}-reason`} name="reason" required />
                </div>
              </ActionForm>
            </details>
          </>
        ) : null}
      </div>
      <div className="row-side">
        {item.document_id ? (
          <Link href={`/documents/${item.document_id}`} className="link-action">
            {item.status === "held" ? "Open" : "Open and renew"}
          </Link>
        ) : null}
        {r.can_edit && item.status === "waived" ? (
          <ActionForm
            action={restoreRequirement.bind(null, projectId, item.key)}
            label="Needed after all"
            pendingLabel="Saving"
            secondary
          />
        ) : null}
      </div>
    </li>
  );
}

function RoomsSection({ r, projectId }: { r: DocumentsView; projectId: string }) {
  return (
    <section className="section">
      <div className="section-head">
        <h2>Data rooms</h2>
        <p>Share chosen documents with a lender or investor through a link that closes on a date</p>
      </div>
      {r.rooms.length === 0 ? (
        <p className="empty">Nothing has been shared.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Room</th>
              <th className="right">Documents</th>
              <th>Closes</th>
              <th>State</th>
              <th className="right">Opened</th>
              <th className="right">Downloads</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {r.rooms.map((room) => (
              <tr key={room.id}>
                <td>
                  {room.name}
                  {room.audience ? (
                    <>
                      <br />
                      <span className="small muted">{room.audience}</span>
                    </>
                  ) : null}
                </td>
                <td className="right num">{room.documents}</td>
                <td className="nowrap">{day(room.expires_on)}</td>
                <td>{room.state === "open" ? "Open" : room.state === "revoked" ? "Closed" : "Expired"}</td>
                <td className="right num">{room.opens}</td>
                <td className="right num">{room.downloads}</td>
                <td className="right">
                  <Link href={`/rooms/${room.id}`} className="link-action">
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {r.can_share && r.documents.length > 0 ? (
        <details className="disclosure">
          <summary>Share documents with a lender or investor</summary>
          <ActionForm action={createRoom.bind(null, projectId)} label="Make the data room" pendingLabel="Making it">
            <div className="field-grid">
              <div className="field">
                <label htmlFor="room-name">Name</label>
                <input id="room-name" name="name" required placeholder="Construction finance review" />
              </div>
              <div className="field">
                <label htmlFor="room-audience">Who it is for</label>
                <input id="room-audience" name="audience" placeholder="The lender's credit team" />
              </div>
              <DateField name="expires_on" label="Link closes on" id="room-expires" />
            </div>
            <label className="check-line">
              <input type="checkbox" name="ask_visitor" value="yes" defaultChecked /> Ask each visitor for their name and
              email, and record them with each visit
            </label>
            <label className="check-line">
              <input type="checkbox" name="watermark" value="yes" defaultChecked /> Mark every page of a PDF with who
              opened it and when
            </label>
            <label className="check-line">
              <input type="checkbox" name="notify" value="yes" defaultChecked /> Email me the first time each visitor
              opens it
            </label>
            <div className="field">
              <label htmlFor="room-terms">Terms each visitor must accept (optional)</label>
              <textarea
                id="room-terms"
                name="terms"
                rows={3}
                placeholder="These documents are confidential and are shared only to assess the loan."
              />
              <p className="small muted">Needs visitors to give their name and email, so each acceptance has a name on it.</p>
            </div>
            <p className="small muted" style={{ marginBottom: 8 }}>
              Choose what to share. The room always shows the latest version of each.
            </p>
            <div className="checks">
              {r.documents.map((d) => (
                <label key={d.id}>
                  <input type="checkbox" name="document_ids" value={d.id} /> {d.title}
                  <span className="small muted">{d.category_label}</span>
                </label>
              ))}
            </div>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}
