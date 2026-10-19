import type { HistoryEntry } from "@/lib/api";

const SOURCE: Record<string, string> = {
  typed: "typed in",
  import: "imported",
  edited: "edited as a table",
  undo: "import undone",
};

function verb(action: string): string {
  if (action === "created") return "Added";
  if (action === "deleted") return "Deleted";
  return "Changed";
}

/** Who changed what and when, each field before and after. */
export function History({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <details className="disclosure">
      <summary>History ({entries.length})</summary>
      <ul className="rows">
        {entries.map((h, i) => (
          <li key={`${h.at}-${i}`} className="row">
            <div className="small muted">{h.at.replace("T", ", ").slice(0, 17)}</div>
            <div>
              <p className="row-title">
                {`${h.subject ? `${h.subject} ${verb(h.action).toLowerCase()}` : verb(h.action)} by ${h.by}, ${SOURCE[h.source] ?? h.source}`}
              </p>
              {h.changes.map((c) => (
                <p key={c.field} className="row-detail">
                  {`${c.field}: ${c.before ?? "blank"} to ${c.after ?? "blank"}`}
                </p>
              ))}
            </div>
            <div />
          </li>
        ))}
      </ul>
    </details>
  );
}
