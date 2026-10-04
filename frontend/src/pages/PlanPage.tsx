import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'
import { downloadTripPack, getPlace } from '../api/client'
import type { PlaceSummary, TravelMode, TripRequest } from '../api/types'
import { BackButton } from '../components/BackButton'
import { Spinner } from '../components/Spinner'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { friendlyError } from '../lib/errors'
import { siteNameFromId, todayIso } from '../lib/format'
import { resultPath, type PlanState, type ResultState } from '../lib/navigation'

const MODES: { value: TravelMode; label: string }[] = [
  { value: 'road', label: 'Road' },
  { value: 'flight', label: 'Flight' },
]

interface FormValues {
  startCity: string
  startDate: string
  endDate: string
  groupSize: string
  arrivalAirport: string
  budget: string
  mode: TravelMode
}

function initialValues(prev?: TripRequest): FormValues {
  return {
    startCity: prev?.start_city ?? 'Lagos',
    startDate: prev?.start_date ?? todayIso(7),
    endDate: prev?.end_date ?? todayIso(8),
    groupSize: String(prev?.group_size ?? 2),
    arrivalAirport: prev?.arrival_airport ?? '',
    budget: prev?.budget_ngn != null ? String(prev.budget_ngn) : '',
    mode: prev?.mode === 'flight' ? 'flight' : 'road',
  }
}

/** Returns an error message, or the request to send. */
function toRequest(siteId: string, v: FormValues): string | TripRequest {
  const groupSize = Number(v.groupSize)
  const budget = v.budget.trim() === '' ? null : Number(v.budget)
  if (!v.startCity.trim()) return 'Enter the city you are starting from.'
  if (!v.startDate || !v.endDate) return 'Choose your travel dates.'
  if (v.endDate < v.startDate) return 'The end date must be on or after the start date.'
  if (!Number.isInteger(groupSize) || groupSize < 1 || groupSize > 50) {
    return 'Group size must be between 1 and 50.'
  }
  if (budget !== null && (!Number.isInteger(budget) || budget < 0)) {
    return 'Budget must be a whole number of naira.'
  }
  return {
    site_id: siteId,
    start_city: v.startCity.trim(),
    start_date: v.startDate,
    end_date: v.endDate,
    group_size: groupSize,
    arrival_airport: v.arrivalAirport.trim() || null,
    budget_ngn: budget,
    mode: v.mode,
  }
}

