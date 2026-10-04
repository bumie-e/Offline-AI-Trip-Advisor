# Offline-First Itinerary Advisor for Nigerian Heritage Tourism

> Working title. Replace with the final project name.

A small-AI trip companion that tells visitors whether, when, and how to reach a heritage site in Nigeria, then keeps that advice current from a phone with weak or no internet. The first case study is **Olumo Rock, Abeokuta**, for a first-time visitor flying in from abroad.

Built for the World Bank-hosted **Small AI for Development** hackathon (sector: tourism, case study: Nigeria).

---

## The problem

Planning a trip to a heritage site in Nigeria means piecing together blogs, news, and word of mouth, and then hoping conditions on the day match. Two things make this hard:

1. **Roads and weather interact.** According to a World Bank project document, only about 30 percent of Nigeria's road network is paved and most roads are in poor condition. Its 2017 figures put 40 percent of federal roads, 78 percent of state roads, and 87 percent of rural roads in poor condition. A World Bank update on rural access estimated Nigeria's Rural Access Index at 25.5 percent, where the index counts rural people living near an all-season road, meaning one passable year-round including the rainy season. Visitors heading to remote sites are exposed to this.
2. **Plans change suddenly.** Strike threats, flight suspensions, and heavy rain can upend an itinerary, and the people affected often have the weakest connectivity at exactly the moment they need updates.

A general chatbot can answer questions when you have a good connection. It can't carry an auditable, sourced plan with you and re-check it on a bus with no signal.

## The solution

The app does not give turn-by-turn navigation. It generates a **multi-stop itinerary with advice**, for example which road to avoid on a given day and what to do instead, and it **re-checks that advice on the device** when a small update of weather and news arrives.

1. A server pipeline gathers public sources and turns them into structured, sourced facts.
2. The app presents an itinerary with a verdict (go, go with changes, not advised) and the reasons.
3. The traveler decides: download, change dates or travel mode, pick another place, or save for later.
4. The traveler downloads the plan once on good Wi-Fi.
5. Whenever any signal appears, a few KB of weather and disruption news arrive, and a small on-device model decides whether anything changed.

## Example journey: Olumo Rock

First-time visitor from the US, arriving at Lagos (Murtala Muhammed International Airport).

![Journey flow](docs/olumo-rock-journey-flow.png)

| Stage | Connectivity | What happens |
|---|---|---|
| 1. Inspiration | Online | Browse places to visit in Nigeria, tap Olumo Rock |
| 2. Plan my visit | Online | Starting city, dates, arrival airport, group size, budget |
| 3. Itinerary and verdict | Online | Getting there, site info, weather, disruption watch, safety notes, return leg |
| 4. Decision | Online | Download, change dates or mode, other place, or save |
| 5. Download | Wi-Fi | Itinerary, structured facts, photos, contacts, small model |
| 6. Pre-flight refresh | Wi-Fi | Optional update of weather and news |
| 7. Arrival in Lagos | Offline or weak | Pickup instructions, update if any signal |
| 8. Travel day to Abeokuta | Weak or none | Morning update, re-plan on the road, queue a road report |
| 9. At Olumo Rock | Offline | Story, audio, guide contact, queue a site status report |
| 10. Return and onward travel | Weak | Strike and flight watch |
| 11. Afterwards | Online | Sync reports, rate the advice |

Public travel sources describe Olumo Rock as being in Abeokuta, which has no airport of its own. They put the drive from Lagos at about 100 km, roughly 1 hour 40 minutes to 2 hours depending on traffic, and describe November to March as the drier, easier season. Treat these as starting points to verify, not guarantees.

### Example advice (illustrative, not real data)

> **Not advised for 14-16 October.** Heavy rain is forecast, and reports describe difficult road conditions on this route in wet weather. Better options: travel in the drier season, take the train, or leave earlier in the day. Sources: 3, newest 2 days old.

## How it works

### 1. Server pipeline (when online)

