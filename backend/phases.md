# Backend phases

Backend only. Tick items as they are done. Each phase should leave something runnable.

## Phase 0: Scaffold
- [x] Directory structure and `pyproject.toml`
- [x] Settings, `/health` endpoint, CLI stub
- [x] Create venv, install deps (`uv sync --extra dev`), confirm `pytest` and `ruff` run
- [x] Set up CI (lint, format, mypy, tests, schema drift check)

## Phase 1: Contracts (schemas)
- [x] Pydantic models: source, pack records (road note, site facts, contacts), delta (weather, events), itinerary, verdict, reports
- [x] Export JSON Schema for the app and on-device model teams
- [x] Sample pack and delta fixtures in `tests/fixtures/`
- [x] Schema validation tests

## Phase 2: Collect
Sites: Olumo Rock, Osun-Osogbo Sacred Grove, Idanre Hills (all from Lagos airport). Run `uv run trip-advisor collect all`; re-evaluate saved data with `uv run trip-advisor rescore all`.
- [x] Source review: OSM (Nominatim, OSRM, Overpass), Wikivoyage, Google News RSS, FMINO notices. GDELT rate-limits us, FRSC has no API.
- [x] Routes, alternatives and stops from OSM; coordinates pinned in `data/sites/*.toml`
- [x] Road-state evidence limited to the last 3 months; newest real road condition wins, traffic-only items never selected
- [x] Coverage report per site (routes, alternatives, towns, fuel, fresh evidence per corridor)
- [x] Bright Data client (SERP + Web Unlocker) with request budget, tested against mocks
- [ ] Create Bright Data zones, set names in `.env`, run live and check the real SERP response fields
- [ ] Check terms of use for each source before relying on it
- [ ] Better road-state evidence: Olumo Rock's primary corridor and Idanre's Akure-Idanre road have no usable report in the last 3 months
- [ ] Better alternatives: Osun-Osogbo's alternative is nearly the same road as the primary
- Known limits: fuel stops are sparse in OSM; evidence is headline-level until Bright Data fetches full text

## Phase 3: Structure
- [x] LLM extraction prompt: text to records with source, date, confidence
- [x] Validate output against schemas, reject malformed records
- [x] Deduplicate and flag stale or low-confidence items
- [ ] Run live with `LLM_API_KEY` (`uv run trip-advisor structure all`) and hand-check `data/structured/<site>/review.md`

## Phase 4: Context (weather and news)
- [x] Choose weather API: Open-Meteo (free, no key, daily rain probability up to 16 days)
- [x] Weather client for a site and date range
- [x] Disruption news aggregation (strikes, flight suspensions, heavy rain): keyword rules, national or local scope only, one event per story
- [ ] Dates on events: `start`/`end` are always empty (headline-level only); needs article text or the LLM
- [x] Delta builder producing a few-KB delta: `uv run trip-advisor delta all` (about 2.3 KB per site, 6 KB cap)

## Phase 5: Generate
- [x] Itinerary generation (stops, getting there, return leg): `uv run trip-advisor generate <site> --start YYYY-MM-DD`; stops come from collected routes, not the model
- [x] Per-stop advice with sources and data age: reasons cite weather, record, route and news IDs (data age shown by Phase 6 wording checks and the app)
- [x] Verdict: go / go with changes / not advised
- [x] Decide on the optional rule check beside the model: yes, rules set a floor and the more cautious result wins (README updated)
- [ ] Run live with `LLM_API_KEY` and read a few generated itineraries; no live model call has been made yet

## Phase 6: Guardrails
- [ ] Cited-ID check: reject output citing IDs not provided
- [ ] Template-sentence fallback
- [ ] Advisory wording checks (no safe/unsafe verdicts)

## Phase 7: Pack builder and API
- [ ] Pack builder (versioned, sized) and delta endpoint
- [ ] Routes: places, itinerary, pack, delta
- [ ] Reports endpoint: queued road and site reports, ratings
- [ ] DB models and migrations for reports
- [ ] Minimal personal-data handling for reports and trip plans

## Phase 8: Audio and assets
- [ ] Pre-generate audio guide for the site story (ElevenLabs)
- [ ] Photo manifest with licence info

## Phase 9: Evaluation
- [ ] 10-15 cases in `eval/cases/` (rain on sensitive route, strike overlapping flight, no flag, thin evidence)
- [ ] `eval/run_eval.py` measuring faithfulness and correctness
- [ ] Record results per candidate model

## Phase 10: Hardening and demo
- [ ] End-to-end run: pipeline to pack to delta for the demo trip
- [ ] Error handling, rate limits, logging
- [ ] Deploy and document in README "Getting started"
