import { type NextRequest } from "next/server";

const BASE = (process.env.LEKHARA_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

/** The public demo's nightly reset, called by the Vercel Cron job in vercel.json. The API checks
 * the cron secret the request carries; this only passes it on. */
export async function GET(request: NextRequest) {
  const response = await fetch(`${BASE}/demo/reset`, {
    method: "POST",
    cache: "no-store",
    headers: { Authorization: request.headers.get("authorization") ?? "" },
  });
  return new Response(response.ok ? "Reset" : "Not reset", { status: response.status });
}
