'use client'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Example } from '@/lib/types'
import { VENUE_LABEL, pct } from '@/lib/format'

function label([lo, hi]: [number | null, number | null]): string {
  if (lo === null && hi !== null) return `≤${hi}°`
  if (hi === null && lo !== null) return `≥${lo}°`
  return lo === hi ? `${lo}°` : `${lo}–${hi}°`
}

const toggleClass = (on: boolean) =>
  `px-3 py-1 rounded-full border transition-colors ${on
    ? 'border-[var(--color-text)] text-[var(--color-text)]'
    : 'border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]'}`

/** One city-day ladder: what the model and the market said the day before, and what won.
 *  The day shown is the newest scored one per city, picked by date rather than by outcome. */
export default function LadderExample({ examples }: { examples: Record<string, Example[]> }) {
  const venues = Object.keys(examples).filter((v) => examples[v].length)
  const [venue, setVenue] = useState(venues[0])
  const [city, setCity] = useState(venue ? examples[venue][0].city : '')
  if (!venue) return null
  const ex = examples[venue].find((e) => e.city === city) ?? examples[venue][0]
  const data = ex.buckets.map((b, i) => ({
    bucket: label(b),
    model: ex.model_probs[i],
    market: ex.market_probs[i],
    won: ex.outcomes[i] === 1,
  }))
  const winner = data.find((d) => d.won)

  return (
    <figure className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-6 mb-8">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <figcaption>
          <h2 className="text-base font-semibold text-[var(--color-text)]">One day, up close</h2>
          <p className="text-xs text-[var(--color-muted)] mt-1 max-w-md">
            {ex.city}, {ex.target_date}, as of {ex.lead}: each bar is the probability given to one bucket. The high
            landed in <strong className="text-[var(--color-text)]">{winner?.bucket ?? '—'}</strong>. Shown: the most
            recent scored day for each city, not a hand-picked one.
          </p>
        </figcaption>
        <div className="flex flex-col gap-2 items-end text-xs">
          <div role="radiogroup" aria-label="Venue" className="flex gap-1">
            {venues.map((v) => (
              <button key={v} role="radio" aria-checked={v === venue} className={toggleClass(v === venue)}
                onClick={() => { setVenue(v); setCity(examples[v][0].city) }}>
                {VENUE_LABEL[v] ?? v}
              </button>
            ))}
          </div>
          <div role="radiogroup" aria-label="City" className="flex flex-wrap gap-1 justify-end">
            {examples[venue].map((e) => (
              <button key={e.city} role="radio" aria-checked={e.city === ex.city}
                className={toggleClass(e.city === ex.city)} onClick={() => setCity(e.city)}>
                {e.city}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }} barGap={2} barCategoryGap="18%">
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="bucket" tickLine={false} axisLine={{ stroke: 'var(--color-border)' }}
              tick={(props) => {
                const d = data[props.index]
                return (
                  <text x={props.x} y={Number(props.y) + 14} textAnchor="middle" fontSize={12}
                    fill={d?.won ? 'var(--color-text)' : 'var(--color-muted)'} fontWeight={d?.won ? 600 : 400}>
                    {d?.bucket}{d?.won ? ' ✓' : ''}
                  </text>
                )
              }} />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={pct} tickLine={false}
              axisLine={false} tick={{ fill: 'var(--color-muted)', fontSize: 12 }} />
            <Tooltip cursor={{ fill: 'var(--color-border)', opacity: 0.4 }}
              contentStyle={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(v, items) => `${v}${items?.[0]?.payload?.won ? ' (won)' : ''}`}
              formatter={(value, name) => [pct(Number(value)), name]} />
            <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12, color: 'var(--color-muted)' }} />
            <Bar dataKey="model" name="Model" fill="var(--color-model)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="market" name="Market" fill="var(--color-market)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
