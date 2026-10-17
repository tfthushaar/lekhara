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


const UNIT_FIELDS = [
  "label",
  "tower",
  "carpet_area_sqft",
  "owner_share",
  "list_price",
  "guidance_value",
  "buyer_name",
  "buyer_phone",
  "buyer_email",
  "booked_on",
  "agreement_value",
];

export async function createUnit(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send<{ id: string }>("POST", `/projects/${projectId}/units`, filled(form, UNIT_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Unit added." };
}

export async function updateUnit(
  unitId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("PUT", `/units/${unitId}`, filled(form, UNIT_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function markUnsold(unitId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/units/${unitId}/unsold`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function deleteUnit(unitId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send<{ project_id: string }>("POST", `/units/${unitId}/delete`);
  if (!result.ok) return { error: result.error };
  redirect(`/projects/${result.data.project_id}/units`);
}

export async function startImport(
  projectId: string,
  kind: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose a file first." };
  const body = new FormData();
  body.append("file", file, file.name);
  const result = await sendForm<{ id: string }>(`/projects/${projectId}/imports/${kind}`, body);
  if (!result.ok) return { error: result.error };
  redirect(`/imports/${result.data.id}`);
}

export async function mapImport(
  batchId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const mapping: Record<string, string | null> = {};
  for (const [name, value] of form.entries()) {
    if (name.startsWith("column_")) mapping[name.slice(7)] = String(value) || null;
  }
  const result = await send("PUT", `/imports/${batchId}/mapping`, { mapping });
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function applyImport(batchId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/imports/${batchId}/apply`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function undoImport(batchId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/imports/${batchId}/undo`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function uploadTally(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose the file exported from Tally." };
  const body = new FormData();
  body.append("file", file, file.name);
  const result = await sendForm<{ id: string }>(`/projects/${projectId}/tally`, body);
  if (!result.ok) return { error: result.error };
  redirect(`/tally/${result.data.id}`);
}

export async function tallyChoices(
  importId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const links: Record<string, string | { role: string; target?: string }> = {};
  const entries = [...form.entries()];
  for (const [name, value] of entries) {
    if (name.startsWith("ledger_")) links[String(value)] = text(form, `unit_${name.slice(7)}`);
    if (name.startsWith("costledger_")) {
      const choice = text(form, `cost_${name.slice(11)}`);
      links[String(value)] = choice === "ignore" ? { role: "ignore" } : choice ? { role: "cost_line", target: choice } : "";
    }
    if (name.startsWith("bankledger_")) {
      links[String(value)] = text(form, "rera_account") === String(value) ? { role: "rera_account" } : "";
    }
    if (name.startsWith("ownerwas_")) links[String(value)] = "";
  }
  for (const [name, value] of entries) {
    if (!name.startsWith("owner_")) continue;
    const ledger = String(value);
    if (ledger) links[ledger] = { role: "landowner", target: text(form, `ownerid_${name.slice(6)}`) };
  }
  const result = await send("PUT", `/tally/${importId}/options`, {
    cost_centre: text(form, "cost_centre") || null,
    links,
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function applyTally(importId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/tally/${importId}/apply`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function undoTally(importId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/tally/${importId}/undo`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

const BILL_FIELDS = [
  "supplier",
  "bill_no",
  "bill_date",
  "taxable_value",
  "gst_amount",
  "accepted_on",
  "paid_on",
  "cost_line",
  "is_cement",
  "rcm_paid",
  "excluded",
];
const SUPPLIER_FIELDS = ["name", "gstin", "pan", "state", "msme_category", "udyam_number", "written_agreement"];
const COMMITMENT_FIELDS = ["reference", "cost_line", "amount", "committed_on", "supplier", "description"];

/** The optional fields a form left blank, so saving clears them. */
function blanks(form: FormData, names: string[]): string[] {
  return names.filter((name) => form.has(name) && !text(form, name));
}

export async function createBill(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/bills`, filled(form, BILL_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Bill added." };
}

export async function updateBill(billId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body = { ...filled(form, BILL_FIELDS), clear: blanks(form, ["paid_on", "gst_amount", "cost_line"]) };
  const result = await send("PUT", `/bills/${billId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteBill(billId: string, projectId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/bills/${billId}/delete`);
  if (!result.ok) return { error: result.error };
  redirect(`/projects/${projectId}/suppliers`);
}

export async function createSupplier(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/suppliers`, filled(form, SUPPLIER_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Supplier added." };
}

export async function updateSupplier(supplierId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body = { ...filled(form, SUPPLIER_FIELDS), clear: blanks(form, ["gstin", "pan", "state", "udyam_number"]) };
  const result = await send("PUT", `/suppliers/${supplierId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteSupplier(supplierId: string, backTo: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/suppliers/${supplierId}/delete`);
  if (!result.ok) return { error: result.error };
  redirect(backTo);
}

export async function createCommitment(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/commitments`, filled(form, COMMITMENT_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Order added." };
}

export async function updateCommitment(commitmentId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string> = filled(form, COMMITMENT_FIELDS);
  for (const name of blanks(form, ["supplier", "description"])) body[name] = "";
  const result = await send("PUT", `/commitments/${commitmentId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteCommitment(commitmentId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/commitments/${commitmentId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function uploadStatement(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose the statement downloaded from net banking." };
  const body = new FormData();
  body.append("file", file, file.name);
  const result = await sendForm<{ id: string }>(`/projects/${projectId}/bank-statements`, body);
  if (!result.ok) return { error: result.error };
  redirect(`/bank/${result.data.id}`);
}

export async function statementAccount(
  statementId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const role = text(form, "role");
  if (!role) return { error: "Choose which account this is." };
  const result = await send("PUT", `/bank-statements/${statementId}/options`, {
    role,
    buyers_pay_here: role === "rera" && form.get("buyers_pay_here") === "yes",
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function statementChoices(
  statementId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const lines: Record<string, string | null> = {};
  for (const [name, value] of form.entries()) {
    if (name.startsWith("line_")) lines[String(value)] = text(form, `choice_${name.slice(5)}`) || null;
  }
  const result = await send("PUT", `/bank-statements/${statementId}/options`, { lines });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function applyStatement(statementId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/bank-statements/${statementId}/apply`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function undoStatement(statementId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/bank-statements/${statementId}/undo`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function standardCostLines(projectId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send<{ added: number }>("POST", `/projects/${projectId}/cost-lines/standard`);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: result.data.added ? `${result.data.added} cost lines added.` : "Every standard line is already there." };
}

const LINE_FIELDS = ["code", "name", "category", "original_budget", "revised_budget"];

export async function createCostLine(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/cost-lines`, filled(form, LINE_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Cost line added." };
}

export async function updateCostLine(
  lineId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("PUT", `/cost-lines/${lineId}`, filled(form, LINE_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteCostLine(lineId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/cost-lines/${lineId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

const LANDOWNER_FIELDS = ["name", "share_type", "share_pct", "refundable_deposit", "pan"];

export async function createLandowner(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/landowners`, filled(form, LANDOWNER_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Landowner added." };
}

export async function updateLandowner(
  ownerId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("PUT", `/landowners/${ownerId}`, filled(form, LANDOWNER_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function applyPlanTemplate(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/payment-plan/template`, {
    template: text(form, "template"),
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Payment plan set." };
}

export async function savePlan(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const stages = [];
  for (let i = 0; form.has(`stage_${i}_name`); i++) {
    const name = text(form, `stage_${i}_name`);
    const share = text(form, `stage_${i}_share`);
    if (!name && !share) continue;
    stages.push({
      id: text(form, `stage_${i}_id`) || null,
      name,
      trigger: text(form, `stage_${i}_trigger`),
      progress_pct: text(form, `stage_${i}_progress`) || null,
      share_pct: share,
    });
  }
  const result = await send("PUT", `/projects/${projectId}/payment-plan`, { stages });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Payment plan saved." };
}

export async function recordReceipt(
  unitId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/units/${unitId}/receipts`, filled(form, ["received_on", "amount", "tds_deducted", "reference"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Payment recorded." };
}

export async function deleteReceipt(receiptId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/receipts/${receiptId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

const PROJECT_FIELDS = [
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
  "statutory_auditor_firm",
  "development_rights_value",
  "cess_paid",
  "oc_status",
  "oc_received_on",
  "oc_reference",
  "association_formed_on",
  "common_areas_conveyed_on",
];

export async function updateProject(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  // Every field is sent, so clearing one in the form clears it in Lekhara.
  const body = Object.fromEntries(PROJECT_FIELDS.map((name) => [name, text(form, name)]));
  const result = await send("PUT", `/projects/${projectId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function recordProgress(
  projectId: string,
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/progress`, filled(form, ["as_of", "completion_pct", "certified_by"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Progress recorded." };
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
