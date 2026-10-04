import { fetchImage } from '../api/client'
import type { TripPack } from '../api/types'
import { hasCachedImage, saveImage } from '../db/db'

/** The photos a trip shows: one per stop, outbound and return. */
export function tripImagePaths(tripPack: TripPack): string[] {
  const { stops, return_leg = [] } = tripPack.itinerary
  return [...new Set([...stops, ...return_leg].flatMap((s) => (s.image ? [s.image.path] : [])))]
}

/**
 * Stores a trip's photos in IndexedDB so they show offline. Skips photos already stored and
 * never throws: a photo that fails is counted, and simply loads from the network later.
 */
export async function cacheTripImages(tripPack: TripPack): Promise<{ failed: number }> {
  const results = await Promise.allSettled(
    tripImagePaths(tripPack).map(async (path) => {
      if (await hasCachedImage(path)) return
      await saveImage(path, await fetchImage(path))
    }),
  )
  const failed = results.filter((r) => r.status === 'rejected')
  for (const r of failed) console.warn('photo not stored for offline use', r.reason)
  return { failed: failed.length }
}
