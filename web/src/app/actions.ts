"use server";

import { refresh } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { send, sendForm } from "@/lib/api";
import { SESSION_COOKIE, SESSION_DAYS } from "@/lib/session-cookie";

export type ActionState = { error?: string; ok?: string; link?: string };

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

export async function signIn(_previous: ActionState, form: FormData): Promise<ActionState> {
  const email = text(form, "email");
  const password = String(form.get("password") ?? "");
  if (!email || !password) return { error: "Enter your email and password." };
  const result = await send<{ token: string }>("POST", "/auth/login", { email, password });
  if (!result.ok) return { error: result.error };
  await startSession(result.data.token);
  redirect("/");
}

async function startSession(token: string): Promise<void> {
  (await cookies()).set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_DAYS * 24 * 60 * 60,
  });
}


export async function signUp(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ token: string }>("POST", "/auth/signup", {
    name: text(form, "name"),
    firm: text(form, "firm"),
    email: text(form, "email"),
    password: String(form.get("password") ?? ""),
  });
  if (!result.ok) return { error: result.error };
  await startSession(result.data.token);
  redirect("/");
}

export async function forgotPassword(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/auth/forgot", { email: text(form, "email") });
  if (!result.ok) return { error: result.error };
  return { ok: "If there is an account for that email, a link to reset the password is on its way. It works for one hour." };
}

export async function resetPassword(
  token: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const password = String(form.get("password") ?? "");
  if (password !== String(form.get("confirm") ?? "")) return { error: "The two passwords do not match." };
  const result = await send("POST", "/auth/reset", { token, password });
  if (!result.ok) return { error: result.error };
  redirect("/login?reset=1");
}

export async function verifyEmail(token: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", "/auth/verify", { token });
  if (!result.ok) return { error: result.error };
  return { ok: "Your email is confirmed." };
}

export async function resendVerification(_previous: ActionState): Promise<ActionState> {
  const result = await send("POST", "/auth/verify/resend");
  if (!result.ok) return { error: result.error };
  return { ok: "Sent. Check your inbox." };
}

export async function acceptInvitation(
  token: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send<{ token: string }>("POST", `/invitations/${token}/accept`, {
    name: text(form, "name") || null,
    firm: text(form, "firm") || null,
    password: String(form.get("password") ?? ""),
  });
  if (!result.ok) return { error: result.error };
  await startSession(result.data.token);
  redirect("/");
}

export async function updateFirm(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("PUT", "/organization", {
    name: text(form, "name"),
    legal_name: text(form, "legal_name"),
    gstin: text(form, "gstin"),
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function inviteMember(_previous: ActionState, form: FormData): Promise<ActionState> {
  const email = text(form, "email");
  const result = await send<{ link: string }>("POST", "/organization/invitations", {
    email,
    role: text(form, "role"),
    project_ids: form.getAll("project_ids").map(String),
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return {
    ok: `Invitation emailed to ${email}. You can also send them this link, for example on WhatsApp. It works for seven days.`,
    link: result.data.link,
  };
}

export async function cancelInvitation(id: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/organization/invitations/${id}/cancel`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function changeRole(
  userId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("PUT", `/organization/members/${userId}`, { role: text(form, "role") });
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function removeMember(userId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/organization/members/${userId}/remove`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function createProject(_previous: ActionState, form: FormData): Promise<ActionState> {
  const body = filled(form, [
    "name",
    "krera_registration",
    "registered_on",
    "possession_due_on",
    "locality",
    "city",
    "spv_name",
    "land_structure",
    "gst_regime",
    "escrow_bank",
  ]);
  const result = await send<{ id: string }>("POST", "/projects", body);
  if (!result.ok) return { error: result.error };
  redirect(`/projects/${result.data.id}`);
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

const UPLOAD_FIELDS = [
  "category",
  "title",
  "document_date",
  "expires_on",
  "reference",
  "notes",
  "requirement",
  "link_type",
  "link_id",
  "replaces",
];

export async function uploadDocument(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose a file first." };
  const body = new FormData();
  body.append("file", file, file.name);
  for (const [name, value] of Object.entries(filled(form, UPLOAD_FIELDS))) body.append(name, value);
  const result = await sendForm<{ id: string }>(`/projects/${projectId}/documents`, body);
  if (!result.ok) return { error: result.error };
  if (text(form, "then") === "open") redirect(`/documents/${result.data.id}`);
  refresh();
  return {};
}

export async function updateDocument(
  documentId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body = filled(form, ["title", "category", "document_date", "expires_on", "reference", "notes", "requirement"]);
  const result = await send("PUT", `/documents/${documentId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function archiveDocument(
  documentId: string,
  _previous: ActionState,
): Promise<ActionState> {
  const result = await send<{ project_id: string }>("POST", `/documents/${documentId}/archive`);
  if (!result.ok) return { error: result.error };
  redirect(`/projects/${result.data.project_id}/documents`);
}

export async function waiveRequirement(
  projectId: string,
  requirement: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/checklist/${requirement}/waive`, {
    reason: text(form, "reason"),
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function restoreRequirement(
  projectId: string,
  requirement: string,
  _previous: ActionState,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/checklist/${requirement}/restore`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function createRoom(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send<{ id: string; token: string }>("POST", `/projects/${projectId}/rooms`, {
    name: text(form, "name"),
    audience: text(form, "audience") || null,
    expires_on: text(form, "expires_on") || null,
    document_ids: form.getAll("document_ids").map(String),
  });
  if (!result.ok) return { error: result.error };
  redirect(`/rooms/${result.data.id}?link=${encodeURIComponent(result.data.token)}`);
}

export async function updateRoom(
  roomId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const body: Record<string, unknown> = filled(form, ["name", "audience", "expires_on"]);
  if (form.get("documents") === "change") body.document_ids = form.getAll("document_ids").map(String);
  const result = await send("PUT", `/rooms/${roomId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function newRoomLink(roomId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send<{ token: string }>("POST", `/rooms/${roomId}/link`);
  if (!result.ok) return { error: result.error };
  redirect(`/rooms/${roomId}?link=${encodeURIComponent(result.data.token)}`);
}

export async function revokeRoom(roomId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/rooms/${roomId}/revoke`);
  if (!result.ok) return { error: result.error };
  redirect(`/rooms/${roomId}`);
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
