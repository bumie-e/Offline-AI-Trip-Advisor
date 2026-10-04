import { useMemo, type ComponentType, type ReactNode, type SVGProps } from 'react'
import type { Advice, Severity, Stop, StopRoad, TravelMode, TripPack } from '../api/types'
import { citationResolver, type Citation, type CitationKind } from '../lib/citations'
import { formatDateRange, formatDateTime, formatDuration, MODE_LABEL } from '../lib/format'
import {
  AlertIcon,
  ArrowRightIcon,
  CalendarIcon,
  CarIcon,
  ChevronRightIcon,
  ClockIcon,
  InfoIcon,
  LandmarkIcon,
  PinIcon,
  PlaneIcon,
  RainIcon,
  RoadIcon,
  SparkIcon,
  TrainIcon,
  UsersIcon,
  WalkIcon,
} from './icons'
import { Photo } from './Photo'
import { SourceLine, Sources } from './Sources'
import { VerdictBanner } from './VerdictBanner'

type IconType = ComponentType<SVGProps<SVGSVGElement>>

const SEVERITY: Record<Severity, { label: string; stripe: string; badge: string; icon: string }> = {
  high: {
    label: 'High',
    stripe: 'border-l-red-600',
    badge: 'bg-red-600 text-white',
    icon: 'bg-red-50 text-red-700',
  },
  elevated: {
    label: 'Elevated',
    stripe: 'border-l-amber-500',
    badge: 'bg-amber-500 text-stone-950',
    icon: 'bg-amber-50 text-amber-700',
  },
  none: {
    label: 'Note',
    stripe: 'border-l-stone-300',
    badge: 'bg-stone-200 text-stone-800',
    icon: 'bg-stone-100 text-stone-600',
  },
}

/** What a reason is about, from the kinds of evidence it cites. First match wins. */
const TOPICS: { kind: CitationKind; label: string; Icon: IconType }[] = [
  { kind: 'weather', label: 'Weather', Icon: RainIcon },
  { kind: 'event', label: 'Disruption', Icon: AlertIcon },
  { kind: 'road', label: 'Road conditions', Icon: RoadIcon },
  { kind: 'site', label: 'Site information', Icon: LandmarkIcon },
]
const OTHER_TOPIC = { label: 'Note', Icon: InfoIcon }

const KIND_NOUN: Record<CitationKind, [string, string]> = {
  weather: ['forecast day', 'forecast days'],
  event: ['news report', 'news reports'],
  road: ['road report', 'road reports'],
  site: ['site fact', 'site facts'],
  cost: ['cost note', 'cost notes'],
  contact: ['contact', 'contacts'],
  image: ['photo', 'photos'],
  route: ['route', 'routes'],
  unknown: ['other source', 'other sources'],
}

const MODE_ICON: Record<TravelMode, IconType> = {
  road: CarIcon,
  flight: PlaneIcon,
  train: TrainIcon,
  walk: WalkIcon,
}

/**
 * The full trip plan, in reading order: destination and trip details, verdict, summary,
 * reasons, options, itinerary, sources, then `children` (the offline/save section) and the
 * disclaimer.
 */
