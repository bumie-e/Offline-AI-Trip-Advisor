import { ApiError } from '../api/client'

/** A message a traveller can act on. Technical detail stays in the console. */
export function friendlyError(err: unknown): string {
  console.error(err)
  if (err instanceof DOMException && err.name === 'TimeoutError') {
    return 'This is taking longer than expected. Please try again in a moment.'
  }
  if (err instanceof ApiError) {
    if (err.status === 429) {
      return 'Too many trip plans have been requested from this connection. Please wait a few minutes and try again.'
    }
    if (err.status === 404) return 'This place is not available right now.'
    if (err.status === 422) return 'Some trip details were not accepted. Please check the dates and group size.'
    return 'The trip planner is having trouble right now. Please try again shortly.'
  }
  return 'Could not reach the trip planner. Check your connection and try again.'
}
