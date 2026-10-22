import type { Metadata } from "next";
import { Suspense } from "react";

import { checkCertificate } from "@/lib/api";

export const metadata: Metadata = {
  title: "Check a certificate",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function CheckPage({ searchParams }: PageProps<"/check">) {
  return (
    <main className="main">
      <div className="shared-head">
        <span className="wordmark">Lekhara</span>
      </div>
      <div className="page-head">
        <div>
          <h1>Check a certificate</h1>
          <p>For banks and anyone else holding a certificate signed in Lekhara</p>
        </div>
      </div>
      <p style={{ maxWidth: 640, marginBottom: 16 }}>
        A certificate signed in Lekhara ends with a signing record page that carries a check code. Enter it to see what
        was signed, by whom and when. If a figure in the document you hold differs from what is shown here, the
        document was changed after it was signed.
      </p>
      <form action="/check" method="get" className="inline-form" style={{ marginBottom: 32 }}>
        <div className="field" style={{ maxWidth: 360 }}>
          <label htmlFor="check-code">Check code</label>
          <input id="check-code" name="code" required placeholder="ABCD-EFGH-JKLM-NPQR" autoComplete="off" />
        </div>
        <button type="submit" className="button">
          Check
        </button>
      </form>
      <Suspense fallback={<p className="loading">Checking</p>}>
        <Result searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Result({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const code = typeof sp.code === "string" ? sp.code.trim() : "";
  if (!code) return null;
  const result = await checkCertificate(code);
  if ("error" in result) {
    return (
      <p className="notice" style={{ maxWidth: 640 }}>
        {result.error}
      </p>
    );
  }
  const c = result.found;
  const rows: [string, string][] = [
    ["Certificate", c.certificate],
    ["Project", `${c.project}, K-RERA registration ${c.krera_registration}`],
    ["Promoter", c.promoter],
    ["Withdrawal requested", c.amount_requested],
    ["Signed by", `${c.signer_name}, ${c.signer_firm}`],
    ["Dated", c.issued_on],
    ["Signed in Lekhara at", c.signed_at],
  ];
  return (
    <section className="section">
      <p className="status-line">
        {c.unchanged
          ? `Code ${c.code}: unchanged since it was signed.`
          : `Code ${c.code}: changed in Lekhara since it was signed. Do not rely on it; ask the promoter.`}
      </p>
      <table className="table" style={{ maxWidth: 820 }}>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <th style={{ width: 220 }}>{label}</th>
              <td>{value}</td>
            </tr>
          ))}
          <tr>
            <th>What was certified</th>
            <td>{c.statement}</td>
          </tr>
          <tr>
            <th>Fingerprint (SHA-256)</th>
            <td className="mono small" style={{ wordBreak: "break-all" }}>
              {c.fingerprint}
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}
