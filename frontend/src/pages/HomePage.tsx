import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { getPlaces } from '../api/client'
import type { PlaceSummary } from '../api/types'
import { Spinner } from '../components/Spinner'
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

  return (
    <section className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-stone-900">Plan a heritage trip in Nigeria</h1>
        <p className="text-stone-600">
          Pick a place to get advice on whether, when and how to go. Save the plan and it stays on
          your phone, even with no signal.
        </p>
      </div>

      {sorted ? (
        <ul className="space-y-3">
          {sorted.map((place) => (
            <li key={place.id}>
              <PlaceCard place={place} featured={place.id === FEATURED_SITE_ID} />
            </li>
          ))}
        </ul>
      ) : !online ? (
        <Notice>
          You are offline. Places need a connection to load, but{' '}
          <Link to="/trips" className="font-medium underline">
            your saved trips
          </Link>{' '}
          still work.
        </Notice>
      ) : error ? (
        <Notice>
          {error}{' '}
          <button
            type="button"
            onClick={() => {
              setError(null)
              setAttempt((n) => n + 1)
            }}
            className="font-medium underline"
          >
            Try again
          </button>
        </Notice>
      ) : (
        <p className="flex items-center gap-2 text-stone-500">
          <Spinner className="size-4" /> Loading places…
        </p>
      )}
    </section>
  )
}

function PlaceCard({ place, featured }: { place: PlaceSummary; featured: boolean }) {
  const state: PlanState = { place }
  const packInfo = [
    place.pack_bytes != null && `Offline pack ${formatBytes(place.pack_bytes)}`,
    place.pack_generated_at && `updated ${formatDateTime(place.pack_generated_at)}`,
  ]
    .filter(Boolean)
    .join(', ')

  if (featured) {
    return (
      <Link
        to={planPath(place.id)}
        state={state}
        className="block rounded-2xl bg-gradient-to-br from-green-800 to-green-950 p-5 text-white shadow-md active:scale-[0.99]"
      >
        <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold tracking-wide">
          Featured
        </span>
        <p className="mt-3 text-2xl font-bold">{place.name}</p>
        <p className="text-green-100">
          {place.city}, {place.state} State
        </p>
        {packInfo && <p className="mt-2 text-xs text-green-200">{packInfo}</p>}
        <p className="mt-4 inline-flex items-center gap-1 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-green-900">
          Plan a visit <span aria-hidden>→</span>
        </p>
      </Link>
    )
  }

  return (
    <Link
      to={planPath(place.id)}
      state={state}
      className="flex items-center justify-between gap-3 rounded-xl border border-stone-200 bg-white p-4 active:bg-stone-50"
    >
      <span>
        <span className="block font-semibold text-stone-900">{place.name}</span>
        <span className="block text-sm text-stone-600">
          {place.city}, {place.state} State
        </span>
        {packInfo && <span className="mt-1 block text-xs text-stone-400">{packInfo}</span>}
      </span>
      <span aria-hidden className="text-xl text-stone-400">
        ›
      </span>
    </Link>
  )
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      {children}
    </p>
  )
}
