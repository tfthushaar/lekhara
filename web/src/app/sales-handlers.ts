// What the sales forms do on the server: leads, visits, holds, prices, bookings, channel
// partners and their commission. They run only as the server actions in `actions.ts`.

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import type { ActionState } from "@/app/form-handlers";
import { send } from "@/lib/api";

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

function filled(form: FormData, names: string[]): Record<string, string> {
  const body: Record<string, string> = {};
  for (const name of names) {
    const value = text(form, name);
    if (value) body[name] = value;
  }
  return body;
}

const LEAD_FIELDS = ["name", "phone", "email", "source", "partner_id", "interest", "budget", "next_follow_up_on"];

export async function addLead(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ id: string; new: boolean }>("POST", `/projects/${projectId}/leads`, filled(form, LEAD_FIELDS));
  if (!result.ok) return { error: result.error };
  if (!result.data.new) {
    refresh();
    return { ok: "You already have this person, by their phone number. We noted that they asked again." };
  }
  redirect(`/leads/${result.data.id}`);
}

export async function updateLead(leadId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body = filled(form, ["stage", "lost_reason", "interest", "budget", "owner_user_id", "project_id"]);
  const result = await send("PUT", `/leads/${leadId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function reopenLead(leadId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("PUT", `/leads/${leadId}`, { stage: "contacted" });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "They are back on your list." };
}

export async function logActivity(leadId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string> = filled(form, ["kind", "detail"]);
  if (text(form, "next_follow_up_on")) body.next_follow_up_on = text(form, "next_follow_up_on");
  const result = await send("POST", `/leads/${leadId}/activities`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Noted." };
}

export async function planVisit(leadId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/leads/${leadId}/visits`, filled(form, ["on", "time", "project_id"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Visit planned." };
}

export async function recordVisit(visitId: string, status: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/visits/${visitId}`, { status, ...filled(form, ["feedback"]) });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function holdUnit(leadId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/leads/${leadId}/holds`, { unit_id: text(form, "unit_id") });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Held." };
}

export async function releaseHold(holdId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/holds/${holdId}/release`);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Released." };
}

const PRICE_FIELDS = [
  "base_rate",
  "floor_rise",
  "floor_rise_from",
  "plc",
  "car_park",
  "amenities",
  "other_charges",
  "corpus_per_sqft",
  "maintenance_per_sqft_month",
  "maintenance_months",
];

export async function savePriceList(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string> = {};
  for (const name of PRICE_FIELDS) body[name] = String(form.get(name) ?? "");
  const result = await send("PUT", `/projects/${projectId}/price-list`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Prices saved." };
}

export async function bookUnit(leadId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body = {
    ...filled(form, ["unit_id", "booked_on", "booking_amount", "reference", "buyer_pan", "aadhaar_last4", "buyer_address", "discount_per_sqft", "partner_id"]),
    plc: form.getAll("plc").map(String),
  };
  const result = await send<{ id: string }>("POST", `/leads/${leadId}/book`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Booked. The unit is sold to them and the booking amount is saved as their first payment." };
}

const PARTNER_FIELDS = [
  "name",
  "firm",
  "phone",
  "email",
  "krera_number",
  "krera_valid_until",
  "commission_pct",
  "payable_after_pct",
  "gstin",
  "pan",
];

export async function addPartner(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/partners", filled(form, PARTNER_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Partner added." };
}

export async function updatePartner(partnerId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string | boolean> = {};
  for (const name of PARTNER_FIELDS) body[name] = text(form, name);
  body.active = form.get("active") === "yes";
  const result = await send("PUT", `/partners/${partnerId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function payCommission(commissionId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/commissions/${commissionId}/pay`, filled(form, ["reference"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Paid." };
}
