// What each form does on the server. These run only as the server actions in `actions.ts`, which
// wrap them so a form sent before the page's scripts have loaded still shows its result.

import { refresh } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { VISITOR_COOKIE, endSession, send, sendAsVisitor, sendForm } from "@/lib/api";
import { SESSION_COOKIE, SESSION_DAYS, STAFF_COOKIE } from "@/lib/session-cookie";

export type ActionState = { error?: string; ok?: string; link?: string };

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

export async function signIn(_previous: ActionState, form: FormData): Promise<ActionState> {
  const email = text(form, "email");
  const password = String(form.get("password") ?? "");
  if (!email || !password) return { error: "Enter your email and password." };
  const result = await send<{ token?: string; two_step?: boolean; ticket?: string }>("POST", "/auth/login", {
    email,
    password,
  });
  if (!result.ok) return { error: result.error };
  if (result.data.two_step && result.data.ticket) {
    (await cookies()).set({
      name: TWO_STEP_COOKIE,
      value: result.data.ticket,
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/login",
      maxAge: 10 * 60,
    });
    redirect("/login/two-step");
  }
  await startSession(result.data.token ?? "");
  redirect("/");
}

const TWO_STEP_COOKIE = "lekhara_two_step";

/** The second step of signing in: the code from the authenticator app, or a recovery code. */
export async function signInCode(_previous: ActionState, form: FormData): Promise<ActionState> {
  const jar = await cookies();
  const ticket = jar.get(TWO_STEP_COOKIE)?.value;
  if (!ticket) return { error: "This sign-in has timed out. Enter your email and password again." };
  const result = await send<{ token: string }>("POST", "/auth/login/two-step", { ticket, code: text(form, "code") });
  if (!result.ok) return { error: result.error };
  jar.delete({ name: TWO_STEP_COOKIE, path: "/login" });
  await startSession(result.data.token);
  redirect("/");
}

export async function startTwoStep(_previous: ActionState): Promise<ActionState> {
  const result = await send<{ secret: string; uri: string }>("POST", "/auth/two-step/start");
  if (!result.ok) return { error: result.error };
  return {
    ok: `In your authenticator app, add an account and enter this key: ${result.data.secret}. Then enter the six-digit code it shows, below. On a phone, the link below opens the app directly.`,
    link: result.data.uri,
  };
}

export async function confirmTwoStep(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ recovery_codes: string[] }>("POST", "/auth/two-step/confirm", { code: text(form, "code") });
  if (!result.ok) return { error: result.error };
  // No refresh: the page would redraw this section as "on" and the codes, shown only once,
  // would go with the form. They stay on screen; the section reads "on" from the next visit.
  return {
    ok: `Two-step sign-in is on. Keep these recovery codes somewhere safe, away from your phone; each gets you in once if the phone is lost: ${result.data.recovery_codes.join("  ")}`,
  };
}

export async function disableTwoStep(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/auth/two-step/disable", { password: String(form.get("password") ?? "") });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Two-step sign-in is off." };
}

