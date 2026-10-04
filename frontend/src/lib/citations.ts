import type { EventType, IsoDate, TripPack } from '../api/types'
import { ageLabel, formatDate } from './format'

/**
 * Turns the IDs in `cited_ids` into something a traveller can read. The ID kinds come from
 * backend/src/trip_advisor/pipeline/generate/evidence.py: pack record IDs, `weather-YYYY-MM-DD`,
 * event `source_id`s and `route-...` IDs (routes are not in the pack, so only their kind is known).
 */
export interface Citation {
  id: string
  /** Who or what it comes from, e.g. "Punch" or "Weather forecast". */
  label: string
  /** What it says, when known. */
  detail?: string
  /** Date and age, e.g. "16 Sept 2026 · 18 days old". */
  when?: string
  url?: string
}

const EVENT_LABEL: Record<EventType, string> = {
  strike: 'Strike',
  flight_suspension: 'Flight suspension',
  heavy_rain: 'Heavy rain or flooding',
  road_closure: 'Road closure',
  other: 'Disruption',
}

function when(date: IsoDate | null | undefined): string {
  return date ? `${formatDate(date)} · ${ageLabel(date)}` : 'Date unknown'
}

export function citationResolver(tripPack: TripPack): (id: string) => Citation {
  const { pack, delta } = tripPack
  const known = new Map<string, Citation>()

  for (const r of pack.records) {
    known.set(r.id, {
      id: r.id,
      label: r.source.publisher,
      detail: r.summary,
      when: when(r.source.published),
      url: r.source.url,
    })
  }
  for (const w of delta.weather ?? []) {
    const id = `weather-${w.date}`
    known.set(id, {
      id,
      label: 'Weather forecast',
      detail: `${Math.round(w.rain_probability * 100)}% chance of rain on ${formatDate(w.date, false)} in ${w.area}`,
      when: `Forecast from ${when(delta.generated_at.slice(0, 10))}`,
    })
  }
  for (const e of delta.events ?? []) {
    known.set(e.source_id, {
      id: e.source_id,
      label: e.source?.publisher ?? 'News reports',
      detail: `${EVENT_LABEL[e.type]} (${e.status}) affecting ${e.affects.join(', ')}`,
      when: when(e.source?.published),
      url: e.source?.url,
    })
  }

  return (id) =>
    known.get(id) ??
    (id.startsWith('route-')
      ? { id, label: 'Route data', detail: 'Driving route and distance from map routing' }
      : { id, label: id })
}
