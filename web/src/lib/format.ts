const CRORE = 10_000_000;
const LAKH = 100_000;

/** Rupees in the way Indian builders say them: 6.40 crore, 9.40 lakh, 25,000. */
export function inr(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  const n = Number(value);
  const sign = n < 0 ? "-" : "";
  const a = Math.abs(n);
  if (a >= CRORE) return `${sign}₹${(a / CRORE).toFixed(2)} crore`;
  if (a >= LAKH) return `${sign}₹${(a / LAKH).toFixed(2)} lakh`;
  return `${sign}₹${a.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

/** Rupees in full, with Indian digit grouping: 6,40,00,000. */
export function inrFull(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function pct(value: string | null | undefined): string {
  if (value === null || value === undefined) return "Not certified";
  const n = Number(value);
  return `${Number.isInteger(n) ? n : Number(n.toFixed(2))}%`;
}

function parse(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  return parse(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** A moment the API recorded, which it keeps in UTC, as the time in India: 19 Oct 2026, 2:05 pm. */
export function moment(iso: string | null | undefined): string {
  if (!iso) return "";
  const at = new Date(/(z|[+-]\d\d:\d\d)$/i.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

/** "today", "in 5 days", "3 days ago". */
export function relative(iso: string | null | undefined, today: string): string {
  if (!iso) return "";
  const diff = Math.round((parse(iso).getTime() - parse(today).getTime()) / 86_400_000);
  if (diff === 0) return "today";
  if (diff === 1) return "tomorrow";
  if (diff === -1) return "yesterday";
  return diff > 0 ? `in ${diff} days` : `${-diff} days ago`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
