/**
 * Types for the backend API, mirroring the Pydantic models in `backend/src/trip_advisor/schemas/`
 * and the exported JSON Schemas in `backend/data/schemas/`. Keep them in step with those files.
 *
 * Dates arrive as ISO strings: `IsoDate` is `YYYY-MM-DD`, `IsoDateTime` is a full timestamp.
 * Optional fields with a server-side default (e.g. `notes = ""`) are always present in
 * responses, but are marked optional here because the schemas do not list them as required.
 */

export type IsoDate = string
export type IsoDateTime = string

// --- Enums -------------------------------------------------------------------------------

export type Confidence = 'low' | 'medium' | 'high'
export type Sensitivity = 'low' | 'medium' | 'high'
export type Severity = 'none' | 'elevated' | 'high'
export type Verdict = 'go' | 'go_with_changes' | 'not_advised'
export type TravelMode = 'road' | 'train' | 'flight' | 'walk'
export type EventType = 'strike' | 'flight_suspension' | 'heavy_rain' | 'road_closure' | 'other'
export type EventStatus = 'threatened' | 'confirmed' | 'ended'
export type AdviceSource = 'model' | 'rules'

// --- Places (schemas/api.py) -------------------------------------------------------------

export interface PlaceSummary {
  id: string
  name: string
  city: string
  state: string
  /** Null until a pack has been built for the site. */
  pack_version?: string | null
  pack_bytes?: number | null
  pack_generated_at?: IsoDateTime | null
}

// --- Pack (schemas/pack.py, schemas/common.py) -------------------------------------------

export interface Source {
  publisher: string
  url: string
  published?: IsoDate | null
}

interface RecordBase {
  id: string
  summary: string
  source: Source
  confidence: Confidence
  last_verified: IsoDate
}

export interface RoadNote extends RecordBase {
  type: 'road_note'
  route: string
  rain_sensitivity: Sensitivity
}

export interface SiteFact extends RecordBase {
  type: 'site_fact'
  topic: string
}

export interface CostNote extends RecordBase {
  type: 'cost_note'
  item: string
  amount_ngn_min?: number | null
  amount_ngn_max?: number | null
}

export interface Contact extends RecordBase {
  type: 'contact'
  role: string
  name: string
  phone?: string | null
  /** True for sample contacts, until real ones are secured. */
  is_sample?: boolean
}

/** Discriminated on `type`. */
export type PackRecord = RoadNote | SiteFact | CostNote | Contact

export interface Pack {
  site_id: string
  /** Also sent as the ETag of `GET /pack/{site_id}`. */
  version: string
  generated_at: IsoDateTime
  records: PackRecord[]
}

// --- Delta (schemas/delta.py) ------------------------------------------------------------

export interface WeatherEntry {
  date: IsoDate
  area: string
  /** 0 to 1. Citable as `weather-YYYY-MM-DD`. */
  rain_probability: number
}

export interface DisruptionEvent {
  type: EventType
  status: EventStatus
  /** e.g. `["flights"]`, `["road:lagos-abeokuta"]`, `["state:ogun"]`. */
  affects: string[]
  start?: IsoDate | null
  end?: IsoDate | null
  /** Citable ID for this event. */
  source_id: string
  source?: Source | null
}

/** A few KB of weather and news. Compare `generated_at` to tell which delta is newer. */
export interface Delta {
  generated_at: IsoDateTime
  weather?: WeatherEntry[]
  events?: DisruptionEvent[]
}

// --- Itinerary (schemas/itinerary.py) ----------------------------------------------------

/** Body of `POST /pack/{site_id}`; stage 2, "Plan my visit". */
export interface TripRequest {
  site_id: string
  start_city: string
  arrival_airport?: string | null
  start_date: IsoDate
  end_date: IsoDate
  /** 1 to 50. */
  group_size: number
  budget_ngn?: number | null
  mode?: TravelMode | null
}

export interface Stop {
  order: number
  title: string
  mode?: TravelMode | null
  duration_minutes?: number | null
  notes?: string
  cited_ids?: string[]
}

/** One reason behind the verdict. The same shape the on-device model will produce. */
export interface Advice {
  changed: boolean
  severity: Severity
  advice: string
  alternatives?: string[]
  /** Pack record IDs, `weather-YYYY-MM-DD`, event `source_id`s or route IDs. */
  cited_ids: string[]
}

export interface Itinerary {
  site_id: string
  generated_at: IsoDateTime
  request: TripRequest
  verdict: Verdict
  summary?: string
  verdict_reasons: Advice[]
  stops: Stop[]
  return_leg?: Stop[]
}

/** Response of `POST /pack/{site_id}`: everything the device keeps for a planned trip. */
export interface TripPack {
  pack: Pack
  /** The weather and news the advice was based on. */
  delta: Delta
  itinerary: Itinerary
  /** Whether the advice text was written by the server's model or by the rule templates. */
  advice_source: AdviceSource
}
