import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import type { Delta, TripPack } from '../api/types'

/**
 * Offline storage. A saved trip keeps its TripPack unchanged: its `delta` is the baseline the
 * advice was written from. Newer deltas are stored per site, so they can be compared with it.
 */

export interface SavedTrip {
  id: string
  siteId: string
  /** The place name from `/places`; the TripPack itself only carries the site ID. */
  siteName?: string
  savedAt: string
  tripPack: TripPack
}

export interface StoredDelta {
  siteId: string
  fetchedAt: string
  delta: Delta
}

interface TripAdvisorDB extends DBSchema {
  trips: {
    key: string
    value: SavedTrip
    indexes: { bySite: string }
  }
  deltas: {
    key: string
    value: StoredDelta
  }
}

const DB_NAME = 'trip-advisor'
const DB_VERSION = 1

let dbPromise: Promise<IDBPDatabase<TripAdvisorDB>> | undefined

function db(): Promise<IDBPDatabase<TripAdvisorDB>> {
  dbPromise ??= openDB<TripAdvisorDB>(DB_NAME, DB_VERSION, {
    upgrade(database, oldVersion) {
      // Add a `case` per version bump; never edit an earlier one.
      switch (oldVersion) {
        case 0: {
          const trips = database.createObjectStore('trips', { keyPath: 'id' })
          trips.createIndex('bySite', 'siteId')
          database.createObjectStore('deltas', { keyPath: 'siteId' })
        }
      }
    },
  })
  return dbPromise
}

// --- Trips -------------------------------------------------------------------------------

/** Same plan: same site, same request, and the same generated itinerary. */
function isSamePlan(a: TripPack, b: TripPack): boolean {
  return (
    a.itinerary.site_id === b.itinerary.site_id &&
    a.itinerary.generated_at === b.itinerary.generated_at &&
    JSON.stringify(a.itinerary.request) === JSON.stringify(b.itinerary.request)
  )
}

export async function findSavedTrip(tripPack: TripPack): Promise<SavedTrip | undefined> {
  const trips = await (await db()).getAllFromIndex('trips', 'bySite', tripPack.itinerary.site_id)
  return trips.find((t) => isSamePlan(t.tripPack, tripPack))
}

/** Saves the trip, or returns the copy already saved, so saving twice never duplicates it. */
export async function saveTrip(
  tripPack: TripPack,
  opts: { siteName?: string } = {},
): Promise<SavedTrip> {
  const existing = await findSavedTrip(tripPack)
  if (existing) return existing
  const trip: SavedTrip = {
    id: crypto.randomUUID(),
    siteId: tripPack.itinerary.site_id,
    siteName: opts.siteName,
    savedAt: new Date().toISOString(),
    tripPack,
  }
  await (await db()).put('trips', trip)
  void requestPersistentStorage()
  return trip
}

export async function getTrip(id: string): Promise<SavedTrip | undefined> {
  return (await db()).get('trips', id)
}

/** Newest first. */
export async function listTrips(): Promise<SavedTrip[]> {
  const trips = await (await db()).getAll('trips')
  return trips.sort((a, b) => b.savedAt.localeCompare(a.savedAt))
}

export async function deleteTrip(id: string): Promise<void> {
  await (await db()).delete('trips', id)
}

// --- Deltas ------------------------------------------------------------------------------

export async function getLatestDelta(siteId: string): Promise<StoredDelta | undefined> {
  return (await db()).get('deltas', siteId)
}

/** Stores the delta only if it is newer than the one held. Returns whether it was stored. */
export async function saveDeltaIfNewer(siteId: string, delta: Delta): Promise<boolean> {
  const tx = (await db()).transaction('deltas', 'readwrite')
  const held = await tx.store.get(siteId)
  const newer = !held || Date.parse(delta.generated_at) > Date.parse(held.delta.generated_at)
  if (newer) await tx.store.put({ siteId, fetchedAt: new Date().toISOString(), delta })
  await tx.done
  return newer
}

// --- Storage -----------------------------------------------------------------------------

/** Asks the browser not to evict offline data under storage pressure. Best effort. */
export async function requestPersistentStorage(): Promise<boolean> {
  try {
    if (!navigator.storage?.persist) return false
    return (await navigator.storage.persisted()) || (await navigator.storage.persist())
  } catch {
    return false
  }
}
