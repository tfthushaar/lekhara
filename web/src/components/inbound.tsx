import Link from "next/link";

import { allowInbound, rejectInbound, retryInbound } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import type { Inbound, InboundItem, InboundMessage } from "@/lib/api";
import { moment } from "@/lib/format";

const ITEM: Record<InboundItem["status"], { label: string; className: string }> = {
  queued: { label: "Waiting", className: "tag tag-upcoming" },
  done: { label: "Brought in", className: "tag tag-done" },
  review: { label: "Needs you", className: "tag tag-fail" },
  ignored: { label: "Left out", className: "tag" },
  failed: { label: "Could not read", className: "tag tag-soon" },
};

const MESSAGE: Record<string, string> = {
  queued: "Being read",
  held: "Waiting for you to allow it",
  done: "Read",
  rejected: "Turned away",
  failed: "Could not be read",
};

function needsYou(m: InboundMessage): boolean {
  return m.status === "held" || m.items.some((i) => i.status === "review" || i.status === "failed");
}

/** The project's forwarding address, and what came in through it. */
export function InboundBox({ box }: { box: Inbound }) {
  const attention = box.messages.filter(needsYou);
  const earlier = box.messages.filter((m) => !needsYou(m));
  return (
    <section className="section">
      <div className="section-head">
        <h2>Send files by email</h2>
        <p>This project&apos;s own address</p>
      </div>
      <div style={{ maxWidth: 560, marginTop: 12 }}>
        <input className="share-link" readOnly value={box.address} aria-label="This project's email address" />
      </div>
      <p className="small muted" style={{ maxWidth: 760 }}>
        Forward statements, Tally exports, bills and documents here, or have your bank email statements here every month.
        {box.ready ? "" : " Email in is not switched on for this server yet."}
      </p>
      <details className="disclosure">
        <summary>How email works</summary>
        <p className="small muted" style={{ maxWidth: 760 }}>
          Each file is brought in the way it would be if you uploaded it: statements into collections and the RERA account,
          Tally exports into the books, a GSTR-2B for checking, sheets into a preview, and everything else into the
          documents. Mail from your team and from the senders you trust (Settings, Email in) is read at once; anyone
          else&apos;s waits here until you allow it.
        </p>
      </details>
      {attention.length > 0 ? (
        <ul className="rows" style={{ marginTop: 12 }}>
          {attention.map((m) => (
            <Message key={m.id} m={m} canEdit={box.can_edit} />
          ))}
        </ul>
      ) : null}
      {earlier.length > 0 ? (
        <details className="disclosure">
          <summary>{`Earlier emails (${earlier.length})`}</summary>
          <ul className="rows">
            {earlier.map((m) => (
              <Message key={m.id} m={m} canEdit={box.can_edit} />
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function Message({ m, canEdit }: { m: InboundMessage; canEdit: boolean }) {
  return (
    <li className="row">
      <div className="small muted">{moment(m.received_at)}</div>
      <div>
        <p className="row-title">{m.subject ?? "No subject"}</p>
        <p className="row-detail">{`From ${m.from_name ? `${m.from_name}, ` : ""}${m.from_address}. ${MESSAGE[m.status] ?? m.status}.`}</p>
        {m.note ? <p className="row-meta">{m.note}</p> : null}
        {m.items.map((i) => (
          <p key={i.id} className="small" style={{ margin: "6px 0 0" }}>
            <span className={ITEM[i.status].className}>{ITEM[i.status].label}</span>{" "}
            {i.filename}
            {i.note ? <span className="muted">{` ${i.note}`}</span> : null}{" "}
            {i.link ? (
              <Link href={i.link} className="link-action">
                Open
              </Link>
            ) : null}
            {i.can_retry ? (
              <span style={{ display: "inline-block", marginLeft: 8 }}>
                <ActionForm action={retryInbound.bind(null, i.id)} label="Try again" pendingLabel="Reading" secondary />
              </span>
            ) : null}
          </p>
        ))}
        {m.status === "held" && canEdit ? (
          <div style={{ marginTop: 10 }}>
            <ActionForm action={allowInbound.bind(null, m.id)} label="Allow it" pendingLabel="Reading" secondary>
              <div className="checks">
                <label>
                  <input type="checkbox" name="trust" value="yes" />
                  <span className="small">{`Trust ${m.from_address} from now on`}</span>
                </label>
              </div>
            </ActionForm>
            <ActionForm action={rejectInbound.bind(null, m.id)} label="Turn it away" pendingLabel="Turning it away" secondary />
          </div>
        ) : null}
      </div>
      <div />
    </li>
  );
}
