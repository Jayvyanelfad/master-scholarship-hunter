# Master Scholarship Hunter

An Apify Actor for evidence-first scholarship research for one fixed profile:
a Beninese citizen currently studying in India, seeking a fully funded Master's
degree in Computer Science, IT, AI, or a closely related computing field.

It is deliberately a precision-oriented research tool, not a claim to search
every scholarship worldwide. Discovery is handled by an expandable
adapter registry (`my_actor/source_adapters/`): one small adapter per
source defines its discovery URLs, listing/detail parsing, official
domains, and source-specific rules on top of shared evidence
normalization. For an explicitly labelled external application,
official-website, programme, or admissions link, it fetches the linked source,
keeps its evidence separate, and evaluates the official evidence first.

## What qualifies as a strong match

An item is a `strong_match` only when all hard gates pass:

- Master's eligibility is explicit.
- The scholarship itself supports a target computing field.
- Benefits explicitly cover both tuition and living expenses or a stipend.
- Benin is eligible through an explicit country list or a clearly applicable
  broad official rule.
- The structured destination is one of the target countries.
- The rules explicitly permit applying from abroad; a local-residency or
  already-enrolled requirement excludes the item.
- A deadline is active or upcoming.
- The evidence comes from an official government, programme, university, or
  document source (`verification_status: verified`).

`fully funded` alone does not verify funding. An unclear requirement produces
`possible_match`, never a strong match. WMS remains a discovery source: it is
verified only after a qualified official page is fetched and analysed.

## Input

- `start_urls` (optional): Direct programme pages or supported discovery
  listing URLs. When omitted, the Actor starts with the configured
  WeMakeScholars Master's computing listing.
- `sources` (optional): Source ids to crawl (`wemakescholars`,
  `erasmus_mundus`, `daad`, `vlir_uos`, `chevening`, `goi_ies`, `mext`,
  `mastercard_foundation`, `nl_scholarship`, `si_sweden`, `finland`,
  `norway`, `switzerland`, `austria`, `australia`). Use `["all"]` for every
  known source. When omitted, all enabled production sources are used.
  A failing source logs its error and never crashes the run.
- `max_results_per_source` (default `50`): Bounded discovery cap per source.
- `verify_official` (default `true`): Follow official links and merge
  official evidence. Disable only for debugging discovery.
- `max_requests_per_crawl` (default `100`): Maximum discovery/verification
  pages processed in one run.

No credentials are supplied through Actor input. SMTP settings use
`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, and `EMAIL_TO` environment variables.

## Output

Each dataset item preserves extracted source fields and includes:

- identity and provenance: `title`, `discovery_url`, `official_url`,
  `canonical_url`, source domains/types, and `verification_status`;
- decisions and evidence for degree, field, funding, nationality, destination,
  application location, and deadline;
- `match_status` (`strong_match`, `possible_match`, or `rejected`),
  `recommendation`, reasons, warnings, and the profile rule version.

Every evidence item is an object with `claim`, `source_url`, `source_type`, and
`confidence`. The Actor does not invent missing eligibility facts.

## Email behavior

Gmail SMTP is preserved. The emailer sends recommendations only where both
`recommendation == "include"` and `match_status == "strong_match"`.
When there are no strong matches, it sends “No verified strong matches this
run” with run diagnostics for discovered, verified, rejected, possible,
expired, and unknown-evidence records, plus a per-source breakdown
(discovered / official checked / verified / errors) and the top rejection
reasons, so an empty run is debuggable.

## Local development

```bash
apify validate-schema
apify run
python -m unittest discover -s tests -v
```

For a local Actor run, place input in
`storage/key_value_stores/default/INPUT.json`. Results are written to the local
default dataset. Local storage is not uploaded to Apify Console.

## Source coverage and limitations

`my_actor/sources.py` is an explicit registry derived from real adapters in
`my_actor/source_adapters/`. Discovery adapters exist for WeMakeScholars,
Erasmus Mundus, DAAD, VLIR-UOS, Chevening, Government of Ireland (GOI-IES),
MEXT, Mastercard Foundation, NL Scholarship, Swedish Institute, Finland,
Norway, Switzerland (ESKAS), Austria (OeAD), and Australia Awards Africa.
Eiffel/Campus France, Canada (EduCanada), Denmark, Luxembourg, and Singapore
stay disabled with documented reasons because no discovery URL could be
verified for them (unreachable domains or 404s after site migrations); no
guessed URLs are used. The NL Scholarship (EUR 5,000, explicitly not
full-tuition) is a deliberate control case proving discovery and strict
filtering are separate: it is discovered, then rejected.

Cross-source deduplication keys on the canonical official URL, so one
scholarship found via several sources yields one record with merged
provenance. Every run logs per-source health (attempted, discovered,
official queued/fetched, verified, possible, rejected, errors).

The normal pipeline is discovery, normalization, deduplication, structured
extraction, official-link verification, evidence analysis, and final gating.
