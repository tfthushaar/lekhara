import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Barcode } from "@/components/originals";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Labels for originals" };

/** A sheet of labels to print and stick on the folders of originals. */
export default function LabelsPage({ params }: PageProps<"/projects/[id]/originals/labels">) {
  return (
    <Suspense fallback={<p className="loading">Making the labels</p>}>
      <Labels params={params} />
    </Suspense>
  );
}

async function Labels({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await api.originals(id);
  return (
    <>
      <div className="page-head no-print">
        <div>
          <h1>Labels for originals</h1>
          <p>
            Print this page, cut the labels apart and stick each on its folder.{" "}
            <Link href={`/projects/${id}/documents`}>Back to documents</Link>
          </p>
        </div>
      </div>
      <div className="label-sheet">
        {r.originals.map((o) => (
          <div key={o.id} className="label">
            <Barcode number={o.number} />
            <p className="label-number">{o.number}</p>
            <p className="label-title">{o.title}</p>
          </div>
        ))}
      </div>
    </>
  );
}