export function ItineraryView({
  tripPack,
  title,
  nav,
  status,
  children,
}: {
  tripPack: TripPack
  title: string
  /** Above the title, e.g. a back link. */
  nav?: ReactNode
  /** Under the title, e.g. the offline badge. */
  status?: ReactNode
  children?: ReactNode
}) {
  const { itinerary, delta, advice_source } = tripPack
  const { request } = itinerary
  const resolve = useMemo(() => citationResolver(tripPack), [tripPack])

  const options = [...new Set(itinerary.verdict_reasons.flatMap((r) => r.alternatives ?? []))]
  const allSources = [
    ...new Set(
      [...itinerary.verdict_reasons, ...itinerary.stops, ...(itinerary.return_leg ?? [])].flatMap(
        (x) => [...(x.cited_ids ?? []), ...('road' in x ? (x.road?.evidence_ids ?? []) : [])],
      ),
    ),
  ].map(resolve)

  return (
    <div className="space-y-7">
      <header className="relative -mx-4 -mt-5 overflow-hidden bg-forest-900 px-5 pt-3 pb-6 text-white sm:mx-0 sm:mt-0 sm:rounded-2xl">
        <HeaderMotif />
        <div className="relative">
          {nav}
          <p className="eyebrow mt-4 text-forest-200">Heritage trip plan</p>
          <h1 className="mt-1 font-display text-[2rem] leading-tight font-semibold tracking-tight">
            {title}
          </h1>
          {status && <div className="mt-3">{status}</div>}
          <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-white/15 pt-4 text-sm">
            <TripFact Icon={CalendarIcon} label="Dates" value={formatDateRange(request.start_date, request.end_date)} />
            <TripFact
              Icon={UsersIcon}
              label="Travellers"
              value={`${request.group_size} traveller${request.group_size === 1 ? '' : 's'}`}
            />
            <TripFact
              Icon={PinIcon}
              label="Starting from"
              value={`${request.start_city}${request.arrival_airport ? ` via ${request.arrival_airport}` : ''}`}
            />
            {request.mode && (
              <TripFact Icon={MODE_ICON[request.mode]} label="Transport" value={MODE_LABEL[request.mode]} />
            )}
          </dl>
        </div>
      </header>

      <div className="space-y-4">
        <VerdictBanner verdict={itinerary.verdict} />
        {itinerary.summary && (
          <p className="px-1 text-[17px] leading-relaxed text-stone-800">{itinerary.summary}</p>
        )}
      </div>

      {itinerary.verdict_reasons.length > 0 && (
        <Section title="Why this verdict" count={itinerary.verdict_reasons.length}>
          <ul className="space-y-3">
            {itinerary.verdict_reasons.map((reason, i) => (
              <ReasonCard key={i} reason={reason} resolve={resolve} />
            ))}
          </ul>
        </Section>
      )}

      {options.length > 0 && (
        <Section title="Recommended options">
          <ul className="card divide-y divide-stone-100">
            {options.map((option) => (
              <li key={option} className="flex items-center gap-3 px-4 py-3.5">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-forest-50 text-forest-700">
                  <ArrowRightIcon className="size-3.5" strokeWidth={2.2} />
                </span>
                <span className="text-[15px] text-stone-800 first-letter:uppercase">{option}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Your itinerary">
        <div className="space-y-4">
          <Leg title="Outbound" stops={itinerary.stops} resolve={resolve} />
          <Leg title="Return" stops={itinerary.return_leg ?? []} resolve={resolve} />
        </div>
      </Section>

      {allSources.length > 0 && (
        <Section title="Sources">
          <details className="card group">
            <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3.5 select-none [&::-webkit-details-marker]:hidden">
              <span className="flex-1">
                <span className="block text-[15px] font-medium text-stone-900">
                  {allSources.length} source{allSources.length === 1 ? '' : 's'} behind this plan
                </span>
                <span className="mt-0.5 block text-sm text-stone-500">{sourceBreakdown(allSources)}</span>
              </span>
              <ChevronRightIcon className="size-5 text-stone-400 transition-transform group-open:rotate-90" />
            </summary>
            <ul className="space-y-3 border-t border-stone-100 px-4 py-4">
              {allSources.map((c) => (
                <li key={c.id}>
                  <SourceLine citation={c} />
                </li>
              ))}
            </ul>
          </details>
        </Section>
      )}

      {children}

      <footer className="space-y-3 border-t border-stone-200 pt-5 text-xs leading-relaxed text-stone-500">
        <p className="flex items-start gap-2">
          <ClockIcon className="mt-px size-3.5 shrink-0" />
          <span>
            Weather and news as of {formatDateTime(delta.generated_at)}. Plan generated{' '}
            {formatDateTime(itinerary.generated_at)}.
          </span>
        </p>
        <p className="text-stone-600">
          This is advice from public reports and forecasts, not a guarantee of conditions. Confirm
          locally, and consider a local guide, before you travel.
        </p>
        <p className="inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-2.5 py-1 font-medium text-stone-600">
          {advice_source === 'model' ? (
            <>
              <SparkIcon className="size-3.5" /> Advice written by AI
            </>
          ) : (
            <>
              <InfoIcon className="size-3.5" /> Advice from rule-based checks
            </>
          )}
        </p>
      </footer>
    </div>
  )
}

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="section-title flex items-baseline gap-2">
        {title}
        {count !== undefined && <span className="text-sm font-medium text-stone-400">{count}</span>}
      </h2>
      {children}
    </section>
  )
}

function TripFact({ Icon, label, value }: { Icon: IconType; label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <Icon className="mt-0.5 size-4 shrink-0 text-forest-300" />
      <div className="min-w-0">
        <dt className="text-[11px] tracking-wide text-forest-200 uppercase">{label}</dt>
        <dd className="font-medium break-words text-white">{value}</dd>
      </div>
    </div>
  )
}

function ReasonCard({ reason, resolve }: { reason: Advice; resolve: (id: string) => Citation }) {
  const style = SEVERITY[reason.severity]
  const citations = reason.cited_ids.map(resolve)
  const kinds = new Set(citations.map((c) => c.kind))
  const topic = TOPICS.find((t) => kinds.has(t.kind)) ?? OTHER_TOPIC
  const chips = [...new Set(citations.flatMap((c) => (c.chip ? [c.chip] : [])))]

  return (
    <li className={`card border-l-4 p-4 ${style.stripe}`}>
      <div className="flex items-center gap-3">
        <span className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${style.icon}`}>
          <topic.Icon className="size-[18px]" />
        </span>
        <p className="flex-1 font-semibold text-stone-900">{topic.label}</p>
        <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold tracking-wide uppercase ${style.badge}`}>
          {style.label}
        </span>
      </div>
      <p className="mt-3 text-[15px] leading-relaxed text-stone-800">{reason.advice}</p>
      {chips.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <li key={chip} className="rounded-lg bg-sand-100 px-2 py-1 text-xs font-medium text-stone-700">
              {chip}
            </li>
          ))}
        </ul>
      )}
      <Sources ids={reason.cited_ids} resolve={resolve} />
    </li>
  )
}

