import { type NextRequest } from "next/server";

import { VISITOR_COOKIE, fetchSharedFile } from "@/lib/api";

const PASS_ON = ["content-type", "content-disposition", "content-length", "x-content-type-options"];

/** Hands a file from a shared data room to someone outside the company. The link's token is
 * the permission; the API refuses it once the room has closed. */
export async function GET(request: NextRequest, ctx: RouteContext<"/shared/[token]/files/[docId]">) {
  const { token, docId } = await ctx.params;
  const inline = request.nextUrl.searchParams.get("inline") === "1";
  const response = await fetchSharedFile(
    `/shared/${encodeURIComponent(token)}/documents/${encodeURIComponent(docId)}/file${inline ? "?inline=true" : ""}`,
    request.cookies.get(VISITOR_COOKIE)?.value,
  );
  if (response.status === 403) return Response.redirect(new URL(`/shared/${encodeURIComponent(token)}`, request.url), 303);
  if (!response.ok) return new Response("This link has expired or has been withdrawn.", { status: 404 });
  const headers = new Headers({ "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" });
  for (const name of PASS_ON) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(response.body, { headers });
}
