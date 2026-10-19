type Approval = {
  name: string;
  authority: string | null;
  reference: string | null;
  applied_on: string | null;
  granted_on: string | null;
  valid_until: string | null;
  note: string | null;
};

export function ApprovalFields({ prefix, approval }: { prefix: string; approval?: Approval }) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-name`}>Approval</label>
        <input id={`${prefix}-name`} name="name" defaultValue={approval?.name ?? ""} placeholder="Fire NOC (provisional)" required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-authority`}>Authority</label>
        <input id={`${prefix}-authority`} name="authority" defaultValue={approval?.authority ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-ref`}>Number</label>
        <input id={`${prefix}-ref`} name="reference" defaultValue={approval?.reference ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-applied`}>Applied on</label>
        <input id={`${prefix}-applied`} name="applied_on" type="date" defaultValue={approval?.applied_on ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-granted`}>Granted on</label>
        <input id={`${prefix}-granted`} name="granted_on" type="date" defaultValue={approval?.granted_on ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-until`}>Valid until</label>
        <input id={`${prefix}-until`} name="valid_until" type="date" defaultValue={approval?.valid_until ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-note`}>Note</label>
        <input id={`${prefix}-note`} name="note" defaultValue={approval?.note ?? ""} />
      </div>
    </div>
  );
}
