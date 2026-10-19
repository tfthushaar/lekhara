import type { StaffFirmRow } from "@/lib/api";
import { day } from "@/lib/format";

/** Where a firm stands, in a few words. */
export function standing(f: StaffFirmRow): string {
  if (f.is_sample) return "Sample";
  if (f.closing) return `Closing, deleted after ${day(f.closing)}`;
  if (f.access === "trial") return `Free month to ${day(f.trial_ends_on)}`;
  if (f.access === "active") return f.paid_until ? `Paid to ${day(f.paid_until)}` : "Active";
  return f.paid_until ? `Read-only, paid to ${day(f.paid_until)}` : "Read-only, free month over";
}
