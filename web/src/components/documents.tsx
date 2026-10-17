import Link from "next/link";

import { uploadDocument } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Choice, type DocRow, api } from "@/lib/api";
import { day } from "@/lib/format";

export const ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.csv";

export function FileField({ id = "file" }: { id?: string }) {
  return (
    <div className="field field-wide">
      <label htmlFor={id}>File (PDF, Word, Excel, photo or text, up to 20 MB)</label>
      <input id={id} name="file" type="file" accept={ACCEPT} required />
    </div>
  );
}

export function CategoryField({
  categories,
  value,
  id = "category",
}: {
  categories: Choice[];
  value?: string | null;
  id?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>Kind of document</label>
      <select id={id} name="category" defaultValue={value ?? "other"}>
        {categories.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function DateField({
  name,
  label,
  value,
  id,
}: {
  name: string;
  label: string;
  value?: string | null;
  id?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id ?? name}>{label}</label>
      <input id={id ?? name} name={name} type="date" defaultValue={value ?? ""} />
    </div>
  );
}

export function ExpiryTag({ doc }: { doc: Pick<DocRow, "expiry" | "expires_on"> }) {
  if (!doc.expires_on) return null;
  if (doc.expiry === "expired") return <span className="tag tag-overdue">Lapsed {day(doc.expires_on)}</span>;
  if (doc.expiry === "expiring") return <span className="tag tag-soon">Expires {day(doc.expires_on)}</span>;
  return <span className="small muted">Valid to {day(doc.expires_on)}</span>;
}

/** The documents filed against one unit, case or withdrawal, and a form to add one. */
export async function LinkedDocuments({
  linkType,
  linkId,
  category,
  hint,
}: {
  linkType: "unit" | "case" | "withdrawal";
  linkId: string;
  category: string;
  hint: string;
}) {
  const r = await api.linkedDocuments(linkType, linkId);
  const id = `${linkType}-file`;
  return (
    <section className="section no-print">
      <div className="section-head">
        <h2>Documents</h2>
        <p>{hint}</p>
      </div>
      {r.documents.length === 0 ? (
        <p className="empty">Nothing is filed here yet.</p>
      ) : (
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          {r.documents.map((d) => (
            <li key={d.id}>
              <Link href={`/documents/${d.id}`}>{d.title}</Link>
              <span className="small muted">
                {d.category_label}
                {d.document_date ? `, ${day(d.document_date)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {r.can_edit ? (
        <details className="disclosure">
          <summary>Add a document</summary>
          <ActionForm
            action={uploadDocument.bind(null, r.project_id)}
            label="Add to the vault"
            pendingLabel="Uploading"
          >
            <input type="hidden" name="link_type" value={linkType} />
            <input type="hidden" name="link_id" value={linkId} />
            <div className="field-grid">
              <FileField id={id} />
              <CategoryField categories={r.categories} value={category} id={`${id}-category`} />
              <div className="field">
                <label htmlFor={`${id}-title`}>Title (optional)</label>
                <input id={`${id}-title`} name="title" />
              </div>
              <DateField name="document_date" label="Dated" id={`${id}-date`} />
              <div className="field">
                <label htmlFor={`${id}-reference`}>Number on the document</label>
                <input id={`${id}-reference`} name="reference" />
              </div>
            </div>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}
