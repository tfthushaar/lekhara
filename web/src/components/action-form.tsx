"use client";

import { useActionState } from "react";

import type { ActionState } from "@/app/actions";

type Props = {
  action: (previous: ActionState, form: FormData) => Promise<ActionState>;
  label: string;
  pendingLabel?: string;
  secondary?: boolean;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
};

/** A form that runs a server action, shows that it is working, and shows any error in words. */
export function ActionForm({
  action,
  label,
  pendingLabel = "Working",
  secondary = false,
  disabled = false,
  className,
  children,
}: Props) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction} className={className}>
      {children}
      <button
        type="submit"
        className={secondary ? "button button-secondary" : "button"}
        disabled={pending || disabled}
      >
        {pending ? pendingLabel : label}
      </button>
      {state.error ? (
        <p className="form-error" role="alert">
          {state.error}
        </p>
      ) : null}
      {state.ok ? (
        <div className="form-ok" role="status">
          <p>{state.ok}</p>
          {state.link ? (
            <input className="share-link" readOnly value={state.link} aria-label="Link to send" />
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
