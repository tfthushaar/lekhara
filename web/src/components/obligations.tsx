import Link from "next/link";

import { type Obligation, type Status, areaHref } from "@/lib/api";
import { day, inr, relative } from "@/lib/format";

export const STATUS_LABEL: Record<Status, string> = {
  overdue: "Overdue",
  due_soon: "Due soon",
  at_risk: "At risk",
  opportunity: "Money waiting",
  upcoming: "Coming up",
  done: "Done",
};

const STATUS_CLASS: Record<Status, string> = {
  overdue: "tag tag-overdue",
  due_soon: "tag tag-soon",
  at_risk: "tag tag-soon",
  opportunity: "tag tag-opportunity",
  upcoming: "tag tag-upcoming",
  done: "tag tag-done",
};

export function StatusTag({ status }: { status: Status }) {
  return <span className={STATUS_CLASS[status]}>{STATUS_LABEL[status]}</span>;
}

function when(o: Obligation, today: string): string {
  if (!o.due_on) return "";
  if (o.status === "overdue") return `Was due ${day(o.due_on)}, ${relative(o.due_on, today)}`;
  if (o.status === "opportunity") return "";
  return `Due ${day(o.due_on)}, ${relative(o.due_on, today)}`;
}

export function ObligationRows({
  items,
  today,
  showProject = true,
  empty = "Nothing here.",
}: {
  items: Obligation[];
  today: string;
  showProject?: boolean;
  empty?: string;
}) {
  if (items.length === 0) return <p className="empty">{empty}</p>;
  return (
    <ul className="rows">
      {items.map((o) => {
        const meta = [showProject ? o.project_name : null, `Owed to ${o.owed_to}`, when(o, today)]
          .filter(Boolean)
          .join("  ·  ");
        return (
          <li key={`${o.project_id}:${o.key}`} className="row">
            <div>
              <StatusTag status={o.status} />
            </div>
            <div>
              <p className="row-title">{o.title}</p>
              <p className="row-detail">{o.detail}</p>
              <p className="row-meta">{meta}</p>
            </div>
            <div className="row-side">
              {o.amount ? (
                <>
                  <p className="amount-label">{o.amount_label}</p>
                  <p className="row-amount">{inr(o.amount)}</p>
                </>
              ) : null}
              {o.action ? (
                <Link className="link-action" href={areaHref(o)}>
                  {o.action}
                </Link>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
