import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { PrintButton } from "@/components/print-button";
import { api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Demand letter" };

export default function DemandPage({ params }: PageProps<"/demands/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Preparing the letter</p>}>
      <Letter params={params} />
    </Suspense>
  );
}

async function Letter({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const letter = await api.demand(id);
  return (
    <>
      <div className="page-head no-print">
        <div>
          <p className="crumb">
            <Link href={`/projects/${letter.project_id}/collections`}>Collections</Link>
          </p>
          <h1>Demand letter</h1>
          <p>{letter.note}</p>
        </div>
        <PrintButton />
      </div>

      <article className="letter">
        <header className="letter-head">
          <p className="strong">{letter.from}</p>
          <p>{letter.project}</p>
          <p className="small muted">K-RERA registration {letter.krera_registration}</p>
        </header>
        <p>{day(letter.date)}</p>
        <p>
          To {letter.to}
          <br />
          Unit {letter.unit}
        </p>
        <p className="strong">{letter.subject}</p>
        <p>Dear {letter.to},</p>
        {letter.paragraphs.slice(0, 2).map((p) => (
          <p key={p}>{p}</p>
        ))}
        <ul className="calc">
          {letter.lines.map((line, i) => (
            <li key={line.label} className={i === letter.lines.length - 1 ? "calc-total" : undefined}>
              <span>{line.label}</span>
              <span className="num">{line.value}</span>
            </li>
          ))}
        </ul>
        <p className="strong">Please pay by {day(letter.due_on)}.</p>
        {letter.paragraphs.slice(2).map((p) => (
          <p key={p}>{p}</p>
        ))}
        <p>
          Yours faithfully,
          <br />
          {letter.from}
        </p>
      </article>
    </>
  );
}
