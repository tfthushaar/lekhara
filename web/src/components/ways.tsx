import type { ReactNode } from "react";

/** One way of bringing data in: a single line until opened, then its steps and upload. */
export function Way({
  title,
  what,
  open = false,
  children,
}: {
  title: string;
  what: string;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <li>
      <details className="way" open={open}>
        <summary>
          <span className="way-title">{title}</span>
          <span className="way-what">{what}</span>
          <span className="way-open">
            <span className="when-closed">Open</span>
            <span className="when-open">Close</span>
          </span>
        </summary>
        <div className="way-body">{children}</div>
      </details>
    </li>
  );
}

/** Numbered steps, kept short. */
export function Steps({ steps }: { steps: ReactNode[] }) {
  return (
    <ol className="how-to">
      {steps.map((step, i) => (
        <li key={i}>{step}</li>
      ))}
    </ol>
  );
}
