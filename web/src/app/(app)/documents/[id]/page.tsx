import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { archiveDocument, updateDocument, uploadDocument } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { CategoryField, DateField, ExpiryTag, FileField } from "@/components/documents";
import { type DocumentDetail, api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Document" };

export default function DocumentPage({ params }: PageProps<"/documents/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Opening the document</p>}>
      <DocumentView params={params} />
    </Suspense>
  );
}

function textLine(d: DocumentDetail): string {
  if (d.text_status === "text") return `${d.pages === 1 ? "1 page" : `${d.pages} pages`}, searchable`;
  if (d.text_status === "unreadable") return "The file could not be read for text";
  return "No text found. Scans become searchable once AI document reading is switched on.";
}

async function DocumentView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const d = await api.document(id);
  const base = `/projects/${d.project_id}`;
  const previewable = d.content_type === "application/pdf" || d.content_type.startsWith("image/");
  const editable = d.can_edit && d.current && !d.archived_on;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{d.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/documents`}>Documents</Link>
          </p>
          <h1>{d.title}</h1>
          <p>
            {d.category_label}
            {d.document_date ? `, dated ${day(d.document_date)}` : ""}
            {d.version > 1 ? `. Version ${d.version}` : ""}
          </p>
        </div>
        <div className="head-side">
          <a href={`/files/${d.id}`} className="button">
            Download
          </a>
        </div>
      </div>

      {!d.current ? (
        <p className="notice" style={{ marginBottom: 24 }}>
          This is an earlier version.{" "}
          <Link href={`/documents/${d.versions[0].id}`}>Open the latest version</Link>
        </p>
      ) : null}
      {d.archived_on ? (
        <p className="notice" style={{ marginBottom: 24 }}>
          Archived on {day(d.archived_on)}. It is kept, but left out of the checklist, search and
          data rooms.
        </p>
      ) : null}

      <ul className="calc" style={{ maxWidth: 640 }}>
        <Fact label="Kind" value={d.category_label} />
        {d.requirement_title ? <Fact label="Answers the checklist item" value={d.requirement_title} /> : null}
        {d.record ? <Fact label="Filed against" value={d.record} /> : null}
        <Fact label="Number on the document" value={d.reference ?? "None"} />
        <li>
          <span className="muted">Expiry</span>
          <span>{d.expires_on ? <ExpiryTag doc={d} /> : "Does not expire"}</span>
        </li>
        <Fact label="Text" value={textLine(d)} />
        <Fact label="File" value={`${d.filename}, ${d.size}`} />
        <Fact label="Added on" value={day(d.uploaded_on)} />
      </ul>
      {d.notes ? <p style={{ marginTop: 16, maxWidth: 640 }}>{d.notes}</p> : null}

      {previewable ? (
        <section className="section">
          <iframe className="preview" src={`/files/${d.id}?inline=1`} title={d.title} />
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>Versions</h2>
          <p>Every version is kept; the latest one counts</p>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Version</th>
              <th>File</th>
              <th>Added</th>
              <th>Valid to</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {d.versions.map((v) => (
              <tr key={v.id}>
                <td>{v.id === d.id ? <strong>{v.version}</strong> : v.version}</td>
                <td>
                  {v.filename} <span className="small muted">{v.size}</span>
                </td>
                <td className="nowrap">{day(v.uploaded_on)}</td>
                <td className="nowrap">{day(v.expires_on)}</td>
                <td className="right">
                  {v.id === d.id ? null : (
                    <Link href={`/documents/${v.id}`} className="link-action">
                      Open
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {editable ? (
          <details className="disclosure">
            <summary>Add a new version</summary>
            <ActionForm action={uploadDocument.bind(null, d.project_id)} label="Add the new version" pendingLabel="Uploading">
              <input type="hidden" name="replaces" value={d.id} />
              <input type="hidden" name="then" value="open" />
              <div className="field-grid">
                <FileField id="version-file" />
                <DateField name="document_date" label="Dated" id="version-date" />
                <DateField name="expires_on" label="Valid to, if it expires" id="version-expiry" />
                <div className="field">
                  <label htmlFor="version-reference">Number on the document</label>
                  <input id="version-reference" name="reference" defaultValue={d.reference ?? ""} />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
      </section>

      {d.rooms.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Shared in</h2>
          </div>
          <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
            {d.rooms.map((room) => (
              <li key={room.id}>
                <Link href={`/rooms/${room.id}`}>{room.name}</Link>
                <span className="small muted">
                  {room.state === "open" ? "Open" : room.state === "revoked" ? "Closed" : "Expired"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {editable ? (
        <section className="section">
          <details className="disclosure">
            <summary>Change the details</summary>
            <ActionForm action={updateDocument.bind(null, d.id)} label="Save the changes" pendingLabel="Saving" secondary>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="edit-title">Title</label>
                  <input id="edit-title" name="title" defaultValue={d.title} required />
                </div>
                <CategoryField categories={d.categories} value={d.category} id="edit-category" />
                <div className="field">
                  <label htmlFor="edit-requirement">Checklist item</label>
                  <select id="edit-requirement" name="requirement" defaultValue={d.requirement ?? ""}>
                    <option value="">None</option>
                    {d.requirements.map((req) => (
                      <option key={req.value} value={req.value}>
                        {req.label}
                      </option>
                    ))}
                  </select>
                </div>
                <DateField name="document_date" label="Dated" value={d.document_date} id="edit-date" />
                <DateField name="expires_on" label="Valid to" value={d.expires_on} id="edit-expiry" />
                <div className="field">
                  <label htmlFor="edit-reference">Number on the document</label>
                  <input id="edit-reference" name="reference" defaultValue={d.reference ?? ""} />
                </div>
                <div className="field field-wide">
                  <label htmlFor="edit-notes">Notes</label>
                  <textarea id="edit-notes" name="notes" rows={2} defaultValue={d.notes ?? ""} />
                </div>
              </div>
            </ActionForm>
          </details>
          <details className="disclosure">
            <summary>Archive this document</summary>
            <p className="small muted" style={{ marginBottom: 12 }}>
              Archived documents are kept, with every version, but leave the checklist, search and
              data rooms.
            </p>
            <ActionForm action={archiveDocument.bind(null, d.id)} label="Archive it" pendingLabel="Archiving" secondary />
          </details>
        </section>
      ) : null}
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <li>
      <span className="muted">{label}</span>
      <span>{value}</span>
    </li>
  );
}
