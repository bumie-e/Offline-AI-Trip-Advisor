import { useMemo, type ReactNode } from 'react'
import type { Severity, Stop, TripPack } from '../api/types'
import { citationResolver, type Citation } from '../lib/citations'
import { formatDateRange, formatDateTime, formatDuration, MODE_LABEL } from '../lib/format'
import { Sources } from './Sources'
import { VerdictBanner } from './VerdictBanner'

const SEVERITY: Record<Severity, { label: string; icon: string; card: string; pill: string }> = {
  high: { label: 'High', icon: '!', card: 'border-red-200 border-l-red-600 bg-red-50/60', pill: 'bg-red-600 text-white' },
  elevated: { label: 'Elevated', icon: '!', card: 'border-amber-200 border-l-amber-500 bg-amber-50/60', pill: 'bg-amber-500 text-stone-950' },
  none: { label: 'Note', icon: 'i', card: 'border-stone-200 border-l-stone-400 bg-white', pill: 'bg-stone-200 text-stone-800' },
}

/**
 * The full trip plan: verdict, summary, reasons with sources, stops and return leg.
 * `children` is rendered right after the summary, for page actions such as saving.
 */
export function ItineraryView({ tripPack, children }: { tripPack: TripPack; children?: ReactNode }) {
  const { itinerary, delta, advice_source } = tripPack
  const { request } = itinerary
  const resolve = useMemo(() => citationResolver(tripPack), [tripPack])
  const travellers = `${request.group_size} traveller${request.group_size === 1 ? '' : 's'}`

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-stone-200 bg-stone-200 text-sm">
        <Detail label="Dates" value={formatDateRange(request.start_date, request.end_date)} />
        <Detail label="Travellers" value={travellers} />
        <Detail
          label="Starting from"
          value={`${request.start_city}${request.arrival_airport ? ` via ${request.arrival_airport}` : ''}`}
        />
        {request.mode && <Detail label="Transport" value={MODE_LABEL[request.mode]} />}
      </dl>

      <VerdictBanner verdict={itinerary.verdict} />

      {itinerary.summary && (
        <p className="text-[17px] leading-relaxed text-stone-800">{itinerary.summary}</p>
      )}

      {children}

      {itinerary.verdict_reasons.length > 0 && (
        <section aria-labelledby="reasons" className="space-y-3">
          <h2 id="reasons" className="text-xl font-bold tracking-tight text-stone-900">
            Why this verdict
          </h2>
          <ul className="space-y-3">
            {itinerary.verdict_reasons.map((reason, i) => {
              const style = SEVERITY[reason.severity]
              return (
                <li key={i} className={`rounded-xl border border-l-[6px] p-4 shadow-sm ${style.card}`}>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold tracking-wide uppercase ${style.pill}`}
                  >
                    <span aria-hidden>{style.icon}</span>
                    {style.label}
                  </span>
                  <p className="mt-2 text-[15px] leading-relaxed text-stone-900">{reason.advice}</p>
                  {!!reason.alternatives?.length && (
                    <div className="mt-3">
                      <p className="text-xs font-semibold tracking-wide text-stone-500 uppercase">
                        Options
                      </p>
                      <ul className="mt-1 flex flex-wrap gap-1.5">
                        {reason.alternatives.map((alt) => (
                          <li key={alt} className="rounded-full border border-green-200 bg-white px-3 py-1 text-sm font-medium text-green-900">
                            {alt}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <Sources ids={reason.cited_ids} resolve={resolve} />
                </li>
              )
            })}
          </ul>
        </section>
      )}

      <StopList title="Getting there" stops={itinerary.stops} resolve={resolve} />
      <StopList title="Return" stops={itinerary.return_leg ?? []} resolve={resolve} />

      <footer className="space-y-2 rounded-xl border border-stone-200 bg-white p-4 text-xs leading-relaxed text-stone-600">
        <p>
          Weather and news as of {formatDateTime(delta.generated_at)}. Plan generated{' '}
          {formatDateTime(itinerary.generated_at)}.
        </p>
        <p className="font-medium text-stone-700">
          This is advice from public reports and forecasts, not a guarantee of conditions. Confirm
          locally, and consider a local guide, before you travel.
        </p>
        <p>
          <span className="rounded-full bg-stone-100 px-2.5 py-1 font-medium text-stone-700">
            {advice_source === 'model' ? 'Advice written by AI' : 'Advice from rule-based checks'}
          </span>
        </p>
      </footer>
    </div>
  )
}

function StopList({
  title,
  stops,
  resolve,
}: {
  title: string
  stops: Stop[]
  resolve: (id: string) => Citation
}) {
  if (!stops.length) return null
  const sorted = [...stops].sort((a, b) => a.order - b.order)

  return (
    <section className="space-y-3">
      <h2 className="text-xl font-bold tracking-tight text-stone-900">{title}</h2>
      <ol className="relative ml-3 space-y-5 border-l-2 border-green-300 pl-6">
        {sorted.map((stop) => (
          <li key={stop.order} className="relative">
            <span
              aria-hidden
              className="absolute top-0 -left-[2.15rem] flex size-6 items-center justify-center rounded-full bg-green-800 text-xs font-bold text-white ring-4 ring-stone-50"
            >
              {stop.order}
            </span>
            <p className="font-semibold text-stone-900">{stop.title}</p>
            {(stop.mode || !!stop.duration_minutes) && (
              <p className="mt-0.5 inline-block rounded-md bg-green-100 px-2 py-0.5 text-xs font-medium text-green-900">
                {[stop.mode && MODE_LABEL[stop.mode], stop.duration_minutes && formatDuration(stop.duration_minutes)]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
            {stop.notes && <p className="mt-1 text-sm leading-relaxed text-stone-700">{stop.notes}</p>}
            <Sources ids={stop.cited_ids} resolve={resolve} />
          </li>
        ))}
      </ol>
    </section>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white px-4 py-3">
      <dt className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">{label}</dt>
      <dd className="mt-0.5 font-semibold text-stone-900">{value}</dd>
    </div>
  )
}
