import type { UnitDetail } from "@/lib/api";

/** The fields of a unit, for adding one or changing it. Amounts can be typed as builders
 * write them: 1,20,00,000, 1.2 crore or 95 lakh. Dates day first. */
export function UnitFields({ unit, prefix = "unit" }: { unit?: UnitDetail; prefix?: string }) {
  const id = (name: string) => `${prefix}-${name}`;
  const text = (name: string, label: string, value?: string | number | null, required = false) => (
    <div className="field">
      <label htmlFor={id(name)}>{label}</label>
      <input id={id(name)} name={name} defaultValue={value ?? ""} required={required} />
    </div>
  );
  return (
    <>
      <div className="field-grid">
        {text("label", "Unit number", unit?.label, !unit)}
        {text("tower", "Tower or block", unit?.tower)}
        {text("carpet_area_sqft", "Carpet area (sq ft)", unit?.carpet_area_sqft, !unit)}
        <div className="field">
          <label htmlFor={id("owner_share")}>Whose share</label>
          <select id={id("owner_share")} name="owner_share" defaultValue={unit?.owner_share ?? "developer"}>
            <option value="developer">Developer</option>
            <option value="landowner">Landowner</option>
          </select>
        </div>
        {text("list_price", "List price (rupees)", unit?.list_price)}
        {text("guidance_value", "Guidance value (rupees)", unit?.guidance_value)}
      </div>
      <p className="small muted" style={{ margin: "4px 0 12px" }}>
        If it is sold: the buyer, the booking date and the agreement value.
      </p>
      <div className="field-grid">
        {text("buyer_name", "Buyer", unit?.buyer_name)}
        {text("buyer_phone", "Buyer phone", unit?.buyer_phone)}
        {text("buyer_email", "Buyer email", unit?.buyer_email)}
        <div className="field">
          <label htmlFor={id("booked_on")}>Booked on</label>
          <input id={id("booked_on")} name="booked_on" type="date" defaultValue={unit?.booked_on ?? ""} />
        </div>
        {text("agreement_value", "Agreement value (rupees)", unit?.agreement_value)}
      </div>
    </>
  );
}
