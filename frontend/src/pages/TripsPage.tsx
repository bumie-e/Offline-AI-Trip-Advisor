import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import {
  ArrowRightIcon,
  BookmarkIcon,
  CalendarIcon,
  OfflineReadyIcon,
  PinIcon,
  UsersIcon,
} from '../components/icons'
import { OfflineBadge } from '../components/OfflineBadge'
import { VerdictPill } from '../components/VerdictBanner'
import { listTrips, type SavedTrip } from '../db/db'
import { formatDateRange, formatDateTime, siteNameFromId } from '../lib/format'
import { tripPath } from '../lib/navigation'

/** The trips saved on this device. Read from IndexedDB, so this works offline. */
export function TripsPage() {
  const [trips, setTrips] = useState<SavedTrip[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    listTrips()
      .then(setTrips)
      .catch((err: unknown) => {
        console.error(err)
        setFailed(true)
      })
  }, [])

  return (
    <section className="space-y-6">
      <div className="space-y-3">
        <h1 className="font-display text-[2rem] leading-tight font-semibold tracking-tight text-stone-900">
          My trips
        </h1>
        <p className="flex items-start gap-2.5 rounded-xl border border-forest-200 bg-forest-50 px-3.5 py-3 text-sm text-forest-900">
          <OfflineReadyIcon className="mt-0.5 size-4 shrink-0" strokeWidth={2.2} />
          <span>Every trip here is saved on this phone and opens without a connection.</span>
        </p>
      </div>

      {failed ? (
        <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          Saved trips could not be read on this device. Storage may be blocked, for example in a
          private window.
        </p>
      ) : trips === null ? (
        <ul className="space-y-3" aria-label="Loading saved trips">
          {[0, 1].map((i) => (
            <li key={i} className="card h-36 animate-pulse bg-white/60" />
          ))}
        </ul>
      ) : trips.length === 0 ? (
        <div className="card flex flex-col items-center px-6 py-10 text-center">
          <span className="flex size-14 items-center justify-center rounded-2xl bg-sand-100 text-forest-800">
            <BookmarkIcon className="size-6" />
          </span>
          <p className="mt-4 text-lg font-semibold text-stone-900">No trips saved yet</p>
          <p className="mt-1 max-w-xs text-sm leading-relaxed text-stone-600">
            Plan a visit and tap “Save for offline” to keep it here for the road.
          </p>
          <Link to="/" className="btn-primary mt-6">
            Explore places <ArrowRightIcon className="size-4" />
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {trips.map((trip) => {
            const { itinerary } = trip.tripPack
            const { request } = itinerary
            return (
              <li key={trip.id}>
                <Link to={tripPath(trip.id)} className="card interactive-card block overflow-hidden">
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="eyebrow text-stone-500">Heritage trip</p>
                        <p className="mt-1 font-display text-xl leading-snug font-semibold text-stone-900">
                          {trip.siteName ?? siteNameFromId(trip.siteId)}
                        </p>
                      </div>
                      <VerdictPill verdict={itinerary.verdict} />
                    </div>
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-sm text-stone-700">
                      <span className="inline-flex items-center gap-1.5">
                        <CalendarIcon className="size-4 text-stone-400" />
                        {formatDateRange(request.start_date, request.end_date)}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <UsersIcon className="size-4 text-stone-400" />
                        {request.group_size} traveller{request.group_size === 1 ? '' : 's'}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <PinIcon className="size-4 text-stone-400" />
                        From {request.start_city}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-t border-stone-100 bg-sand-50/70 px-4 py-3">
                    <span className="flex min-w-0 flex-col items-start gap-1">
                      <OfflineBadge />
                      <span className="text-[11px] text-stone-400">Saved {formatDateTime(trip.savedAt)}</span>
                    </span>
                    <span className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-forest-800">
                      Open trip <ArrowRightIcon className="size-4" />
                    </span>
                  </div>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
