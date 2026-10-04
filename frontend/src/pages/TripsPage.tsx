import { useEffect, useState } from 'react'
import { Link } from 'react-router'
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
    <section className="space-y-5">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-stone-900">My trips</h1>
        <p className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-900">
          <span aria-hidden>✓</span> Saved on this phone, available offline
        </p>
      </div>

      {failed ? (
        <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          Saved trips could not be read on this device. Storage may be blocked, for example in a
          private window.
        </p>
      ) : trips === null ? (
        <p className="text-stone-500">Loading saved trips…</p>
      ) : trips.length === 0 ? (
        <div className="rounded-xl border border-dashed border-stone-300 bg-white p-5 text-center">
          <p className="text-stone-700">No trips saved yet.</p>
          <p className="mt-1 text-sm text-stone-500">
            Plan a visit and tap “Save for offline” to keep it here.
          </p>
          <Link
            to="/"
            className="mt-4 inline-block rounded-lg bg-green-800 px-4 py-2 text-sm font-semibold text-white"
          >
            Explore places
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {trips.map((trip) => {
            const { itinerary } = trip.tripPack
            const { request } = itinerary
            return (
              <li key={trip.id}>
                <Link
                  to={tripPath(trip.id)}
                  className="block rounded-xl border border-stone-200 bg-white p-4 active:bg-stone-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-semibold text-stone-900">
                      {trip.siteName ?? siteNameFromId(trip.siteId)}
                    </p>
                    <VerdictPill verdict={itinerary.verdict} />
                  </div>
                  <p className="mt-1 text-sm text-stone-700">
                    {formatDateRange(request.start_date, request.end_date)} · {request.group_size}{' '}
                    traveller{request.group_size === 1 ? '' : 's'} · from {request.start_city}
                  </p>
                  <p className="mt-1 text-xs text-stone-400">Saved {formatDateTime(trip.savedAt)}</p>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
