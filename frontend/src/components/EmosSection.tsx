import type { EmosResult } from '@/lib/types'
import { VENUE_LABEL, daySpan, signed } from '@/lib/format'

const ci = (d: number, [lo, hi]: [number, number]) => `${signed(d)} [${signed(lo)}, ${signed(hi)}]`

/** Protocol v3: the model rebuilt around v1's diagnosed failures, scored only on days
 *  after it was frozen, against v1 on the same city-days and against the market. */
export default function EmosSection({ result }: { result: EmosResult }) {
  const rows = Object.entries(result.venues).flatMap(([venue, v]) =>
    v.vs_v1.map((r) => ({ venue, r, m: v.vs_market.find((x) => x.lead === r.lead) })))
  if (!rows.length) return null
  return (
    <section className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl mb-8 overflow-x-auto">
      <div className="px-6 pt-5">
        <h2 className="text-base font-semibold text-[var(--color-text)]">
          Model v2, forward only ({daySpan(result.window)})
        </h2>
        <p className="text-xs text-[var(--color-muted)] mt-1 max-w-2xl">
          A pre-registered rebuild aimed at v1&apos;s failures: GFS and ECMWF weighted by their past skill, a
          seasonal bias, and wider uncertainty on days the two disagree (EMOS). Fit on the training window and
          scored only on days after it was frozen. Brier differences; below zero means v2 was better.
        </p>
      </div>
      <table className="w-full text-sm tabular-nums mt-3">
        <thead>
          <tr className="text-xs text-[var(--color-muted)] text-left border-y border-[var(--color-border)]">
            {['Venue', 'Lead', 'City-days', 'v2 − v1 [95% CI]', 'v2 − market [95% CI]'].map((h, i) => (
              <th key={h} className={`font-normal px-6 py-2 ${i > 1 ? 'text-right' : ''}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ venue, r, m }) => (
            <tr key={`${venue}-${r.lead}`} className="border-b border-[var(--color-border)] last:border-0">
              <td className="px-6 py-2 text-[var(--color-muted)]">{VENUE_LABEL[venue] ?? venue}</td>
              <td className="px-6 py-2 text-[var(--color-text)]">{r.lead}</td>
              <td className="px-6 py-2 text-right text-[var(--color-muted)]">{r.n_events}</td>
              <td className={`px-6 py-2 text-right ${r.brier_diff_ci[1] < 0 ? 'text-[var(--color-model)]' : 'text-[var(--color-muted)]'}`}>
                {ci(r.brier_diff, r.brier_diff_ci)}
              </td>
              <td className="px-6 py-2 text-right text-[var(--color-muted)]">
                {m ? ci(m.brier_diff, m.brier_diff_ci) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pb-5" />
    </section>
  )
}