| Step | What it does |
|---|---|
| Collect | Pulls blogs, news, tour-operator pages, forums, and airline and union notices (Bright Data) |
| Structure | An LLM converts text into records with source, date, and confidence |
| Add context | Adds the weather forecast for the traveler's dates and recent disruption news |
| Generate | Produces the itinerary, per-stop advice, photos, and the overall verdict |

### 2. Pack plus delta

| Layer | Contents | Updated by | How often |
|---|---|---|---|
| Pack | Stops, road and route notes, options, site facts, costs, contacts, photos | Server pipeline | Rarely, on Wi-Fi |
| Delta | Weather forecast and disruption news | Server | Any signal, a few KB |
| Verdict and advice text | Result of combining the pack and the delta | On-device model | After each delta or date change |

Roads are **not** re-collected in the delta. Road knowledge lives in the pack. What changes is the weather and the news that interact with it.

### 3. On-device model

A small language model with retrieval over the stored pack reads the latest delta and decides whether anything changed. Its output is structured and checked.

Example pack record (illustrative):

```json
{
  "id": "road-note-001",
  "type": "road_note",
  "route": "Lagos to Abeokuta, by road",
  "summary": "Short description from the source",
  "rain_sensitivity": "medium",
  "source": { "publisher": "example", "url": "https://example.com", "published": "2026-09-01" },
  "confidence": "medium",
  "last_verified": "2026-09-20"
}
```

Example delta (illustrative):

```json
{
  "generated_at": "2026-10-03T08:00:00Z",
  "weather": [{ "date": "2026-10-14", "area": "Abeokuta", "rain_probability": 0.8 }],
  "events": [{ "type": "strike", "status": "threatened", "affects": ["flights"], "start": "2026-10-20", "source_id": "news-014" }]
}
```

Example model output:

```json
{
  "changed": true,
  "severity": "elevated",
  "advice": "Rain is forecast on 14 October and the stored note marks this route as rain-sensitive. Consider leaving a day earlier or taking the train.",
  "alternatives": ["train", "earlier departure"],
  "cited_ids": ["road-note-001", "weather-2026-10-14"]
}
```

**Guardrails**
- The model may cite only IDs it was given. Output citing anything else is rejected and replaced by a template sentence.
- Every advice line shows its sources and their age.
- Wording is advisory ("reports suggest"), never a safe/unsafe verdict.
- A rule check runs beside the model. Heavy rain on a rain-sensitive road forces a flag, an active strike or flight suspension forces a flag, and the more cautious of rules and model is shown. The server applies it when generating the itinerary; the on-device version is still to be decided.

## Features

### Hackathon prototype (target)
- Olumo Rock itinerary generated from collected sources
- Verdict banner with reasons, sources, and data age
- Download for offline use
- Delta update with a visible "what changed" banner
- On-device re-plan after a date change, using the last update
- Queued road and site status reports
- Pre-generated audio guide for the site story
- Guide and driver contacts (samples unless real contacts are secured)

### Roadmap (not built)
- Multiple sites and regions
- Payments and booking confirmation
- Guide onboarding and verification at scale
- SMS or WhatsApp fallback for updates
- Local-language advice and audio beyond pre-written content
- Integration with tourism boards and official data feeds

## Tech stack

| Layer | Choice | Status |
|---|---|---|
| Data collection | Bright Data | Planned |
| Extraction and itinerary generation | Server-side LLM | Planned |
| App shell | Lovable, as a mobile-first PWA with a service worker and IndexedDB | Planned |
| Audio | ElevenLabs, pre-generated and cached | Planned |
| On-device model | Small instruction-tuned model, runtime to be chosen after a device test | **TBD** |
| Weather | Open-Meteo forecast API (no key) | Built |

The on-device model is the riskiest part of the build. It should be tested on a real phone early, measuring load time, memory, and speed, with a fallback to rules plus template text if it can't run acceptably.

## Impact

**Goals**
1. Make planning easier for local and foreign tourists, so they can decide before they travel.
2. Support community and national economic growth through tourism and better planning.

