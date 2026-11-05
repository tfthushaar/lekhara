import { cookies } from "next/headers";

/**
 * Which part of Lekhara to show: the main software (what only Lekhara does) or the expanded
 * software, which adds the business modules for firms that have no ERP or CRM of their own.
 * The demo asks on its first screen; everyone else sees everything.
 */
export type View = "main" | "expanded";

export const VIEW_COOKIE = "lekhara_view";

export async function chosenView(): Promise<View | null> {
  const value = (await cookies()).get(VIEW_COOKIE)?.value;
  return value === "main" || value === "expanded" ? value : null;
}

export async function currentView(): Promise<View> {
  return (await chosenView()) ?? "expanded";
}
