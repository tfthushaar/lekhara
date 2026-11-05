import Link from "next/link";
import { Suspense } from "react";

import { type CostLine, api } from "@/lib/api";
import { inr, inrFull } from "@/lib/format";

export default function CostSheetPage({ params, searchParams }: PageProps<"/projects/[id]/sales/cost-sheet/[unit]">) {
  return (
    <Suspense fallback={<p className="loading">Working out the cost sheet</p>}>
      <CostSheetView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

function Lines({ lines }: { lines: CostLine[] }) {
  return (
    <>
      {lines.map((line) => (
        <tr key={line.label}>
          <td>
            {line.label}
            {line.detail ? <span className="small muted">{` ${line.detail}`}</span> : null}
          </td>
          <td className="right num">{inrFull(line.amount)}</td>
        </tr>
      ))}
    </>
  );
}

async function CostSheetView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; unit: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id, unit } = await params;
  const query = await searchParams;
  const chosen = ([] as string[]).concat(query.plc ?? []);
  const discount = typeof query.discount === "string" ? query.discount : "";
  const asked = new URLSearchParams();
  for (const name of chosen) asked.append("plc", name);
  if (discount) asked.set("discount", discount);
  const [c, s] = await Promise.all([api.costSheet(id, unit, asked.toString()), api.sales(id)]);
  const plcNames = Object.keys(s.price_list?.plc ?? {});

  return (
    <>
      <p className="crumb">
        <Link href={`/projects/${id}/sales`}>Sales</Link>
      </p>
      <section>
        <div className="section-head">
          <h2>{`Cost sheet for ${c.unit}`}</h2>
          <p>{`${c.tower}, ${c.carpet_area_sqft} sq ft carpet area. ${inr(c.rate_per_sqft)} a sq ft all in, before GST.`}</p>
        </div>

        <form method="get" className="filters">
          {plcNames.map((name) => (
            <label key={name} className="field-check">
              <input type="checkbox" name="plc" value={name} defaultChecked={chosen.includes(name)} /> {name}
            </label>
          ))}
          <div className="field">
            <label htmlFor="cs-discount">Discount a sq ft</label>
            <input id="cs-discount" name="discount" defaultValue={discount} inputMode="decimal" />
          </div>
          <button type="submit" className="button button-secondary">
            Work it out again
          </button>
        </form>

        {c.below_guidance ? (
          <p className="notice" style={{ marginTop: 12 }}>
            {`This price is more than 10% below the guidance value of ${inr(c.guidance_value)}. The income tax department would count the guidance value as your sale price (s.43CA), which could cost about ${inr(c.guidance_tax)} more in tax.`}
          </p>
        ) : null}

        <table className="table" style={{ marginTop: 16, maxWidth: 760 }}>
          <tbody>
            <Lines lines={c.agreement_lines} />
            <tr>
              <td className="strong">Agreement value</td>
              <td className="right num strong">{inrFull(c.agreement_value)}</td>
            </tr>
            <tr>
              <td>{`GST at ${c.gst_rate}%`}</td>
              <td className="right num">{inrFull(c.gst)}</td>
            </tr>
          </tbody>
        </table>

        {c.handover_lines.length > 0 ? (
          <>
            <h3 style={{ marginTop: 20 }}>Paid at handover</h3>
            <table className="table" style={{ maxWidth: 760 }}>
              <tbody>
                <Lines lines={c.handover_lines} />
              </tbody>
            </table>
          </>
        ) : null}

        <h3 style={{ marginTop: 20 }}>Paid to the government</h3>
        <table className="table" style={{ maxWidth: 760 }}>
          <tbody>
            <tr>
              <td>Stamp duty on the agreement for sale</td>
              <td className="right num">{inrFull(c.agreement_stamp_duty)}</td>
            </tr>
            <tr>
              <td>Stamp duty on the sale deed</td>
              <td className="right num">{inrFull(c.stamp_duty)}</td>
            </tr>
            <tr>
              <td>Cess</td>
              <td className="right num">{inrFull(c.cess)}</td>
            </tr>
            <tr>
              <td>Registration fee</td>
              <td className="right num">{inrFull(c.registration_fee)}</td>
            </tr>
            <tr>
              <td className="strong">All in</td>
              <td className="right num strong">{inrFull(c.total)}</td>
            </tr>
          </tbody>
        </table>

        <p className="small muted" style={{ marginTop: 12, maxWidth: 760 }}>
          {Number(c.tds) > 0
            ? `The buyer deducts TDS of ${c.tds_rate}% (${inr(c.tds)} in all) from what they pay you and gives you Form 16B. `
            : ""}
          Stamp duty and the registration fee are worked out at today&apos;s rates; the sub-registrar&apos;s figure on the day
          is final.
        </p>
        <p className="chips">
          <a href={`/download/projects/${id}/units/${unit}/cost-sheet.pdf${asked.size ? `?${asked}` : ""}`} className="button">
            Print for the buyer
          </a>
        </p>
      </section>
    </>
  );
}
