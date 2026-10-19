import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { SESSION_COOKIE } from "@/lib/session-cookie";

const BASE = process.env.LEKHARA_API_URL ?? "http://localhost:8000";

export type Status = "overdue" | "due_soon" | "at_risk" | "opportunity" | "upcoming" | "done";
export type Area =
  | "escrow"
  | "collections"
  | "handover"
  | "disputes"
  | "documents"
  | "approvals"
  | "krera"
  | "tax"
  | "units";

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
      to_review: number;
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

export type Access = "active" | "trial" | "read_only";

export type Me = {
  user: { id: string; name: string; email: string; firm: string | null };
  role_label: string;
  kind: "team" | "certifier";
  organizations: string[];
  organization: {
    id: string;
    name: string;
    access: Access;
    trial_ends_on: string | null;
    days_left: number | null;
    is_sample: boolean;
    delete_after: string | null;
    can_add_projects: boolean;
  } | null;
  email_verified: boolean;
  terms_accepted: boolean;
};

export type Firm = {
  id: string;
  name: string;
  legal_name: string | null;
  gstin: string | null;
  state: string | null;
  access: Access;
  trial_ends_on: string | null;
  days_left: number | null;
  is_sample: boolean;
  closing_on: string | null;
  delete_after: string | null;
  role: string;
  can_manage: boolean;
  is_owner: boolean;
  members: { user_id: string; name: string; email: string; role: string; role_label: string; you: boolean }[];
  certifiers: { user_id: string; name: string; email: string; firm: string | null; role_label: string; projects: string[] }[];
  invitations: { id: string; email: string; role_label: string; expires_on: string }[];
  projects: { id: string; name: string }[];
  roles: Choice[];
};

export type InvitationInfo = {
  firm: string;
  email: string;
  role: string;
  role_label: string;
  certifier: boolean;
  projects: string[];
  has_account: boolean;
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
  sample: boolean;
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
  access: { sample: boolean; team: boolean; certifies: string[] };
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
    id: string;
    pan: string | null;
    name: string;
    share_type: "area" | "revenue";
    share_pct: string;
    refundable_deposit: string;
    paid_to_date: string;
    tds_to_date: string;
  }[];
  units: {
    id: string;
    label: string;
    tower: string;
    carpet_area_sqft: number;
    owner_share: "developer" | "landowner";
    booked: boolean;
    list_price: string;
    agreement_value: string | null;
    guidance_value: string;
    below_guidance: boolean;
    buyer_name: string | null;
  }[];
};

export type Collections = {
  as_of: string;
  can_raise: boolean;
  summary: {
    billed: string;
    received: string;
    outstanding: string;
    overdue: string;
    overdue_buyers: number;
    interest: string;
  };
  ready: {
    milestone_id: string;
    name: string;
    units: number;
    amount: string;
    gst: string;
    total: string;
    reason: string;
  }[];
  milestones: {
    id: string;
    sequence: number;
    name: string;
    share_pct: string;
    trigger: "booking" | "agreement" | "progress" | "possession";
    progress_pct: string | null;
    reached: boolean;
    raised_units: number;
    billed: string;
  }[];
  overdue: {
    unit: string;
    buyer: string | null;
    overdue: string;
    interest: string;
    days_overdue: number;
    demand_id: string | null;
  }[];
  accounts: {
    unit: string;
    buyer: string | null;
    agreement_value: string;
    billed: string;
    received: string;
    tds: string;
    outstanding: string;
    overdue: string;
    interest: string;
    last_demand_id: string | null;
  }[];
  deposit_checks: {
    month_end: string;
    receipts: string;
    required: string;
    deposits: string;
    shortfall: string;
  }[];
};

export type DemandLetter = {
  id: string;
  project_id: string;
  from: string;
  project: string;
  krera_registration: string;
  date: string;
  to: string | null;
  unit: string;
  subject: string;
  paragraphs: string[];
  lines: { label: string; value: string }[];
  due_on: string;
  note: string;
};

