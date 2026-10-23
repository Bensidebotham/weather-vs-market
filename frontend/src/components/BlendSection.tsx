import type { BlendResult } from '@/lib/types'
import { VENUE_LABEL, num, signed } from '@/lib/format'

type Props = { test: BlendResult | null; forward: BlendResult | null }

/** Protocol v2: pool the market with the model. If the model knew something the price
 *  didn't, the blend would beat the market and the model weight b would be clearly above 0. */
export default function BlendSection({ test, forward }: Props) {
  const base = forward ?? test
  if (!base) return null
  const venues = Object.keys(base.weights).filter((v) => Object.keys(base.weights[v]).length)
  const diff = (r: BlendResult | null, venue: string, lead: string) =>
    r?.venues[venue]?.summary.find((s) => s.lead === lead)
  const cell = (r: BlendResult | null, venue: string, lead: string) => {
    const s = diff(r, venue, lead)
    return s ? `${signed(s.brier_diff)} [${signed(s.brier_diff_ci[0])}, ${signed(s.brier_diff_ci[1])}]` : '—'
  }
  return (
    <section className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl mb-8 overflow-x-auto">
      <div className="px-6 pt-5">
        <h2 className="text-base font-semibold text-[var(--color-text)]">Does the model add anything to the price?</h2>
        <p className="text-xs text-[var(--color-muted)] mt-1 max-w-2xl">
          A pre-registered blend pools the market with the model, p ∝ market<sup>a</sup> · model<sup>b</sup>, with a
          and b fit on the training window only. b = 0 means the model adds nothing; a blend − market Brier difference
          below zero means the blend beat the market.
        </p>
      </div>
      <table className="w-full text-sm tabular-nums mt-3">
        <thead>
          <tr className="text-xs text-[var(--color-muted)] text-left border-y border-[var(--color-border)]">
            {['Venue', 'Lead', 'Model weight b [95% CI]', 'Blend − market, test', 'Blend − market, forward'].map(
              (h, i) => <th key={h} className={`font-normal px-6 py-2 ${i > 1 ? 'text-right' : ''}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {venues.flatMap((venue) => Object.entries(base.weights[venue]).map(([lead, w]) => (
            <tr key={`${venue}-${lead}`} className="border-b border-[var(--color-border)] last:border-0">
              <td className="px-6 py-2 text-[var(--color-muted)]">{VENUE_LABEL[venue] ?? venue}</td>
              <td className="px-6 py-2 text-[var(--color-text)]">{lead}</td>
              <td className="px-6 py-2 text-right text-[var(--color-text)]">
                {num(w.b, 2)} [{num(w.b_ci[0], 2)}, {num(w.b_ci[1], 2)}]
              </td>
              <td className="px-6 py-2 text-right text-[var(--color-muted)]">{cell(test, venue, lead)}</td>
              <td className="px-6 py-2 text-right text-[var(--color-muted)]">{cell(forward, venue, lead)}</td>
            </tr>
          )))}
        </tbody>
      </table>
      <div className="pb-5" />
    </section>
  )
}
