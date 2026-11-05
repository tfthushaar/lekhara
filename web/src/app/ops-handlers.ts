// What the forms for running the firm do: contractors and payments, the site, after handover,
// and loans. They run only as the server actions in `actions.ts`.

import { refresh } from "next/cache";

import type { ActionState } from "@/app/form-handlers";
import { send, sendForm } from "@/lib/api";

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

async function done(result: { ok: boolean; error?: string }, ok: string): Promise<ActionState> {
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok };
}

// Contractors and payments

export async function addWorkOrder(projectId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  const body = { ...filled(form, ["contractor", "amount", "description", "reference", "cost_line", "retention_pct", "advance"]), deduct_cess: form.get("deduct_cess") === "yes" ? "yes" : "no" };
  return done(await send("POST", `/projects/${projectId}/contractors/orders`, body), "Work order added.");
}

export async function addRunningBill(orderId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ net_payable: string }>("POST", `/contractors/orders/${orderId}/bills`, filled(form, ["work_value", "gst", "period_to", "bill_no", "advance_recovery"]));
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Bill added. It now waits for approval." };
}

export async function releaseRetention(orderId: string, _p: ActionState): Promise<ActionState> {
  return done(await send("POST", `/contractors/orders/${orderId}/release-retention`), "Marked released.");
}

export async function approveBill(billId: string, _p: ActionState): Promise<ActionState> {
  return done(await send("POST", `/payables/${billId}/approve`), "Approved.");
}

export async function holdBill(billId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/payables/${billId}/hold`, { note: text(form, "note") }), "On hold.");
}

export async function payBill(billId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/payables/${billId}/pay`, filled(form, ["reference", "paid_on"])), "Paid.");
}

// The site

export async function saveDailyReport(projectId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  const body = new FormData();
  for (const name of ["work_done", "workers", "issues", "day"]) {
    const value = text(form, name);
    if (value) body.append(name, value);
  }
  for (let i = 0; i < 6; i += 1) {
    for (const key of [`used_item_${i}`, `used_qty_${i}`]) {
      const value = text(form, key);
      if (value) body.append(key, value);
    }
  }
  for (const file of form.getAll("photos")) {
    if (file instanceof File && file.size > 0) body.append("photos", file, file.name);
  }
  const result = await sendForm("/projects/" + projectId + "/daily-reports", body);
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: "Today's report is saved." };
}

export async function askForMaterial(projectId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/projects/${projectId}/material-requests`, filled(form, ["item", "unit", "quantity", "needed_by", "note"])), "Sent to the office.");
}

export async function materialArrived(projectId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/projects/${projectId}/materials/received`, filled(form, ["item", "unit", "quantity", "note"])), "Added to stock.");
}

export async function addQuote(requestId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/material-requests/${requestId}/quotes`, filled(form, ["supplier", "rate"])), "Quote added.");
}

export async function orderMaterial(requestId: string, quoteId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  const result = await send<{ order: string }>("POST", `/material-requests/${requestId}/order`, { quote_id: quoteId, ...filled(form, ["cost_line"]) });
  if (!result.ok) return { error: result.error };
  refresh();
  return { ok: `Ordered, as ${result.data.order}.` };
}

export async function receiveMaterial(requestId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/material-requests/${requestId}/receive`, filled(form, ["quantity"])), "Received, and added to stock.");
}

export async function cancelMaterial(requestId: string, _p: ActionState): Promise<ActionState> {
  return done(await send("POST", `/material-requests/${requestId}/cancel`), "Cancelled.");
}

// After handover

export async function addIssue(projectId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/projects/${projectId}/issues`, filled(form, ["unit_id", "kind", "title", "detail", "reported_on"])), "Added.");
}

export async function closeIssue(issueId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/issues/${issueId}/done`, filled(form, ["reply"])), "Done.");
}

// Loans

export async function addLoan(projectId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/projects/${projectId}/loans`, filled(form, ["lender", "sanctioned", "rate_pct", "sanctioned_on"])), "Loan added.");
}

export async function addLoanMove(loanId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/loans/${loanId}/moves`, filled(form, ["kind", "amount", "on", "note"])), "Saved.");
}

export async function addLoanCondition(loanId: string, _p: ActionState, form: FormData): Promise<ActionState> {
  return done(await send("POST", `/loans/${loanId}/conditions`, filled(form, ["text", "due_on"])), "Added.");
}

export async function meetLoanCondition(conditionId: string, _p: ActionState): Promise<ActionState> {
  return done(await send("POST", `/loan-conditions/${conditionId}/met`), "Marked as met.");
}
