import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { SESSION_COOKIE } from "@/lib/session-cookie";

const BASE = process.env.HORUS_API_URL ?? "http://localhost:8000";

export type Status = "overdue" | "due_soon" | "at_risk" | "opportunity" | "upcoming" | "done";
export type Area = "escrow" | "krera" | "tax" | "units";

export type Obligation = {
  key: string;
  project_id: string;
  project_name: string;
  title: string;
  detail: string;
  owed_to: string;
  status: Status;
  area: Area;
  due_on: string | null;
  amount: string | null;
  amount_label: string | null;
  exposure: boolean;
  rule_key: string | null;
  action: string | null;
  link: string | null;
};

export type Counts = Record<Status, number>;

export type Today =
  | {
      kind: "team";
      as_of: string;
      organization: string;
      summary: { drawable_now: string; at_stake: string; due_this_week: number; projects: number };
      items: Obligation[];
    }
  | {
      kind: "certifier";
      as_of: string;
      organization: string;
      summary: { waiting: number; projects: number };
      items: Obligation[];
    };

export type Me = {
  user: { id: string; name: string; email: string; firm: string | null };
  role_label: string;
  kind: "team" | "certifier";
  organizations: string[];
};

export type DemoAccounts = {
  password: string;
  accounts: { email: string; name: string; label: string }[];
};

export type ProjectCard = {
  id: string;
  name: string;
  locality: string;
  land_structure: string;
  progress_pct: string | null;
  budget: string;
  anticipated_final_cost: string;
  incurred: string;
  drawable_now: string;
  possession_due_on: string | null;
  counts: Counts;
  next: Obligation | null;
};

export type Alert = { code: string; title: string; detail: string; amount: string | null };

export type MoneySummary = {
  as_of: string;
  budget: string;
  committed: string;
  incurred: string;
  paid: string;
  retained: string;
  contingency_budget: string;
  contingency_remaining: string;
  overrun_beyond_contingency: string;
  anticipated_final_cost: string;
  cost_to_complete: string;
  certified_progress_pct: string | null;
  development_incurred_pct: string;
  alerts: Alert[];
};

export type ProjectDetail = {
  id: string;
  name: string;
  locality: string;
  city: string;
  krera_registration: string;
  registered_on: string;
  spv_name: string;
  gst_regime: string;
  land_structure: string;
  possession_due_on: string | null;
  escrow_bank: string | null;
  money: MoneySummary;
  drawable_now: string;
  open_request_id: string | null;
  obligations: Obligation[];
  counts: Counts;
  access: { team: boolean; certifies: string[] };
};

export type MoneyLine = {
  id: string;
  code: string;
  name: string;
  category: string;
  budget: string;
  committed: string;
  incurred: string;
  paid: string;
  anticipated_final_cost: string;
  cost_to_complete: string;
  overrun: string;
};

export type RequestSummary = {
  id: string;
  amount: string;
  created_on: string;
  submitted_on: string | null;
  released_on: string | null;
  released_amount: string | null;
  status: RequestStatus;
  waiting_on: string | null;
};

export type Escrow = {
  as_of: string;
  drawable_now: string;
  limited_by: "cost" | "balance";
  limited_by_text: string;
  steps: { label: string; value: string; kind: "money" | "percent" }[];
  deposits: {
    receipts_from_buyers: string;
    deposit_share_pct: string;
    required: string;
    deposited: string;
    shortfall: string;
  };
  last_withdrawal_on: string | null;
  next_cycle_due_on: string | null;
  open_request_id: string | null;
  can_start: boolean;
  requests: RequestSummary[];
};

export type RequestStatus = "awaiting_signatures" | "ready" | "submitted" | "released" | "rejected";

export type Figure = {
  field: string;
  label: string;
  value: string | null;
  books: string | null;
  kind: "money" | "percent";
  matches_books: boolean;
};

export type CertificateView = {
  role: "architect" | "engineer" | "ca";
  label: string;
  certifies: string;
  signed: boolean;
  signer_name: string | null;
  signer_firm: string | null;
  issued_on: string | null;
  figures: Figure[];
};

export type CheckView = {
  code: string;
  status: "pass" | "warn" | "fail" | "pending";
  title: string;
  detail: string;
};

export type Withdrawal = {
  id: string;
  project_id: string;
  project_name: string;
  escrow_bank: string | null;
  amount: string;
  created_on: string;
  submitted_on: string | null;
  released_on: string | null;
  released_amount: string | null;
  bank_reference: string | null;
  rejected_on: string | null;
  rejection_reason: string | null;
  status: RequestStatus;
  waiting_on: string | null;
  can_submit: boolean;
  permissions: {
    edit_roles: string[];
    sign_roles: string[];
    can_submit: boolean;
    can_release: boolean;
  };
  drawable_now: string;
  steps: { name: string; status: "done" | "current" | "todo" }[];
  certificates: CertificateView[];
  checks: CheckView[];
};

