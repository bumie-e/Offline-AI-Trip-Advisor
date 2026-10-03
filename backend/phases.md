# Backend phases

Backend only. Tick items as they are done. Each phase should leave something runnable.

## Phase 0: Scaffold
- [x] Directory structure and `pyproject.toml`
- [x] Settings, `/health` endpoint, CLI stub
- [x] Create venv, install deps (`uv sync --extra dev`), confirm `pytest` and `ruff` run
- [ ] Set up CI (lint + tests)

## Phase 1: Contracts (schemas)
- [x] Pydantic models: source, pack records (road note, site facts, contacts), delta (weather, events), itinerary, verdict, reports
- [x] Export JSON Schema for the app and on-device model teams
- [x] Sample pack and delta fixtures in `tests/fixtures/`
- [x] Schema validation tests

## Phase 2: Collect
- [ ] Verify terms of use for each candidate source
- [ ] Bright Data client and per-source collectors
- [ ] Store raw pages in `data/raw/` with URL and fetch date
- [ ] Olumo Rock source list in `data/sites/olumo-rock.toml`

## Phase 3: Structure
- [ ] LLM extraction prompt: text to records with source, date, confidence
- [ ] Validate output against schemas, reject malformed records
- [ ] Deduplicate and flag stale or low-confidence items
- [ ] Hand-check a sample of extractions

## Phase 4: Context (weather and news)
- [ ] Choose weather API (currently TBD)
- [ ] Weather client for a site and date range
- [ ] Disruption news aggregation (strikes, flight suspensions, heavy rain)
- [ ] Delta builder producing a few-KB delta

## Phase 5: Generate
- [ ] Itinerary generation (stops, getting there, return leg)
- [ ] Per-stop advice with sources and data age
- [ ] Verdict: go / go with changes / not advised
- [ ] Decide on the optional rule check beside the model (open decision in README)

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