export type UnitReadiness = {
  unit_id: string;
  label: string;
  buyer: string | null;
  blocker: string;
  blocker_text: string;
  steps: { stage: string; label: string; done: boolean }[];
  ekhata_status: "none" | "applied" | "draft" | "final";
  ekhata_label: string;
  khata_type: string | null;
  agreement_value: string;
  guidance_value: string;
  balance_due: string;
  final_demand_raised: boolean;
  deed_drafted_on: string | null;
  appointment_on: string | null;
  registered_on: string | null;
  document_no: string | null;
  possession_on: string | null;
  cost: { base: string; stamp_duty: string; cess: string; registration_fee: string; total: string };
};

export type Handover = {
  can_edit: boolean;
  oc: { status: string; label: string; received_on: string | null; reference: string | null };
  conveyance_due_on: string | null;
  common_areas_conveyed_on: string | null;
  association_formed_on: string | null;
  summary: { units: number; registered: number; handed_over: number; money_waiting: string };
  stages: { stage: string; label: string; blocked: number }[];
  units: UnitReadiness[];
  association: { key: string; label: string; done_on: string | null; note: string | null }[];
};

export type PossessionLetter = {
  unit_id: string;
  project_id: string;
  from: string;
  project: string;
  krera_registration: string;
  date: string;
  to: string;
  unit: string;
  subject: string;
  paragraphs: string[];
  lines: { label: string; value: string }[];
  take_by: string;
  after: string[];
  note: string;
};

export type EarlierBooking = {
  id: string;
  buyer_name: string | null;
  booked_on: string | null;
  cancelled_on: string;
  agreement_value: string | null;
  paid: string;
  refunded: string | null;
  refunded_on: string | null;
  reason: string | null;
  case_id: string | null;
};

export type UnitHandover = UnitReadiness & {
  project_id: string;
  project_name: string;
  can_edit: boolean;
  fact_sheet: { label: string; value: string }[];
};

export type Choice = { value: string; label: string };

export type CaseEvent = {
  on: string;
  kind: "reply" | "hearing" | "comply" | "appeal";
  case_id: string;
  text: string;
};

export type CaseRow = {
  id: string;
  forum: string;
  forum_label: string;
  case_number: string;
  complainant: string;
  unit: string | null;
  relief: string;
  relief_label: string;
  status: string;
  status_label: string;
  open: boolean;
  at_stake: string;
  ordered: boolean;
  next: CaseEvent | null;
};

export type Disputes = {
  can_edit: boolean;
  summary: {
    open: number;
    at_stake: string;
    owed_under_orders: string;
    overdue_orders: number;
    next: CaseEvent | null;
  };
  events: CaseEvent[];
  cases: CaseRow[];
  patterns: {
    total: number;
    by_relief: { label: string; count: number }[];
    by_forum: { label: string; count: number }[];
    filed_after_possession_due: number;
    with_filing_date: number;
    possession_due_on: string | null;
    units_with_cases: number;
    booked_units: number;
  };
  choices: { forums: Choice[]; reliefs: Choice[] };
  units: string[];
};

export type CaseOrder = {
  id: string;
  kind: string;
  label: string;
  summary: string | null;
  ordered_on: string;
  received_on: string | null;
  comply_by: string | null;
  worked_out: boolean;
  due: string;
  paid: string;
  outstanding: string;
  overdue: boolean;
  appeal_to: string | null;
  appeal_by: string | null;
  appeal_deposit: string | null;
};

export type CaseDetail = CaseRow & {
  booking: {
    unit_id: string;
    unit: string;
    refund_paid: boolean;
    registered: boolean;
    can_cancel: boolean;
    cancelled_on: string | null;
  } | null;
  project_id: string;
  project_name: string;
  can_edit: boolean;
  summary: string | null;
  lawyer: string | null;
  claim_amount: string | null;
  filed_on: string | null;
  notice_received_on: string | null;
  reply_due_on: string | null;
  reply_filed_on: string | null;
  next_hearing_on: string | null;
  appealed_on: string | null;
  closed_on: string | null;
  possession_due_on: string | null;
  possession_on: string | null;
  buyer_paid: string;
  rate_pct: string;
  estimate: { principal: string; interest: string; other: string; total: string; basis: string };
  orders: CaseOrder[];
  ordered_total: string;
  owed: string;
  paid: string;
  settlement: { offered: string | null; agreed: string | null; saving: string | null };
  hearings: { held_on: string; purpose: string; outcome: string | null }[];
  payments: { paid_on: string; amount: string; reference: string | null }[];
  events: CaseEvent[];
  choices: { statuses: Choice[]; order_kinds: Choice[] };
};