export type Tax = {
  as_of: string;
  regime: string;
  procurement: {
    applies: boolean;
    fy: string;
    total: string;
    qualifying: string;
    registered_share_pct: string;
    min_share_pct: string;
    shortfall: string;
    rcm_on_shortfall: string;
    unregistered_headroom: string;
    cement_rcm: string;
    payment_due_on: string;
  };
  development_rights: {
    applies: boolean;
    dr_value: string;
    unbooked_units: number;
    gst_on_unbooked_share: string;
    cap: string;
    liability: string;
    capped: boolean;
    saving_per_unit_sold: string;
  };
  guidance: {
    unit: string;
    agreement_value: string;
    guidance_value: string;
    gap: string;
    gap_pct: string;
    estimated_tax: string;
    booked_on: string;
  }[];
  landowner_tds: {
    landowner: string;
    paid_on: string;
    amount: string;
    expected: string;
    deducted: string;
    short: string;
  }[];
  msme: {
    vendor: string;
    bill_no: string;
    amount: string;
    accepted_on: string;
    due_on: string;
    status: "ok" | "due_soon" | "overdue";
    days_left: number;
  }[];
  cess: {
    construction_incurred: string;
    due_to_date: string;
    paid: string;
    balance_due: string;
    on_estimate: string;
  };
  delay: {
    possession_due_on: string | null;
    days_late: number;
    days_to_possession: number | null;
    annual_rate_pct: string;
    buyer_money: string;
    accrued: string;
    per_month: string;
  };
};

export type Units = {
  summary: {
    total: number;
    developer: number;
    landowner: number;
    developer_booked: number;
    developer_unbooked: number;
  };
  landowners: {
    name: string;
    share_type: "area" | "revenue";
    share_pct: string;
    refundable_deposit: string;
    paid_to_date: string;
    tds_to_date: string;
  }[];
  units: {
    label: string;
    tower: string;
    carpet_area_sqft: number;
    owner_share: "developer" | "landowner";
    booked: boolean;
    list_price: string;
    agreement_value: string | null;
    guidance_value: string;
    below_guidance: boolean;
  }[];
};

export type Rules = {
  state: string;
  version: string;
  rules: {
    key: string;
    title: string;
    value: string;
    display: string;
    basis: string;
    source_quality: "official" | "secondary" | "unsettled" | "unverified" | "horus_default";
    confirm_against: string;
    note: string;
  }[];
};

async function authHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: await authHeaders(),
  });
  if (response.status === 401) redirect("/login");
  if (response.status === 404 || response.status === 403) notFound();
  if (!response.ok) throw new Error(`Horus API ${response.status} on ${path}`);
  return response.json() as Promise<T>;
}

export type SendResult<T> = { ok: true; data: T } | { ok: false; error: string };

export async function send<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown = {},
): Promise<SendResult<T>> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 204) return { ok: true, data: undefined as T };
  if (response.ok) return { ok: true, data: (await response.json()) as T };
  if (response.status === 401) return { ok: false, error: "Your session has ended. Sign in again." };
  try {
    const problem = await response.json();
    const detail = problem?.detail;
    return {
      ok: false,
      error: typeof detail === "string" ? detail : "Some of the details entered are not valid.",
    };
  } catch {
    return { ok: false, error: "Horus could not complete that. Try again." };
  }
}

/** The demo accounts, when the API runs in demo mode. Public; no session needed. */
export async function demoAccounts(): Promise<DemoAccounts | null> {
  try {
    const response = await fetch(`${BASE}/auth/demo`, { cache: "no-store" });
    return response.ok ? ((await response.json()) as DemoAccounts) : null;
  } catch {
    return null;
  }
}

export const api = {
  me: () => get<Me>("/auth/me"),
  today: () => get<Today>("/today"),
  projects: () => get<ProjectCard[]>("/projects"),
  project: (id: string) => get<ProjectDetail>(`/projects/${id}`),
  money: (id: string) => get<{ summary: MoneySummary; lines: MoneyLine[] }>(`/projects/${id}/money`),
  escrow: (id: string) => get<Escrow>(`/projects/${id}/escrow`),
  tax: (id: string) => get<Tax>(`/projects/${id}/tax`),
  units: (id: string) => get<Units>(`/projects/${id}/units`),
  withdrawal: (id: string) => get<Withdrawal>(`/withdrawals/${id}`),
  rules: () => get<Rules>("/rules"),
};

export function areaHref(o: Obligation): string {
  if (o.link) return o.link;
  const base = `/projects/${o.project_id}`;
  switch (o.area) {
    case "escrow":
      return `${base}/escrow`;
    case "tax":
      return `${base}/tax`;
    case "units":
      return `${base}/units`;
    default:
      return base;
  }
}
