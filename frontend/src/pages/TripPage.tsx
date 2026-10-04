import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { BackButton } from '../components/BackButton'
import { CheckIcon } from '../components/icons'
import { ItineraryView } from '../components/ItineraryView'
import { OfflineBadge } from '../components/OfflineBadge'
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

  if (trip === undefined) {
    return <p className="pt-4 text-stone-500">Loading trip…</p>
  }

  if (trip === null) {
    return (
      <section className="space-y-4">
        <BackButton fallback="/trips" label="My trips" />
        <div className="card p-6 text-center">
          <p className="font-medium text-stone-800">This trip is not saved on this device.</p>
        </div>
      </section>
    )
  }

  return (
    <ItineraryView
      tripPack={trip.tripPack}
      title={trip.siteName ?? siteNameFromId(trip.siteId)}
      nav={<BackButton fallback="/trips" label="My trips" tone="light" />}
      status={<OfflineBadge tone="dark" />}
    >
      <div className="card flex items-start gap-3.5 border-forest-300 bg-forest-50 p-5">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-forest-700 text-white">
          <CheckIcon className="size-5" strokeWidth={2.4} />
        </span>
        <div>
          <p className="text-lg font-semibold text-forest-900">Available offline</p>
          <p className="mt-0.5 text-sm leading-relaxed text-forest-800">
            Saved on this phone {formatDateTime(trip.savedAt)}. It opens without a connection.
          </p>
        </div>
      </div>
    </ItineraryView>
  )
}
