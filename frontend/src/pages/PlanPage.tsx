import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'
import { downloadTripPack, getPlace } from '../api/client'
import type { PlaceSummary, TravelMode, TripRequest } from '../api/types'
import { BackButton } from '../components/BackButton'
import {
  AlertIcon,
  ArrowRightIcon,
  CarIcon,
  CloudOffIcon,
  MinusIcon,
  OfflineReadyIcon,
  PinIcon,
  PlaneIcon,
  PlusIcon,
  RainIcon,
  RoadIcon,
} from '../components/icons'
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
      <div className="flex min-h-[65dvh] flex-col items-center justify-center px-2 text-center" role="status">
        <div className="card w-full max-w-sm p-7">
          <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-forest-50 text-forest-700">
            <Spinner className="size-8" />
          </span>
          <p className="mt-5 font-display text-2xl font-semibold text-stone-900">Building your trip plan…</p>
          <p className="mt-2 text-sm leading-relaxed text-stone-600">
            Checking routes, weather and news for {siteName}. This can take up to a minute.
          </p>
          <ul className="mt-5 space-y-2 border-t border-stone-100 pt-5 text-left text-sm text-stone-700">
            {CHECKS.map(({ Icon, label }) => (
              <li key={label} className="flex items-center gap-2.5">
                <Icon className="size-4 text-forest-600" /> {label}
              </li>
            ))}
          </ul>
        </div>
      </div>
    )
  }

  const groupSize = Number(values.groupSize)
  const stepGroup = (delta: number) => {
    const current = Number.isInteger(groupSize) ? groupSize : 1
    set('groupSize', String(Math.min(50, Math.max(1, current + delta))))
  }

  return (
    <section className="space-y-6">
      <div>
        <BackButton fallback="/" />
        <p className="eyebrow mt-3 text-clay-600">Plan your visit</p>
        <h1 className="mt-1 font-display text-[2rem] leading-tight font-semibold tracking-tight text-stone-900">
          {siteName}
        </h1>
        {place && (
          <p className="mt-1 flex items-center gap-1.5 text-stone-600">
            <PinIcon className="size-4 text-stone-400" />
            {place.city}, {place.state} State, Nigeria
          </p>
        )}
      </div>

      {!online && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <CloudOffIcon className="mt-0.5 size-5 shrink-0 text-amber-700" />
          <p>
            <span className="font-semibold">You are offline.</span> You need a connection to generate
            a new plan. Saved trips are still available in My trips.
          </p>
        </div>
      )}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <FormCard title="When and where">
          <Field label="Starting city">
            <input
              type="text"
              value={values.startCity}
              onChange={(e) => set('startCity', e.target.value)}
              autoComplete="address-level2"
              className="field-input"
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
                className="field-input min-h-12"
                required
              />
            </Field>
            <Field label="End date">
              <input
                type="date"
                value={values.endDate}
                min={values.startDate}
                onChange={(e) => set('endDate', e.target.value)}
                className="field-input min-h-12"
                required
              />
            </Field>
          </div>
        </FormCard>

        <FormCard title="Who and how">
          <div>
            <label htmlFor="group-size" className="field-label">
              Group size
            </label>
            <div className="mt-1.5 flex items-stretch overflow-hidden rounded-xl border border-stone-300 bg-white focus-within:border-forest-600 focus-within:ring-4 focus-within:ring-forest-600/15">
              <button
                type="button"
                onClick={() => stepGroup(-1)}
                disabled={groupSize <= 1}
                aria-label="Fewer travellers"
                className="flex w-14 items-center justify-center text-forest-800 transition hover:bg-sand-50 active:bg-sand-100 disabled:text-stone-300"
              >
                <MinusIcon className="size-5" />
              </button>
              <input
                id="group-size"
                type="number"
                inputMode="numeric"
                min={1}
                max={50}
                value={values.groupSize}
                onChange={(e) => set('groupSize', e.target.value)}
                className="w-full border-x border-stone-200 py-3 text-center text-lg font-semibold text-stone-900 focus:outline-none [&::-webkit-inner-spin-button]:appearance-none"
                required
              />
              <button
                type="button"
                onClick={() => stepGroup(1)}
                disabled={groupSize >= 50}
                aria-label="More travellers"
                className="flex w-14 items-center justify-center text-forest-800 transition hover:bg-sand-50 active:bg-sand-100 disabled:text-stone-300"
              >
                <PlusIcon className="size-5" />
              </button>
            </div>
          </div>

          <fieldset>
            <legend className="field-label">Getting there</legend>
            <div className="mt-1.5 grid grid-cols-2 gap-2.5">
              {MODES.map((m) => {
                const Icon = m.value === 'flight' ? PlaneIcon : CarIcon
                return (
                  <label
                    key={m.value}
                    className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-stone-300 bg-white py-3.5 font-medium text-stone-700 transition hover:border-stone-400 has-checked:border-forest-700 has-checked:bg-forest-50 has-checked:text-forest-900 has-checked:ring-1 has-checked:ring-forest-700 has-focus-visible:ring-4 has-focus-visible:ring-forest-600/20"
                  >
                    <input
                      type="radio"
                      name="mode"
                      value={m.value}
                      checked={values.mode === m.value}
                      onChange={() => set('mode', m.value)}
                      className="sr-only"
                    />
                    <Icon className="size-5" />
                    {m.label}
                  </label>
                )
              })}
            </div>
          </fieldset>
        </FormCard>

        <FormCard title="Optional details" tag="Optional">
          <Field label="Arrival airport" hint="e.g. Lagos (LOS)">
            <input
              type="text"
              value={values.arrivalAirport}
              onChange={(e) => set('arrivalAirport', e.target.value)}
              placeholder="If you are flying in"
              className="field-input"
            />
          </Field>

          <Field label="Budget" hint="in naira">
            <div className="relative">
              <span className="pointer-events-none absolute inset-y-0 left-3.5 mt-1.5 flex items-center text-stone-500">
                ₦
              </span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                step={1000}
                value={values.budget}
                onChange={(e) => set('budget', e.target.value)}
                placeholder="Total for the group"
                className="field-input pl-8"
              />
            </div>
          </Field>
        </FormCard>

        {error && (
          <div role="alert" className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
            <AlertIcon className="mt-0.5 size-5 shrink-0 text-red-700" />
            <p>{error}</p>
          </div>
        )}

        <div className="space-y-3 pt-1">
          <button type="submit" disabled={!online} className="btn-primary w-full py-4 text-[17px]">
            {online ? (
              <>
                Generate trip plan <ArrowRightIcon className="size-5" />
              </>
            ) : (
              <>
                <CloudOffIcon className="size-5" /> Connect to generate a plan
              </>
            )}
          </button>
          <p className="flex items-center justify-center gap-1.5 text-center text-xs text-stone-500">
            <OfflineReadyIcon className="size-3.5" />
            You can save the plan to your phone for offline use.
          </p>
        </div>
      </form>
    </section>
  )
}

const CHECKS = [
  { Icon: RoadIcon, label: 'Route and road reports' },
  { Icon: RainIcon, label: 'Weather forecast for your dates' },
  { Icon: AlertIcon, label: 'Strikes and travel disruptions' },
]

function FormCard({ title, tag, children }: { title: string; tag?: string; children: ReactNode }) {
  return (
    <fieldset className="card space-y-4 p-4">
      <legend className="sr-only">{title}</legend>
      <p aria-hidden className="flex items-center gap-2 text-sm font-semibold text-stone-900">
        {title}
        {tag && (
          <span className="rounded-full bg-sand-100 px-2 py-0.5 text-[11px] font-medium text-stone-500">{tag}</span>
        )}
      </p>
      {children}
    </fieldset>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="field-label">
        {label}
        {hint && <span className="font-normal text-stone-400"> · {hint}</span>}
      </span>
      {children}
    </label>
  )
}
