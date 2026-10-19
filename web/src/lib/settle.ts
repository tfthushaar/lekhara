import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import type { ActionState } from "@/app/actions";
import { FLASH_COOKIE, FORM_FIELD, encodeFlash } from "@/lib/flash";

type Asked = Awaited<ReturnType<typeof headers>>;

/**
 * Wraps a form's handler so the form works the same before the page's scripts have loaded.
 *
 * With its scripts, the page calls the action and shows the result itself. Without them (on a
 * slow connection a form can be sent before they arrive) the browser posts the form as it is, and
 * Next answers with the page resumed from its prerendered shell, which cannot carry the result:
 * the message would appear only once the scripts had loaded. So then the result is kept for a
 * minute and the browser is sent back to the page, where the form that was sent shows it straight
 * away. Being sent back also means reloading the page does not send the form again.
 */
export function settled<F extends (...args: never[]) => Promise<unknown>>(handler: F): F {
  return (async (...args: Parameters<F>) => {
    const state = await handler(...args);
    const asked = await headers();
    if (asked.get("next-action") !== null) return state; // called by the page's own scripts
    const back = backTo(asked);
    if (back === null) return state;
    const form = (args as unknown[]).find((arg): arg is FormData => arg instanceof FormData);
    const key = form?.get(FORM_FIELD);
    const result = (state ?? {}) as ActionState;
    if (typeof key === "string" && (result.error || result.ok)) {
      (await cookies()).set(FLASH_COOKIE, encodeFlash({ form: key, path: back.pathname, state: result }), {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: 60,
      });
    }
    redirect(back.pathname + back.search);
  }) as F;
}

/** The page the form was sent from, if it is one of ours. */
function backTo(asked: Asked): URL | null {
  const referer = asked.get("referer");
  const host = asked.get("x-forwarded-host") ?? asked.get("host");
  if (!referer || !host) return null;
  try {
    const url = new URL(referer);
    return url.host === host ? url : null;
  } catch {
    return null;
  }
}
