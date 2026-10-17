import { type NextRequest } from "next/server";

import { fetchFile } from "@/lib/api";

const PASS_ON = ["content-type", "content-disposition", "content-length", "x-content-type-options"];

/** Hands a vault file to the browser. The API checks the signed-in person's access. */
export async function GET(request: NextRequest, ctx: RouteContext<"/files/[id]">) {
  const { id } = await ctx.params;
  const inline = request.nextUrl.searchParams.get("inline") === "1";
  const response = await fetchFile(
    `/documents/${encodeURIComponent(id)}/file${inline ? "?inline=true" : ""}`,
    true,
  );
  if (response.status === 401) return Response.redirect(new URL("/login", request.url), 307);
  if (!response.ok) return new Response("Not found", { status: 404 });
  const headers = new Headers({ "Cache-Control": "private, no-store" });
  for (const name of PASS_ON) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(response.body, { headers });
}