**How the app is meant to contribute to the second goal:** confident advance planning leads to more trips completed, which leads to more local guides, drivers, homestays, and vendors being used. Guides and caretakers can also correct stale warnings, which keeps the data fair to the communities involved.

**Proposed pilot indicators (not yet measured)**
- Trips planned in advance through the app
- Guide and service enquiries generated, and how many convert to paid work (self-reported)
- Local operators onboarded and how many update their information
- Pack and delta sizes, and success rates on mid-range phones

No impact results are claimed. This is a prototype.

## Limitations

- **Road conditions are not measured.** They come from collected sources and curated notes, which can be wrong or out of date.
- **Offline means last-known.** Without a signal, the app knows only what it last synced, and shows the age of its data.
- **Collected news is noisy.** It can be false, duplicated, delayed, or biased toward places that get media coverage.
- **Coverage is tiny:** one site and one corridor at first, so generalization is unproven.
- **Small models are weak** in Pidgin and local languages, and may miss things. Advice is generated in English first.
- **Not every phone can run the model.** Devices that can't should fall back to rules and template text.
- **Economic benefit is a theory.** It needs a pilot to test.
- **Security-related advice is sensitive.** It must show sources and dates, avoid verdicts, and avoid stigmatizing communities.

## Responsible use

- This is advisory information, not navigation or a safety guarantee. Visitors should use a local guide for remote sites.
- Check the terms of use of every source before collecting, and use collected content to extract facts, not to republish it.
- Use only images you have rights to, such as openly licensed material or your own.
- Take care with sacred and culturally sensitive sites, and involve community members.
- Location reports and trip plans are personal data. Collect the minimum and protect it.
- Link to official sources for visa and entry rules instead of summarizing them.

## Repository structure (proposed)

```
.
├── README.md
├── docs/
│   └── olumo-rock-journey-flow.png
├── pipeline/        # collection, extraction, itinerary generation
├── pack/            # structured pack and delta schemas and samples
├── app/             # PWA front end
├── model/           # on-device model tests and evaluation cases
└── eval/            # test cases for advice faithfulness
```

## Getting started

> To be completed once the code exists.

1. Clone the repository.
2. Add your API keys for the data collection and LLM services to a `.env` file (never commit it).
3. Run the pipeline to generate a pack and a delta for the demo trip.
4. Serve the app, load it online once, then switch to airplane mode to test offline behavior.

## Evaluation plan

Write 10-15 test cases (rain on a sensitive route, a strike overlapping a flight, no flag, thin evidence). For each candidate model, record:
- **Faithfulness:** does the advice use only the provided facts?
- **Correctness** of the recommendation against the expected result
- **Latency and memory** on the target phone

## Sources

- World Bank, Rural Access and Agricultural Marketing Project Scale-Up (P180640): https://documents1.worldbank.org/curated/en/099101624122030301/pdf/P180640153b37e0118f6619610a8cd46c2.pdf
- World Bank, Measuring Rural Access: Update 2017/18: https://documents1.worldbank.org/curated/en/543621569435525309/pdf/World-Measuring-Rural-Access-Update-2017-18.pdf
- UNESCO, Nigeria's initiative to protect cultural heritage during emergencies: https://www.unesco.org/en/articles/nigeria-embarks-crucial-national-initiative-strengthen-protection-its-cultural-heritage-during
- Built heritage and planning laws in Africa: the Nigerian experience: https://built-heritage.springeropen.com/articles/10.1186/s43238-022-00052-2
- Travel information on getting to Abeokuta: https://www.kupi.com/en-ae/explore/nigeria/abeokuta/getting-there and https://www.realjourneytravels.com/places/abeokuta/

## Team

> Add names, roles, and contact details.

## License

> Choose a license (for example MIT or Apache-2.0) and add a `LICENSE` file.

## Acknowledgements

Thanks to the hackathon organizers, and to the guides, caretakers, and community members whose knowledge this project depends on.