export type DocRow = {
  id: string;
  title: string;
  category: string;
  category_label: string;
  filename: string;
  content_type: string;
  size: string;
  document_date: string | null;
  expires_on: string | null;
  expiry: "held" | "expiring" | "expired";
  reference: string | null;
  version: number;
  pages: number;
  text_status: "text" | "no_text" | "unreadable";
  requirement: string | null;
  link_type: string | null;
  link_id: string | null;
  uploaded_on: string;
};

export type ChecklistRow = {
  key: string;
  title: string;
  category: string;
  why: string;
  tracks_expiry: boolean;
  status: "held" | "missing" | "expiring" | "expired" | "waived";
  document_id: string | null;
  expires_on: string | null;
  waiver_reason: string | null;
};

export type RoomRow = {
  id: string;
  name: string;
  audience: string | null;
  created_on: string;
  expires_on: string;
  state: "open" | "expired" | "revoked";
  documents: number;
  opens: number;
  downloads: number;
  last_visit: string | null;
};

export type DocumentsView = {
  can_edit: boolean;
  can_share: boolean;
  notice_days: number;
  summary: { documents: number; missing: number; expiring: number; rooms_open: number };
  checklist: ChecklistRow[];
  records: {
    key: string;
    title: string;
    category: string;
    link_type: string;
    needed: number;
    held: number;
    missing: { id: string; label: string }[];
  }[];
  documents: DocRow[];
  categories: Choice[];
  rooms: RoomRow[];
};

export type SearchResults = {
  query: string;
  results: {
    document: DocRow;
    page: number | null;
    snippets: { before: string; match: string; after: string }[];
  }[];
};

export type DocumentDetail = DocRow & {
  project_id: string;
  project_name: string;
  can_edit: boolean;
  notes: string | null;
  archived_on: string | null;
  record: string | null;
  requirement_title: string | null;
  current: boolean;
  versions: {
    id: string;
    version: number;
    filename: string;
    size: string;
    uploaded_on: string;
    expires_on: string | null;
  }[];
  rooms: { id: string; name: string; state: string }[];
  categories: Choice[];
  requirements: Choice[];
};

export type LinkedDocuments = {
  project_id: string;
  can_edit: boolean;
  documents: DocRow[];
  categories: Choice[];
};

export type RoomDetail = RoomRow & {
  project_id: string;
  project_name: string;
  can_share: boolean;
  documents_in_room: DocRow[];
  available: { id: string; title: string; category_label: string }[];
  ask_visitor: boolean;
  visits: { at: string; action: "open" | "download"; document: string | null; visitor: string | null }[];
};

export type SharedGate = { gate: true; name: string; organization: string; project: string; expires_on: string };

export type SharedRoom = {
  gate: false;
  name: string;
  audience: string | null;
  organization: string;
  project: string;
  krera_registration: string;
  expires_on: string;
  documents: {
    id: string;
    title: string;
    category_label: string;
    document_date: string | null;
    reference: string | null;
    size: string;
    content_type: string;
  }[];
};

export type FieldChange = { field: string; before: string | number | null; after: string | number | null };

export type UnitDetail = {
  id: string;
  project_id: string;
  project_name: string;
  label: string;
  tower: string;
  carpet_area_sqft: number;
  owner_share: string;
  owner_share_label: string;
  list_price: string;
  guidance_value: string;
  buyer_name: string | null;
  buyer_phone: string | null;
  buyer_email: string | null;
  booked: boolean;
  booked_on: string | null;
  agreement_value: string | null;
  can_edit: boolean;
  can_delete: boolean;
  dependents: string[];
  earlier_bookings: EarlierBooking[];
  history: { at: string; action: string; source: string; by: string; changes: FieldChange[] }[];
  receipts: {
    id: string;
    received_on: string;
    amount: string;
    tds: string;
    reference: string | null;
    source: string;
    can_delete: boolean;
  }[];
};

