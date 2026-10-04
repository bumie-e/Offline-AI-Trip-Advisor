import type { Delta, ImageRecord, Pack, PlaceSummary, TripPack, TripRequest } from './types'

/**
 * Same-origin by default: `/api` is forwarded to the backend by the Vite dev/preview proxy
 * (see vite.config.ts), because the backend does not send CORS headers.
 */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')

const GET_TIMEOUT_MS = 15_000
// Generating a trip pack can wait on the server's model, which has its own 40 s limit.
const GENERATE_TIMEOUT_MS = 90_000

/** A non-2xx response. `detail` is FastAPI's error message when there is one. */
export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

interface RequestOptions {
  signal?: AbortSignal
  timeoutMs?: number
  method?: 'GET' | 'POST'
  body?: unknown
  headers?: Record<string, string>
}

async function request(path: string, opts: RequestOptions = {}): Promise<Response> {
  const timeout = AbortSignal.timeout(opts.timeoutMs ?? GET_TIMEOUT_MS)
  const res = await fetch(`${BASE_URL}${path}`, {
    method: opts.method ?? 'GET',
    headers: {
      Accept: 'application/json',
      ...(opts.body !== undefined && { 'Content-Type': 'application/json' }),
      ...opts.headers,
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal ? AbortSignal.any([opts.signal, timeout]) : timeout,
  })
  if (!res.ok && res.status !== 304) {
    const body: unknown = await res.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : body
    throw new ApiError(res.status, detail)
  }
  return res
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return (await request(path, { signal })).json() as Promise<T>
}

const site = (siteId: string) => encodeURIComponent(siteId)

/** `GET /places`: every site with a summary of its pack. */
export function getPlaces(signal?: AbortSignal): Promise<PlaceSummary[]> {
  return getJson('/places', signal)
}

/** `GET /places/{site_id}` */
export function getPlace(siteId: string, signal?: AbortSignal): Promise<PlaceSummary> {
  return getJson(`/places/${site(siteId)}`, signal)
}

export type PackResult = { status: 'updated'; pack: Pack } | { status: 'not-modified' }

/**
 * `GET /pack/{site_id}`: the site's records. Pass the version you hold and an unchanged pack
 * comes back as a cheap 304 (`not-modified`); the pack version is the ETag.
 */
export async function getPack(
  siteId: string,
  opts: { knownVersion?: string; signal?: AbortSignal } = {},
): Promise<PackResult> {
  const res = await request(`/pack/${site(siteId)}`, {
    signal: opts.signal,
    headers: opts.knownVersion ? { 'If-None-Match': `"${opts.knownVersion}"` } : undefined,
  })
  if (res.status === 304) return { status: 'not-modified' }
  return { status: 'updated', pack: (await res.json()) as Pack }
}

/**
 * `POST /pack/{site_id}`: plan a trip and download everything needed offline.
 * `ai: false` asks for rule-based advice text only, skipping the server's model.
 */
export async function downloadTripPack(
  tripRequest: TripRequest,
  opts: { ai?: boolean; signal?: AbortSignal } = {},
): Promise<TripPack> {
  const query = opts.ai === false ? '?ai=false' : ''
  const res = await request(`/pack/${site(tripRequest.site_id)}${query}`, {
    method: 'POST',
    body: tripRequest,
    signal: opts.signal,
    timeoutMs: GENERATE_TIMEOUT_MS,
  })
  return res.json() as Promise<TripPack>
}

/** `GET /delta/{site_id}`: the latest weather and disruption snapshot (a few KB). */
export function getDelta(siteId: string, signal?: AbortSignal): Promise<Delta> {
  return getJson(`/delta/${site(siteId)}`, signal)
}

/** `GET /images/{site_id}`: the site's photo records, the same ones the pack carries. */
export function getImages(siteId: string, signal?: AbortSignal): Promise<ImageRecord[]> {
  return getJson(`/images/${site(siteId)}`, signal)
}

/**
 * Network URL for an image `path` from an image record or a stop (`/images/{site}/{file}`),
 * for use as an `<img src>`. Files never change: the name contains a hash of the content.
 */
export function imageUrl(path: string): string {
  return `${BASE_URL}${path}`
}

/** `GET /images/{site_id}/{filename}` as a Blob, for storing on the device. */
export async function fetchImage(path: string, signal?: AbortSignal): Promise<Blob> {
  const res = await request(path, { signal, headers: { Accept: 'image/*' } })
  return res.blob()
}
