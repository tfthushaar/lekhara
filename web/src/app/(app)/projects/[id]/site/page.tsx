import { Suspense } from "react";

import { saveDailyReport } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type DailyReportRow, type SiteView, api } from "@/lib/api";
import { day } from "@/lib/format";

export default function SitePage({ params }: PageProps<"/projects/[id]/site">) {
  return (
    <Suspense fallback={<p className="loading">Loading the site</p>}>
      <SiteViewPage params={params} />
    </Suspense>
  );
}

const USED_ROWS = 3;

function ReportForm({ s, projectId }: { s: SiteView; projectId: string }) {
  const r = s.today_report;
  return (
    <ActionForm action={saveDailyReport.bind(null, projectId)} label={r ? "Save the changes" : "Save today's report"} pendingLabel="Saving">
      {r?.photos.length ? (
        <div className="photos" style={{ marginBottom: 16 }}>
          {r.photos.map((p) => (
            <a key={p} href={`/download/daily-reports/${r.id}/photos/${p}`} target="_blank" rel="noreferrer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/download/daily-reports/${r.id}/photos/${p}`} alt="Today's site photo" loading="lazy" />
            </a>
          ))}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="dr-work">What work was done today?</label>
        <textarea id="dr-work" name="work_done" rows={3} required defaultValue={r?.work_done ?? ""} placeholder="Slab cast on the 9th floor, Tower A" />
      </div>
      <div className="field" style={{ maxWidth: 240 }}>
        <label htmlFor="dr-workers">Workers on site</label>
        <input id="dr-workers" name="workers" inputMode="numeric" defaultValue={r?.workers ?? ""} />
      </div>
      <div className="field">
        <span>Material used</span>
        <datalist id="dr-items">
          {s.items.map((i) => (
            <option key={i.name} value={i.name} />
          ))}
        </datalist>
        {Array.from({ length: USED_ROWS }, (_, i) => {
          const used = r?.used[i];
          return (
            <div key={i} className="pair">
              <input name={`used_item_${i}`} list="dr-items" aria-label={`Material ${i + 1}`} placeholder={i === 0 ? "Cement" : ""} defaultValue={used?.item ?? ""} />
              <input name={`used_qty_${i}`} inputMode="decimal" aria-label={`How much ${i + 1}`} placeholder="How much" defaultValue={used?.quantity ?? ""} />
            </div>
          );
        })}
      </div>
      <div className="field">
        <label htmlFor="dr-photos">{r?.photos.length ? `Add more photos (${r.photos.length} so far)` : "Photos"}</label>
        <input id="dr-photos" name="photos" type="file" accept="image/*" capture="environment" multiple />
      </div>
      <details className="disclosure">
        <summary>Any problems?</summary>
        <div className="field">
          <label htmlFor="dr-issues">What held things up</label>
          <textarea id="dr-issues" name="issues" rows={2} defaultValue={r?.issues ?? ""} placeholder="Ready-mix came two hours late" />
        </div>
      </details>
    </ActionForm>
  );
}

function Report({ r }: { r: DailyReportRow }) {
  return (
    <li className="row row-1">
      <div>
        <p className="row-title">{day(r.on)}</p>
        <p style={{ marginTop: 4 }}>{r.work_done}</p>
        <p className="row-meta">
          {[r.workers ? `${r.workers} workers` : null, r.used.map((u) => `${u.quantity} ${u.unit} ${u.item.toLowerCase()}`).join(", ") || null, r.by]
            .filter(Boolean)
            .join(". ")}
        </p>
        {r.issues ? <p className="row-meta">{`Problem: ${r.issues}`}</p> : null}
        {r.photos.length ? (
          <div className="photos">
            {r.photos.map((p) => (
              <a key={p} href={`/download/daily-reports/${r.id}/photos/${p}`} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`/download/daily-reports/${r.id}/photos/${p}`} alt={`Site photo, ${day(r.on)}`} loading="lazy" />
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </li>
  );
}

async function SiteViewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await api.site(id);
  return (
    <>
      <section>
        <div className="section-head">
          <h2>{`Today, ${day(s.today)}`}</h2>
          {s.today_report ? <p>Saved. You can change it until the day ends.</p> : null}
        </div>
        {s.can_report ? <ReportForm s={s} projectId={id} /> : s.today_report ? <ul className="rows"><Report r={s.today_report} /></ul> : <p className="empty">No report yet today.</p>}
        {s.missed.length && s.can_report ? (
          <p className="small muted" style={{ marginTop: 12 }}>{`No report for ${s.missed.map((d) => day(d)).join(", ")}.`}</p>
        ) : null}
      </section>
      {s.reports.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Earlier days</h2>
          </div>
          <ul className="rows">
            {s.reports.slice(0, 3).map((r) => (
              <Report key={r.id} r={r} />
            ))}
          </ul>
          {s.reports.length > 3 ? (
            <details className="disclosure">
              <summary>{`${s.reports.length - 3} more days`}</summary>
              <ul className="rows">
                {s.reports.slice(3).map((r) => (
                  <Report key={r.id} r={r} />
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
