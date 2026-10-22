import { api } from "@/lib/api";

/** Where to report a security weakness, in the standard form (RFC 9116). */
export async function GET(request: Request) {
  const info = await api.legal();
  const site = new URL(request.url).origin;
  const expires = new Date(Date.now() + 180 * 24 * 60 * 60 * 1000).toISOString();
  const body = [
    `Contact: mailto:${info.contact_email}`,
    `Expires: ${expires}`,
    "Preferred-Languages: en",
    `Policy: ${site}/security`,
    `Canonical: ${site}/.well-known/security.txt`,
    "",
  ].join("\n");
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "public, max-age=86400" } });
}
