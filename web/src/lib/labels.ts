import type { RequestStatus, Rules } from "@/lib/api";

export const REQUEST_STATUS: Record<RequestStatus, string> = {
  awaiting_signatures: "Waiting for signatures",
  ready: "Ready for the bank",
  submitted: "With the bank",
  released: "Released",
  rejected: "Rejected",
};

export const SOURCE_QUALITY: Record<Rules["rules"][number]["source_quality"], string> = {
  official: "Official",
  secondary: "Secondary",
  unsettled: "Unsettled",
  unverified: "To confirm",
  horus_default: "Horus setting",
};
