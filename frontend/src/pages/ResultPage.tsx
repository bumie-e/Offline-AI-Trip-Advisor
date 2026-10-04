import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { ItineraryView } from '../components/ItineraryView'
import { ArrowLeftIcon, ArrowRightIcon, CheckIcon, OfflineReadyIcon } from '../components/icons'
import { OfflineBadge } from '../components/OfflineBadge'
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
      <section className="card mt-4 space-y-3 p-6 text-center">
        <h1 className="font-display text-2xl font-semibold text-stone-900">No plan to show</h1>
        <p className="text-stone-600">This plan is no longer available. Plan the trip again.</p>
        <Link to={planPath(siteId)} className="btn-primary mt-2">
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
    <ItineraryView
      tripPack={tripPack}
      title={siteName || 'Your trip plan'}
      nav={
        <Link
          to={planPath(siteId)}
          state={changeState}
          className="-ml-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-forest-100 transition-colors hover:bg-white/10 active:bg-white/15"
        >
          <ArrowLeftIcon className="size-4" /> Change details
        </Link>
      }
      status={
        saved ? (
          <OfflineBadge tone="dark" label="Saved for offline" />
        ) : (
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs font-semibold text-forest-900 transition hover:bg-sand-100 active:scale-[0.98] disabled:opacity-70"
          >
            {saving ? <Spinner className="size-3" /> : <OfflineReadyIcon className="size-3.5" strokeWidth={2.2} />}
            Save for offline
          </button>
        )
      }
    >
      {saved ? (
        <div role="status" className="card flex items-start gap-3.5 border-forest-300 bg-forest-50 p-5">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-forest-700 text-white">
            <CheckIcon className="size-5" strokeWidth={2.4} />
          </span>
          <div>
            <p className="text-lg font-semibold text-forest-900">Saved for offline</p>
            <p className="mt-0.5 text-sm leading-relaxed text-forest-800">
              This trip is on your phone now. You can open it from My trips without a connection.
            </p>
            <Link
              to={tripPath(saved.id)}
              className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-forest-800 underline-offset-2 hover:underline"
            >
              Open in My trips <ArrowRightIcon className="size-4" />
            </Link>
          </div>
        </div>
      ) : (
        <div className="card space-y-4 p-5">
          <div className="flex items-start gap-3.5">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-sand-100 text-forest-800">
              <OfflineReadyIcon className="size-5" />
            </span>
            <div>
              <p className="text-lg font-semibold text-stone-900">Take this plan with you</p>
              <p className="mt-0.5 text-sm leading-relaxed text-stone-600">
                Save it to this phone before you go. It opens from My trips, even with no signal.
              </p>
            </div>
          </div>
          <button type="button" onClick={() => void onSave()} disabled={saving} className="btn-primary w-full">
            {saving && <Spinner className="size-4" />}
            {saving ? 'Saving…' : 'Save for offline'}
          </button>
          {saveError && (
            <p role="alert" className="text-sm text-red-800">
              {saveError}
            </p>
          )}
        </div>
      )}
    </ItineraryView>
  )
}
