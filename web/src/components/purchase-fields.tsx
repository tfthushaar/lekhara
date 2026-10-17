import type { BillRow, CostLineRef, SupplierRow } from "@/lib/api";

type Choice = { value: string; label: string };

const MSME: Choice[] = [
  { value: "none", label: "Not MSME" },
  { value: "micro", label: "Micro" },
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
];

function YesNo({ id, name, label, value }: { id: string; name: string; label: string; value: boolean }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} name={name} defaultValue={value ? "yes" : "no"}>
        <option value="no">No</option>
        <option value="yes">Yes</option>
      </select>
    </div>
  );
}

function CostLineSelect({
  id,
  lines,
  value,
  required = false,
  blank = "None: the cost comes from Tally",
}: {
  id: string;
  lines: CostLineRef[];
  value: string | null | undefined;
  required?: boolean;
  blank?: string;
}) {
  return (
    <select id={id} name="cost_line" defaultValue={value ?? ""} required={required}>
      <option value="">{required ? "Choose the cost line" : blank}</option>
      {lines.map((l) => (
        <option key={l.id} value={l.code}>{`${l.code}, ${l.name}`}</option>
      ))}
    </select>
  );
}

export function BillFields({
  prefix,
  lines,
  suppliers,
  bill,
}: {
  prefix: string;
  lines: CostLineRef[];
  suppliers: { name: string }[];
  bill?: BillRow;
}) {
  return (
    <>
      <div className="field-grid">
        <div className="field">
          <label htmlFor={`${prefix}-supplier`}>Supplier</label>
          <input
            id={`${prefix}-supplier`}
            name="supplier"
            list={`${prefix}-suppliers`}
            defaultValue={bill?.supplier.name ?? ""}
            placeholder="Name or GSTIN"
            required
          />
          <datalist id={`${prefix}-suppliers`}>
            {suppliers.map((s) => (
              <option key={s.name} value={s.name} />
            ))}
          </datalist>
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-no`}>Bill number</label>
          <input id={`${prefix}-no`} name="bill_no" defaultValue={bill?.bill_no ?? ""} required />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-date`}>Bill date</label>
          <input id={`${prefix}-date`} name="bill_date" type="date" defaultValue={bill?.bill_date ?? ""} required />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-taxable`}>Taxable value (rupees)</label>
          <input id={`${prefix}-taxable`} name="taxable_value" inputMode="decimal" defaultValue={bill?.taxable_value ?? ""} required />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-gst`}>GST (rupees)</label>
          <input id={`${prefix}-gst`} name="gst_amount" inputMode="decimal" defaultValue={bill?.gst_amount ?? ""} />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-accepted`}>Accepted on</label>
          <input id={`${prefix}-accepted`} name="accepted_on" type="date" defaultValue={bill?.accepted_on ?? ""} />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-paid`}>Paid on</label>
          <input id={`${prefix}-paid`} name="paid_on" type="date" defaultValue={bill?.paid_on ?? ""} />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-line`}>Cost line</label>
          <CostLineSelect id={`${prefix}-line`} lines={lines} value={bill?.cost_line?.code} />
        </div>
      </div>
      <div className="field-grid">
        <YesNo id={`${prefix}-cement`} name="is_cement" label="Cement" value={bill?.is_cement ?? false} />
        <YesNo id={`${prefix}-rcm`} name="rcm_paid" label="Reverse charge paid" value={bill?.rcm_paid ?? false} />
        <YesNo id={`${prefix}-excluded`} name="excluded" label="Leave out of the 80% test" value={bill?.excluded ?? false} />
      </div>
      <p className="small muted" style={{ margin: "0 0 12px", maxWidth: 720 }}>
        The acceptance date starts the MSME clock; the bill date is used if it is blank. With a cost line, the bill counts as
        cost incurred, and as paid once paid; leave it blank when your costs come from Tally, so nothing counts twice.
      </p>
    </>
  );
}

export function SupplierFields({ prefix, supplier }: { prefix: string; supplier?: SupplierRow }) {
  return (
    <>
      <div className="field-grid">
        <div className="field">
          <label htmlFor={`${prefix}-name`}>Name</label>
          <input id={`${prefix}-name`} name="name" defaultValue={supplier?.name ?? ""} required />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-gstin`}>GSTIN</label>
          <input id={`${prefix}-gstin`} name="gstin" defaultValue={supplier?.gstin ?? ""} placeholder="Blank if not registered" />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-pan`}>PAN</label>
          <input id={`${prefix}-pan`} name="pan" defaultValue={supplier?.pan ?? ""} placeholder="From the GSTIN if blank" />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-state`}>State</label>
          <input id={`${prefix}-state`} name="state" defaultValue={supplier?.state ?? ""} placeholder="From the GSTIN if blank" />
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-msme`}>MSME category</label>
          <select id={`${prefix}-msme`} name="msme_category" defaultValue={supplier?.msme_category ?? "none"}>
            {MSME.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-udyam`}>Udyam number</label>
          <input id={`${prefix}-udyam`} name="udyam_number" defaultValue={supplier?.udyam_number ?? ""} />
        </div>
        <YesNo
          id={`${prefix}-agreement`}
          name="written_agreement"
          label="Written agreement on payment terms"
          value={supplier?.written_agreement ?? true}
        />
      </div>
      <p className="small muted" style={{ margin: "0 0 12px", maxWidth: 720 }}>
        Micro and small suppliers must be paid within 45 days of acceptance, or 15 without a written agreement, for the
        payment to be deductible.
      </p>
    </>
  );
}

export function CommitmentFields({
  prefix,
  lines,
  suppliers,
  c,
}: {
  prefix: string;
  lines: CostLineRef[];
  suppliers: { name: string }[];
  c?: { reference: string; cost_line: { code: string | null }; amount: string; committed_on: string; supplier: string | null; description: string | null };
}) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-ref`}>Order number</label>
        <input id={`${prefix}-ref`} name="reference" defaultValue={c?.reference ?? ""} required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-line`}>Cost line</label>
        <CostLineSelect id={`${prefix}-line`} lines={lines} value={c?.cost_line.code} required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-amount`}>Amount (rupees, before GST)</label>
        <input id={`${prefix}-amount`} name="amount" inputMode="decimal" defaultValue={c?.amount ?? ""} required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-date`}>Ordered on</label>
        <input id={`${prefix}-date`} name="committed_on" type="date" defaultValue={c?.committed_on ?? ""} required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-supplier`}>Supplier</label>
        <input id={`${prefix}-supplier`} name="supplier" list={`${prefix}-suppliers`} defaultValue={c?.supplier ?? ""} />
        <datalist id={`${prefix}-suppliers`}>
          {suppliers.map((s) => (
            <option key={s.name} value={s.name} />
          ))}
        </datalist>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-what`}>What for</label>
        <input id={`${prefix}-what`} name="description" defaultValue={c?.description ?? ""} />
      </div>
    </div>
  );
}