export type ImportBatch = {
  id: string;
  kind: string;
  title: string;
  filename: string;
  status: "preview" | "applied" | "undone";
  project_id: string;
  project_name: string;
  created_at: string;
  applied_at: string | null;
  can_edit: boolean;
  can_undo: boolean;
  header_row: number;
  total_rows: number;
  columns: { index: number; header: string; field: string | null; sample: string }[];
  fields: { value: string; label: string; required: boolean }[];
  missing_required: string[];
  counts: { add: number; update: number; unchanged: number; error: number };
  rows: { row: number; key: string | null; action: string; messages: string[]; changes: FieldChange[] }[];
  result: { added: number; updated: number; unchanged: number; errors: number } | null;
};

export type ImportList = {
  can_import: boolean;
  imports: {
    id: string;
    title: string;
    filename: string;
    status: string;
    created_at: string;
    added: number | null;
    updated: number | null;
  }[];
};

export type GstRow = {
  id: string;
  filename: string;
  form: string;
  gstin: string | null;
  period: string | null;
  period_label: string | null;
  invoices: number;
  status: "review" | "applied" | "undone";
  created_at: string;
};

export type GstList = { can_import: boolean; imports: GstRow[] };

export type GstReview = GstRow & {
  project_id: string;
  project_name: string;
  can_edit: boolean;
  can_undo: boolean;
  add_missing: boolean;
  counts: Record<string, number>;
  alerts: TallyAlert[];
  lines: {
    supplier_gstin: string;
    supplier_name: string | null;
    number: string;
    date: string | null;
    kind: "invoice" | "credit_note" | "debit_note";
    taxable: string;
    gst: string;
    value: string;
    itc_available: boolean | null;
    reverse_charge: boolean;
    outcome: "matched" | "differs" | "missing" | "note";
    note: string;
    bill_id: string | null;
  }[];
  unreported: { bill_id: string; supplier: string; bill_no: string; bill_date: string; taxable: string }[];
  new_suppliers: { gstin: string; name: string }[];
  gstin_updates: { vendor_id: string; name: string; gstin: string }[];
  result: { gstins: string[]; suppliers: string[]; bills: string[] } | null;
};

export type ConnectorRow = {
  id: string;
  kind: string;
  name: string | null;
  status: "pending" | "active" | "unlinked";
  company: string | null;
  last_seen_at: string | null;
  last_sync_at: string | null;
  last_state: string | null;
  last_import_id: string | null;
  code_expires_at: string | null;
};

export type ConnectorList = { can_edit: boolean; connectors: ConnectorRow[] };

/** Where a connector on a builder's computer reaches the API. */
export const PUBLIC_API_URL = process.env.LEKHARA_PUBLIC_API_URL ?? BASE;

export type LegalInfo = {
  version: string;
  company_name: string;
  company_address: string;
  grievance_officer: string;
  grievance_email: string;
  close_after_days: number;
  log_days: number;
  sub_processors: { what: string; who: string }[];
};

export type AccessLog = {
  keep_days: number;
  events: { at: string; who: string | null; action: string; detail: string | null; ip: string | null }[];
};

export type ReviewQueue = {
  count: number;
  items: {
    project_id: string;
    project_name: string;
    kind: "bank" | "tally" | "sheet" | "mail" | "gst";
    title: string;
    detail: string;
    href: string;
    since: string;
  }[];
};

export type InboundItem = {
  id: string;
  filename: string;
  size: number;
  kind: string | null;
  status: "queued" | "done" | "review" | "ignored" | "failed";
  note: string | null;
  link: string | null;
  can_retry: boolean;
};

export type InboundMessage = {
  id: string;
  from_address: string;
  from_name: string | null;
  subject: string | null;
  received_at: string;
  trusted: boolean;
  status: "queued" | "held" | "done" | "rejected" | "failed";
  note: string | null;
  items: InboundItem[];
};

export type Inbound = {
  project_id: string;
  address: string;
  ready: boolean;
  can_edit: boolean;
  messages: InboundMessage[];
};

export type InboundSettings = {
  can_edit: boolean;
  senders: { id: string; address: string }[];
  passwords: { id: string; label: string; added_on: string }[];
};

export type HistoryEntry = {
  at: string;
  action: string;
  source: string;
  by: string;
  subject?: string | null;
  changes: FieldChange[];
};

export type CostLineRef = { id: string; code: string; name: string };

export type SupplierRow = {
  id: string;
  name: string;
  gstin: string | null;
  registered: boolean;
  pan: string | null;
  state: string | null;
  msme_category: string;
  msme_label: string;
  udyam_number: string | null;
  written_agreement: boolean;
  bills: number;
  unpaid: number;
};