/** Stage 2, "Plan my visit". Generates the trip with `POST /pack/{site_id}`. */
export function PlanPage() {
  const { siteId = '' } = useParams()
  const navigate = useNavigate()
  const online = useOnlineStatus()
  const state = (useLocation().state ?? {}) as PlanState

  const [place, setPlace] = useState<PlaceSummary | undefined>(state.place)
  const [values, setValues] = useState(() => initialValues(state.request))
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef<AbortController | null>(null)

  // Opened from a link without state: look the place up for its name.
  useEffect(() => {
    if (place || !online) return
    const controller = new AbortController()
    getPlace(siteId, controller.signal)
      .then(setPlace)
      .catch(() => {}) // the name falls back to one built from the ID
    return () => controller.abort()
  }, [place, online, siteId])

  // Leaving the page cancels a request still in flight.
  useEffect(() => () => inFlight.current?.abort(), [])

  const siteName = place?.name ?? siteNameFromId(siteId)
  const set = <K extends keyof FormValues>(key: K, value: FormValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }))

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (inFlight.current || !online) return // one request at a time
    const request = toRequest(siteId, values)
    if (typeof request === 'string') {
      setError(request)
      return
    }
    const controller = new AbortController()
    inFlight.current = controller
    setGenerating(true)
    setError(null)
    try {
      const tripPack = await downloadTripPack(request, { signal: controller.signal })
      const result: ResultState = { tripPack, siteName }
      navigate(resultPath(siteId), { state: result })
    } catch (err) {
      if (controller.signal.aborted) return // the user left the page
      setError(friendlyError(err))
      setGenerating(false)
    } finally {
      inFlight.current = null
    }
  }

  if (generating) {
    return (
      <div className="flex min-h-[60dvh] flex-col items-center justify-center gap-4 text-center" role="status">
        <Spinner className="size-10 text-green-700" />
        <div className="space-y-1">
          <p className="text-lg font-semibold text-stone-900">Building your trip plan…</p>
          <p className="text-sm text-stone-600">
            Checking routes, weather and news for {siteName}. This can take up to a minute.
          </p>
        </div>
      </div>
    )
  }

  return (
    <section className="space-y-5">
      <div>
        <BackButton fallback="/" />
        <h1 className="mt-2 text-2xl font-semibold text-stone-900">Plan your visit</h1>
        <p className="text-stone-600">
          {siteName}
          {place && `, ${place.city}, ${place.state} State`}
        </p>
      </div>

      {!online && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          You are offline. You need a connection to generate a new plan. Saved trips are still
          available in My trips.
        </p>
      )}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field label="Starting city">
          <input
            type="text"
            value={values.startCity}
            onChange={(e) => set('startCity', e.target.value)}
            autoComplete="address-level2"
            className={INPUT}
            required
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Start date">
            <input
              type="date"
              value={values.startDate}
              min={todayIso()}
              onChange={(e) => {
                const startDate = e.target.value
                setValues((v) => ({
                  ...v,
                  startDate,
                  endDate: v.endDate < startDate ? startDate : v.endDate,
                }))
              }}
              className={INPUT}
              required
            />
          </Field>
          <Field label="End date">
            <input
              type="date"
              value={values.endDate}
              min={values.startDate}
              onChange={(e) => set('endDate', e.target.value)}
              className={INPUT}
              required
            />
          </Field>
        </div>

        <Field label="Group size">
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={50}
            value={values.groupSize}
            onChange={(e) => set('groupSize', e.target.value)}
            className={INPUT}
            required
          />
        </Field>

        <fieldset>
          <legend className={LABEL}>Getting there</legend>
          <div className="mt-1.5 grid grid-cols-2 gap-2">
            {MODES.map((m) => (
              <label
                key={m.value}
                className="flex cursor-pointer items-center justify-center rounded-xl border border-stone-300 bg-white py-3 font-medium text-stone-700 has-checked:border-green-700 has-checked:bg-green-50 has-checked:text-green-900 has-focus-visible:ring-2 has-focus-visible:ring-green-600"
              >
                <input
                  type="radio"
                  name="mode"
                  value={m.value}
                  checked={values.mode === m.value}
                  onChange={() => set('mode', m.value)}
                  className="sr-only"
                />
                {m.label}
              </label>
            ))}
          </div>
        </fieldset>

        <Field label="Arrival airport" hint="Optional, e.g. Lagos (LOS)">
          <input
            type="text"
            value={values.arrivalAirport}
            onChange={(e) => set('arrivalAirport', e.target.value)}
            className={INPUT}
          />
        </Field>

        <Field label="Budget in naira (₦)" hint="Optional">
          <input
            type="number"
            inputMode="numeric"
            min={0}
            step={1000}
            value={values.budget}
            onChange={(e) => set('budget', e.target.value)}
            className={INPUT}
          />
        </Field>

        {error && (
          <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={!online}
          className="w-full rounded-xl bg-green-800 py-3.5 text-base font-semibold text-white shadow-sm active:bg-green-900 disabled:bg-stone-300 disabled:text-stone-600"
        >
          {online ? 'Get my trip plan' : 'Connect to generate a plan'}
        </button>
      </form>
    </section>
  )
}

const LABEL = 'block text-sm font-medium text-stone-700'
const INPUT =
  'mt-1.5 block w-full rounded-xl border border-stone-300 bg-white px-3 py-3 text-base text-stone-900 focus:border-green-700 focus:ring-2 focus:ring-green-600/30 focus:outline-none'

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className={LABEL}>
        {label}
        {hint && <span className="font-normal text-stone-400"> · {hint}</span>}
      </span>
      {children}
    </label>
  )
}
