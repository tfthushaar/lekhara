type Owner = { name: string; share_type: string; share_pct: string; refundable_deposit: string; pan: string | null };

export function LandownerFields({ prefix, owner }: { prefix: string; owner?: Owner }) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-name`}>Name</label>
        <input id={`${prefix}-name`} name="name" defaultValue={owner?.name ?? ""} required={!owner} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-type`}>Share of</label>
        <select id={`${prefix}-type`} name="share_type" defaultValue={owner?.share_type ?? "area"}>
          <option value="area">The built area</option>
          <option value="revenue">Revenue</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-pct`}>Share (per cent)</label>
        <input id={`${prefix}-pct`} name="share_pct" inputMode="decimal" defaultValue={owner?.share_pct ?? ""} required={!owner} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-deposit`}>Refundable deposit (rupees)</label>
        <input id={`${prefix}-deposit`} name="refundable_deposit" defaultValue={owner?.refundable_deposit ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-pan`}>PAN</label>
        <input id={`${prefix}-pan`} name="pan" defaultValue={owner?.pan ?? ""} placeholder="ABCDE1234F" />
      </div>
    </div>
  );
}

type Payment = { paid_on: string; amount: string; tds_deducted: string; deposit: boolean; reference: string | null };

export function LandownerPaymentFields({ prefix, payment }: { prefix: string; payment?: Payment }) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-on`}>Paid on</label>
        <input id={`${prefix}-on`} name="paid_on" type="date" defaultValue={payment?.paid_on ?? ""} required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-amount`}>Amount before TDS (rupees)</label>
        <input id={`${prefix}-amount`} name="amount" defaultValue={payment?.amount ?? ""} placeholder="30 lakh" required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-tds`}>TDS deducted (rupees)</label>
        <input id={`${prefix}-tds`} name="tds_deducted" defaultValue={payment && payment.tds_deducted !== "0.00" ? payment.tds_deducted : ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-kind`}>What for</label>
        <select id={`${prefix}-kind`} name="deposit" defaultValue={payment?.deposit ? "yes" : "no"}>
          <option value="no">Consideration</option>
          <option value="yes">Refundable deposit</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-ref`}>Reference</label>
        <input id={`${prefix}-ref`} name="reference" defaultValue={payment?.reference ?? ""} placeholder="UTR or cheque number" />
      </div>
    </div>
  );
}