export type BillRow = {
  id: string;
  supplier: { id: string; name: string; registered: boolean; msme: boolean };
  bill_no: string;
  bill_date: string;
  accepted_on: string;
  taxable_value: string;
  gst_amount: string | null;
  paid_on: string | null;
  cost_line: CostLineRef | null;
  is_cement: boolean;
  rcm_paid: boolean;
  excluded: boolean;
  source: string;
};

export type Purchases = {
  project_id: string;
  can_edit: boolean;
  bills: BillRow[];
  suppliers: SupplierRow[];
  cost_lines: CostLineRef[];
  totals: { taxable: string; gst: string; unpaid: number };
};

export type BillDetail = BillRow & {
  project_id: string;
  project_name: string;
  can_edit: boolean;
  can_delete: boolean;
  cost_lines: CostLineRef[];
  gst_is_cost: boolean;
  history: HistoryEntry[];
};

export type SupplierDetail = SupplierRow & {
  can_edit: boolean;
  can_delete: boolean;
  bill_list: (BillRow & { project: string | null })[];
  history: HistoryEntry[];
};

export type Commitments = {
  project_id: string;
  can_edit: boolean;
  cost_lines: CostLineRef[];
  commitments: {
    id: string;
    reference: string;
    description: string | null;
    amount: string;
    committed_on: string;
    cost_line: { id: string; code: string | null; name: string | null };
    supplier: string | null;
  }[];
  total: string;
};

export type BankStatementRow = {
  id: string;
  filename: string;
  bank: string | null;
  account: string | null;
  period_from: string | null;
  period_to: string | null;
  lines: number;
  status: "review" | "applied" | "undone";
  created_at: string;
};

export type BankStatementList = { can_import: boolean; statements: BankStatementRow[] };

export type BankLine = {
  key: string;
  on: string;
  narration: string;
  reference: string | null;
  channel: string | null;
  payer: string | null;
  debit: string | null;
  credit: string | null;
  balance: string | null;
  outcome: string;
  outcome_label: string;
  note: string;
  unit_id: string | null;
  unit_label: string | null;
  how: string | null;
  candidates: { id: string; label: string }[];
  loan: boolean;
  buyer_line: boolean;
  choice: string | null;
};

export type BankReview = BankStatementRow & {
  project_id: string;
  project_name: string;
  applied_at: string | null;
  role: "rera" | "collections" | null;
  buyers_pay_here: boolean;
  can_edit: boolean;
  can_place: boolean;
  can_apply: boolean;
  can_apply_rest: boolean;
  can_undo: boolean;
  opening: string | null;
  closing: string | null;
  reversed_order: boolean;
  columns: Record<string, string>;
  counts: Record<string, number>;
  totals: Record<string, string>;
  alerts: TallyAlert[];
  lines: BankLine[];
  units: { id: string; label: string; buyer: string | null }[];
};

export type TallyAlert = {
  level: "blocking" | "missing" | "info";
  code: string;
  title: string;
  detail: string;
  fix: string;
  items: string[];
};

export type TallyReview = {
  id: string;
  filename: string;
  status: "review" | "applied" | "undone";
  project_id: string;
  project_name: string;
  created_at: string;
  applied_at: string | null;
  can_edit: boolean;
  can_apply_rest: boolean;
  can_undo: boolean;
  source: string;
  source_label: string;
  company: string | null;
  period: { from: string | null; to: string | null };
  found: {
    masters: boolean;
    totals_only: boolean;
    groups: number;
    ledgers: number;
    ledger_kinds: Record<string, number>;
    cost_centres: number;
    stock_items: number;
    vouchers: number;
    voucher_kinds: Record<string, number>;
  };
  counts: {
    vendors_new: number;
    vendors_updated: number;
    bills_new: number;
    bills_known: number;
    bills_paid: number;
    receipts_new: number;
    receipts_known: number;
    receipts_waiting: number;
  };
  alerts: TallyAlert[];
  buyers: { ledger: string; total: string; count: number; suggestions: string[]; ignored: boolean }[];
  units: { id: string; label: string; buyer: string | null }[];
  cost_centres: string[];
  cost_centre: string | null;
  vendors: { name: string; gstin: string | null; registered: boolean; msme: string | null; existing: boolean; changes: string[]; bills: number }[];
  bills: { vendor: string; bill_no: string; bill_date: string; taxable_value: string; gst: string; paid_on: string | null; is_cement: boolean }[];
  receipts: { ledger: string; unit: string | null; amount: string; tds: string; received_on: string }[];
  money: TallyMoney;
  result: {
    vendors_added: string[];
    vendors_changed: unknown[];
    bills_added: string[];
    bills_paid: string[];
    receipts_added: string[];
  } | null;
};

