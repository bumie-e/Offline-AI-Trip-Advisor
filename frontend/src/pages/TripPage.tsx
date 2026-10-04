import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { BackButton } from '../components/BackButton'
import { ItineraryView } from '../components/ItineraryView'
import { getTrip, type SavedTrip } from '../db/db'
import { formatDateTime, siteNameFromId } from '../lib/format'

/** A saved trip, read from IndexedDB, so it opens with no connection. */
export function TripPage() {
  const { tripId = '' } = useParams()
  const [trip, setTrip] = useState<SavedTrip | null | undefined>(undefined)

  useEffect(() => {
    getTrip(tripId)
      .then((t) => setTrip(t ?? null))
      .catch((err: unknown) => {
        console.error(err)
        setTrip(null)
      })
  }, [tripId])

  return (
    <section className="space-y-5">
      <BackButton fallback="/trips" label="My trips" />

      {trip === undefined ? (
        <p className="text-stone-500">Loading trip…</p>
      ) : trip === null ? (
        <p className="text-stone-600">This trip is not saved on this device.</p>
      ) : (
        <>
          <header className="rounded-3xl bg-gradient-to-br from-green-800 to-green-950 px-5 py-6 text-white shadow-md">
            <p className="text-xs font-semibold tracking-widest text-green-200 uppercase">
              Heritage trip plan
            </p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight">
              {trip.siteName ?? siteNameFromId(trip.siteId)}
            </h1>
            <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-semibold text-green-900">
              <span aria-hidden>✓</span> Available offline · saved {formatDateTime(trip.savedAt)}
            </p>
          </header>
          <ItineraryView tripPack={trip.tripPack} />
        </>
      )}
    </section>
  )
}
