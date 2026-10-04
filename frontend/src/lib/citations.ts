import type { EventType, IsoDate, PackRecord, TripPack } from '../api/types'
import { ageLabel, formatDate } from './format'

/**
 * Turns the IDs in `cited_ids` into something a traveller can read. The ID kinds come from
 * backend/src/trip_advisor/pipeline/generate/evidence.py: pack record IDs, `weather-YYYY-MM-DD`,
 * event `source_id`s and `route-...` IDs (routes are not in the pack, so only their kind is known).
 */
export type CitationKind = 'road' | 'site' | 'cost' | 'contact' | 'weather' | 'event' | 'route' | 'unknown'

export interface Citation {
  id: string
  kind: CitationKind
  /** Who or what it comes from, e.g. "Punch" or "Weather forecast". */
  label: string
  /** What it says, when known. */
  detail?: string
  /** Date and age, e.g. "16 Sept 2026 · 18 days old". */
  when?: string
  url?: string
  /** A short fact for a chip, e.g. "11 Oct · 78% rain" or "Strike · confirmed". */
  chip?: string
}

const EVENT_LABEL: Record<EventType, string> = {
  strike: 'Strike',
  flight_suspension: 'Flight suspension',
  heavy_rain: 'Heavy rain or flooding',
  road_closure: 'Road closure',
  other: 'Disruption',
}

const RECORD_KIND: Record<PackRecord['type'], CitationKind> = {
  road_note: 'road',
  site_fact: 'site',
  cost_note: 'cost',
  contact: 'contact',
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
      kind: RECORD_KIND[r.type],
      label: r.source.publisher,
      detail: r.summary,
      when: when(r.source.published),
      url: r.source.url,
    })
  }
  for (const w of delta.weather ?? []) {
    const id = `weather-${w.date}`
    const pct = Math.round(w.rain_probability * 100)
    known.set(id, {
      id,
      kind: 'weather',
      label: 'Weather forecast',
      detail: `${pct}% chance of rain on ${formatDate(w.date, false)} in ${w.area}`,
      when: `Forecast from ${when(delta.generated_at.slice(0, 10))}`,
      chip: `${formatDate(w.date, false)} · ${pct}% rain`,
    })
  }
  for (const e of delta.events ?? []) {
    known.set(e.source_id, {
      id: e.source_id,
      kind: 'event',
      label: e.source?.publisher ?? 'News reports',
      detail: `${EVENT_LABEL[e.type]} (${e.status}) affecting ${e.affects.join(', ')}`,
      when: when(e.source?.published),
      url: e.source?.url,
      chip: `${EVENT_LABEL[e.type]} · ${e.status}`,
    })
  }

  return (id) =>
    known.get(id) ??
    (id.startsWith('route-')
      ? { id, kind: 'route', label: 'Route data', detail: 'Driving route and distance from map routing' }
      : { id, kind: 'unknown', label: id })
}
