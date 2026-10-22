import { addBankRule, deleteBankRule, moveBankRuleUp } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type BankLine, type BankRules, api } from "@/lib/api";

/** What a rule made from a statement line starts with, carried in the link to the form. */
export type RulePrefill = { words?: string; action?: string; unit?: string; direction?: string };

const COMMON = new Set([
  "the", "and", "from", "transfer", "neft", "rtgs", "imps", "upi", "inb", "chq", "cheque", "ltd",
  "pvt", "limited", "bank", "credit", "debit", "for", "via", "ref", "txn",
]); // prettier-ignore

/** A link that opens the rule form filled in from a statement line: its payer, or the first
 * telling words of the narration, and what Lekhara made of the line. */
export function ruleLink(projectId: string, l: BankLine): string {
  const words =
    l.payer?.toLowerCase() ??
    l.narration
      .toLowerCase()
      .replace(/[^a-z ]+/g, " ")
      .split(/\s+/)
      .filter((w) => w.length >= 3 && !COMMON.has(w))
      .slice(0, 3)
      .join(" ");
  const action = l.credit
    ? l.unit_id
      ? "unit"
      : l.outcome === "interest" || l.outcome === "deposit"
        ? l.outcome
        : l.outcome === "not_buyer"
          ? "not_buyer"
          : "leave_out"
    : l.outcome === "charges" || l.outcome === "withdrawal"
      ? l.outcome
      : "leave_out";
  const q = new URLSearchParams({ rule_words: words, rule_action: action, rule_direction: l.credit ? "in" : "out" });
  if (action === "unit" && l.unit_id) q.set("rule_unit", l.unit_id);
  return `/projects/${projectId}/import?${q.toString()}#bank-rules`;
}

/** The firm's bank rules that apply to a project's statements, on its Import page. */
export async function BankRulesSection({ projectId, prefill }: { projectId: string; prefill: RulePrefill }) {
  const r: BankRules = await api.bankRules(projectId);
  const opened = Boolean(prefill.words);
  return (
    <section className="section" id="bank-rules">
      <div className="section-head">
        <h2>Bank rules</h2>
        <p>Words in a statement line that say what it is</p>
      </div>
      <p className="small muted" style={{ maxWidth: 760, marginTop: 12 }}>
        For what repeats every month: the same buyer paying from the same account, transfers to fixed deposits, the
        bank&apos;s own fees. Rules are tried in this order and the first that fits a line decides it. A choice you make
        for a line on a statement still comes first, and the payers Lekhara remembers come after.
      </p>
      {r.rules.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Looks for</th>
              <th>Lines</th>
              <th>Then</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {r.rules.map((rule, i) => (
              <tr key={rule.id}>
                <td>
                  {rule.name}
                  {rule.every_project ? <span className="small muted"> Every project</span> : null}
                </td>
                <td>
                  {`"${rule.words}"`} <span className="small muted">{rule.how_label.toLowerCase()}</span>
                </td>
                <td>{rule.lines}</td>
                <td>{rule.then}</td>
                <td className="right nowrap">
                  {r.can_edit ? (
                    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                      {i > 0 ? (
                        <ActionForm action={moveBankRuleUp.bind(null, projectId, rule.id)} label="Move up" pendingLabel="Moving" secondary />
                      ) : null}
                      <ActionForm action={deleteBankRule.bind(null, projectId, rule.id)} label="Remove" pendingLabel="Removing" secondary />
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">No rules yet. On a statement, each line has a link to make a rule from it.</p>
      )}
      {r.can_edit ? (
        <details className="disclosure" open={opened}>
          <summary>Add a rule</summary>
          <ActionForm action={addBankRule.bind(null, projectId)} label="Add the rule" pendingLabel="Checking the statements">
            <div className="field-grid" style={{ marginTop: 12 }}>
              <div className="field">
                <label htmlFor="bank-rule-name">Name</label>
                <input id="bank-rule-name" name="name" required placeholder="Priya Sharma's payments" />
              </div>
              <div className="field">
                <label htmlFor="bank-rule-words">Words to look for in the narration</label>
                <input id="bank-rule-words" name="words" required defaultValue={prefill.words} placeholder="priya sharma" />
              </div>
              <div className="field">
                <label htmlFor="bank-rule-how">How</label>
                <select id="bank-rule-how" name="how" defaultValue="all">
                  {r.hows.map((h) => (
                    <option key={h.value} value={h.value}>
                      {h.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="bank-rule-action">Then the line is</label>
                <select id="bank-rule-action" name="action" defaultValue={prefill.action ?? "unit"}>
                  {r.actions.map((a) => (
                    <option key={a.value} value={a.value}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="bank-rule-unit">The unit, for a buyer&apos;s payment</label>
                <select id="bank-rule-unit" name="unit_id" defaultValue={prefill.unit ?? ""}>
                  <option value="">Choose the unit</option>
                  {r.units.map((u) => (
                    <option key={u.id} value={u.id}>
                      {`${u.label}${u.buyer ? `, ${u.buyer}` : ""}`}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="bank-rule-direction">Lines, for leaving out</label>
                <select id="bank-rule-direction" name="direction" defaultValue={prefill.direction ?? "any"}>
                  {r.directions.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="bank-rule-min">Amount at least (optional)</label>
                <input id="bank-rule-min" name="min_amount" inputMode="decimal" placeholder="0" />
              </div>
              <div className="field">
                <label htmlFor="bank-rule-max">Amount at most (optional)</label>
                <input id="bank-rule-max" name="max_amount" inputMode="decimal" />
              </div>
            </div>
            <label className="check-line">
              <input type="checkbox" name="every_project" value="yes" /> Use it for every project&apos;s statements (not for
              a rule that names a unit)
            </label>
            <label className="check-line">
              <input type="checkbox" name="only_try" value="yes" /> Only try it: show the lines it fits in this
              project&apos;s statements, without saving it
            </label>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}
