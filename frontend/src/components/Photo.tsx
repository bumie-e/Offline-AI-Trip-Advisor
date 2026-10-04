import { useState } from 'react'
import { useImageSrc } from '../hooks/useImageSrc'

/**
 * A photo from the API, from the device copy when stored. The licences require the credit to be
 * shown beside every photo. Renders nothing if the photo cannot be loaded (e.g. offline and not
 * stored), so a missing photo never breaks the layout.
 */
export function Photo({
  path,
  alt,
  credit,
  caption,
  width,
  height,
  label,
  ratio,
  className = '',
  creditClassName = 'text-stone-400',
}: {
  path: string
  alt: string
  credit: string
  /** Shown above the credit. */
  caption?: string
  width?: number
  height?: number
  /** A small tag over the photo, e.g. "Typical road in the area". */
  label?: string
  /** Width / height of the frame; the photo is cropped to fill it. */
  ratio?: number
  className?: string
  creditClassName?: string
}) {
  const src = useImageSrc(path)
  const [failedSrc, setFailedSrc] = useState<string>()
  if (src && failedSrc === src) return null

  return (
    <figure>
      <div
        className={`relative overflow-hidden bg-stone-200/70 ${className}`}
        style={ratio ? { aspectRatio: ratio } : undefined}
      >
        {src && (
          <img
            src={src}
            alt={alt}
            width={width}
            height={height}
            loading="lazy"
            decoding="async"
            onError={() => setFailedSrc(src)}
            className="absolute inset-0 size-full object-cover"
          />
        )}
        {label && (
          <span className="absolute top-2 left-2 rounded-full bg-stone-950/65 px-2 py-0.5 text-[11px] font-medium text-white backdrop-blur-sm">
            {label}
          </span>
        )}
      </div>
      <figcaption className="mt-1.5">
        {caption && <span className="block text-xs leading-snug text-stone-600">{caption}</span>}
        <span className={`block text-[10.5px] leading-snug ${creditClassName}`}>{credit}</span>
      </figcaption>
    </figure>
  )
}
