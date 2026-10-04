import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { ItineraryView } from '../components/ItineraryView'
import { Spinner } from '../components/Spinner'
import { findSavedTrip, saveTrip, type SavedTrip } from '../db/db'
import { planPath, tripPath, type PlanState, type ResultState } from '../lib/navigation'

/** Stages 3 and 4: the generated plan, and the choice to save it for offline use. */
export function ResultPage() {
  const { siteId = '' } = useParams()
  const state = useLocation().state as Partial<ResultState> | null
  const tripPack = state?.tripPack?.itinerary ? state.tripPack : undefined
  const siteName = state?.siteName ?? ''

  const [saved, setSaved] = useState<SavedTrip | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Already saved earlier (e.g. after a reload)? Then show it as saved.
  useEffect(() => {
    if (!tripPack) return
    findSavedTrip(tripPack)
      .then((trip) => trip && setSaved(trip))
      .catch(() => {})
  }, [tripPack])

  if (!tripPack) {
    return (
      <section className="space-y-4">
        <h1 className="text-2xl font-semibold text-stone-900">No plan to show</h1>
        <p className="text-stone-600">This plan is no longer available. Plan the trip again.</p>
        <Link to={planPath(siteId)} className="font-medium text-green-800 underline">
          Plan a visit
        </Link>
      </section>
    )
  }

  async function onSave() {
    if (!tripPack || saving || saved) return
    setSaving(true)
    setSaveError(null)
    try {
      setSaved(await saveTrip(tripPack, { siteName }))
    } catch (err) {
      console.error(err)
      setSaveError(
        'Could not save on this device. Storage may be full or blocked, for example in a private window.',
      )
    } finally {
      setSaving(false)
    }
  }

  const changeState: PlanState = { request: tripPack.itinerary.request }

  return (
    <section className="space-y-5">
      <header className="rounded-3xl bg-gradient-to-br from-green-800 to-green-950 px-5 pt-3 pb-6 text-white shadow-md">
        <Link
          to={planPath(siteId)}
          state={changeState}
          className="-ml-2 inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm font-medium text-green-100 active:bg-white/10"
        >
          <span aria-hidden>←</span> Change details
        </Link>
        <p className="mt-3 text-xs font-semibold tracking-widest text-green-200 uppercase">
          Heritage trip plan
        </p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">{siteName || 'Your trip plan'}</h1>
      </header>

      <ItineraryView tripPack={tripPack}>
        {saved ? (
          <div
            role="status"
            className="flex items-start gap-3 rounded-2xl border-2 border-green-600 bg-green-50 p-4 text-green-900"
          >
            <span
              aria-hidden
              className="flex size-9 shrink-0 items-center justify-center rounded-full bg-green-700 text-lg font-bold text-white"
            >
              ✓
            </span>
            <div>
              <p className="text-lg font-bold">Saved for offline</p>
              <p className="mt-0.5 text-sm">
                This trip is on your phone now. You can open it from My trips without a connection.
              </p>
              <Link to={tripPath(saved.id)} className="mt-2 inline-block text-sm font-semibold underline">
                Open in My trips →
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-green-800 py-4 text-lg font-bold text-white shadow-lg active:bg-green-900 disabled:opacity-70"
            >
              {saving && <Spinner className="size-4" />}
              {saving ? 'Saving…' : 'Save for offline'}
            </button>
            {!saving && (
              <p className="text-center text-xs text-stone-500">
                Keeps this plan on your phone, so it works with no signal.
              </p>
            )}
            {saveError && (
              <p role="alert" className="text-sm text-red-800">
                {saveError}
              </p>
            )}
          </div>
        )}
      </ItineraryView>
    </section>
  )
}
