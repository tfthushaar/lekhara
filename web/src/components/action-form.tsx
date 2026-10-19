import { createHash } from "node:crypto";

import { headers } from "next/headers";
import { Suspense } from "react";

import { ActionFormClient, type ActionFormProps } from "@/components/action-form-client";
import { FLASH_HEADER, decodeFlash } from "@/lib/flash";

/**
 * A form that runs a server action, shows that it is working, and shows any error in words.
 *
 * If the form was sent before the page's scripts had loaded, the page is shown again with this
 * form's result (see `settled`); the form is drawn at once and given that result when the request
 * is read.
 */
export function ActionForm(props: ActionFormProps) {
  const formKey = keyOf(props.action, props.label);
  return (
    <Suspense fallback={<ActionFormClient {...props} formKey={formKey} />}>
      <WithResult {...props} formKey={formKey} />
    </Suspense>
  );
}

async function WithResult(props: ActionFormProps & { formKey: string }) {
  const flash = decodeFlash((await headers()).get(FLASH_HEADER));
  return <ActionFormClient {...props} sent={flash?.form.startsWith(props.formKey) ? flash : undefined} />;
}

/** The same on every render of the page: the action, what is bound to it, and the button. */
function keyOf(action: ActionFormProps["action"], label: string): string {
  const reference = action as { $$id?: string; $$bound?: unknown[] | null };
  let bound = "";
  try {
    bound = JSON.stringify(reference.$$bound ?? null);
  } catch {
    bound = String(reference.$$bound?.length ?? 0);
  }
  return createHash("sha256")
    .update(`${reference.$$id ?? action.name}\n${bound}\n${label}`)
    .digest("hex")
    .slice(0, 16);
}
