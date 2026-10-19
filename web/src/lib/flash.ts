import type { ActionState } from "@/app/actions";

/**
 * The result of a form sent before the page's scripts had loaded, carried back to the page that
 * sent it: the action keeps it in a cookie for a minute (`settled`), the proxy hands it to that
 * page once as a request header, and the form it belongs to shows it (`ActionForm`).
 */
export const FLASH_COOKIE = "lekhara_flash";
export const FLASH_HEADER = "x-lekhara-flash";

/** The hidden field naming the form that was sent. */
export const FORM_FIELD = "_form";

export type Flash = { form: string; path: string; state: ActionState };

export function encodeFlash(flash: Flash): string {
  return encodeURIComponent(JSON.stringify(flash));
}

export function decodeFlash(value: string | null | undefined): Flash | null {
  if (!value) return null;
  try {
    const flash = JSON.parse(decodeURIComponent(value));
    if (typeof flash?.form !== "string" || typeof flash?.path !== "string") return null;
    if (typeof flash.state !== "object" || flash.state === null) return null;
    const { error, ok, link } = flash.state;
    const state: ActionState = {};
    if (typeof error === "string") state.error = error;
    if (typeof ok === "string") state.ok = ok;
    if (typeof link === "string") state.link = link;
    return { form: flash.form, path: flash.path, state };
  } catch {
    return null;
  }
}
