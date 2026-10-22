import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { findOriginal } from "@/lib/api";

export const metadata: Metadata = { title: "Find an original" };

/** Where a scanned label lands: the original's own page, or why there is none. */
export default function FindOriginal({ searchParams }: PageProps<"/originals">) {
  return (
    <Suspense fallback={<p className="loading">Finding it</p>}>
      <Found searchParams={searchParams} />
    </Suspense>
  );
}

async function Found({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const number = typeof sp.n === "string" ? sp.n.trim() : "";
  if (!number) return <p className="empty">Scan a label, or type an original&apos;s number, on a project&apos;s Documents tab.</p>;
  const found = await findOriginal(number);
  if ("id" in found) redirect(`/originals/${found.id}`);
  return <p className="empty">{found.error}</p>;
}
