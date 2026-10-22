import { type NextRequest } from "next/server";

import { fetchFile } from "@/lib/api";

const ALLOWED = [
  /^projects\/[A-Za-z0-9_-]+\/exports\/[a-z_]+\.(xlsx|csv)$/,
  /^imports\/templates\/[a-z_]+\.(xlsx|csv)$/,
  /^organization\/export$/,
  /^withdrawals\/[A-Za-z0-9_-]+\/pack\.pdf$/,
  /^projects\/[A-Za-z0-9_-]+\/packs\/(qpr|audit)\/\d{4}-\d{2}-\d{2}\.(pdf|xlsx)$/,
];
const PASS_ON = ["content-type", "content-disposition", "content-length"];

/** Hands an export, the whole-workspace export, an import template or a pack to the browser, for the signed-in person. */
export async function GET(request: NextRequest, ctx: RouteContext<"/download/[...path]">) {
  const { path } = await ctx.params;
  const joined = path.map(decodeURIComponent).join("/");
  if (!ALLOWED.some((pattern) => pattern.test(joined))) return new Response("Not found", { status: 404 });
  const response = await fetchFile(`/${joined}`, true);
  if (response.status === 401) return Response.redirect(new URL("/login", request.url), 307);
  if (response.status === 428) {
    // Downloading everything asks the person to confirm it is them, then try again.
    return Response.redirect(new URL("/confirm?next=%2Fsettings", request.url), 307);
  }
  if (!response.ok) return new Response("Not found", { status: 404 });
  const headers = new Headers({ "Cache-Control": "private, no-store" });
  for (const name of PASS_ON) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(response.body, { headers });
}
