import type { PlaceSummary, TripPack, TripRequest } from '../api/types'

/** Router paths and the history state passed between pages. */

export const planPath = (siteId: string) => `/places/${encodeURIComponent(siteId)}/plan`
export const resultPath = (siteId: string) => `/places/${encodeURIComponent(siteId)}/result`
export const tripPath = (tripId: string) => `/trips/${encodeURIComponent(tripId)}`

/** Optional: lets the plan page show the place at once and prefill a previous request. */
export interface PlanState {
  place?: PlaceSummary
  request?: TripRequest
}

/** The generated, not yet saved trip. Kept in history state, so it survives a reload. */
export interface ResultState {
  tripPack: TripPack
  siteName: string
}
