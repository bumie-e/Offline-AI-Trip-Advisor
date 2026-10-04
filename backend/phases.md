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
- [x] Run live and hand-check a sample: done for Osun-Osogbo (10 records read against source text, 4 rejections reviewed); Olumo Rock and Idanre Hills run but not hand-checked. Remaining weakness: near-duplicate road notes, and most road notes are headline-only (low confidence) until the Bright Data unlocker zone is set

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
- [x] Run live with `LLM_API_KEY` and read the itineraries for all three sites (trip date 14 Oct 2026). Checked in code: the model never gave a verdict below the rules-only result, every citation resolves to a record, delta entry or route, and no safe/unsafe wording. Found and fixed: route towns were missing as stops (now added, grouped and capped at 6), and Osun-Osogbo's visit note gave art gallery hours (a visit note must now name the site)
- [x] Event relevance: local floods and heavy rain only count for the destination and the towns on the primary route (whole-word match, not the state); general union strikes still count everywhere; edible-oil tanker strikes no longer count as fuel strikes. Events per site fell from 4 to 2 or 3. Remaining noise: the national strike reasons still appear on every site with unknown dates, marked "elevated". Leave until event dates exist (Phase 4)
- [x] Event sources: each delta event now carries its source (publisher, link, date), so a reason can be traced to a story. Limits: the link is a Google News redirect and the headline is not stored, so a reader sees publisher and date but not the title; deltas stay at 2.8 to 3.4 KB, under the 6 KB cap
- [ ] Keep an eye on: Osun-Osogbo's guide page produced facts about nearby galleries as site facts. Structure prompt should keep facts to the site itself

## Phase 6: Guardrails
- [x] Cited-ID check: reject output citing IDs not provided (`guardrails/checks.py`; also flags warnings with no source, and percentages not found in a cited source). Stop notes too: a model-written note must cite at least one id that exists, or it is dropped and reported as `uncited`; generated stops (towns, fuel) cite the route
- [x] Template-sentence fallback: a failed line keeps its severity and gets a sentence built from its valid sources; the generator prefers the specific rule text
- [x] Advisory wording checks (no safe/unsafe verdicts, guarantees, or "do not travel" commands)
- [x] Sources and data age per advice line: `Catalog.sources_for` (for the app/API)
- [ ] On-device: the same checks must be ported to the app's runtime (the Python module is the reference). Number check covers percentages only, not dates or prices

## Phase 7: Pack builder and API
- [x] Pack builder (versioned by content hash, 100 KB cap, stale road notes left out): `uv run trip-advisor build-pack all`; delta served from the last `delta` snapshot
- [x] Routes: `GET /places`, `POST /itinerary` (stored pack + delta, rules only unless `?ai=true`), `GET /pack/{site}` (ETag = version, 304 when unchanged), `GET /delta/{site}`
- [x] Reports endpoint: `POST /reports/road|site-status|ratings`, batches of up to 50, idempotent by client UUID, bad items rejected individually
- [x] DB models and migrations for reports: SQLAlchemy + Alembic for Supabase Postgres (pooler-safe engine, row-level security on). Migration tested on a throwaway database only
- [ ] Create the Supabase project, set `DATABASE_URL`, run `uv run alembic upgrade head`, and test a real insert (never run against Postgres yet)
- [ ] Redeploy to Vercel with `DATABASE_URL` set as an environment variable
- [ ] Delta stays a snapshot: refresh by running `delta all`, `build-pack all` and redeploying (a scheduled job would automate it). No auth or rate limit on the report endpoints yet
- [x] Minimal personal-data handling: no identity or IP stored, coordinates rounded to about 1 km, phone numbers/emails/links removed from notes, 365-day purge (`purge-reports`), trip requests never stored

## Phase 8: Update (refresh and reconcile)
When the phone gets a connection, it pulls new weather and related news, and a small on-device LLM reconciles that with the stored itinerary and updates the verdict and advice. Builds on the Phase 7 delta endpoint. The backend owns the contract, the delta service, the guardrails, and the evaluation. The model runtime itself runs on the phone (see "Needs the app team" below).

Flow: connectivity regained, app opens, trip dates change, or pre-flight, so the app requests a delta for its trip. The server returns a few KB of weather and news. The device reconciles it with the stored pack and itinerary, then shows a "what changed" banner.

- [ ] Write the refresh flow down: triggers, what the phone sends (site, trip dates, pack version, time of last delta), what comes back, and what it does on failure
- [ ] Trip-scoped delta endpoint: weather for the trip dates and events touching the trip's routes and flights, only entries newer than the phone's last pull, an empty or not-modified reply when nothing changed, and a hard size cap with a test
- [ ] Stale-pack signal: the delta says when a newer pack exists, so the phone can fetch it on Wi-Fi
- [ ] Freshness on the server: drop items outside the 3-month window or past their expiry, give weather and news entries stable ids (such as `weather-2026-10-14`) so on-device citations resolve, and fill event `start`/`end` (depends on the Phase 4 dates item)
- [ ] Reconcile contract: input is the stored itinerary, pack records with ids, and the delta. Output is `Advice` plus the updated verdict. Publish JSON Schema for the on-device model team
- [ ] Portable rule floor: the Phase 5 rules (rain on a rain-sensitive road, active strike or flight suspension) as a spec or small port, so the phone computes the floor without the LLM and the more cautious of rules and model wins
- [ ] Reconcile guardrails (Phase 6 applied to this output): cite only given ids, advisory wording, template fallback
- [ ] "What changed" payload: previous and new verdict, reasons added and removed, each with source and age
- [ ] Offline behavior spec: partial or failed fetch, stale delta, clock skew, and queued reports syncing alongside the delta
- [ ] Server-side reference reconcile (same prompt and schema on a hosted model) to compare against and to fall back on when a phone can't run the model
- [ ] Tests: delta scoping and size, not-modified, stale-pack signal, guardrails, and golden cases (rain appears on a rain-sensitive road, strike overlaps a flight, nothing changed gives `changed=false`)
- Needs the app team (tracked here as dependencies): on-device runtime chosen after a real-phone test of load time, memory and speed (README: TBD); fallback to rules plus template text if the model can't run acceptably; background fetch and IndexedDB storage of pack and delta; the banner UI
- Known risk: rain sensitivity is often missing in collected road notes and stored as an assumed `medium`, so the rain-on-sensitive-road rule is weaker than it looks until that data improves

## Phase 9: Audio and assets
- [ ] Pre-generate audio guide for the site story (ElevenLabs)
- [ ] Photo manifest with licence info

## Phase 10: Evaluation
- [ ] 10-15 cases in `eval/cases/` (rain on sensitive route, strike overlapping flight, no flag, thin evidence)
- [ ] `eval/run_eval.py` measuring faithfulness and correctness
- [ ] Record results per candidate model
- [ ] Include the Phase 8 reconcile cases (stored plan plus new delta), and measure the small on-device candidates, not only the server model

## Phase 11: Hardening and demo
- [ ] End-to-end run: pipeline to pack to delta for the demo trip
- [ ] Error handling, rate limits, logging
- [ ] Deploy and document in README "Getting started"