async function startSession(token: string): Promise<void> {
  const jar = await cookies();
  if (jar.has(STAFF_COOKIE)) jar.delete(STAFF_COOKIE);
  jar.set({
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

export async function allowInbound(messageId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/inbound/${messageId}/allow`, { trust: form.get("trust") === "yes" });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Allowed; its files are being brought in." };
}

export async function rejectInbound(messageId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/inbound/${messageId}/reject`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function retryInbound(itemId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/inbound/items/${itemId}/retry`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function addSender(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/organization/senders", { address: text(form, "address") });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Added." };
}

export async function removeSender(senderId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/organization/senders/${senderId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function addStatementPassword(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/organization/statement-passwords", {
    label: text(form, "label"),
    password: String(form.get("password") ?? ""),
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Kept. Statements protected by it now open." };
}

export async function removeStatementPassword(passwordId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/organization/statement-passwords/${passwordId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function newConnectorCode(projectId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send<{ code: string }>("POST", `/projects/${projectId}/connectors`);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Type this code into the connector within 30 minutes:", link: result.data.code };
}

export async function unlinkConnector(connectorId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/connectors/${connectorId}/unlink`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function uploadGst(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose the GSTR-2B downloaded from the GST portal." };
  const body = new FormData();
  body.append("file", file, file.name);
  const result = await sendForm<{ id: string }>(`/projects/${projectId}/gst`, body);
  if (!result.ok) return { error: result.error };
  redirect(`/gst/${result.data.id}`);
}

export async function gstChoices(importId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("PUT", `/gst/${importId}/options`, { add_missing: form.get("add_missing") === "yes" });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function applyGst(importId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/gst/${importId}/apply`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function undoGst(importId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/gst/${importId}/undo`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

/** Adds a bank rule, or with "only try it" ticked shows the lines it would fit. */
export async function addBankRule(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body = {
    ...filled(form, ["name", "words", "how", "action", "direction", "min_amount", "max_amount"]),
    unit_id: text(form, "unit_id") || null,
    every_project: form.get("every_project") === "yes",
  };
  if (form.get("only_try") === "yes") {
    const tried = await send<{ fits: number; lines: { on: string; narration: string; amount: string }[] }>(
      "POST",
      `/projects/${projectId}/bank-rules/try`,
      { ...body, name: text(form, "name") || "Trying" },
    );
    if (!tried.ok) return { error: tried.error };
    const { fits, lines } = tried.data;
    if (!fits) return { ok: "It fits no line in this project's statements. Nothing was saved." };
    const shown = lines.slice(0, 3).map((l) => `${l.on}, ${l.narration}, ${l.amount}`);
    return {
      ok: `It fits ${fits === 1 ? "1 line" : `${fits} lines`}, such as: ${shown.join("; ")}. Nothing was saved yet; untick "Only try it" to add it.`,
    };
  }
  const result = await send<{ fits: number }>("POST", `/projects/${projectId}/bank-rules`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  const n = result.data.fits;
  return {
    ok: n
      ? `Added. It fits ${n === 1 ? "1 line" : `${n} lines`} in this project's statements; any not yet brought in follow it now.`
      : "Added. It fits no line in this project's statements yet.",
  };
}

export async function moveBankRuleUp(projectId: string, ruleId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/bank-rules/${ruleId}/up`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function deleteBankRule(projectId: string, ruleId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/bank-rules/${ruleId}/delete`);
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
    accept_terms: form.get("accept_terms") === "yes",
    code: text(form, "code") || null,
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
    accept_terms: form.get("accept_terms") === "yes",
  });
  if (!result.ok) return { error: result.error };
  await startSession(result.data.token);
  redirect("/");
}

export async function acceptTerms(_previous: ActionState): Promise<ActionState> {
  const result = await send("POST", "/auth/accept-terms");
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function deleteAccount(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/auth/delete-account", { password: String(form.get("password") ?? "") });
  if (!result.ok) return { error: result.error };
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}

export async function closeFirm(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/organization/close", { confirm: text(form, "confirm") });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "The firm's account will close. Download everything before then." };
}

export async function keepFirm(_previous: ActionState): Promise<ActionState> {
  const result = await send("POST", "/organization/keep");
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "The firm's account stays open." };
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
  const jar = await cookies();
  const own = jar.get(STAFF_COOKIE)?.value;
  if (own) {
    await endSession(own);
    jar.delete(STAFF_COOKIE);
  }
  jar.delete(SESSION_COOKIE);
  redirect("/login");
}

// Confirming it is you, the sessions open, and the firm's two-step rule

function safeNext(next: string): string {
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export async function confirmIdentity(next: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/auth/confirm", {
    password: String(form.get("password") ?? ""),
    code: text(form, "code"),
  });
  if (!result.ok) return { error: result.error };
  redirect(safeNext(next));
}

export async function endSessionElsewhere(sessionId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/auth/sessions/${sessionId}/end`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function endOtherSessions(_previous: ActionState): Promise<ActionState> {
  const result = await send<{ ended: number }>("POST", "/auth/sessions/end-others");
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: result.data.ended === 1 ? "Signed out of 1 other session." : `Signed out of ${result.data.ended} other sessions.` };
}

export async function setTwoStepRule(required: boolean, _previous: ActionState): Promise<ActionState> {
  const result = await send("PUT", "/organization/two-step-rule", { required });
  if (!result.ok) return { error: result.error };
  refresh();
  return {
    ok: required
      ? "Everyone in the firm now signs in with a code. Anyone without it set up is asked to set it up."
      : "Two-step sign-in is no longer required.",
  };
}

// The register of originals

const ORIGINAL_FIELDS = ["title", "kind", "held_at", "held_by", "since", "against", "note"];

export async function addOriginal(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ number: string }>("POST", `/projects/${projectId}/originals`, filled(form, ORIGINAL_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: `Added as ${result.data.number}. Print its label and stick it on the folder.` };
}

export async function moveOriginal(originalId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/originals/${originalId}/move`, filled(form, ORIGINAL_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Moved." };
}

// Filing documents by rules

export async function addFilingRule(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ would_file: number }>(
    "POST",
    "/organization/filing-rules",
    filled(form, ["name", "words", "how", "category", "requirement"]),
  );
  if (!result.ok) return { error: result.error };
  refresh();
  const n = result.data.would_file;
  return {
    ok: n
      ? `Added. It fits ${n === 1 ? "1 document" : `${n} documents`} already in the vault; file what is still under Other to use it on them.`
      : "Added. It fits no document in the vault yet.",
  };
}

export async function addStandardFilingRules(_previous: ActionState): Promise<ActionState> {
  const result = await send<{ added: number }>("POST", "/organization/filing-rules/standard");
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: `${result.data.added} rules added.` };
}

export async function deleteFilingRule(ruleId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/organization/filing-rules/${ruleId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function refileDocuments(_previous: ActionState): Promise<ActionState> {
  const result = await send<{ filed: number }>("POST", "/organization/filing-rules/refile");
  if (!result.ok) return { error: result.error };
  refresh();
  const n = result.data.filed;
  return { ok: n ? `${n === 1 ? "1 document" : `${n} documents`} filed.` : "No document under Other fits a rule." };
}

// Passkeys. These are called from the page's own scripts (the browser does the passkey part),
// not from forms, so they return data rather than redirect, except where noted.

export async function passkeyOptions(): Promise<{ options: unknown } | { error: string }> {
  const result = await send<unknown>("POST", "/auth/passkeys/options");
  if (!result.ok) return { error: result.error };
  return { options: result.data };
}

export async function savePasskey(response: unknown, name: string): Promise<ActionState> {
  const result = await send("POST", "/auth/passkeys", { response, name });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Passkey added." };
}

export async function removePasskey(passkeyId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/auth/passkeys/${passkeyId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function passkeyLoginOptions(): Promise<{ ticket: string; options: unknown } | { error: string }> {
  const result = await send<{ ticket: string; options: unknown }>("POST", "/auth/passkey/login/options");
  if (!result.ok) return { error: result.error };
  return result.data;
}

/** Signs in with the passkey's answer, and goes to Today. */
export async function passkeyLogin(ticket: string, response: unknown): Promise<ActionState> {
  const result = await send<{ token: string }>("POST", "/auth/passkey/login", { ticket, response });
  if (!result.ok) return { error: result.error };
  await startSession(result.data.token);
  redirect("/");
}

// Support access, as the firm allows it

export async function allowSupport(_previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", "/organization/support", { days: Number(text(form, "days")) });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Lekhara support can now see your workspace, read-only." };
}

export async function withdrawSupport(_previous: ActionState): Promise<ActionState> {
  const result = await send("POST", "/organization/support/withdraw");
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Support can no longer see your workspace." };
}

// Our admin console

export async function extendTrial(orgId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/staff/firms/${orgId}/trial`, filled(form, ["ends_on", "reason"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "The free month is extended." };
}

const PAYMENT_FIELDS = ["amount", "paid_on", "method", "reference", "covers_from", "covers_to", "note"];

export async function recordPayment(orgId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/staff/firms/${orgId}/payments`, filled(form, PAYMENT_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Payment recorded." };
}

export async function removePayment(paymentId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/staff/payments/${paymentId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

/** Opens the firm's workspace as support: staff's own session is kept aside until they end it. */
export async function openSupport(orgId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send<{ token: string }>("POST", `/staff/firms/${orgId}/support`);
  if (!result.ok) return { error: result.error };
  const jar = await cookies();
  const own = jar.get(SESSION_COOKIE)?.value;
  const options = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
  };
  if (own) jar.set({ name: STAFF_COOKIE, value: own, ...options, maxAge: SESSION_DAYS * 24 * 60 * 60 });
  jar.set({ name: SESSION_COOKIE, value: result.data.token, ...options, maxAge: 2 * 60 * 60 });
  redirect("/");
}

export async function endSupport(): Promise<void> {
  await send("POST", "/auth/logout");
  const jar = await cookies();
  const own = jar.get(STAFF_COOKIE)?.value;
  if (!own) {
    jar.delete(SESSION_COOKIE);
    redirect("/login");
  }
  await startSession(own);
  redirect("/admin");
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
    ask_visitor: form.get("ask_visitor") === "yes",
    watermark: form.get("watermark") === "yes",
    notify: form.get("notify") === "yes",
    terms: text(form, "terms") || null,
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
  if (form.get("protections") === "change") {
    body.ask_visitor = form.get("ask_visitor") === "yes";
    body.watermark = form.get("watermark") === "yes";
    body.notify = form.get("notify") === "yes";
    body.terms = text(form, "terms");
  }
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

const LANDOWNER_PAYMENT_FIELDS = ["paid_on", "amount", "tds_deducted", "deposit", "reference"];

export async function addLandownerPayment(ownerId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/landowners/${ownerId}/payments`, filled(form, LANDOWNER_PAYMENT_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Payment added." };
}

export async function updateLandownerPayment(paymentId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string> = filled(form, LANDOWNER_PAYMENT_FIELDS);
  for (const name of blanks(form, ["tds_deducted", "reference"])) body[name] = "";
  const result = await send("PUT", `/landowner-payments/${paymentId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteLandownerPayment(paymentId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/landowner-payments/${paymentId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

const APPROVAL_FIELDS = ["name", "authority", "reference", "applied_on", "granted_on", "valid_until", "note"];

export async function createApproval(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/approvals`, filled(form, APPROVAL_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Approval added." };
}

export async function addStandardApprovals(projectId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/approvals/standard`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

export async function updateApproval(approvalId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string> = filled(form, APPROVAL_FIELDS);
  for (const name of blanks(form, APPROVAL_FIELDS.filter((n) => n !== "name"))) body[name] = "";
  const result = await send("PUT", `/approvals/${approvalId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteApproval(approvalId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/approvals/${approvalId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

const FILING_FIELDS = ["kind", "period_end", "filed_on", "reference"];

export async function recordFiling(projectId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/filings`, filled(form, FILING_FIELDS));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Recorded as filed." };
}

export async function updateFiling(filingId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body: Record<string, string> = filled(form, FILING_FIELDS);
  for (const name of blanks(form, ["reference"])) body[name] = "";
  const result = await send("PUT", `/filings/${filingId}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

export async function deleteFiling(filingId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/filings/${filingId}/delete`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

/** Rows edited as a table become an import, so the change is previewed before it is saved. */
export async function saveTable(
  projectId: string,
  kind: string,
  shape: { rows: number; columns: number },
  _previous: ActionState,
  form: FormData,
): Promise<ActionState> {
  const rows: string[][] = [];
  for (let r = 0; r < shape.rows; r += 1) {
    const row: string[] = [];
    for (let c = 0; c < shape.columns; c += 1) row.push(String(form.get(`c-${r}-${c}`) ?? "").trim());
    rows.push(row);
  }
  const result = await send<{ id: string }>("POST", `/projects/${projectId}/table/${kind}`, { rows });
  if (!result.ok) return { error: result.error };
  redirect(`/imports/${result.data.id}`);
}

export async function cancelBooking(unitId: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send("POST", `/units/${unitId}/cancel-booking`, filled(form, ["cancelled_on", "refunded", "refunded_on", "reason"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "The booking is cancelled; the unit can be sold again." };
}

export async function cancelCaseBooking(caseId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/cases/${caseId}/cancel-booking`, {});
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "The booking is cancelled; the unit can be sold again." };
}

export async function setAssociationItem(projectId: string, key: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const body = { done_on: text(form, "done_on"), note: text(form, "note") };
  const result = await send("PUT", `/projects/${projectId}/association/${key}`, body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Saved." };
}

/** Someone opening a data room that asks who they are: their name and email are recorded with
 * their visits, and their browser keeps a token for this room's link only. */
export async function enterRoom(token: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ visitor: string }>("POST", `/shared/${encodeURIComponent(token)}/visitor`, {
    name: text(form, "name"),
    email: text(form, "email"),
    accept_terms: form.get("accept_terms") === "yes",
  });
  if (!result.ok) return { error: result.error };
  (await cookies()).set({
    name: VISITOR_COOKIE,
    value: result.data.visitor,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: `/shared/${encodeURIComponent(token)}`,
    maxAge: 60 * 24 * 60 * 60,
  });
  redirect(`/shared/${encodeURIComponent(token)}`);
}

/** The code emailed to a data room visitor, proving the email is theirs. */
export async function confirmRoomCode(token: string, _previous: ActionState, form: FormData): Promise<ActionState> {
  const visitor = (await cookies()).get(VISITOR_COOKIE)?.value;
  const result = await sendAsVisitor(`/shared/${encodeURIComponent(token)}/visitor/verify`, visitor, {
    code: text(form, "code"),
  });
  if (!result.ok) return { error: result.error };
  redirect(`/shared/${encodeURIComponent(token)}`);
}

/** A known visitor accepting a room's terms again, after they changed. */
export async function acceptRoomTerms(token: string, _previous: ActionState): Promise<ActionState> {
  const visitor = (await cookies()).get(VISITOR_COOKIE)?.value;
  const result = await sendAsVisitor(`/shared/${encodeURIComponent(token)}/visitor/terms`, visitor, {});
  if (!result.ok) return { error: result.error };
  redirect(`/shared/${encodeURIComponent(token)}`);
}

/** Starts again with another name or email: the browser forgets the visitor it was. */
export async function forgetRoomVisitor(token: string, _previous: ActionState): Promise<ActionState> {
  (await cookies()).delete({ name: VISITOR_COOKIE, path: `/shared/${encodeURIComponent(token)}` });
  redirect(`/shared/${encodeURIComponent(token)}`);
}

export async function recordEarlierFilings(projectId: string, _previous: ActionState): Promise<ActionState> {
  const result = await send("POST", `/projects/${projectId}/filings/earlier`);
  if (!result.ok) return { error: result.error };
  refresh();
  return {};
}

/** Reads a project's details from its K-RERA certificate and opens the form filled in, to check. */
export async function readCertificate(_previous: ActionState, form: FormData): Promise<ActionState> {
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose the certificate first." };
  const body = new FormData();
  body.append("file", file, file.name);
  const result = await sendForm<{ fields: Record<string, string>; missing: string[] }>("/projects/from-certificate", body);
  if (!result.ok) return { error: result.error };
  const query = new URLSearchParams({ ...result.data.fields, from: "certificate", missing: result.data.missing.join(", ") });
  redirect(`/projects/new?${query}`);
}
