"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import { send } from "@/lib/api";

export type ActionState = { error?: string };

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
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
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/withdrawals/${requestId}/certificates/${role}/sign`, {
    signer_name: text(form, "signer_name"),
    signer_firm: text(form, "signer_firm"),
  });
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
