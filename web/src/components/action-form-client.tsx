"use client";

import { useActionState, useId } from "react";

import type { ActionState } from "@/app/actions";
import { FORM_FIELD, type Flash } from "@/lib/flash";

export type ActionFormProps = {
  action: (previous: ActionState, form: FormData) => Promise<ActionState>;
  label: string;
  pendingLabel?: string;
  secondary?: boolean;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
};

/** The form itself: see `ActionForm`. `sent` is the result of a form on this page just sent
 * before the page's scripts had loaded, shown if it was this one. Forms are told apart by their
 * action, button and place on the page, which are the same each time the page is drawn. */
export function ActionFormClient({
  action,
  label,
  pendingLabel = "Working",
  secondary = false,
  disabled = false,
  className,
  children,
  formKey,
  sent,
}: ActionFormProps & { formKey: string; sent?: Flash }) {
  const name = `${formKey}${useId()}`;
  const [state, formAction, pending] = useActionState(action, sent?.form === name ? sent.state : {});
  return (
    <form action={formAction} className={className}>
      <input type="hidden" name={FORM_FIELD} value={name} />
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