export type TallyList = {
  can_import: boolean;
  imports: {
    id: string;
    filename: string;
    status: string;
    company: string | null;
    created_at: string;
    bills: number | null;
    receipts: number | null;
  }[];
};

export type CostLines = {
  can_edit: boolean;
  categories: Choice[];
  lines: {
    id: string;
    code: string;
    name: string;
    category: string;
    category_label: string;
    rera_head: string;
    original_budget: string;
    revised_budget: string;
    incurred: string | null;
    paid: string | null;
  }[];
};

export type TallyMoney = {
  counts: {
    incurred: string;
    paid: string;
    cost_entries: number;
    escrow: number;
    deposits: string;
    withdrawals: string;
    landowner_payments: number;
    unmapped_spend: string;
  };
  cost_ledgers: { ledger: string; target: string | null; source: string; total: string }[];
  bank_ledgers: { ledger: string; rera: boolean; source: string; total: string }[];
  landowner_ledgers: { ledger: string; target: string | null; source: string; total: string }[];
  cost_lines: { id: string; code: string; name: string }[];
  landowners: { id: string; name: string }[];
  party_ledgers: string[];
};

export type PaymentPlan = {
  can_edit: boolean;
  stages: {
    id: string;
    name: string;
    trigger: string;
    trigger_label: string;
    progress_pct: string | null;
    share_pct: string;
    demands: number;
  }[];
  total_pct: string;
  any_raised: boolean;
  templates: {
    key: string;
    label: string;
    stages: { name: string; trigger_label: string; progress_pct: string | null; share_pct: string }[];
  }[];
  triggers: Choice[];
};

export type Setup = {
  project_id: string;
  can_edit: boolean;
  summary: { done: number; total: number; next: string | null };
  items: {
    key: string;
    title: string;
    status: "done" | "partial" | "stale" | "missing";
    detail: string;
    unlocks: string;
    action: string;
    href: string;
  }[];
  details: {
    name: string;
    krera_registration: string;
    registered_on: string;
    possession_due_on: string | null;
    locality: string;
    city: string;
    spv_name: string;
    land_structure: string;
    gst_regime: string;
    escrow_bank: string | null;
    statutory_auditor_firm: string | null;
    development_rights_value: string | null;
    cess_paid: string | null;
    oc_status: string;
    oc_received_on: string | null;
    oc_reference: string | null;
    association_formed_on: string | null;
    common_areas_conveyed_on: string | null;
  };
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
    source_quality: "official" | "secondary" | "unsettled" | "unverified" | "lekhara_default";
    confirm_against: string;
    note: string;
  }[];
};

async function authHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  // Who is asking, for the access log Lekhara keeps (CERT-In asks for 180 days of it).
  const incoming = await headers();
  const ip = (incoming.get("x-forwarded-for") ?? incoming.get("x-real-ip") ?? "").split(",")[0].trim();
  const agent = incoming.get("user-agent") ?? "";
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(ip ? { "X-Lekhara-Client-IP": ip } : {}),
    ...(agent ? { "X-Lekhara-User-Agent": agent.slice(0, 300) } : {}),
  };
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: await authHeaders(),
  });
  if (response.status === 401) redirect("/login");
  if (response.status === 404 || response.status === 403) notFound();
  if (!response.ok) throw new Error(`Lekhara API ${response.status} on ${path}`);
  return response.json() as Promise<T>;
}

/** An invitation, read without signing in. Null once it has been used or has expired. */
export async function invitationInfo(token: string): Promise<InvitationInfo | null> {
  const response = await fetch(`${BASE}/invitations/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Lekhara API ${response.status} on an invitation`);
  return response.json() as Promise<InvitationInfo>;
}

/** A shared data room, opened without signing in. Null once the link has closed. */
export const VISITOR_COOKIE = "lekhara_visitor";

