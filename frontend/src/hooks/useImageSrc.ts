import { useEffect, useState } from 'react'
import { imageUrl } from '../api/client'
import { getCachedImage } from '../db/db'

/**
 * A `src` for an image path: the copy stored on the device when there is one (works offline),
 * otherwise the network URL. Undefined while the device copy is being looked up.
 */
export function useImageSrc(path: string | undefined): string | undefined {
  const [resolved, setResolved] = useState<{ path: string; src: string }>()

  useEffect(() => {
    if (!path) return
    let objectUrl: string | undefined
    let cancelled = false
    getCachedImage(path)
      .catch(() => undefined)
      .then((blob) => {
        if (cancelled) return
        if (blob) objectUrl = URL.createObjectURL(blob)
        setResolved({ path, src: objectUrl ?? imageUrl(path) })
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  return resolved && resolved.path === path ? resolved.src : undefined
}