function Leg({ title, stops, resolve }: { title: string; stops: Stop[]; resolve: (id: string) => Citation }) {
  if (!stops.length) return null
  const sorted = [...stops].sort((a, b) => a.order - b.order)

  return (
    <div className="card p-4">
      <p className="eyebrow text-stone-500">{title}</p>
      <ol className="mt-4">
        {sorted.map((stop, i) => {
          const last = i === sorted.length - 1
          const ModeIcon = stop.mode ? MODE_ICON[stop.mode] : null
          return (
            <li key={stop.order} className={`relative pl-12 ${last ? '' : 'pb-6'}`}>
              {!last && <span aria-hidden className="absolute top-9 bottom-1 left-[15px] w-0.5 rounded-full bg-forest-100" />}
              <span
                aria-hidden
                className="absolute top-0 left-0 flex size-8 items-center justify-center rounded-full bg-forest-800 text-sm font-semibold text-white"
              >
                {stop.order}
              </span>
              <p className="pt-1 font-semibold text-stone-900">{stop.title}</p>
              {(ModeIcon || !!stop.duration_minutes) && (
                <p className="mt-1.5 flex flex-wrap gap-1.5 text-xs font-medium text-stone-600">
                  {ModeIcon && stop.mode && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-forest-50 px-2 py-1 text-forest-800">
                      <ModeIcon className="size-3.5" /> {MODE_LABEL[stop.mode]}
                    </span>
                  )}
                  {!!stop.duration_minutes && (
                    <span className="inline-flex items-center gap-1 rounded-md bg-sand-100 px-2 py-1">
                      <ClockIcon className="size-3.5" /> {formatDuration(stop.duration_minutes)}
                    </span>
                  )}
                </p>
              )}
              {stop.comment && <p className="mt-2 text-sm font-medium text-stone-700">{stop.comment}</p>}
              {stop.image && (
                <div className="mt-3">
                  <Photo
                    path={stop.image.path}
                    alt={stop.image.caption}
                    caption={stop.image.caption}
                    credit={stop.image.credit}
                    width={stop.image.width}
                    height={stop.image.height}
                    ratio={Math.min(2.2, Math.max(4 / 3, stop.image.width / stop.image.height))}
                    label={stop.image.shows_this_stop === false ? 'Typical road in the area' : undefined}
                    className="rounded-xl"
                  />
                </div>
              )}
              {stop.road && <RoadPanel road={stop.road} resolve={resolve} />}
              {stop.advice && (
                <div className="mt-3 flex items-start gap-2.5 rounded-xl bg-forest-50 p-3 text-sm text-forest-900">
                  <SparkIcon className="mt-0.5 size-4 shrink-0 text-forest-700" />
                  <p className="leading-relaxed">{stop.advice}</p>
                </div>
              )}
              {stop.notes && <p className="mt-2 text-sm leading-relaxed text-stone-600">{stop.notes}</p>}
              <Sources ids={stop.cited_ids} resolve={resolve} />
            </li>
          )
        })}
      </ol>
    </div>
  )
}

