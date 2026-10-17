"use server";

import { refresh } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { send } from "@/lib/api";
import { SESSION_COOKIE, SESSION_DAYS } from "@/lib/session-cookie";

export type ActionState = { error?: string };

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

export async function signIn(_previous: ActionState, form: FormData): Promise<ActionState> {
  const email = text(form, "email");
  const password = String(form.get("password") ?? "");
  if (!email || !password) return { error: "Enter your email and password." };
  const result = await send<{ token: string }>("POST", "/auth/login", { email, password });
  if (!result.ok) return { error: result.error };
  (await cookies()).set({
    name: SESSION_COOKIE,
    value: result.data.token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_DAYS * 24 * 60 * 60,
  });
  redirect("/");
}

export async function signOut(): Promise<void> {
  await send("POST", "/auth/logout");
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}

export async function startWithdrawal(
  projectId: string,
  _previous: ActionState,
  _form: FormData,
): Promise<ActionState> {
  const result = await send<{ id: string }>("POST", `/projects/${projectId}/withdrawals`, {});
  if (!result.ok) return { error: result.error };
  redirect(`/withdrawals/${result.data.id}`);
}

export async function raiseDemands(
  projectId: string,
  milestoneId: string,
  _previous: ActionState,
  _form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/milestones/${milestoneId}/raise`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

const HANDOVER_FIELDS = [
  "ekhata_status",
  "khata_type",
  "deed_drafted_on",
  "appointment_on",
  "registered_on",
  "document_no",
  "possession_on",
];

export async function updateHandover(
  unitId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body: Record<string, string> = {};
  for (const field of HANDOVER_FIELDS) {
    const value = text(form, field);
    if (value) body[field] = value;
  }
  if (Object.keys(body).length === 0) return { error: "Fill in the details first." };
  const result = await send("PUT", `/units/${unitId}/handover`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

function filled(form: FormData, names: string[]): Record<string, string> {
  const body: Record<string, string> = {};
  for (const name of names) {
    const value = text(form, name);
    if (value) body[name] = value;
  }
  return body;
}

export async function createCase(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body = filled(form, [
    "forum",
    "case_number",
    "relief",
    "unit",
    "complainant",
    "filed_on",
    "notice_received_on",
    "reply_due_on",
    "next_hearing_on",
    "claim_amount",
    "lawyer",
    "summary",
  ]);
  const result = await send<{ id: string }>("POST", `/projects/${projectId}/disputes`, body);
  if (!result.ok) return { error: result.error };
  redirect(`/cases/${result.data.id}`);
}

export async function updateCase(
  caseId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body = filled(form, [
    "status",
    "lawyer",
    "summary",
    "claim_amount",
    "reply_due_on",
    "reply_filed_on",
    "next_hearing_on",
    "settlement_offered",
    "settlement_agreed",
    "appealed_on",
  ]);
  if (Object.keys(body).length === 0) return { error: "Fill in the details first." };
  const result = await send("PUT", `/cases/${caseId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function addHearing(
  caseId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body: Record<string, string | boolean> = filled(form, [
    "held_on",
    "purpose",
    "outcome",
    "next_hearing_on",
  ]);
  body.order_reserved = form.get("order_reserved") === "on";
  const result = await send("POST", `/cases/${caseId}/hearings`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function addOrder(
  caseId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body = filled(form, [
    "ordered_on",
    "received_on",
    "kind",
    "amount",
    "comply_by",
    "summary",
  ]);
  const result = await send("POST", `/cases/${caseId}/orders`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function addPayment(
  caseId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body = filled(form, ["paid_on", "amount", "reference"]);
  const result = await send("POST", `/cases/${caseId}/payments`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function updateFigure(
  requestId: string,
  role: string,
  field: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const value = text(form, "value").replace(/,/g, "");
  if (!value || Number.isNaN(Number(value))) return { error: "Enter a number." };
  const result = await send("PUT", `/withdrawals/${requestId}/certificates/${role}`, {
    [field]: value,
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function signCertificate(
  requestId: string,
  role: string,
  _previous: ActionState,
  _form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/withdrawals/${requestId}/certificates/${role}/sign`, {});
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function submitWithdrawal(
  requestId: string,
  _previous: ActionState,
  _form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/withdrawals/${requestId}/submit`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function releaseWithdrawal(
  requestId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const amount = text(form, "amount").replace(/,/g, "");
  const result = await send("POST", `/withdrawals/${requestId}/release`, {
    amount: amount || null,
    bank_reference: text(form, "bank_reference") || null,
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function rejectWithdrawal(
  requestId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/withdrawals/${requestId}/reject`, {
    reason: text(form, "reason"),
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}