export async function sharedRoom(token: string, visitor?: string): Promise<SharedRoom | SharedGate | null> {
  const response = await fetch(`${BASE}/shared/${encodeURIComponent(token)}`, {
    cache: "no-store",
    headers: visitor ? { "X-Lekhara-Visitor": visitor } : {},
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Lekhara API ${response.status} on a shared room`);
  return response.json() as Promise<SharedRoom | SharedGate>;
}

/** Fetches a file from a shared data room, as the visitor who gave their name. */
export async function fetchSharedFile(path: string, visitor?: string): Promise<Response> {
  return fetch(`${BASE}${path}`, { cache: "no-store", headers: visitor ? { "X-Lekhara-Visitor": visitor } : {} });
}

/** Fetches a file from the API for a route handler to pass on to the browser. */
export async function fetchFile(path: string, signedIn: boolean): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: signedIn ? await authHeaders() : {},
  });
}

/** Sends a multipart form, for uploads. */
export async function sendForm<T>(path: string, body: FormData): Promise<SendResult<T>> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: await authHeaders(),
    body,
    cache: "no-store",
  });
  if (response.ok) return { ok: true, data: (await response.json()) as T };
  if (response.status === 401) return { ok: false, error: "Your session has ended. Sign in again." };
  if (response.status === 413) return { ok: false, error: "The file is too large." };
  try {
    const detail = (await response.json()).detail;
    return { ok: false, error: typeof detail === "string" ? detail : "Check the details and try again." };
  } catch {
    return { ok: false, error: "Something went wrong. Try again." };
  }
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
    return { ok: false, error: "Lekhara could not complete that. Try again." };
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

export type LandownerDetail = {
  id: string;
  project_id: string;
  project_name: string;
  can_edit: boolean;
  name: string;
  pan: string | null;
  share_type: string;
  share_pct: string;
  refundable_deposit: string;
  totals: { consideration: string; tds: string; deposits: string; tds_short: string };
  payments: {
    id: string;
    paid_on: string;
    amount: string;
    tds_deducted: string;
    deposit: boolean;
    reference: string | null;
    source: "typed" | "import" | "tally";
    tds_short: string | null;
  }[];
  history: HistoryEntry[];
};

export type ApprovalStatus = "lapsed" | "lapsing" | "granted" | "applied" | "to_apply";

export type ApprovalRow = {
  id: string;
  name: string;
  authority: string | null;
  reference: string | null;
  applied_on: string | null;
  granted_on: string | null;
  valid_until: string | null;
  note: string | null;
  status: ApprovalStatus;
  status_text: string;
  days_left: number | null;
  history: HistoryEntry[];
};

export type Approvals = {
  project_id: string;
  can_edit: boolean;
  approvals: ApprovalRow[];
  counts: Record<ApprovalStatus, number>;
  standard_missing: number;
};

export type FilingPeriod = {
  period_end: string;
  period_start: string;
  due_on: string;
  state: "filed" | "late" | "due" | "open";
  filing: { id: string; filed_on: string; reference: string | null; history: HistoryEntry[] } | null;
};

export type Krera = {
  project_id: string;
  can_edit: boolean;
  registered_on: string;
  quarters: FilingPeriod[];
  audits: FilingPeriod[];
  qpr_due_days: number;
  audit_months: number;
};

export type TableEdit = {
  project_id: string;
  project_name: string;
  kind: string;
  title: string;
  page: number;
  pages: number;
  total: number;
  fields: { key: string; label: string; kind: string; locked: boolean; choices: { value: string; label: string }[] }[];
  rows: string[][];
};

export const api = {
  me: () => get<Me>("/auth/me"),
  today: () => get<Today>("/today"),
  projects: () => get<ProjectCard[]>("/projects"),
  project: (id: string) => get<ProjectDetail>(`/projects/${id}`),
  money: (id: string) => get<{ summary: MoneySummary; lines: MoneyLine[] }>(`/projects/${id}/money`),
  escrow: (id: string) => get<Escrow>(`/projects/${id}/escrow`),
  collections: (id: string) => get<Collections>(`/projects/${id}/collections`),
  handover: (id: string) => get<Handover>(`/projects/${id}/handover`),
  unitHandover: (unitId: string) => get<UnitHandover>(`/units/${unitId}/handover`),
  possessionLetter: (unitId: string) => get<PossessionLetter>(`/units/${unitId}/possession-letter`),
  disputes: (id: string) => get<Disputes>(`/projects/${id}/disputes`),
  case: (id: string) => get<CaseDetail>(`/cases/${id}`),
  documents: (id: string) => get<DocumentsView>(`/projects/${id}/documents`),
  searchDocuments: (id: string, q: string) =>
    get<SearchResults>(`/projects/${id}/documents/search?q=${encodeURIComponent(q)}`),
  document: (id: string) => get<DocumentDetail>(`/documents/${id}`),
  linkedDocuments: (linkType: string, linkId: string) =>
    get<LinkedDocuments>(
      `/documents?link_type=${encodeURIComponent(linkType)}&link_id=${encodeURIComponent(linkId)}`,
    ),
  room: (id: string) => get<RoomDetail>(`/rooms/${id}`),
  firm: () => get<Firm>("/organization"),
  unit: (id: string) => get<UnitDetail>(`/units/${id}`),
  imports: (projectId: string) => get<ImportList>(`/projects/${projectId}/imports`),
  importBatch: (id: string) => get<ImportBatch>(`/imports/${id}`),
  tally: (id: string) => get<TallyReview>(`/tally/${id}`),
  bankStatement: (id: string) => get<BankReview>(`/bank-statements/${id}`),
  purchases: (projectId: string) => get<Purchases>(`/projects/${projectId}/purchases`),
  inbound: (projectId: string) => get<Inbound>(`/projects/${projectId}/inbound`),
  review: () => get<ReviewQueue>("/review"),
  legal: () => get<LegalInfo>("/legal"),
  accessLog: () => get<AccessLog>("/organization/access-log"),
  gstImports: (projectId: string) => get<GstList>(`/projects/${projectId}/gst`),
  gst: (id: string) => get<GstReview>(`/gst/${id}`),
  connectors: (projectId: string) => get<ConnectorList>(`/projects/${projectId}/connectors`),
  inboundSettings: () => get<InboundSettings>("/organization/inbound"),
  bill: (id: string) => get<BillDetail>(`/bills/${id}`),
  supplier: (id: string) => get<SupplierDetail>(`/suppliers/${id}`),
  commitments: (projectId: string) => get<Commitments>(`/projects/${projectId}/commitments`),
  bankStatements: (projectId: string) => get<BankStatementList>(`/projects/${projectId}/bank-statements`),
  costLines: (projectId: string) => get<CostLines>(`/projects/${projectId}/cost-lines`),
  paymentPlan: (projectId: string) => get<PaymentPlan>(`/projects/${projectId}/payment-plan`),
  setup: (projectId: string) => get<Setup>(`/projects/${projectId}/setup`),
  tallyImports: (projectId: string) => get<TallyList>(`/projects/${projectId}/tally`),
  demand: (id: string) => get<DemandLetter>(`/demands/${id}`),
  tax: (id: string) => get<Tax>(`/projects/${id}/tax`),
  units: (id: string) => get<Units>(`/projects/${id}/units`),
  withdrawal: (id: string) => get<Withdrawal>(`/withdrawals/${id}`),
  rules: () => get<Rules>("/rules"),
  landowner: (id: string) => get<LandownerDetail>(`/landowners/${id}`),
  approvals: (projectId: string) => get<Approvals>(`/projects/${projectId}/approvals`),
  krera: (projectId: string) => get<Krera>(`/projects/${projectId}/krera`),
  table: (projectId: string, kind: string, page: number) =>
    get<TableEdit>(`/projects/${projectId}/table/${kind}?page=${page}`),
};

export function areaHref(o: Obligation): string {
  if (o.link) return o.link;
  const base = `/projects/${o.project_id}`;
  switch (o.area) {
    case "escrow":
      return `${base}/escrow`;
    case "collections":
      return `${base}/collections`;
    case "handover":
      return `${base}/handover`;
    case "disputes":
      return `${base}/disputes`;
    case "documents":
      return `${base}/documents`;
    case "tax":
      return `${base}/tax`;
    case "units":
      return `${base}/units`;
    case "approvals":
      return `${base}/approvals`;
    case "krera":
      return `${base}/krera`;
    default:
      return base;
  }
}
