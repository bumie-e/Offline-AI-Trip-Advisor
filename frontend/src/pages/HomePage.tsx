import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { getPlaces } from '../api/client'
import type { PlaceSummary } from '../api/types'
import { APP_NAME } from '../components/AppShell'
import {
  AlertIcon,
  ArrowRightIcon,
  BookmarkIcon,
  ChevronRightIcon,
  CloudOffIcon,
  LandmarkIcon,
  OfflineReadyIcon,
  PinIcon,
  SparkIcon,
} from '../components/icons'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { friendlyError } from '../lib/errors'
import { formatBytes, formatDateTime } from '../lib/format'
import { planPath, type PlanState } from '../lib/navigation'

/** The demo case study, shown first and larger. */
const FEATURED_SITE_ID = 'olumo-rock'

/** Stage 1, "Inspiration": the places from `GET /places`. */
export function HomePage() {
  const online = useOnlineStatus()
  const [places, setPlaces] = useState<PlaceSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (places || !online) return
    const controller = new AbortController()
    getPlaces(controller.signal)
      .then((list) => {
        setPlaces(list)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(friendlyError(err))
      })
    return () => controller.abort()
  }, [places, online, attempt])

  const sorted = places && [
    ...places.filter((p) => p.id === FEATURED_SITE_ID),
    ...places.filter((p) => p.id !== FEATURED_SITE_ID),
  ]

  const [featured, ...others] = sorted ?? []
  const hasFeatured = featured?.id === FEATURED_SITE_ID

  return (
    <div className="space-y-8">
      <section className="space-y-4 pt-2">
        <p className="eyebrow text-clay-600">Heritage travel · Nigeria</p>
        <h1 className="font-display text-[2.35rem] leading-[1.08] font-semibold tracking-tight text-stone-900">
          {APP_NAME}
        </h1>
        <p className="max-w-md text-[17px] leading-relaxed text-stone-600">
          Plan smarter heritage trips, even when connectivity is unreliable.
        </p>
        <ol className="grid grid-cols-3 gap-2 pt-1">
          {STEPS.map(({ Icon, title }, i) => (
            <li key={title} className="rounded-xl border border-stone-200/80 bg-white/70 p-3">
              <span className="flex items-center gap-1.5 text-forest-700">
                <Icon className="size-4" />
                <span className="text-[11px] font-semibold text-stone-400">0{i + 1}</span>
              </span>
              <p className="mt-2 text-[13px] leading-snug font-medium text-stone-800">{title}</p>
            </li>
          ))}
        </ol>
      </section>

      {sorted ? (
        <>
          {hasFeatured && (
            <section className="space-y-3">
              <h2 className="section-title">Featured destination</h2>
              <FeaturedCard place={featured} />
            </section>
          )}
          {(hasFeatured ? others : sorted).length > 0 && (
            <section className="space-y-3">
              <h2 className="section-title">{hasFeatured ? 'More heritage sites' : 'Heritage sites'}</h2>
              <ul className="space-y-2.5">
                {(hasFeatured ? others : sorted).map((place) => (
                  <li key={place.id}>
                    <PlaceRow place={place} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      ) : !online ? (
        <Notice Icon={CloudOffIcon}>
          <p className="font-semibold">You are offline</p>
          <p className="mt-0.5">
            Places need a connection to load, but{' '}
            <Link to="/trips" className="font-semibold underline underline-offset-2">
              your saved trips
            </Link>{' '}
            still work.
          </p>
        </Notice>
      ) : error ? (
        <Notice Icon={AlertIcon}>
          <p>{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null)
              setAttempt((n) => n + 1)
            }}
            className="btn-secondary mt-3"
          >
            Try again
          </button>
        </Notice>
      ) : (
        <div className="space-y-3" aria-label="Loading places" role="status">
          <div className="h-64 animate-pulse rounded-2xl bg-forest-900/10" />
          <div className="h-[4.5rem] animate-pulse rounded-2xl bg-stone-200/60" />
          <div className="h-[4.5rem] animate-pulse rounded-2xl bg-stone-200/60" />
        </div>
      )}

      <Link to="/trips" className="card interactive-card flex items-center gap-3.5 p-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-forest-50 text-forest-800">
          <BookmarkIcon className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold text-stone-900">My trips</span>
          <span className="block text-sm text-stone-500">Plans saved on this phone open offline</span>
        </span>
        <ChevronRightIcon className="size-5 text-stone-400" />
      </Link>
    </div>
  )
}

const STEPS = [
  { Icon: SparkIcon, title: 'Plan with current conditions' },
  { Icon: OfflineReadyIcon, title: 'Save before you go' },
  { Icon: CloudOffIcon, title: 'Access your trip offline' },
]

function packInfo(place: PlaceSummary): string {
  return [
    place.pack_bytes != null && `Offline pack ${formatBytes(place.pack_bytes)}`,
    place.pack_generated_at && `updated ${formatDateTime(place.pack_generated_at)}`,
  ]
    .filter(Boolean)
    .join(' · ')
}

function FeaturedCard({ place }: { place: PlaceSummary }) {
  const state: PlanState = { place }
  const info = packInfo(place)
  return (
    <Link
      to={planPath(place.id)}
      state={state}
      className="group relative block overflow-hidden rounded-2xl bg-forest-900 p-5 text-white shadow-raised transition duration-150 hover:-translate-y-px active:scale-[0.995]"
    >
      <Ridges />
      <div className="relative">
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-full bg-clay-500 px-2.5 py-1 text-[11px] font-semibold tracking-wide text-white">
            Featured
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-semibold tracking-wide text-forest-100 ring-1 ring-white/15">
            <LandmarkIcon className="size-3.5" /> Heritage site
          </span>
        </div>
        <p className="mt-14 font-display text-[2.4rem] leading-none font-semibold tracking-tight">{place.name}</p>
        <p className="mt-2 flex items-center gap-1.5 text-forest-100">
          <PinIcon className="size-4" />
          {place.city}, {place.state} State, Nigeria
        </p>
        {info && <p className="mt-1.5 text-xs text-forest-300">{info}</p>}
        <span className="mt-5 inline-flex items-center gap-2 rounded-xl bg-sand-50 px-5 py-3 text-[15px] font-semibold text-forest-900 transition group-hover:bg-white">
          Plan your visit
          <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </Link>
  )
}

function PlaceRow({ place }: { place: PlaceSummary }) {
  const state: PlanState = { place }
  const info = packInfo(place)
  return (
    <Link to={planPath(place.id)} state={state} className="card interactive-card flex items-center gap-3.5 p-4">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-sand-100 text-clay-600">
        <LandmarkIcon className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-stone-900">{place.name}</span>
        <span className="block text-sm text-stone-600">
          {place.city}, {place.state} State
        </span>
        {info && <span className="mt-0.5 block text-xs text-stone-400">{info}</span>}
      </span>
      <ChevronRightIcon className="size-5 shrink-0 text-stone-400" />
    </Link>
  )
}

function Notice({ Icon, children }: { Icon: typeof AlertIcon; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
      <Icon className="mt-0.5 size-5 shrink-0 text-amber-700" />
      <div>{children}</div>
    </div>
  )
}

/** Layered granite ridges and a low sun, a quiet nod to the outcrop at Abeokuta. */
function Ridges() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 400 260"
      preserveAspectRatio="xMaxYMax slice"
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      <circle cx="318" cy="70" r="30" fill="#e0a43a" opacity="0.55" />
      <path d="M150 260 L250 120 L300 175 L345 128 L400 170 L400 260 Z" fill="#ffffff" opacity="0.06" />
      <path d="M90 260 L200 170 L270 205 L330 160 L400 200 L400 260 Z" fill="#ffffff" opacity="0.07" />
    </svg>
  )
}