const SCOPE_LABEL: Record<NonNullable<StopRoad['scope']>, string> = {
  here: 'Reported at this place',
  road: 'Reported on this road',
  corridor: 'Reported on the wider route, so it may not apply at this exact spot',
}

/** The road at a stop: name, distance, and the latest report with how far it applies. */
function RoadPanel({ road, resolve }: { road: StopRoad; resolve: (id: string) => Citation }) {
  const distance = [
    road.km_from_start != null && `${formatKm(road.km_from_start)} from start`,
    road.km_since_previous_stop != null && `${formatKm(road.km_since_previous_stop)} since last stop`,
  ].filter(Boolean)
  const reportMeta = [
    road.confidence && `${road.confidence.charAt(0).toUpperCase()}${road.confidence.slice(1)} confidence`,
    road.report_age_days != null && (road.report_age_days === 1 ? '1 day old' : `${road.report_age_days} days old`),
  ].filter(Boolean)

  return (
    <div className="mt-3 rounded-xl border border-stone-200 bg-sand-50/60 p-3 text-sm">
      <div className="flex items-start gap-2.5">
        <RoadIcon className="mt-0.5 size-4 shrink-0 text-stone-500" />
        <div className="min-w-0 flex-1">
          {road.name && <p className="font-medium text-stone-900">{road.name}</p>}
          {distance.length > 0 && <p className="text-xs text-stone-500">{distance.join(' · ')}</p>}
          {road.condition && (
            <p className="mt-2 leading-relaxed text-stone-700">
              {road.has_recent_report && road.scope && (
                <span className="mb-0.5 block text-xs font-medium text-amber-800">{SCOPE_LABEL[road.scope]}</span>
              )}
              {road.condition}
            </p>
          )}
          {road.has_recent_report && reportMeta.length > 0 && (
            <p className="mt-1 text-xs text-stone-500">{reportMeta.join(' · ')}</p>
          )}
          <Sources ids={road.evidence_ids} resolve={resolve} />
        </div>
      </div>
    </div>
  )
}

function formatKm(km: number): string {
  return `${km < 10 ? km.toFixed(1).replace(/\.0$/, '') : Math.round(km)} km`
}

/** "6 forecast days · 2 news reports · 1 route" */
function sourceBreakdown(citations: Citation[]): string {
  const counts = new Map<CitationKind, number>()
  for (const c of citations) counts.set(c.kind, (counts.get(c.kind) ?? 0) + 1)
  return [...counts]
    .map(([kind, n]) => `${n} ${KIND_NOUN[kind][n === 1 ? 0 : 1]}`)
    .join(' · ')
}

/** Faint layered ridges, echoing the granite outcrop in the app mark. */
function HeaderMotif() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 400 160"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-x-0 bottom-0 h-28 w-full text-white"
    >
      <path d="M0 160 L0 120 L90 70 L150 105 L230 45 L300 95 L400 60 L400 160 Z" fill="currentColor" opacity="0.04" />
      <path d="M0 160 L0 140 L70 110 L160 135 L250 95 L330 125 L400 105 L400 160 Z" fill="currentColor" opacity="0.05" />
    </svg>
  )
}
